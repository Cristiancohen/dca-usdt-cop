#!/usr/bin/env python3
"""Aviso DCA USDT/COP basado en datos públicos; nunca ejecuta órdenes."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_URL = os.environ.get("BINANCE_DATA_URL", "https://data-api.binance.vision").rstrip("/")
SYMBOL = os.environ.get("DCA_SYMBOL", "USDTCOP")
BUY_DISCOUNT_PCT = float(os.environ.get("DCA_BUY_DISCOUNT_PCT", "1.5"))
REFERENCE_BUDGET_USD = 5.0  # Solo referencia para el aviso; no se convierte ni se gasta.
TIMEOUT_SECONDS = 20
USER_AGENT = "dca-usdt-cop-alert/1.0"


def get_json(path: str, params: dict[str, str]) -> object:
    url = f"{BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} consultando {url}")
        return json.loads(response.read().decode("utf-8"))


def run() -> bool:
    if not 1.0 <= BUY_DISCOUNT_PCT <= 2.0:
        raise ValueError("DCA_BUY_DISCOUNT_PCT debe estar entre 1 y 2")

    ticker = get_json("/api/v3/ticker/price", {"symbol": SYMBOL})
    candles = get_json("/api/v3/klines", {"symbol": SYMBOL, "interval": "1d", "limit": "16"})
    if not isinstance(ticker, dict) or not isinstance(candles, list):
        raise RuntimeError("Respuesta inesperada de Binance data API")

    price = float(ticker["price"])
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    # Solo velas UTC cerradas; excluye la vela diaria que aún está en curso.
    completed = [c for c in candles if isinstance(c, list) and len(c) > 6 and int(c[6]) < now_ms]
    closes = [float(c[4]) for c in completed[-14:]]
    if len(closes) < 14:
        raise RuntimeError(f"Se recibieron {len(closes)} velas diarias completas; hacen falta 14")

    average = sum(closes) / len(closes)
    threshold = average * (1 - BUY_DISCOUNT_PCT / 100)
    if price > threshold:
        return False  # Sin señal: silencio deliberado en stdout.

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(
        "AVISO DCA USDT/COP — SEÑAL SIMULADA (sin compra ejecutada)\n"
        f"Hora UTC: {timestamp}\n"
        f"Precio spot: {price:,.2f} COP por USDT\n"
        f"Promedio de 14 cierres diarios completos: {average:,.2f} COP\n"
        f"Descuento configurado: {BUY_DISCOUNT_PCT:.2f}% (umbral: {threshold:,.2f} COP)\n"
        f"Referencia de presupuesto: USD {REFERENCE_BUDGET_USD:.2f}; no se gastó ni convirtió dinero.\n"
        "Modo: AVISO / DRY_RUN — orders_sent=false",
        flush=True,
    )
    return True


def main() -> int:
    try:
        run()
        return 0
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, RuntimeError, OSError) as exc:
        print(f"ERROR DCA USDT/COP (DRY_RUN, sin órdenes): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
