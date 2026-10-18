#!/usr/bin/env python3
"""Prueba spot real opt-in: compra LIMIT mínima y deja una venta LIMIT con margen.

Ejecutar sólo con --live y las credenciales correctas en el entorno.
"""
from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal, ROUND_CEILING

from trade import (
    BinanceAPIError, SYMBOL, _ceil_step, _floor_step, account, book_ticker, check_order,
    place_limit_buy, place_limit_sell, symbol_filters,
)

# Límite deliberadamente inferior a los 20.000 COP indicados por el usuario.
MAX_TEST_NOTIONAL_COP = Decimal("8000")
POLL_SECONDS = 3
WAIT_SECONDS = 90
SELL_MARGIN = Decimal("0.01")


def available_balance(data: dict, asset: str) -> Decimal:
    for entry in data.get("balances", []):
        if entry.get("asset") == asset:
            return Decimal(entry.get("free", "0"))
    return Decimal("0")


def require_spot_trade_permission(data: dict) -> None:
    if data.get("canTrade") is not True:
        raise RuntimeError(f"La cuenta no confirma permiso de trading spot (canTrade={data.get('canTrade')!r})")
    perms = data.get("permissions")
    sets = data.get("permissionSets")
    explicit_spot = isinstance(perms, list) and "SPOT" in perms
    if isinstance(sets, list):
        explicit_spot = explicit_spot or any(
            isinstance(group, list) and "SPOT" in group for group in sets
        )
    if not explicit_spot:
        raise RuntimeError(
            f"La respuesta de cuenta no confirma permiso SPOT (permissions={perms!r}, permissionSets={sets!r}); no se envió orden"
        )


def print_order(label: str, order: dict) -> None:
    print(
        f"{label}: order_id={order.get('orderId')} lado={order.get('side')} "
        f"tipo={order.get('type')} precio={order.get('price')} "
        f"cantidad={order.get('origQty')} estado={order.get('status')} "
        f"ejecutada={order.get('executedQty')} monto_ejecutado={order.get('cummulativeQuoteQty')}",
        flush=True,
    )


def run_live() -> int:
    print(f"Prueba real LIMIT para {SYMBOL}; no se crearán órdenes MARKET.", flush=True)
    # Este chequeo debe ser el primer acceso a la API privada y preceder a cualquier orden.
    acct = account()
    require_spot_trade_permission(acct)
    cop_free = available_balance(acct, "COP")
    usdt_free = available_balance(acct, "USDT")
    print(f"GET /api/v3/account OK; permiso spot confirmado; saldo libre COP={cop_free} USDT={usdt_free}", flush=True)

    filters = symbol_filters()
    book = book_ticker()
    ask = Decimal(book["askPrice"])
    if ask <= 0:
        raise RuntimeError(f"Precio ask no válido devuelto por Binance: {ask}")
    limit_price = (ask / filters["tick_size"]).to_integral_value(rounding=ROUND_CEILING) * filters["tick_size"]
    # Usa la cantidad mínima que satisface minQty y minNotional después de los filtros vigentes.
    needed = max(filters["min_qty"], filters["min_notional"] / limit_price)
    qty = _ceil_step(needed, filters["step_size"])
    total = qty * limit_price
    if total > MAX_TEST_NOTIONAL_COP:
        raise RuntimeError(
            f"La cantidad mínima de filtros costaría {total} COP, supera el tope de prueba {MAX_TEST_NOTIONAL_COP} COP; no se envió orden"
        )
    if cop_free < total:
        raise RuntimeError(f"Saldo libre COP insuficiente: disponible={cop_free}, requerido={total}; no se envió orden")

    print(
        f"Libro público actual: ask={ask} COP/USDT; límite de compra={limit_price}; "
        f"cantidad mínima válida={qty} USDT; total máximo de la orden={total} COP.",
        flush=True,
    )
    buy = place_limit_buy(qty, limit_price)
    print_order("COMPRA LIMIT enviada", buy)
    order_id = buy["orderId"]
    deadline = time.monotonic() + WAIT_SECONDS
    current = buy
    while current.get("status") not in ("FILLED", "CANCELED", "REJECTED", "EXPIRED") and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
        current = check_order(order_id)
        print_order("Estado de compra consultado", current)

    if current.get("status") != "FILLED":
        if current.get("status") in ("NEW", "PARTIALLY_FILLED"):
            cancelled = __import__("trade").cancel_order(order_id)
            print_order("Compra LIMIT cancelada para no dejar saldo bloqueado", cancelled)
        print("No hubo compra completamente ejecutada; no se creó venta (no hay cantidad neta segura para vender).", flush=True)
        return 2

    executed = Decimal(current.get("executedQty", "0"))
    quote_executed = Decimal(current.get("cummulativeQuoteQty", "0"))
    if executed <= 0 or quote_executed <= 0:
        raise RuntimeError(f"Binance informó FILLED pero sin cantidad ejecutada válida: {current}")
    avg_fill = quote_executed / executed

    # Relee saldo base para descontar cualquier comisión que Binance haya cobrado en USDT.
    after_buy = account()
    net_available = available_balance(after_buy, "USDT")
    sell_qty = _floor_step(min(executed, net_available), filters["step_size"])
    if sell_qty < filters["min_qty"]:
        raise RuntimeError(f"USDT neto disponible ({net_available}) no alcanza el mínimo para vender")
    sell_price = _ceil_step(avg_fill * (Decimal("1") + SELL_MARGIN), filters["tick_size"])
    sell_notional = sell_qty * sell_price
    if sell_notional < filters["min_notional"]:
        raise RuntimeError(f"Venta neta {sell_notional} COP menor al minNotional {filters['min_notional']}; venta no enviada")
    sell = place_limit_sell(sell_qty, sell_price)
    print_order(f"VENTA LIMIT colocada con margen {SELL_MARGIN * 100}% (queda abierta hasta ejecución/cancelación)", sell)
    print(
        f"PRUEBA REAL FINALIZADA: compra order_id={order_id} estado={current.get('status')}; "
        f"venta order_id={sell.get('orderId')} estado={sell.get('status')}.",
        flush=True,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="autoriza enviar una compra y venta LIMIT reales")
    args = parser.parse_args()
    if not args.live:
        print("Modo seguro: no se enviaron órdenes. Repite con --live para ejecutar la prueba real.")
        return 0
    try:
        return run_live()
    except (BinanceAPIError, RuntimeError, ValueError, KeyError) as exc:
        # BinanceAPIError incluye el código y el campo msg exacto si lo devolvió el exchange.
        print(f"ERROR DE PRUEBA: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
