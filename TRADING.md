# Órdenes LIMIT USDTCOP

La vigilancia existente (`bot.py` y `.github/workflows/dca.yml`) permanece intacta. La lógica de operación está aislada en `trade.py` y crea únicamente órdenes spot `LIMIT` con `GTC`; los precios y cantidades se ajustan usando `exchangeInfo` en tiempo de ejecución. Antes de comprar, `test_order.py` consulta `/api/v3/account`, verifica `canTrade` y permiso `SPOT`, y comprueba el saldo libre en COP.

## Prueba real opt-in

Sólo ejecutar tras confirmar saldo y en una cuenta donde se autoriza la compra real:

```bash
export BINANCE_API_KEY='…'
export BINANCE_API_SECRET='…'
python test_order.py --live
```

La compra toma el ask vigente del libro, usa la cantidad mínima que respeta `LOT_SIZE`/`NOTIONAL` y se limita a 8.000 COP de notional. Espera hasta 90 segundos a que Binance la ejecute; si no se completa, cancela la compra abierta y no intenta vender una cantidad no ejecutada. Si la compra se completa, deja colocada una venta LIMIT 1% sobre el precio medio de ejecución. El test sin `--live` no envía órdenes.

En GitHub Actions, ejecutar manualmente **Prueba real de orden LIMIT USDTCOP** y escribir exactamente `EJECUTAR_COMPRA_LIMIT_REAL`. Los secretos `BINANCE_API_KEY` y `BINANCE_API_SECRET` se leen del entorno de Actions; nunca se incluyen en archivos ni página web.

## Página de órdenes

`docs/index.html` muestra las órdenes LIMIT cuyo `clientOrderId` comienza con `dcacop_`; el feed se obtiene con `GET /api/v3/allOrders` en Actions, y publica sólo lado, precio, cantidad, notional, estado y fecha. La página es pública y se actualiza con el workflow **Publicar página de órdenes USDTCOP** cada 15 minutos, además de poder ejecutarse manualmente. No publica llaves ni saldos. Los registros de órdenes quedan visibles para cualquier visitante de GitHub Pages.

Las órdenes pueden quedar abiertas si Binance no las ejecuta; no se cancelan automáticamente las órdenes de venta, para respetar el propósito de la prueba.
