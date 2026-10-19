@echo off
setlocal
chcp 65001 >nul
title Bot USDTCOP - MODO RUN
cd /d "%~dp0"

echo ==================================================
echo MODO RUN: el bot puede enviar ordenes LIMIT reales a Binance.
echo Deja esta ventana abierta para ver los registros del bot.
echo Detener el programa no cancela ordenes ya abiertas en Binance.
echo ==================================================

if not exist "%~dp0bot_local.py" goto SIN_BOT
where python >nul 2>&1
if errorlevel 1 goto SIN_PYTHON

echo.
echo Ejecutando: python bot_local.py run
echo.
python bot_local.py run
set "BOT_RESULT=%ERRORLEVEL%"
if "%BOT_RESULT%"=="0" goto FIN
echo.
echo ERROR: el bot termino con codigo %BOT_RESULT%.
echo Revisa el mensaje anterior. La ventana quedara abierta.
pause >nul
exit /b %BOT_RESULT%

:SIN_BOT
echo ERROR: No se encontro bot_local.py en esta misma carpeta.
goto ERROR_FINAL

:SIN_PYTHON
echo ERROR: No se encontro Python. Instala Python antes de usar este archivo.
goto ERROR_FINAL

:ERROR_FINAL
pause >nul
exit /b 1

:FIN
exit /b 0
