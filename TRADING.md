# Órdenes LIMIT USDTCOP

La vigilancia existente (`bot.py`) y el disparador programado de `.github/workflows/dca.yml` se conservan. El workflow también recibe el evento `repository_dispatch` `manual-order` para la prueba individual. La lógica de operación está aislada en `trade.py` y crea únicamente órdenes spot `LIMIT` con `GTC`; los precios y cantidades se ajustan usando `exchangeInfo` en tiempo de ejecución. Antes de comprar, `test_order.py` consulta `/api/v3/account`, verifica `canTrade` y permiso `SPOT`, y comprueba el saldo libre en COP.

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

## Panel de órdenes en la calculadora

La calculadora conserva el panel **MODO CONTROLADO** por defecto. `Simular escalera` registra las órdenes hipotéticas y no llama a endpoints privados ni envía órdenes. La lógica y los cálculos de la calculadora, así como la escalera proyectada, se mantienen. Para evitar pedir o almacenar credenciales de Binance en el navegador, el envío real de la escalera y la cancelación directa están deshabilitados en Pages.

La sección **PRUEBA INDIVIDUAL** permite elegir compra o venta, escribir precio COP y cantidad USDT, y simular sin enviar órdenes. Para enviar una única orden LIMIT, la página hace POST a `https://api.github.com/repos/Cristiancohen/dca-usdt-cop/dispatches` con `event_type: manual-order` y un payload con precio, lado, cantidad y timestamp. Requiere un Personal Access Token (classic) con scopes `repo` y `workflow`; al guardarlo, queda solo en `localStorage` de ese navegador, sin cifrar. No se incluye en HTML, repositorio ni payload. La página muestra si el token está guardado o vacío y permite cambiarlo o borrarlo.

El workflow `.github/workflows/dca.yml` recibe el `repository_dispatch` `manual-order` y ejecuta `manual_order.py`. El bot valida el payload, filtros del par, libro (evita una LIMIT que cruce), permiso Spot y saldo libre antes de pedir exactamente una orden `LIMIT GTC` mediante `trade.py`. Lee los Actions Secrets `BINGTUSH_API_KEY`/`BINGTUSH_API_SECRET`, con compatibilidad para los nombres existentes `BINANCE_API_KEY`/`BINANCE_API_SECRET`. El resultado o error queda en el resumen de Actions. HTTP 204 solo confirma que GitHub recibió el evento; no confirma que Binance aceptó la orden. Si la red no permite confirmar el resultado, revisa Actions y Binance antes de volver a enviar. No hay reintentos automáticos de una orden incierta.
