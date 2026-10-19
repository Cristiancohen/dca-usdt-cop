# Guía breve: bot local de Binance en Windows

Python y la librería `requests` ya deben estar instalados en la PC. Los cuatro archivos siguientes deben quedar juntos en una misma carpeta: `bot_local.py`, `PROBAR_BOT.bat`, `INICIAR_BOT.bat` y esta guia.

## 1. Crear `config_local.json` con tus llaves

1. En Binance, usa una API Key propia. Para la prueba basta el permiso de lectura; para el modo `run` también se requiere permiso de Spot Trading. **No actives retiros.**
2. Abre el Bloc de notas y pega esta plantilla, reemplazando los textos de ejemplo por tus llaves:

   ```json
   {
     "binance_api_key": "PEGA_AQUI_TU_API_KEY",
     "binance_api_secret": "PEGA_AQUI_TU_API_SECRET"
   }
   ```

3. Guarda el archivo con el nombre exacto `config_local.json` en la misma carpeta que `bot_local.py`. En **Guardar como**, selecciona **Todos los archivos** para evitar que quede como `config_local.json.txt`.
4. No compartas ni subas ese archivo. `config_local.json` esta excluido del repositorio; mantenlo solo en tu PC.

## 2. Probar la conexión (no envía órdenes)

Haz doble clic en `PROBAR_BOT.bat` y espera a que termine. La ventana mostrará las respuestas y quedará abierta para que puedas leerlas. El modo de prueba consulta la conectividad, la cuenta en modo de solo lectura y los filtros de `USDTCOP`; **no crea, cancela ni modifica órdenes**.

Si la prueba da error, no inicies el bot. Comparte solo los códigos HTTP y mensajes de error; oculta cualquier saldo o dato personal y no compartas las llaves ni `config_local.json`.

## 3. Iniciar el bot

Haz doble clic en `INICIAR_BOT.bat` solo después de que la prueba haya salido bien y hayas decidido habilitar el modo real. La ventana queda abierta mostrando los registros mientras funciona.

**Aviso: `run` puede enviar órdenes LIMIT reales a Binance.** La estrategia tiene cinco niveles de compra separados aproximadamente 20 COP, 2 USDT por nivel, ventas asociadas con objetivo bruto de +1% y un máximo de 15 USDT en nuevas compras por día UTC. El objetivo es antes de comisiones y no garantiza ganancia neta. Detener el programa no cancela órdenes que ya estén abiertas; revísalas directamente en Binance.
