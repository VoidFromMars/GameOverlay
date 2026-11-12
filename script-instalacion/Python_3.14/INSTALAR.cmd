@echo off
setlocal
chcp 65001 >nul
title Overlay Teclado - Instalador Python 3.14
echo ================================================================
echo   OVERLAY TECLADO - INSTALADOR PARA PYTHON 3.14
echo ================================================================
echo.

where py >nul 2>&1
if not errorlevel 1 (
    py -3.14 -c "import sys; raise SystemExit(sys.version_info[:2] != (3, 14))" >nul 2>&1
    if not errorlevel 1 (
        py -3.14 "%~dp0..\instalador_dependencias.py" 3.14
        goto :FIN
    )
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(sys.version_info[:2] != (3, 14))" >nul 2>&1
    if not errorlevel 1 (
        python "%~dp0..\instalador_dependencias.py" 3.14
        goto :FIN
    )
)

echo [ERROR] No se encontro Python 3.14.
echo Instala Python 3.14 desde python.org y vuelve a intentarlo.
:FIN
echo.
echo Pulsa una tecla para cerrar esta ventana.
pause >nul
endlocal
