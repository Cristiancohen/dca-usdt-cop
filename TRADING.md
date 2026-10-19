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

## Panel de órdenes en la calculadora

La calculadora incluye un panel **MODO CONTROLADO** por defecto. `Simular escalera` registra las órdenes hipotéticas y no llama a ningún endpoint de trading. Las líneas proyectadas y la lógica/cálculos de la calculadora permanecen intactos; el panel toma sus cantidades de la escalera existente. Al preparar una ejecución real, reancla las compras al menos 20 COP bajo el precio Spot recién consultado y las ventas desde 2 COP sobre él, conservando la separación de la escalera. Consulta `exchangeInfo` en cada preparación y valida estado Spot, filtros de precio/cantidad/notional, saldo libre COP y USDT, y precios que no crucen.

Para operar en Pages, expande **Configurar llaves de Binance en este navegador**, pega tu propia API Key y API Secret y pulsa **Guardar en este navegador**. Los nombres `BINANCE_API_KEY` y `BINANCE_API_SECRET` existen como secretos de Actions de este repositorio, pero una página estática de GitHub Pages no puede leerlos ni debe publicarlos; el panel no intenta acceder a ellos. No se lee ningún valor secreto desde GitHub. Las llaves que el usuario pegue se guardan únicamente en `localStorage` del navegador/origen, sin cifrar: extensiones o código ejecutado en esa página podrían leerlas. Usa permisos Spot mínimos, sin retiros, y evita equipos compartidos.

Para habilitar operación real, hay que activar el segundo switch **Habilitar envío REAL**, aceptar la confirmación y escribir exactamente `REAL USDTCOP`; cada lote también requiere confirmar **Enviar órdenes LIMIT reales**. La sección **PRUEBA INDIVIDUAL** permite elegir compra o venta y escribir un precio COP y una cantidad USDT independientes de la escalera. La simulación no llama a endpoints de trading; en modo real prepara, valida filtros, precio que no cruce el precio vivo y saldo para una sola orden, muestra el resumen y exige confirmación final antes de enviar exactamente un `LIMIT GTC`. No modifica ni envía la escalera. Se requiere validar las credenciales con **Probar conexión** antes del primer envío. La página consulta el precio y filtros oficiales de Binance, comprueba saldo disponible para toda la escalera y solo envía órdenes `LIMIT` `GTC` para `USDTCOP` (USDT como activo base y COP como cotizado). No reintenta automáticamente un fallo de red: el resultado puede ser incierto, así que se debe revisar Binance antes de volver a enviar. El botón de cancelación consulta las abiertas, pero solo cancela órdenes cuyo `clientOrderId` empieza por `dcaweb_`; no toca otras órdenes del usuario. Los aciertos, errores y respuestas de orden/cancelación se muestran en el registro del navegador.

En la verificación de implementación, el endpoint oficial `data-api.binance.vision/api/v3/exchangeInfo?symbol=USDTCOP` informó `TRADING` y Spot permitido; la página vuelve a consultar esa información en cada preparación. No se envió ninguna orden real durante las pruebas. La disponibilidad de los endpoints privados desde el navegador depende de CORS, red, permisos de la API Key y región de Binance; los fallos se muestran en el registro y bloquean/reducen la operación según el punto de fallo.
