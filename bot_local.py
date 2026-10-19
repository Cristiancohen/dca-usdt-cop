#!/usr/bin/env python3
"""Bot local USDTCOP para Windows. El modo normal es seguro; el trading requiere `run` o `--run`."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent
SYMBOL = "USDTCOP"
API_BASE = "https://api.binance.com"
DATA_BASE = "https://data-api.binance.vision"
CONFIG_PATH = ROOT / "config_local.json"
STATE_PATH = ROOT / "bot_local_state.json"
LOCK_PATH = ROOT / "bot_local.lock"
MONITOR_PATH = ROOT / "monitor" / "local_log.json"
TIMEOUT_SECONDS = 20
POLL_SECONDS = 20
MAX_BACKOFF_SECONDS = 60
LEVELS = 5
BUY_QUANTITY_USDT = Decimal("2")
LEVEL_GAP_COP = Decimal("20")
SELL_PROFIT = Decimal("0.01")
DAILY_LIMIT_USDT = Decimal("15")
TERMINAL = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
SAFE_REQUEST_FIELDS = {
    "symbol", "side", "type", "timeInForce", "quantity", "price",
    "newClientOrderId", "orderId", "origClientOrderId", "limit",
}


class BinanceError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, status: int | None = None,
                 body: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.body = body


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_day() -> str:
    return utc_now().date().isoformat()


def mask_text(text: str, credentials: dict[str, str] | None = None) -> str:
    """Redacta literalmente las credenciales por si un servidor las repitiera."""
    result = str(text)
    for secret in (credentials or {}).values():
        if secret:
            result = result.replace(secret, "[REDACTADO]")
    return result


def safe_json_value(value: Any, credentials: dict[str, str] | None = None) -> Any:
    if isinstance(value, dict):
        hidden = {"signature", "apikey", "api_key", "secret", "token"}
        return {
            key: "[REDACTADO]" if str(key).lower() in hidden else safe_json_value(item, credentials)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [safe_json_value(item, credentials) for item in value]
    if isinstance(value, str):
        return mask_text(value, credentials)
    return value


def _response_body(response: requests.Response, credentials: dict[str, str]) -> str:
    return mask_text(response.text, credentials)


def _json_response(response: requests.Response, credentials: dict[str, str]) -> Any:
    try:
        value = response.json()
        return safe_json_value(value, credentials)
    except (ValueError, requests.exceptions.JSONDecodeError):
        return _response_body(response, credentials)


def load_credentials() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            "No existe config_local.json. Créalo junto a bot_local.py con binance_api_key y binance_api_secret; consulta GUiA_PC.md."
        )
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("No se pudo leer config_local.json como JSON válido.") from exc
    if not isinstance(data, dict):
        raise ValueError("config_local.json debe contener un objeto JSON.")
    key = data.get("binance_api_key")
    secret = data.get("binance_api_secret")
    if not isinstance(key, str) or not key.strip() or not isinstance(secret, str) or not secret.strip():
        raise ValueError("Completa binance_api_key y binance_api_secret en config_local.json.")
    return {"key": key.strip(), "secret": secret.strip()}


def _error_code(body: str) -> int | None:
    try:
        data = json.loads(body)
        return int(data["code"]) if isinstance(data, dict) and "code" in data else None
    except (ValueError, TypeError, KeyError):
        return None


def _error_message(response: requests.Response, body: str, credentials: dict[str, str]) -> BinanceError:
    code = _error_code(body)
    safe_body = mask_text(body, credentials)
    message = f"Binance respondió HTTP {response.status_code}"
    if code is not None:
        message += f" (código {code})"
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict) and parsed.get("msg"):
            message += f": {mask_text(str(parsed['msg']), credentials)}"
        elif safe_body:
            message += f": {safe_body[:500]}"
    except ValueError:
        if safe_body:
            message += f": {safe_body[:500]}"
    return BinanceError(message, code=code, status=response.status_code, body=safe_body)


class BinanceClient:
    def __init__(self, credentials: dict[str, str] | None = None) -> None:
        self.credentials = credentials or {}
        self.time_offset_ms = 0
        self.time_sync_at = 0.0
        self.last_trace: dict[str, Any] | None = None

    def raw_request(self, method: str, path: str, params: dict[str, Any] | None = None,
                    *, signed: bool = False) -> requests.Response:
        values = {key: str(value) for key, value in (params or {}).items()}
        headers = {"User-Agent": "dca-usdt-cop-local/1.0"}
        if signed:
            if not self.credentials.get("key") or not self.credentials.get("secret"):
                raise BinanceError("No hay llaves cargadas desde config_local.json.")
            values["timestamp"] = str(int(time.time() * 1000) + self.time_offset_ms)
            values["recvWindow"] = "10000"
            query = urlencode(values)
            values["signature"] = hmac.new(
                self.credentials["secret"].encode("utf-8"), query.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            headers["X-MBX-APIKEY"] = self.credentials["key"]
        url = API_BASE + path
        try:
            response = requests.request(
                method.upper(), url, params=values, headers=headers, timeout=TIMEOUT_SECONDS
            )
        except requests.RequestException as exc:
            # No se imprime el objeto RequestException: podría contener una URL firmada.
            raise BinanceError(f"Error de red al conectar con Binance ({type(exc).__name__}).") from None
        self.last_trace = {
            "method": method.upper(),
            "endpoint": path,
            "signed": signed,
            "request_params": {
                key: value for key, value in values.items() if key in SAFE_REQUEST_FIELDS
            },
            "proxy": None,
            "http_status": response.status_code,
            "raw_response": _response_body(response, self.credentials),
            "response_json": safe_json_value(_json_response(response, self.credentials), self.credentials),
        }
        # El timestamp, la firma y la llave API nunca se copian a la traza.
        return response

    def update_time_offset(self, server_time_ms: int, sent_at: float, received_at: float) -> None:
        midpoint_ms = int(((sent_at + received_at) / 2) * 1000)
        self.time_offset_ms = int(server_time_ms) - midpoint_ms
        self.time_sync_at = received_at

    def sync_time(self) -> tuple[requests.Response, float, float]:
        started = time.time()
        response = requests.get(API_BASE + "/api/v3/time", timeout=TIMEOUT_SECONDS,
                                headers={"User-Agent": "dca-usdt-cop-local/1.0"})
        finished = time.time()
        if response.ok:
            try:
                data = response.json()
                self.update_time_offset(int(data["serverTime"]), started, finished)
            except (ValueError, TypeError, KeyError):
                pass
        return response, started, finished

    def ensure_time_sync(self, force: bool = False) -> None:
        if force or not self.time_sync_at or time.time() - self.time_sync_at > 60:
            try:
                response, started, finished = self.sync_time()
            except requests.RequestException:
                raise BinanceError("No se pudo sincronizar la hora con /api/v3/time.") from None
            if not response.ok:
                raise _error_message(response, response.text, self.credentials)
            if not self.time_sync_at or self.time_sync_at < finished - 0.01:
                raise BinanceError("/api/v3/time no devolvió serverTime válido.")

    def signed_raw_with_timestamp_retry(self, method: str, path: str,
                                        params: dict[str, Any] | None = None) -> requests.Response:
        self.ensure_time_sync()
        for attempt in range(4):
            response = self.raw_request(method, path, params, signed=True)
            body = response.text
            if _error_code(body) != -1021:
                return response
            if attempt == 3:
                return response
            print("Binance indicó -1021 (reloj desfasado). Sincronizando hora y reintentando con espera...", flush=True)
            try:
                self.ensure_time_sync(force=True)
            except (BinanceError, requests.RequestException):
                if attempt == 3:
                    return response
            time.sleep(min(2 ** attempt, 8))
        raise BinanceError("No se pudo obtener respuesta firmada de Binance.")

    def request_json(self, method: str, path: str, params: dict[str, Any] | None = None,
                     *, signed: bool = False) -> Any:
        response = self.signed_raw_with_timestamp_retry(method, path, params) if signed else self.raw_request(method, path, params)
        if not response.ok:
            raise _error_message(response, response.text, self.credentials)
        try:
            return response.json()
        except ValueError:
            raise BinanceError(f"Binance respondió HTTP {response.status_code} con contenido que no es JSON.",
                               status=response.status_code, body=_response_body(response, self.credentials)) from None


def show_http_result(label: str, response: requests.Response | None,
                     credentials: dict[str, str] | None = None, error: str | None = None) -> None:
    print(f"\n{label}")
    if response is None:
        print("Código HTTP: sin respuesta")
        print(f"Cuerpo crudo de Binance: {mask_text(error or 'No hubo respuesta HTTP.', credentials)}")
        return
    print(f"Código HTTP: {response.status_code}")
    print("Cuerpo crudo de Binance:")
    print(mask_text(response.text, credentials) or "(cuerpo vacío)")


def extract_filters(data: Any) -> dict[str, str]:
    if not isinstance(data, dict) or not isinstance(data.get("symbols"), list) or not data["symbols"]:
        raise ValueError("Binance no devolvió información del símbolo USDTCOP.")
    symbol = data["symbols"][0]
    found = {item.get("filterType"): item for item in symbol.get("filters", []) if isinstance(item, dict)}
    price_filter = found.get("PRICE_FILTER", {})
    lot_filter = found.get("LOT_SIZE", {})
    notional = found.get("NOTIONAL") or found.get("MIN_NOTIONAL") or {}
    return {
        "tickSize": str(price_filter.get("tickSize", "no disponible")),
        "stepSize": str(lot_filter.get("stepSize", "no disponible")),
        "minNotional": str(notional.get("minNotional", "no disponible")),
        "status": str(symbol.get("status", "no disponible")),
    }


def run_test() -> int:
    print("PRUEBA DE CONEXIÓN CON BINANCE — MODO TEST; NO SE ENVÍAN ÓRDENES.", flush=True)
    try:
        credentials = load_credentials()
        client = BinanceClient(credentials)
    except (FileNotFoundError, ValueError) as exc:
        credentials = {}
        client = BinanceClient()
        setup_error = str(exc)
    else:
        setup_error = ""

    # Prueba 1: dos consultas públicas en orden. La hora sirve para firmar la prueba 2.
    print("\nPRUEBA 1/3: conexión pública (ping y hora).", flush=True)
    try:
        ping_response = requests.get(API_BASE + "/api/v3/ping", timeout=TIMEOUT_SECONDS,
                                    headers={"User-Agent": "dca-usdt-cop-local/1.0"})
        show_http_result("1a) GET /api/v3/ping", ping_response, credentials)
    except requests.RequestException as exc:
        ping_response = None
        show_http_result("1a) GET /api/v3/ping", None, credentials, f"Error de red ({type(exc).__name__}).")
    try:
        time_start = time.time()
        time_response = requests.get(API_BASE + "/api/v3/time", timeout=TIMEOUT_SECONDS,
                                     headers={"User-Agent": "dca-usdt-cop-local/1.0"})
        time_end = time.time()
        if time_response.ok:
            try:
                client.update_time_offset(int(time_response.json()["serverTime"]), time_start, time_end)
            except (ValueError, TypeError, KeyError):
                pass
        show_http_result("1b) GET /api/v3/time", time_response, credentials)
    except requests.RequestException as exc:
        time_response = None
        show_http_result("1b) GET /api/v3/time", None, credentials, f"Error de red ({type(exc).__name__}).")

    # Prueba 2: sólo lectura privada GET /account. Nunca crea ni modifica órdenes.
    print("\nPRUEBA 2/3: solicitud firmada de solo lectura GET /api/v3/account.", flush=True)
    if setup_error:
        account_response = None
        show_http_result("2) GET /api/v3/account firmado", None, credentials, setup_error)
    else:
        try:
            account_response = client.signed_raw_with_timestamp_retry("GET", "/api/v3/account")
            show_http_result("2) GET /api/v3/account firmado", account_response, credentials)
        except (BinanceError, requests.RequestException) as exc:
            account_response = None
            show_http_result("2) GET /api/v3/account firmado", None, credentials, str(exc))

    # Prueba 3: filtros públicos vigentes del símbolo; solo se extraen y muestran.
    print("\nPRUEBA 3/3: filtros públicos de USDTCOP (exchangeInfo).", flush=True)
    filters_valid = False
    try:
        exchange_response = requests.get(
            API_BASE + "/api/v3/exchangeInfo", params={"symbol": SYMBOL}, timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": "dca-usdt-cop-local/1.0"},
        )
        show_http_result("3) GET /api/v3/exchangeInfo?symbol=USDTCOP", exchange_response, credentials)
        if exchange_response.ok:
            try:
                filters = extract_filters(exchange_response.json())
                print("Filtros leídos: " + ", ".join(f"{name}={filters[name]}" for name in ("tickSize", "stepSize", "minNotional")))
                filters_valid = all(filters[name] != "no disponible" for name in ("tickSize", "stepSize", "minNotional"))
            except (ValueError, TypeError, KeyError) as exc:
                print(f"No se pudieron extraer los filtros: {exc}")
    except requests.RequestException as exc:
        exchange_response = None
        show_http_result("3) GET /api/v3/exchangeInfo?symbol=USDTCOP", None, credentials,
                         f"Error de red ({type(exc).__name__}).")

    results = [ping_response, time_response, account_response, exchange_response]
    if all(response is not None and response.status_code == 200 for response in results) and filters_valid:
        print("\nRESULTADO: las tres pruebas pasaron (HTTP 200 en ping, hora, cuenta y filtros). No se envió ninguna orden.", flush=True)
        return 0
    print("\nRESULTADO: hubo una o más pruebas sin HTTP 200. Revisa los cuerpos mostrados arriba; no se envió ninguna orden.", flush=True)
    return 1


def dec(value: Any, label: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} no es un número válido.") from None
    if not number.is_finite():
        raise ValueError(f"{label} no es un número finito.")
    return number


def floor_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError("Filtro stepSize/tickSize no válido.")
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def ceil_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError("Filtro stepSize/tickSize no válido.")
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def fmt(value: Decimal) -> str:
    return format(value, "f")


def symbol_rules(client: BinanceClient) -> dict[str, Decimal]:
    info = client.request_json("GET", "/api/v3/exchangeInfo", {"symbol": SYMBOL})
    symbol = info["symbols"][0]
    if symbol.get("status") != "TRADING" or not symbol.get("isSpotTradingAllowed", False):
        raise BinanceError(f"{SYMBOL} no está habilitado para trading spot.")
    filters = {item["filterType"]: item for item in symbol.get("filters", [])}
    price = filters["PRICE_FILTER"]
    lot = filters["LOT_SIZE"]
    notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL")
    if not notional:
        raise BinanceError("Binance no publicó NOTIONAL/MIN_NOTIONAL; no se enviará ninguna orden.")
    return {
        "min_price": dec(price["minPrice"], "minPrice"),
        "max_price": dec(price["maxPrice"], "maxPrice"),
        "tick_size": dec(price["tickSize"], "tickSize"),
        "min_qty": dec(lot["minQty"], "minQty"),
        "max_qty": dec(lot["maxQty"], "maxQty"),
        "step_size": dec(lot["stepSize"], "stepSize"),
        "min_notional": dec(notional["minNotional"], "minNotional"),
        "max_notional": dec(notional.get("maxNotional", "0"), "maxNotional"),
    }


def account_balance(account: dict[str, Any], asset: str) -> Decimal:
    for row in account.get("balances", []):
        if row.get("asset") == asset:
            return dec(row.get("free", "0"), f"saldo libre {asset}")
    return Decimal("0")


def write_state(state: dict[str, Any]) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "day": utc_day(), "daily_buy_usdt": "0", "orders": [],
                "regenerate_grid": True, "cycles_completed": 0}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("bot_local_state.json no se pudo leer. No se operó; conserva una copia y revisa el archivo.") from exc
    if not isinstance(state, dict) or not isinstance(state.get("orders"), list):
        raise ValueError("bot_local_state.json tiene un formato inesperado; no se operó.")
    state.setdefault("day", utc_day())
    state.setdefault("daily_buy_usdt", "0")
    state.setdefault("regenerate_grid", not bool(state.get("orders")))
    state.setdefault("cycles_completed", 0)
    return state


def append_monitor_event(*, status: str, request: dict[str, Any] | None,
                         final_response: Any = None, error: str | None = None,
                         order: dict[str, Any] | None = None,
                         credentials: dict[str, str] | None = None) -> None:
    """Guarda sólo actividad de órdenes; el archivo local sigue el esquema monitor/log.json."""
    MONITOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(MONITOR_PATH.read_text(encoding="utf-8")) if MONITOR_PATH.exists() else {}
    except (OSError, json.JSONDecodeError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    entries = existing.get("entries")
    if not isinstance(entries, list):
        entries = []
    trace = safe_json_value(request, credentials) if request else None
    event = {
        "timestamp": utc_now().isoformat(timespec="seconds"),
        "finished_at": utc_now().isoformat(timespec="seconds"),
        "run_id": "local",
        "status": status,
        "order_received": safe_json_value(order or {}, credentials),
        "proxy": {"used": None, "attempts": [],
                  "note": "Conexión directa desde el PC; no se utilizó proxy."},
        "requests": [trace] if trace else [],
        "final_response": safe_json_value(final_response, credentials),
        "error": mask_text(error, credentials) if error else None,
    }
    entries.insert(0, event)
    existing["updated_at"] = utc_now().isoformat(timespec="seconds")
    existing["notes"] = existing.get("notes", []) if isinstance(existing.get("notes", []), list) else []
    existing["entries"] = entries[:500]
    MONITOR_PATH.write_text(json.dumps(safe_json_value(existing, credentials), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_order_trace(client: BinanceClient) -> dict[str, Any] | None:
    trace = client.last_trace
    if not trace or trace.get("endpoint") != "/api/v3/order":
        return None
    # La API privada puede devolver detalles de fills, pero nunca guardamos cuenta, saldos, firma ni headers.
    safe = dict(trace)
    return safe_json_value(safe, client.credentials)


def get_price(client: BinanceClient) -> Decimal:
    try:
        response = requests.get(
            DATA_BASE + "/api/v3/ticker/price", params={"symbol": SYMBOL}, timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": "dca-usdt-cop-local/1.0"},
        )
    except requests.RequestException:
        raise BinanceError("No se pudo leer el precio público desde data-api.binance.vision.") from None
    if not response.ok:
        raise _error_message(response, response.text, client.credentials)
    try:
        return dec(response.json()["price"], "precio spot")
    except (ValueError, TypeError, KeyError):
        raise BinanceError("Binance devolvió un precio público inesperado.") from None


def order_by_client_id(client: BinanceClient, client_id: str) -> dict[str, Any] | None:
    try:
        return client.request_json("GET", "/api/v3/order", {"symbol": SYMBOL, "origClientOrderId": client_id}, signed=True)
    except BinanceError as exc:
        if exc.code == -2013:
            return None
        raise


def order_status(client: BinanceClient, order: dict[str, Any]) -> dict[str, Any] | None:
    if order.get("order_id"):
        try:
            return client.request_json("GET", "/api/v3/order", {"symbol": SYMBOL, "orderId": order["order_id"]}, signed=True)
        except BinanceError as exc:
            if exc.code == -2013:
                return None
            raise
    return order_by_client_id(client, order["client_id"])


def place_limit(client: BinanceClient, state: dict[str, Any], rules: dict[str, Decimal],
                *, side: str, qty: Decimal, price: Decimal, client_id: str,
                order_record: dict[str, Any]) -> dict[str, Any]:
    quantity = floor_step(qty, rules["step_size"])
    limit_price = floor_step(price, rules["tick_size"]) if side == "BUY" else ceil_step(price, rules["tick_size"])
    notional = quantity * limit_price
    if limit_price < rules["min_price"] or limit_price > rules["max_price"]:
        raise ValueError(f"Precio {limit_price} fuera de los filtros de Binance; orden no enviada.")
    if quantity < rules["min_qty"] or quantity > rules["max_qty"]:
        raise ValueError(f"Cantidad {quantity} fuera de LOT_SIZE; orden no enviada.")
    if notional < rules["min_notional"]:
        raise ValueError(f"Monto {notional} COP menor al mínimo {rules['min_notional']} COP; orden no enviada.")
    if rules["max_notional"] and notional > rules["max_notional"]:
        raise ValueError(f"Monto {notional} COP supera NOTIONAL máximo; orden no enviada.")

    # Persistir el clientOrderId ANTES del POST permite recuperar una respuesta incierta sin duplicar órdenes.
    order_record.update({"client_id": client_id, "side": side, "price": fmt(limit_price),
                         "quantity": fmt(quantity), "status": "PENDING", "created_day": utc_day()})
    write_state(state)
    params = {"symbol": SYMBOL, "side": side, "type": "LIMIT", "timeInForce": "GTC",
              "quantity": fmt(quantity), "price": fmt(limit_price), "newClientOrderId": client_id,
              "newOrderRespType": "FULL"}
    try:
        response = client.request_json("POST", "/api/v3/order", params, signed=True)
    except BinanceError as exc:
        append_monitor_event(status="error", request=_safe_order_trace(client), order=params,
                             error=str(exc), credentials=client.credentials)
        raise
    order_record["order_id"] = response.get("orderId")
    order_record["status"] = response.get("status", "NEW")
    order_record["response"] = response
    write_state(state)
    append_monitor_event(status="success", request=_safe_order_trace(client), final_response=response,
                         order=params, credentials=client.credentials)
    print(f"Binance aceptó solicitud LIMIT {side}: orderId={response.get('orderId')}, estado={response.get('status')}, cantidad={quantity} USDT, precio={limit_price} COP.", flush=True)
    return response


def recover_pending(client: BinanceClient, state: dict[str, Any], order: dict[str, Any]) -> dict[str, Any] | None:
    found = order_status(client, order)
    if found:
        order["order_id"] = found.get("orderId", order.get("order_id"))
        order["status"] = found.get("status", order.get("status"))
        order["response"] = found
        write_state(state)
        return found
    return None


def cancel_buy_if_open(client: BinanceClient, state: dict[str, Any], order: dict[str, Any]) -> None:
    current = recover_pending(client, state, order)
    if current is None or current.get("status") in TERMINAL:
        return
    if current.get("status") in {"NEW", "PARTIALLY_FILLED"}:
        response = client.request_json("DELETE", "/api/v3/order", {"symbol": SYMBOL, "orderId": current["orderId"]}, signed=True)
        order["status"] = response.get("status", "CANCELED")
        order["response"] = response
        write_state(state)
        print(f"Compra LIMIT pendiente cancelada con respuesta de Binance: orderId={current.get('orderId')}, estado={order['status']}.", flush=True)


def ensure_companion_sell(client: BinanceClient, state: dict[str, Any], rules: dict[str, Decimal],
                          buy: dict[str, Any]) -> None:
    if buy.get("sell_client_id"):
        return
    source = buy.get("response", {})
    executed = dec(source.get("executedQty", buy.get("executed_qty", "0")), "cantidad ejecutada")
    quote = dec(source.get("cummulativeQuoteQty", "0"), "valor de compra ejecutado")
    if executed <= 0:
        return
    average_price = quote / executed if quote > 0 else dec(buy["price"], "precio de compra")
    account = client.request_json("GET", "/api/v3/account", signed=True)
    free_usdt = account_balance(account, "USDT")
    sell_qty = floor_step(min(executed, free_usdt), rules["step_size"])
    if sell_qty < rules["min_qty"]:
        print(f"Compra {buy.get('order_id')} ejecutada, pero el saldo libre USDT no alcanza el mínimo de venta. Se reintentará en el siguiente ciclo.", flush=True)
        return
    sell_price = ceil_step(average_price * (Decimal("1") + SELL_PROFIT), rules["tick_size"])
    if sell_qty * sell_price < rules["min_notional"]:
        print(f"La venta pareja de la compra {buy.get('order_id')} no cumple NOTIONAL mínimo; no se envió venta.", flush=True)
        return
    sell_id = "dcaS_" + uuid.uuid4().hex[:24]
    sell = {"role": "SELL", "parent_client_id": buy["client_id"], "client_id": sell_id,
            "price": fmt(sell_price), "quantity": fmt(sell_qty), "status": "PENDING", "created_day": utc_day()}
    state["orders"].append(sell)
    buy["sell_client_id"] = sell_id
    write_state(state)
    place_limit(client, state, rules, side="SELL", qty=sell_qty, price=sell_price,
                client_id=sell_id, order_record=sell)
    print(f"Venta pareja configurada con margen bruto objetivo de {SELL_PROFIT * 100}% (antes de comisiones).", flush=True)


def _status_from_exchange(client: BinanceClient, state: dict[str, Any], order: dict[str, Any]) -> str:
    response = recover_pending(client, state, order)
    if response is None:
        if order.get("status") == "PENDING":
            return "PENDING"
        return str(order.get("status", "UNKNOWN"))
    order["response"] = response
    order["status"] = str(response.get("status", order.get("status", "UNKNOWN")))
    order["executed_qty"] = str(response.get("executedQty", "0"))
    write_state(state)
    return order["status"]


def process_orders(client: BinanceClient, state: dict[str, Any], rules: dict[str, Decimal]) -> bool:
    cycle_finished = False
    for order in list(state["orders"]):
        if order.get("role") == "SELL":
            status = _status_from_exchange(client, state, order)
            if status == "PENDING" and order.get("client_id"):
                # Una solicitud anterior pudo ser aceptada antes de perderse la respuesta; consulta por clientOrderId.
                found = order_by_client_id(client, order["client_id"])
                if found is None:
                    params = {"symbol": SYMBOL, "side": "SELL", "type": "LIMIT", "timeInForce": "GTC",
                              "quantity": order["quantity"], "price": order["price"],
                              "newClientOrderId": order["client_id"], "newOrderRespType": "FULL"}
                    place_limit(client, state, rules, side="SELL", qty=dec(order["quantity"], "cantidad"),
                                price=dec(order["price"], "precio"), client_id=order["client_id"], order_record=order)
                else:
                    order["response"] = found
                    order["order_id"] = found.get("orderId")
                    order["status"] = found.get("status", "NEW")
                    write_state(state)
            if order.get("status") == "FILLED" and not order.get("cycle_processed"):
                order["cycle_processed"] = True
                state["cycles_completed"] = int(state.get("cycles_completed", 0)) + 1
                state["regenerate_grid"] = True
                cycle_finished = True
                write_state(state)
                print(f"Ciclo completado: la venta LIMIT pareja fue informada FILLED por Binance (orderId={order.get('order_id')}).", flush=True)
        elif order.get("role") == "BUY":
            status = _status_from_exchange(client, state, order)
            if status == "PENDING":
                found = order_by_client_id(client, order["client_id"])
                if found is None:
                    if order.get("created_day") == utc_day():
                        place_limit(client, state, rules, side="BUY", qty=dec(order["quantity"], "cantidad"),
                                    price=dec(order["price"], "precio"), client_id=order["client_id"], order_record=order)
                    continue
                order["response"] = found
                order["order_id"] = found.get("orderId")
                order["status"] = found.get("status", "NEW")
                write_state(state)
                status = str(order["status"])
            if order.get("created_day") != utc_day() and status in {"NEW", "PARTIALLY_FILLED"}:
                cancel_buy_if_open(client, state, order)
                status = str(order.get("status", status))
                current = order.get("response", {})
                if dec(current.get("executedQty", order.get("executed_qty", "0")), "cantidad ejecutada") > 0:
                    ensure_companion_sell(client, state, rules, order)
            if status == "PARTIALLY_FILLED":
                cancel_buy_if_open(client, state, order)
                current = order.get("response", {})
                order["executed_qty"] = str(current.get("executedQty", order.get("executed_qty", "0")))
                order["status"] = str(current.get("status", order.get("status", "CANCELED")))
                if dec(order.get("executed_qty", "0"), "cantidad ejecutada") > 0:
                    order["response"] = current
                    ensure_companion_sell(client, state, rules, order)
            elif status in {"FILLED", "CANCELED", "EXPIRED"}:
                current = order.get("response", {})
                if dec(current.get("executedQty", order.get("executed_qty", "0")), "cantidad ejecutada") > 0:
                    ensure_companion_sell(client, state, rules, order)
    if cycle_finished:
        for order in state["orders"]:
            if order.get("role") == "BUY" and order.get("status") in {"NEW", "PARTIALLY_FILLED"}:
                cancel_buy_if_open(client, state, order)
        state["regenerate_grid"] = True
        write_state(state)
    return cycle_finished


def ensure_grid(client: BinanceClient, state: dict[str, Any], rules: dict[str, Decimal]) -> None:
    if not state.get("regenerate_grid"):
        return
    # No reemplazar niveles mientras haya compras pendientes de confirmar.
    active = [item for item in state["orders"] if item.get("role") == "BUY" and item.get("status") in {"PENDING", "NEW", "PARTIALLY_FILLED"}]
    if active:
        return
    account = client.request_json("GET", "/api/v3/account", signed=True)
    if account.get("canTrade") is not True:
        raise BinanceError("La cuenta no confirma canTrade=true; se detuvo sin crear compras.")
    price = get_price(client)
    print(f"Precio público {SYMBOL}: {price} COP/USDT. Preparando hasta {LEVELS} compras LIMIT.", flush=True)
    placed = 0
    daily = dec(state.get("daily_buy_usdt", "0"), "límite diario usado")
    for level in range(1, LEVELS + 1):
        if daily + BUY_QUANTITY_USDT > DAILY_LIMIT_USDT:
            print(f"Límite diario de compras alcanzado: reservado {daily} de {DAILY_LIMIT_USDT} USDT. No se crean más niveles hoy.", flush=True)
            break
        buy_price = floor_step(price - LEVEL_GAP_COP * level, rules["tick_size"])
        qty = floor_step(BUY_QUANTITY_USDT, rules["step_size"])
        notional = qty * buy_price
        if buy_price < rules["min_price"] or buy_price > rules["max_price"] or notional < rules["min_notional"]:
            print(f"Nivel {level} omitido: precio/monto ({buy_price} COP; {notional} COP) no cumple filtros publicados.", flush=True)
            continue
        current_account = client.request_json("GET", "/api/v3/account", signed=True)
        free_cop = account_balance(current_account, "COP")
        if free_cop < notional:
            print(f"Saldo libre COP insuficiente para el nivel {level} ({free_cop} disponible; {notional} requerido); se detienen nuevas compras.", flush=True)
            break
        client_id = "dcaB_" + uuid.uuid4().hex[:24]
        record = {"role": "BUY", "level": level, "client_id": client_id,
                  "price": fmt(buy_price), "quantity": fmt(qty), "status": "PENDING",
                  "created_day": utc_day()}
        state["orders"].append(record)
        # Reservamos el cupo antes de enviar: nunca superar 15 USDT en intentos de compra del día.
        daily += qty
        state["daily_buy_usdt"] = fmt(daily)
        write_state(state)
        try:
            place_limit(client, state, rules, side="BUY", qty=qty, price=buy_price,
                        client_id=client_id, order_record=record)
        except BinanceError:
            # Se conserva PENDING y su clientOrderId; el siguiente ciclo primero consulta ese ID.
            raise
        placed += 1
    state["regenerate_grid"] = False
    write_state(state)
    if placed:
        print(f"Malla creada: {placed} compra(s) LIMIT colocada(s); inversión máxima reservada hoy {daily} USDT de {DAILY_LIMIT_USDT}.", flush=True)
    else:
        print("No se creó ningún nivel nuevo; el bot seguirá vigilando y reintentará con espera.", flush=True)


def handle_new_day(state: dict[str, Any]) -> None:
    today = utc_day()
    if state.get("day") != today:
        state["day"] = today
        state["daily_buy_usdt"] = "0"
        # Las compras que quedaron abiertas de días previos se cancelan en process_orders antes de reponer malla.
        state["regenerate_grid"] = True
        write_state(state)
        print("Comenzó un nuevo día UTC; se reinicia el cupo diario a 15 USDT y se cancelarán niveles viejos aún abiertos.", flush=True)


def run_forever(client: BinanceClient) -> int:
    state = read_state()
    print("MODO REAL ACTIVADO por parámetro explícito. Este proceso puede crear órdenes LIMIT reales para USDTCOP.", flush=True)
    print("Estrategia: 5 niveles cada 20 COP, compras de 2 USDT, venta pareja +1% bruto y máximo 15 USDT de compras nuevas por día UTC.", flush=True)
    print("La cuenta debe tener permiso Spot y saldo COP/USDT. Para detener el bot, presiona Ctrl+C; las órdenes abiertas no se cancelan automáticamente.", flush=True)
    backoff = 2
    while True:
        try:
            handle_new_day(state)
            client.ensure_time_sync()
            rules = symbol_rules(client)
            process_orders(client, state, rules)
            ensure_grid(client, state, rules)
            backoff = 2
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            print("Bot detenido por el usuario. Las órdenes LIMIT abiertas permanecen en Binance.", flush=True)
            return 0
        except (BinanceError, requests.RequestException, OSError, ValueError, KeyError, InvalidOperation) as exc:
            # No mostrar URLs firmadas ni cuerpos potencialmente sensibles.
            print(f"Error operativo: {mask_text(str(exc), client.credentials)}. Reintento en {backoff} s.", file=sys.stderr, flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)


def acquire_lock() -> int:
    try:
        descriptor = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError("Ya existe bot_local.lock: parece que el bot está ejecutándose. Si está cerrado, verifica y elimina ese archivo manualmente.") from None
    os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    return descriptor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bot local USDTCOP. Sin parámetro no opera; test solo consulta.")
    parser.add_argument("mode", nargs="?", choices=("test", "run"), help="test consulta Binance; run activa la estrategia real")
    parser.add_argument("--run", dest="run_flag", action="store_true", help="activa explícitamente la estrategia real (equivale a escribir run)")
    args = parser.parse_args(argv)
    if args.mode == "test" and args.run_flag:
        parser.error("usa test o --run, no ambos")
    if args.mode == "test":
        return run_test()
    if args.mode != "run" and not args.run_flag:
        print("Modo seguro: no se envió ninguna orden. Para comprobar conexión: python bot_local.py test. La estrategia real solo empieza con: python bot_local.py --run", flush=True)
        return 0
    try:
        credentials = load_credentials()
        client = BinanceClient(credentials)
        lock = acquire_lock()
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"No se inició el bot: {mask_text(str(exc))}", file=sys.stderr)
        return 1
    try:
        return run_forever(client)
    finally:
        os.close(lock)
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
