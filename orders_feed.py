#!/usr/bin/env python3
"""Genera el feed público mínimo de órdenes LIMIT creadas por este bot."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from trade import BinanceAPIError, SYMBOL, recent_orders

STATUS_ES = {
    "NEW": "Nueva", "PARTIALLY_FILLED": "Parcialmente ejecutada", "FILLED": "Ejecutada",
    "CANCELED": "Cancelada", "PENDING_CANCEL": "Cancelación pendiente", "REJECTED": "Rechazada",
    "EXPIRED": "Vencida", "EXPIRED_IN_MATCH": "Vencida",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="docs/orders.json")
    args = parser.parse_args()
    try:
        raw = recent_orders(1000)
        # Identificador del cliente aplicado exclusivamente a órdenes enviadas por trade.py.
        bot_orders = [o for o in raw if o.get("type") == "LIMIT" and str(o.get("clientOrderId", "")).startswith("dcacop_")]
        bot_orders.sort(key=lambda o: int(o.get("time", 0)), reverse=True)
        result = []
        for order in bot_orders[:100]:
            price = Decimal(str(order.get("price", "0")))
            quantity = Decimal(str(order.get("origQty", "0")))
            result.append({
                "orderId": str(order.get("orderId", "")),
                "side": order.get("side", ""),
                "price": format(price, "f"),
                "quantity": format(quantity, "f"),
                "total": format(price * quantity, "f"),
                "status": order.get("status", ""),
                "statusEs": STATUS_ES.get(order.get("status", ""), order.get("status", "Desconocido")),
                "time": datetime.fromtimestamp(int(order.get("time", 0)) / 1000, timezone.utc).isoformat(timespec="seconds"),
                "type": order.get("type", ""),
            })
        payload = {"symbol": SYMBOL, "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "orders": result}
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Feed actualizado desde GET /api/v3/allOrders: {len(result)} órdenes LIMIT del bot; archivo={out}", flush=True)
        return 0
    except (BinanceAPIError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR al actualizar feed de órdenes: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
