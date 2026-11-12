@echo off
setlocal
chcp 65001 >nul
title Overlay Teclado - Instalador Python 3.13 e inferiores
echo ================================================================
echo   OVERLAY TECLADO - INSTALADOR PARA PYTHON 3.13 O ANTERIOR
echo ================================================================
echo.

set "PY_SELECTED="
where py >nul 2>&1
if not errorlevel 1 (
    for %%V in (3.13 3.12 3.11 3.10 3.9 3.8 3.7) do (
        if not defined PY_SELECTED (
            py -%%V -c "import sys" >nul 2>&1
            if not errorlevel 1 set "PY_SELECTED=%%V"
        )
    )
)

if defined PY_SELECTED (
    echo Usando Python %PY_SELECTED%.
    py -%PY_SELECTED% "%~dp0..\instalador_dependencias.py" legacy
    goto :FIN
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(not (sys.version_info[0] == 3 and 7 <= sys.version_info[1] <= 13))" >nul 2>&1
    if not errorlevel 1 (
        python "%~dp0..\instalador_dependencias.py" legacy
        goto :FIN
    )
)

echo [ERROR] No se encontro Python 3.7 a 3.13.
echo Instala una version compatible de Python desde python.org y vuelve a intentarlo.
:FIN
echo.
echo Pulsa una tecla para cerrar esta ventana.
pause >nul
endlocal
