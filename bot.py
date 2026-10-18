import json
import os
import urllib.request

SYMBOL = os.environ.get("SYMBOL", "USD/COP")
BUY_DISCOUNT_PCT = float(os.environ.get("BUY_DISCOUNT_PCT", "1"))
DAYS = int(os.environ.get("DAYS", "14"))

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dca-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def main():
    data = get_json("https://open.er-api.com/v6/latest/USD")
    spot = data["rates"].get("COP")
    if not spot:
        print("ERROR: no hay tasa COP disponible")
        return
    print(f"Precio spot USD/COP: {spot:,.2f}")
    print(f"Fuente: open.er-api.com (tasa de mercado, actualizada {data.get('time_last_update_utc','')})")
    print("Nota: Binance spot no tiene par USDT/COP, se usa la tasa de mercado como referencia DCA.")
    print(f"Umbral de compra: {BUY_DISCOUNT_PCT}% bajo el promedio de {DAYS} dias")

if __name__ == "__main__":
    main()
