# Guía sencilla: probar Binance desde tu PC con Windows

Esta es la **Fase 1: comprobar conexión**, sin crear órdenes. El archivo `bot_local.py` incluye además una estrategia real optativa, pero permanece apagada si no escribes expresamente `run` o `--run`. **No uses ese modo todavía**: primero corre el test y revisa sus resultados.

## 1. Instalar Python

1. Entra en [python.org/downloads](https://www.python.org/downloads/) y descarga Python para Windows.
2. Abre el instalador. Marca **Add python.exe to PATH** antes de instalar.
3. Cuando termine, abre **Símbolo del sistema** (busca `cmd` en Inicio) y ejecuta:

   ```text
   python --version
   ```

   Debe aparecer una versión de Python 3. Si Windows no reconoce `python`, prueba `py --version` y usa `py` en vez de `python` en los pasos siguientes.

## 2. Guardar los archivos

1. Crea una carpeta sencilla, por ejemplo `C:\dca-usdt-cop`.
2. Guarda dentro de esa carpeta el archivo adjunto `bot_local.py`.
3. Guarda también `GUiA_PC.md` si quieres conservar estas instrucciones.
4. Abre el Símbolo del sistema y entra a la carpeta:

   ```text
   cd C:\dca-usdt-cop
   ```

## 3. Instalar la única dependencia

En esa misma ventana ejecuta:

```text
python -m pip install requests
```

Si utilizas el lanzador `py`, ejecuta `py -m pip install requests`.

## 4. Crear `config_local.json` con tus llaves

1. En Binance, crea una API Key propia. Activa **lectura** para que el test pueda consultar la cuenta. Para la estrategia futura también hará falta permiso **Spot Trading**.
2. **No actives retiros/withdrawals. No compartas las llaves por WhatsApp ni las pegues aquí.** Puedes restringir la llave a la IP de tu casa si sabes que esa IP no cambia; una restricción incorrecta puede bloquear la conexión.
3. Abre el Bloc de notas y pega esta plantilla. Sustituye los dos textos de ejemplo por tus valores reales, conservando comillas y comas:

   ```json
   {
     "binance_api_key": "PEGA_AQUI_TU_API_KEY",
     "binance_api_secret": "PEGA_AQUI_TU_API_SECRET"
   }
   ```

4. En Bloc de notas, elige **Archivo > Guardar como**. Guarda el nombre exacto `config_local.json` dentro de `C:\dca-usdt-cop`. En **Tipo** elige **Todos los archivos** para que no termine como `config_local.json.txt`.
5. No subas ni envíes ese archivo. En el repositorio, su nombre está excluido por `.gitignore`; de todos modos, mantenlo solo en tu PC.

## 5. Ejecutar el test (no envía órdenes)

En el Símbolo del sistema, todavía dentro de `C:\dca-usdt-cop`, ejecuta:

```text
python bot_local.py test
```

El programa hace estas consultas en este orden y muestra para cada respuesta el **código HTTP** y el **cuerpo crudo recibido de Binance**:

1. Conexión pública: `/api/v3/ping` y `/api/v3/time`.
2. Consulta firmada de solo lectura: `/api/v3/account`.
3. Filtros públicos de `USDTCOP`: `/api/v3/exchangeInfo`.

Si todo está bien, lo esperado es **HTTP 200** en ping, hora, cuenta y filtros (son tres pruebas; la primera consulta dos endpoints). El resumen final dirá que pasaron. En la tercera respuesta se mostrarán `tickSize`, `stepSize` y `minNotional`; el dato publicado anteriormente por este proyecto fue 1 COP, 1 USDT y 4.000 COP, respectivamente, pero Binance puede cambiar los filtros.

**El modo `test` no tiene código para crear, cancelar ni modificar órdenes.** La respuesta de cuenta puede mostrar datos de saldo en la consola: no publiques una captura sin ocultarlos. Las llaves no se muestran ni se guardan en la bitácora.

Si alguna consulta no da HTTP 200, copia aquí solo el número HTTP y el mensaje de error, ocultando cualquier saldo o dato personal. No compartas `config_local.json`. Errores `-2015`/HTTP 401 suelen indicar llave o permiso incorrecto; `-1021` indica desfase del reloj (el script sincroniza y reintenta); un error de red/451 requiere revisar conectividad desde esa PC. **No intentes la estrategia real hasta que el test se haya revisado.**

## 6. Inicio automático de Windows (solo después de validar el test)

La tarea automática ejecuta el modo real. **No la crees ni la habilites durante esta Fase 1.** Espera a revisar primero los resultados del test y a recibir autorización explícita para pasar a órdenes reales.

Cuando llegue ese momento:

1. Deja el equipo conectado a Internet y evita que Windows entre en suspensión. La PC debe permanecer encendida para que el programa vigile el mercado.
2. Abre **Programador de tareas** desde Inicio y elige **Crear tarea básica**.
3. Ponle un nombre reconocible, por ejemplo `Bot USDTCOP Binance`.
4. Elige el desencadenador **Al iniciar sesión** (se inicia al entrar a Windows). Si eliges **Al iniciar el equipo**, Windows puede pedir permisos de administrador.
5. En **Iniciar un programa**, pon `python.exe` en **Programa o script**. Para encontrar su ruta exacta, en el Símbolo del sistema ejecuta `where python` y copia la primera ruta completa.
6. En **Agregar argumentos**, escribe exactamente:

   ```text
   bot_local.py --run
   ```

7. En **Iniciar en**, escribe la carpeta donde guardaste el script, por ejemplo:

   ```text
   C:\dca-usdt-cop
   ```

8. Termina el asistente y revisa la tarea antes de habilitarla. En sus opciones evita iniciar una segunda instancia si la tarea ya está ejecutándose.

`--run` **sí habilita órdenes LIMIT reales**: cinco niveles de compra separados aproximadamente 20 COP, 2 USDT por nivel, venta asociada con objetivo bruto +1% y máximo de 15 USDT en nuevas compras por día UTC. El objetivo +1% es antes de comisiones; no garantiza ganancia neta. El archivo `bot_local_state.json` conserva el estado y `monitor/local_log.json` guarda eventos en el formato del monitor del proyecto; ambos son archivos locales ignorados por Git.

Cerrar el programa con Ctrl+C o detener la tarea **no cancela las órdenes que ya estén abiertas en Binance**. Revísalas en Binance; la estrategia futura y sus riesgos deben validarse antes de habilitar el inicio automático.
