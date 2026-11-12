# -*- coding: utf-8 -*-
"""Instalador interactivo para Overlay Teclado v1.0.0 (Windows).

Uso mediante los archivos .cmd de la carpeta script-instalacion.
No se instala nada sin consentimiento explicito.
"""

import io
import os
import subprocess
import sys
from contextlib import redirect_stdout, redirect_stderr


def compatible_python(mode, version=None):
    version = version or sys.version_info
    if mode == '3.14':
        return version.major == 3 and version.minor == 14
    if mode == 'legacy':
        return version.major == 3 and 7 <= version.minor <= 13
    return False


def check_pillow():
    """Comprueba que Pillow se importe y tenga la API requerida por el overlay."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        if not hasattr(Image, 'Resampling') or not hasattr(Image.Resampling, 'LANCZOS'):
            return False, 'Pillow presente, pero demasiado antiguo (falta Image.Resampling)'
        return True, 'Pillow ' + getattr(Image, '__version__', 'instalado')
    except Exception as exc:
        return False, 'Pillow no utilizable: {}'.format(exc)


def check_pygame():
    """El overlay importa pygame, tanto con pygame como con pygame-ce."""
    try:
        # Pygame imprime un mensaje de bienvenida durante el import.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            import pygame
        if not hasattr(pygame, 'joystick') or not hasattr(pygame, 'display'):
            return False, 'pygame incompleto (faltan modulos SDL)'
        return True, 'pygame ' + getattr(getattr(pygame, 'version', None), 'ver', 'instalado')
    except Exception as exc:
        return False, 'pygame no utilizable: {}'.format(exc)


def run_command(command):
    """Ejecucion visible: se muestra la salida de pip en la consola."""
    try:
        return subprocess.run(command, check=False).returncode == 0
    except OSError as exc:
        print('    [ERROR] No fue posible ejecutar el comando: {}'.format(exc))
        return False


def check_windows_stdlib():
    """tkinter y ctypes deben venir en la instalacion de Python para Windows."""
    try:
        import ctypes
        import tkinter
        return True, 'tkinter y ctypes disponibles'
    except Exception as exc:
        return False, str(exc)


def pip_ready():
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return result.returncode == 0
    except OSError:
        return False


def install_missing(display_name, package_name, checker):
    """Comprueba; si falla instala; vuelve a comprobar antes de continuar."""
    print('\nComprobando {}...'.format(display_name))
    ok, description = checker()
    if ok:
        print('  [OK] {}. Se omite la instalacion.'.format(description))
        return True
    print('  [FALTA] {}'.format(description))
    print('  [INSTALAR] {} (instalar o reparar si esta desactualizado)'.format(package_name))
    if not run_command([sys.executable, '-m', 'pip', 'install', '--upgrade', package_name]):
        print('  [ERROR] Fallo la instalacion de {}.'.format(package_name))
        return False
    # Un modulo que se intento importar antes puede quedar en sys.modules; la
    # comprobacion despues de pip se hace en un nuevo proceso Python.
    code = (
        'from PIL import Image, ImageDraw, ImageFont; '
        'assert hasattr(Image, "Resampling")'
        if package_name == 'pillow'
        else 'import pygame; assert hasattr(pygame, "joystick") and hasattr(pygame, "display")'
    )
    if run_command([sys.executable, '-c', code]):
        print('  [OK] {} instalado y verificado.'.format(display_name))
        return True
    print('  [ERROR] Se instalo {}, pero la importacion sigue fallando.'.format(package_name))
    print('  Revisa versiones incompatibles en este interprete de Python.')
    return False


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    print('=' * 64)
    print('INSTALADOR DE DEPENDENCIAS - OVERLAY TECLADO')
    print('=' * 64)
    print('Python activo: {}.{}.{}'.format(*sys.version_info[:3]))
    print('Interprete: {}'.format(sys.executable))
    print('')
    if len(argv) != 1 or argv[0] not in ('3.14', 'legacy'):
        print('[ERROR] Debes iniciar este instalador desde el .cmd apropiado.')
        return 1
    mode = argv[0]
    if os.name != 'nt':
        print('[ERROR] Este instalador esta preparado para Windows.')
        return 1
    if not compatible_python(mode):
        expected = 'Python 3.14' if mode == '3.14' else 'Python 3.7 a 3.13'
        print('[ERROR] Este instalador requiere {}.'.format(expected))
        print('Abre el otro .cmd o instala la version de Python adecuada.')
        return 1

    package_gamepad = 'pygame-ce' if mode == '3.14' else 'pygame'
    print('Se comprobaran las bibliotecas en ESTE Python:')
    print('  - Pillow (graficos)')
    print('  - {} (mandos; ambos se importan como pygame)'.format(package_gamepad))
    print('  - tkinter / ctypes (incluidas en Python para Windows)')
    print('  - pip (herramienta de instalacion que viene con Python)')
    print('')
    print('Solo se descargaran e instalaran bibliotecas que falten o no funcionen.')
    print('No se eliminaran ni actualizaran bibliotecas que ya funcionen.')
    print('Las descargas requieren conexion a Internet; no se necesitan permisos de administrador en condiciones normales.')
    print('')
    try:
        answer = input('¿Autorizas comprobar e instalar automaticamente lo necesario? [S/N]: ').strip().casefold()
    except (KeyboardInterrupt, EOFError):
        print('\nOperacion cancelada. No se instalo nada.')
        return 2
    if answer not in ('s', 'si', 'sí', 'y', 'yes'):
        print('\nNo se otorgo consentimiento. No se instalo nada.')
        return 2

    print('\n[1/4] Comprobando bibliotecas incluidas en Python...')
    std_ok, std_msg = check_windows_stdlib()
    if std_ok:
        print('  [OK] {}'.format(std_msg))
    else:
        print('  [ERROR] Falta alguna biblioteca incluida en Python: {}'.format(std_msg))
        print('  Repara la instalacion de Python e incluye Tcl/Tk (tkinter).')
        return 1

    print('\n[2/4] Comprobando pip...')
    if pip_ready():
        print('  [OK] pip ya esta disponible.')
    else:
        print('  [FALTA] pip. Se intentara activar con ensurepip (incluido en Python).')
        if not run_command([sys.executable, '-m', 'ensurepip', '--upgrade']) or not pip_ready():
            print('  [ERROR] No fue posible habilitar pip. Repara la instalacion de Python.')
            return 1
        print('  [OK] pip habilitado.')

    print('\n[3/4] Biblioteca de graficos')
    pillow_ok = install_missing('Pillow', 'pillow', check_pillow)
    print('\n[4/4] Biblioteca de mandos')
    gamepad_ok = install_missing('pygame', package_gamepad, check_pygame)

    print('\n' + '=' * 64)
    if pillow_ok and gamepad_ok:
        print('[EXITO] Todas las bibliotecas necesarias estan listas.')
        print('Puedes ejecutar overlay_teclado_v1.2.5.pyw con este Python.')
        return 0
    print('[ATENCION] Falta resolver alguna biblioteca.')
    print('Puedes volver a ejecutar este instalador; omitira las que ya funcionen.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
