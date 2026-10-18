import json
import os
import urllib.request

BASE_URL = os.environ.get("BINANCE_DATA_URL", "https://data-api.binance.vision")
SYMBOL = os.environ.get("SYMBOL", "USDCOP")
BUY_DISCOUNT_PCT = float(os.environ.get("BUY_DISCOUNT_PCT", "1"))
DAYS = int(os.environ.get("DAYS", "14"))

def get_json(path):
    req = urllib.request.Request(BASE_URL + path, headers={"User-Agent": "dca-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def main():
    klines = get_json(f"/api/v3/klines?symbol={SYMBOL}&interval=1d&limit={DAYS}")
    closes = [float(k[4]) for k in klines]
    avg = sum(closes) / len(closes)
    ticker = get_json(f"/api/v3/ticker/price?symbol={SYMBOL}")
    spot = float(ticker["price"])
    dev = (spot - avg) / avg * 100
    print(f"Precio spot USDT/COP: {spot:,.2f}")
    print(f"Promedio {DAYS} dias: {avg:,.2f}")
    print(f"Desviacion: {dev:+.2f}%")
    if dev <= -BUY_DISCOUNT_PCT:
        print(f"ALERTA: precio {abs(dev):.2f}% por debajo del promedio, momento de compra DCA")
    else:
        print("Sin senal de compra: precio dentro del rango normal")

if __name__ == "__main__":
    main()
