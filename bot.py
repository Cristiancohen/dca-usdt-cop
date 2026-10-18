""import requests

import json



BASE = 'https://data-api.binance.vision/api/v3'



def precio(symbol):
  
    r = requests.get(f'{BASE}/ticker/price', params={'symbol': symbol}, timeout=15)
  
    r.raise_for_status()
  
    return float(r.json()['price'])
  


if __name__ == '__main__':
  
    p = precio('USDTBRL')
  
    print(f'Prueba OK: {p}')""





