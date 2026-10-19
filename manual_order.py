#!/usr/bin/env python3
"""Ejecuta una orden LIMIT USDTCOP recibida por repository_dispatch."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import trade


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} debe ser un número válido") from None
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{label} debe ser mayor que cero")
    return result


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Falta timestamp ISO-8601 en client_payload")
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("timestamp debe tener formato ISO-8601") from None
    if parsed.tzinfo is None:
        raise ValueError("timestamp debe incluir zona horaria")
    return parsed.isoformat()


def _free_balance(account: dict[str, Any], asset: str) -> Decimal:
    balances = account.get("balances", [])
    for entry in balances:
        if entry.get("asset") == asset:
            return Decimal(str(entry.get("free", "0")))
    return Decimal("0")


def execute_order(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida payload, mercado, filtros y saldo antes de enviar una LIMIT GTC."""
    if not isinstance(payload, dict):
        raise ValueError("client_payload debe ser un objeto JSON")
    side_text = payload.get("lado")
    if side_text not in ("buy", "sell"):
        raise ValueError("lado debe ser exactamente 'buy' o 'sell'")
    side = "BUY" if side_text == "buy" else "SELL"
    requested_price = _decimal(payload.get("precio"), "precio")
    requested_qty = _decimal(payload.get("cantidad"), "cantidad USDT")
    timestamp = _timestamp(payload.get("timestamp"))

    # Conserva precios de compra/venta pasivos y redondea solo según filtros del exchange.
    quantity, price = trade._validated_order(side, requested_qty, requested_price)
    book = trade.book_ticker()
    bid, ask = _decimal(book.get("bidPrice"), "mejor compra del libro"), _decimal(book.get("askPrice"), "mejor venta del libro")
    if side == "BUY" and price >= ask:
        raise ValueError(f"La compra LIMIT ({price} COP) cruzaría la mejor venta ({ask} COP); no se envió")
    if side == "SELL" and price <= bid:
        raise ValueError(f"La venta LIMIT ({price} COP) cruzaría la mejor compra ({bid} COP); no se envió")

    account = trade.account()
    if account.get("canTrade") is False:
        raise ValueError("La cuenta Binance no tiene habilitado el trading")
    permissions = account.get("permissions")
    if isinstance(permissions, list) and "SPOT" not in permissions:
        raise ValueError("La API Key de Actions no declara permiso SPOT")
    required_asset, required_amount = ("COP", price * quantity) if side == "BUY" else ("USDT", quantity)
    available = _free_balance(account, required_asset)
    if available < required_amount:
        raise ValueError(f"Saldo {required_asset} insuficiente: disponible {available}, requerido {required_amount}; no se envió")

    if side == "BUY":
        response = trade.place_limit_buy(quantity, price)
    else:
        response = trade.place_limit_sell(quantity, price)
    if not isinstance(response, dict):
        raise RuntimeError("Binance devolvió una respuesta de orden inesperada")
    return {
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp,
        "response": response,
    }


def _summary(result: dict[str, Any]) -> str:
    response = result["response"]
    return (
        "## Orden individual USDTCOP\n\n"
        "**Resultado: Binance aceptó la solicitud.**\n\n"
        f"- Lado: `{result['side']}`\n"
        f"- Precio límite: `{result['price']} COP`\n"
        f"- Cantidad: `{result['quantity']} USDT`\n"
        f"- Estado informado por Binance: `{response.get('status', 'no informado')}`\n"
        f"- Order ID: `{response.get('orderId', 'no informado')}`\n"
        f"- Client order ID: `{response.get('clientOrderId', 'no informado')}`\n"
        f"- Solicitud original (ISO-8601): `{result['timestamp']}`\n\n"
        "La orden fue LIMIT GTC; verifica su estado en Binance. No se reintentó automáticamente.\n"
    )


def _error_summary(error: Exception) -> str:
    safe = str(error).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    return f"## Orden individual USDTCOP\n\n**Resultado: error; no se confirmó una orden aceptada.**\n\n`{safe}`\n"


def _write_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as summary:
            summary.write(markdown + "\n")


def main() -> int:
    try:
        payload = json.loads(os.environ.get("MANUAL_ORDER_PAYLOAD", ""))
        result = execute_order(payload)
        _write_summary(_summary(result))
        response = result["response"]
        print(f"Orden LIMIT {result['side']} aceptada por Binance: orderId={response.get('orderId')}, estado={response.get('status')}.")
        return 0
    except Exception as exc:
        _write_summary(_error_summary(exc))
        print(f"ERROR en orden individual USDTCOP: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
