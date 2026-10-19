#!/usr/bin/env python3
"""Órdenes LIMIT spot para USDTCOP en Binance. No implementa órdenes MARKET."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any

SYMBOL = os.environ.get("DCA_SYMBOL", "USDTCOP")
PRIVATE_BASE_URL = os.environ.get("BINANCE_API_URL", "https://api.binance.com").rstrip("/")
PUBLIC_BASE_URL = os.environ.get("BINANCE_DATA_URL", "https://data-api.binance.vision").rstrip("/")
TIMEOUT_SECONDS = 20

# Estructura de auditoría de solicitudes (sin headers, timestamp firmado ni firma).
REQUEST_TRACE: list[dict[str, Any]] = []
_SAFE_LOG_PARAMS = {
    "symbol", "side", "type", "timeInForce", "quantity", "price",
    "newOrderRespType", "orderId", "limit", "interval",
}


def _safe_response_text(value: str) -> str:
    """Evita que valores de credenciales presentes por error en una respuesta se publiquen."""
    for name in ("BINANCE_API_KEY", "BINANCE_API_SECRET", "GITHUB_TOKEN", "GH_TOKEN"):
        secret = os.environ.get(name, "")
        if secret:
            value = value.replace(secret, "[REDACTADO]")
    return value


class BinanceAPIError(RuntimeError):
    """Error de Binance, conservando literalmente su mensaje cuando está disponible."""


def _credentials() -> tuple[str, str]:
    key = os.environ.get("BINANCE_API_KEY", "").strip()
    secret = os.environ.get("BINANCE_API_SECRET", "").strip()
    if not key or not secret:
        raise RuntimeError("Faltan BINANCE_API_KEY o BINANCE_API_SECRET en el entorno")
    return key, secret


def _request(method: str, path: str, params: dict[str, Any] | None = None, *, signed: bool = False,
             public: bool = False) -> Any:
    values = {k: str(v) for k, v in (params or {}).items()}
    headers = {"User-Agent": "dca-usdt-cop-limit-trader/1.0"}
    if signed:
        key, secret = _credentials()
        values["timestamp"] = str(int(time.time() * 1000))
        values["recvWindow"] = "10000"
        query = urllib.parse.urlencode(values)
        values["signature"] = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        headers["X-MBX-APIKEY"] = key
    query = urllib.parse.urlencode(values)
    base = PUBLIC_BASE_URL if public else PRIVATE_BASE_URL
    url = f"{base}{path}" + (f"?{query}" if query else "")
    req = urllib.request.Request(url, method=method, headers=headers)
    event: dict[str, Any] = {
        "method": method,
        "endpoint": path,
        "signed": signed,
        "request_params": {k: str(v) for k, v in values.items() if k in _SAFE_LOG_PARAMS},
        "proxy": None,
    }
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8", errors="replace")
            event["http_status"] = response.status
            event["raw_response"] = _safe_response_text(payload)
            try:
                decoded = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                decoded = None
            event["response_json"] = decoded
            REQUEST_TRACE.append(event)
            return decoded if decoded is not None else payload
    except urllib.error.HTTPError as exc:
        body = _safe_response_text(exc.read().decode("utf-8", errors="replace"))
        event["http_status"] = exc.code
        event["raw_response"] = body
        try:
            data = json.loads(body)
            event["response_json"] = data
            # Binance's JSON `msg` is surfaced verbatim, e.g. signature/permission errors.
            message = data.get("msg", body) if isinstance(data, dict) else body
            code = f" (código {data['code']})" if isinstance(data, dict) and "code" in data else ""
            REQUEST_TRACE.append(event)
            raise BinanceAPIError(f"Binance HTTP {exc.code}{code}: {message}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError):
            event["response_json"] = None
            REQUEST_TRACE.append(event)
            raise BinanceAPIError(f"Binance HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        event["error"] = _safe_response_text(str(exc.reason))
        REQUEST_TRACE.append(event)
        raise BinanceAPIError(f"Error de conexión con Binance: {exc.reason}") from exc


def symbol_filters(symbol: str = SYMBOL) -> dict[str, Decimal]:
    """Obtiene filtros vigentes del exchange (no valores codificados a mano)."""
    data = _request("GET", "/api/v3/exchangeInfo", {"symbol": symbol}, public=True)
    symbols = data.get("symbols", [])
    if not symbols:
        raise BinanceAPIError(f"Binance no devolvió información para el par {symbol}")
    info = symbols[0]
    if info.get("status") != "TRADING" or not info.get("isSpotTradingAllowed", False):
        raise BinanceAPIError(f"El par {symbol} no está habilitado para operar spot (estado: {info.get('status')})")
    filters = {f["filterType"]: f for f in info.get("filters", [])}
    pf, lot = filters.get("PRICE_FILTER"), filters.get("LOT_SIZE")
    notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL")
    if not pf or not lot or not notional:
        raise BinanceAPIError(f"Filtros PRICE_FILTER, LOT_SIZE o NOTIONAL ausentes para {symbol}")
    return {
        "tick_size": Decimal(pf["tickSize"]), "min_price": Decimal(pf["minPrice"]),
        "max_price": Decimal(pf["maxPrice"]), "step_size": Decimal(lot["stepSize"]),
        "min_qty": Decimal(lot["minQty"]), "max_qty": Decimal(lot["maxQty"]),
        "min_notional": Decimal(notional.get("minNotional", "0")),
        "max_notional": Decimal(notional.get("maxNotional", "0")),
    }


def _floor_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _ceil_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _format(value: Decimal) -> str:
    return format(value, "f")


def _validated_order(side: str, quantity: Decimal, price: Decimal) -> tuple[Decimal, Decimal]:
    f = symbol_filters()
    # Never round price to an invalid exchange tick: buy rounds down, sell rounds up.
    price = _floor_step(price, f["tick_size"]) if side == "BUY" else _ceil_step(price, f["tick_size"])
    quantity = _floor_step(quantity, f["step_size"])
    notional = quantity * price
    if price < f["min_price"] or price > f["max_price"]:
        raise ValueError(f"Precio {price} fuera del filtro del par ({f['min_price']}–{f['max_price']})")
    if quantity < f["min_qty"] or quantity > f["max_qty"]:
        raise ValueError(f"Cantidad {quantity} fuera del filtro LOT_SIZE ({f['min_qty']}–{f['max_qty']})")
    if notional < f["min_notional"]:
        raise ValueError(f"Monto {notional} COP menor al mínimo vigente de {f['min_notional']} COP")
    if f["max_notional"] and notional > f["max_notional"]:
        raise ValueError(f"Monto {notional} COP supera el máximo vigente de {f['max_notional']} COP")
    return quantity, price


def _place_limit(side: str, quantity: Decimal, price: Decimal) -> dict[str, Any]:
    quantity, price = _validated_order(side, quantity, price)
    # Explicit LIMIT + GTC. MARKET orders are intentionally not implemented.
    return _request("POST", "/api/v3/order", {
        "symbol": SYMBOL, "side": side, "type": "LIMIT", "timeInForce": "GTC",
        "quantity": _format(quantity), "price": _format(price),
        "newClientOrderId": f"dcacop_{int(time.time() * 1000)}_{secrets.token_hex(3)}",
        "newOrderRespType": "FULL",
    }, signed=True)


def place_limit_buy(usdt_amount: float | str | Decimal, price: float | str | Decimal) -> dict[str, Any]:
    """Compra `usdt_amount` USDT (activo base) a precio límite COP/USDT."""
    return _place_limit("BUY", Decimal(str(usdt_amount)), Decimal(str(price)))


def place_limit_sell(quantity: float | str | Decimal, price: float | str | Decimal) -> dict[str, Any]:
    """Vende `quantity` USDT a precio límite COP/USDT."""
    return _place_limit("SELL", Decimal(str(quantity)), Decimal(str(price)))


def check_order(order_id: int | str) -> dict[str, Any]:
    return _request("GET", "/api/v3/order", {"symbol": SYMBOL, "orderId": order_id}, signed=True)


def cancel_order(order_id: int | str) -> dict[str, Any]:
    return _request("DELETE", "/api/v3/order", {"symbol": SYMBOL, "orderId": order_id}, signed=True)


def account() -> dict[str, Any]:
    """Consulta GET /api/v3/account y devuelve el resultado real de Binance."""
    return _request("GET", "/api/v3/account", {}, signed=True)


def book_ticker() -> dict[str, Any]:
    return _request("GET", "/api/v3/ticker/bookTicker", {"symbol": SYMBOL}, public=True)


def recent_orders(limit: int = 100) -> list[dict[str, Any]]:
    """Historial de órdenes de este par; sólo lectura, sin endpoints de retiro/crédito."""
    return _request("GET", "/api/v3/allOrders", {"symbol": SYMBOL, "limit": min(max(int(limit), 1), 1000)}, signed=True)
