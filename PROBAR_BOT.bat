@echo off
setlocal
chcp 65001 >nul
title Prueba del bot Binance - solo lectura
cd /d "%~dp0"
set "RESULTADO=1"

echo ==================================================
echo PRUEBA DEL BOT - MODO SOLO LECTURA
echo Esta prueba no envia ni modifica ordenes.
echo ==================================================

if not exist "%~dp0bot_local.py" goto SIN_BOT
where python >nul 2>&1
if errorlevel 1 goto SIN_PYTHON

echo.
echo Ejecutando: python bot_local.py test
echo.
python bot_local.py test
set "RESULTADO=%ERRORLEVEL%"
if "%RESULTADO%"=="0" goto PRUEBA_OK

echo.
echo La prueba termino con error (codigo %RESULTADO%). Lee el resultado anterior.
goto FIN

:PRUEBA_OK
echo.
echo La prueba termino sin errores. Revisa los resultados de Binance anteriores.
goto FIN

:SIN_BOT
echo ERROR: No se encontro bot_local.py en esta misma carpeta.
goto FIN

:SIN_PYTHON
echo ERROR: No se encontro Python. Instala Python antes de usar este archivo.
goto FIN

:FIN
echo.
echo Pulsa una tecla para cerrar esta ventana.
pause >nul
exit /b %RESULTADO%
