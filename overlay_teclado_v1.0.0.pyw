"""Overlay de teclado, mouse y mandos para Windows (Python 3.7–3.14).

Instalacion: ejecutar script-instalacion/<tu Python>/INSTALAR.cmd.
Inicio:       py overlay_teclado_v1.0.0.pyw
Ajustes:      icono de bandeja o Ctrl+Alt+O (configurable).

No requiere ejecutar como administrador ni se inicia automaticamente con Windows.
"""

# ================================================================
# OVERLAY TECLADO - VERSION 1.0.0 (publicacion GitHub)
# Requisitos: Windows, Python y las bibliotecas Pillow + pygame/pygame-ce.
# Instalar mediante script-instalacion/Python_3.14/INSTALAR.cmd,
# o script-instalacion/Python_3.13_o_inferior/INSTALAR.cmd.
# El instalador comprueba cada dependencia y solicita consentimiento.
# Ejecutar: py overlay_teclado_v1.0.0.pyw
# ================================================================

VERSION = "1.0.0"

import ctypes
import json
import math
import os
import re
import tempfile
import time
import tkinter as tk
from ctypes import wintypes as wt
from tkinter import messagebox, ttk

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:  # un .pyw no tiene consola
    messagebox.showerror("Overlay Teclado", "Falta Pillow.\nEjecuta:  py -m pip install pillow")
    raise

DEFAULT_SCALE = 1.0
SCALE_OPTIONS = (0.65, 0.80, 1.0, 1.20, 1.40, 1.60)
MIN_SCALE, MAX_SCALE = 0.55, 2.20  # limites del redimensionamiento libre
ALPHA = 0.85
GAMEPAD_ALPHA = 0.62  # Ajustable desde panel (se preserva la opacidad original)
KEYBOARD_ALPHA = 1.0
THEME = "oscuro"
STICK_SENS = 30
SS = 4
OFF, ON, LINE, TEXT_OFF, TEXT_ON = "#1e1e1e", "#f2f2f2", "#8a8a8a", "#f2f2f2", "#111111"
HERE = os.path.dirname(os.path.abspath(__file__))
POS_FILE = os.path.join(HERE, "overlay_pos.txt")
SCALE_FILE = os.path.join(HERE, "overlay_tamano.txt")
MODE_FILE = os.path.join(HERE, "overlay_vista.txt")
UI_FILE = os.path.join(HERE, "overlay_ajustes.json")

VK_F8, VK_LMB, VK_RMB, VK_MMB, VK_X1, VK_X2 = 0x77, 1, 2, 4, 5, 6
VK_TAB, VK_SHIFT, VK_CTRL, VK_ALT = 0x09, 0x10, 0x11, 0x12

# Menu de la bandeja / area de iconos ocultos
WM_TRAY = 0x8000 + 42  # WM_APP + 42
WM_RBUTTONUP, WM_CONTEXTMENU, WM_LBUTTONDBLCLK = 0x0205, 0x007B, 0x0203
NIM_ADD, NIM_DELETE, NIM_SETVERSION = 0, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
CMD_MOVE, CMD_EXIT, CMD_STATUS = 100, 101, 102
CMD_SETTINGS, CMD_HIDE = 103, 104
CMD_SCALES = {200 + i: value for i, value in enumerate(SCALE_OPTIONS)}
CMD_MODES = {300: "auto", 301: "keyboard", 302: "gamepad", 303: "both"}
MODE_LABELS = {"auto": "Automático (último input)", "keyboard": "Teclado y mouse",
               "gamepad": "Solo mando", "both": "Ambos"}


# ---------- Ajustes de interfaz (los 3 archivos .txt existentes se conservan) ----------
THEME_COLORS = {
    "oscuro": {"OFF": "#1e1e1e", "ON": "#f2f2f2", "LINE": "#8a8a8a",
                "TEXT_OFF": "#f2f2f2", "TEXT_ON": "#111111"},
    "claro": {"OFF": "#e8edf3", "ON": "#304960", "LINE": "#60758b",
               "TEXT_OFF": "#223243", "TEXT_ON": "#ffffff"},
    "minimalista": {"OFF": "#292929", "ON": "#dedede", "LINE": "#686868",
                     "TEXT_OFF": "#dddddd", "TEXT_ON": "#191919"},
}
HOTKEY_CHOICES = (
    "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    "Ctrl+Alt+H", "Ctrl+Alt+O", "Ctrl+Alt+M", "Ctrl+Alt+F8",
    "Ctrl+Shift+H", "Ctrl+Shift+O", "Ctrl+Shift+M", "Ctrl+Shift+F8",
)
HOTKEY_DEFAULTS = {"move": "F8", "hide": "Ctrl+Alt+H", "settings": "Ctrl+Alt+O"}
HOTKEYS = dict(HOTKEY_DEFAULTS)


def read_ui_settings():
    global KEYBOARD_ALPHA, GAMEPAD_ALPHA, THEME, HOTKEYS
    try:
        with open(UI_FILE, encoding="utf-8") as file:
            saved = json.load(file)
        if not isinstance(saved, dict):
            return
        kb = float(saved.get("teclado", 1.0))
        gp = float(saved.get("mando", 0.62))
        if math.isfinite(kb):
            KEYBOARD_ALPHA = max(0.2, min(1.0, kb))
        if math.isfinite(gp):
            GAMEPAD_ALPHA = max(0.15, min(1.0, gp))
        theme = saved.get("tema", "oscuro")
        if theme in THEME_COLORS:
            THEME = theme
        keys = saved.get("atajos", {})
        if isinstance(keys, dict):
            choices = {name: keys.get(name, default)
                       for name, default in HOTKEY_DEFAULTS.items()}
            if all(value in HOTKEY_CHOICES for value in choices.values()) and len(set(choices.values())) == 3:
                HOTKEYS.update(choices)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass


def save_ui_settings():
    payload = {"teclado": KEYBOARD_ALPHA, "mando": GAMEPAD_ALPHA,
               "tema": THEME, "atajos": dict(HOTKEYS)}
    tmp = UI_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        os.replace(tmp, UI_FILE)
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def update_theme_colors():
    global OFF, ON, LINE, TEXT_OFF, TEXT_ON
    p = THEME_COLORS[THEME]
    OFF, ON, LINE, TEXT_OFF, TEXT_ON = (p[k] for k in ("OFF", "ON", "LINE", "TEXT_OFF", "TEXT_ON"))


read_ui_settings()
update_theme_colors()

# ---------- Instancia unica ----------
# Mantiene un mutex nombrado abierto mientras el overlay corre.
# Si se intenta abrir una segunda vez, esta sale de inmediato.
SINGLE_INSTANCE_NAME = r"Local\OverlayTeclado_v1_2"
_single_instance_handle = None

def ensure_single_instance():
    global _single_instance_handle
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
    kernel32.CreateMutexW.restype = wt.HANDLE
    kernel32.ReleaseMutex.argtypes = [wt.HANDLE]
    kernel32.ReleaseMutex.restype = wt.BOOL
    kernel32.CloseHandle.argtypes = [wt.HANDLE]
    kernel32.CloseHandle.restype = wt.BOOL

    handle = kernel32.CreateMutexW(None, True, SINGLE_INSTANCE_NAME)
    if not handle:
        return
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        # Ya hay un overlay corriendo; cerramos esta segunda apertura.
        try:
            kernel32.CloseHandle(handle)
        except Exception:
            pass
        try:
            messagebox.showinfo("Overlay Teclado", "Ya hay una instancia del overlay en ejecución.")
        except Exception:
            pass
        raise SystemExit
    _single_instance_handle = (kernel32, handle)


def release_single_instance():
    global _single_instance_handle
    if not _single_instance_handle:
        return
    kernel32, handle = _single_instance_handle
    try:
        kernel32.ReleaseMutex(handle)
    except Exception:
        pass
    try:
        kernel32.CloseHandle(handle)
    except Exception:
        pass
    _single_instance_handle = None


ensure_single_instance()

# ---------- Recursos SVG rasterizados y embebidos para Windows (sin dependencias extra) ----------
# Originales: xbox.svg, ps4.svg, ps5.svg. Los assets se rasterizaron al generar este .pyw.
# Se cachean al cambiar de tamaño; no se ejecuta ningun blur dentro del tick.
SKIN_META = {
    "xbox": {"w": 7.7, "h": 4.66, "ox": 0.18, "oy": 0.18, "bounds": (0.0, 5.0, 383.8889, 264.4444)},
    "ps4": {"w": 7.5, "h": 4.63, "ox": 0.28, "oy": 0.19, "bounds": (110.0, 41.1111, 718.8889, 419.4444)},
    "ps5": {"w": 7.52, "h": 4.68, "ox": 0.26, "oy": 0.15, "bounds": (8.8889, 5.5556, 523.8889, 347.7778)},
}
# Recursos visuales externos extraidos sin recodificacion del Base64 de v1.2.4.
# Mantener este archivo .pyw y la carpeta assets/ juntos.
ASSETS_DIR = os.path.join(HERE, "assets")
GAMEPAD_ASSET_FILES = {
    family: {layer: os.path.join(ASSETS_DIR, f"{family}_{layer}.png")
             for layer in ("body", "ink")}
    for family in ("xbox", "ps4", "ps5")
}

_SKIN_CACHE = {}

def apply_image_alpha(im, factor):
    """Escala el canal alpha de una imagen sin alterar sus colores."""
    if factor >= 0.999:
        return im
    out = im.copy()
    alpha = out.getchannel("A").point(lambda v: max(0, min(255, int(v * factor))))
    out.putalpha(alpha)
    return out

def rgba_alpha(color, factor=None):
    """Aplica opacidad uniforme a un color RGB/RGBA del overlay de mando."""
    if factor is None:
        factor = GAMEPAD_ALPHA
    if len(color) == 4:
        return (color[0], color[1], color[2], max(0, min(255, round(color[3] * factor))))
    return (color[0], color[1], color[2], max(0, min(255, round(255 * factor))))

def get_skin(family, unit):
    """Dos capas estaticas (cuerpo y detalles); los controles se dibujan entre ambas."""
    key = (family, unit, THEME, GAMEPAD_ALPHA)
    if key in _SKIN_CACHE:
        return _SKIN_CACHE[key]
    if len(_SKIN_CACHE) >= 9:
        _SKIN_CACHE.clear()  # evita memoria acumulada al redimensionar muchas veces
    meta = SKIN_META[family]
    dim = (max(1, round(meta["w"]*unit)), max(1, round(meta["h"]*unit)))
    layers = []
    for kind in ("body", "ink"):
        # Lee desde assets/ solo al iniciar o modificar el tamano (cache por familia/unit).
        # Si falta un archivo, muestra una advertencia clara en lugar de fallar silenciosamente en .pyw.
        path = GAMEPAD_ASSET_FILES[family][kind]
        try:
            with Image.open(path) as img:
                resized = img.convert("RGBA").resize(dim, Image.Resampling.LANCZOS)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Overlay Teclado - recursos faltantes",
                                 f"No se pudo cargar: {path}\n\n"
                                 "Extrae el ZIP completo conservando la carpeta assets/.\n\n"
                                 f"Detalle: {exc}")
            raise
        if THEME != "oscuro":
            alpha_channel = resized.getchannel("A")
            grey = ImageOps.grayscale(resized)
            if THEME == "claro":
                dark, light = ((120, 139, 157), (230, 239, 248)) if kind == "body" else ((29, 49, 68), (99, 125, 147))
            else:
                dark, light = ((38, 38, 38), (141, 141, 141)) if kind == "body" else ((136, 136, 136), (224, 224, 224))
            resized = ImageOps.colorize(grey, dark, light).convert("RGBA")
            resized.putalpha(alpha_channel)
        layers.append(apply_image_alpha(resized, GAMEPAD_ALPHA))
    layers = tuple(layers)
    _SKIN_CACHE[key] = layers
    return layers


def load_scale():
    try:
        with open(SCALE_FILE, encoding="utf-8") as f:
            value = float(f.read().strip())
        if math.isfinite(value) and MIN_SCALE <= value <= MAX_SCALE:
            return value
    except (OSError, ValueError):
        pass
    return DEFAULT_SCALE


SCALE = load_scale()


def load_mode():
    try:
        with open(MODE_FILE, encoding="utf-8") as f:
            value = f.read().strip()
        return value if value in MODE_LABELS else "auto"
    except OSError:
        return "auto"


MODE = load_mode()

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ctypes.windll.shcore.SetProcessDpiAwareness(1)


# ---------- Windows: tipos ----------
class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wt.USHORT), ("usUsage", wt.USHORT),
                ("dwFlags", wt.DWORD), ("hwndTarget", wt.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wt.DWORD), ("dwSize", wt.DWORD),
                ("hDevice", wt.HANDLE), ("wParam", wt.WPARAM)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wt.USHORT), ("ulButtons", wt.ULONG), ("ulRawButtons", wt.ULONG),
                ("lLastX", wt.LONG), ("lLastY", wt.LONG), ("ulExtraInformation", wt.ULONG)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON),
                ("szTip", wt.WCHAR * 128), ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
                ("szInfo", wt.WCHAR * 256), ("uTimeoutOrVersion", wt.UINT),
                ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wt.HICON)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
user32.GetParent.argtypes, user32.GetParent.restype = [wt.HWND], wt.HWND
user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_void_p]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.GetRawInputData.argtypes = [ctypes.c_void_p, wt.UINT, ctypes.c_void_p,
                                   ctypes.POINTER(wt.UINT), wt.UINT]
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wt.UINT, wt.UINT]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, wt.LONG]
user32.GetDC.argtypes, user32.GetDC.restype = [wt.HWND], ctypes.c_void_p
user32.ReleaseDC.argtypes = [wt.HWND, ctypes.c_void_p]
user32.UpdateLayeredWindow.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.c_void_p, ctypes.c_void_p, wt.DWORD,
                                       ctypes.c_void_p, wt.DWORD]
user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.LoadImageW.restype = wt.HICON
user32.DestroyIcon.argtypes = [wt.HICON]
user32.CreatePopupMenu.restype = wt.HMENU
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, wt.WPARAM, wt.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wt.HWND, ctypes.c_void_p]
user32.TrackPopupMenu.restype = wt.UINT
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.RegisterWindowMessageW.argtypes = [wt.LPCWSTR]
user32.RegisterWindowMessageW.restype = wt.UINT
shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wt.BOOL
gdi32.CreateCompatibleDC.argtypes, gdi32.CreateCompatibleDC.restype = [ctypes.c_void_p], ctypes.c_void_p
gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wt.DWORD]
gdi32.CreateDIBSection.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]

st = {"move": False, "f8": False, "ax": 0, "ay": 0, "sx": 0.0, "sy": 0.0,
      "n": 0, "drawn": None, "wd": 0, "wt": 0, "closing": False,
      "resizing": False, "cursor": None,
      "active_input": "keyboard",  # vista inicial, incluso si hay mando conectado
      "held_inputs": set(), "prev_pad": None,
      "wheel_events": 0, "wheel_seen": 0, "mouse_button_events": 0,
      "mouse_button_seen": 0, "mouse_motion_samples": [],
      "last_pad_state": None, "pad_missing_since": None,
      "hidden": False, "hotkeys_pressed": set()}

# Deteccion global: solo teclas normales de teclado (no todos los VK de Windows,
# que incluyen entradas virtuales ajenas al teclado y pueden provocar falsos cambios).
# Se mantienen alfanumericas, funciones, modificadoras, navegacion y puntuacion.
# F8 se excluye porque controla la ventana, no el cambio de dispositivo.
KEY_INPUTS = tuple(vk for vk in (
    0x08, 0x09, 0x0D, 0x10, 0x11, 0x12, 0x13, 0x14, 0x1B, 0x20,
    *range(0x21, 0x29), 0x2C, 0x2D, 0x2E,
    *range(0x30, 0x3A), *range(0x41, 0x5B),
    0x5B, 0x5C, *range(0x60, 0x70), *range(0x70, 0x88),
    0x90, 0x91, *range(0xA0, 0xA6), *range(0xBA, 0xC1),
    *range(0xDB, 0xE0), 0xE2,
) if vk != VK_F8)
MOUSE_INPUTS = (VK_LMB, VK_RMB, VK_MMB, VK_X1, VK_X2)
ALL_INPUTS = KEY_INPUTS + MOUSE_INPUTS
# Un delta aislado de 4 puntos ya no cambia de mando a mouse: se requiere
# movimiento acumulado y repetido dentro de una ventana corta.
MOUSE_MOTION_MIN_SAMPLE = 1.5
MOUSE_MOTION_CONFIRM = 18.0
MOUSE_MOTION_WINDOW = 0.25     # segundos
PAD_DISCONNECT_GRACE = 1.0    # segundos: tolerar cortes breves de SDL/Bluetooth
STICK_ACTIVE_DEADZONE = 0.22
STICK_CHANGE_THRESHOLD = 0.15
TRIGGER_ACTIVE_THRESHOLD = 0.22
TRIGGER_CHANGE_THRESHOLD = 0.14


# ---------- Ventana ----------
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)


# ---------- Mando: SDL2 normaliza el orden de los botones entre marcas ----------
# La interfaz SDL_GAMECONTROLLER puede cubrir Xbox, PS4, PS5, 8BitDo, GameSir...
# Un mando sin mapa SDL se intenta leer como joystick generico (orden aproximado).
class GamepadReader:
    # Codigos SDL2 estables (evita diferencias en exportaciones de pygame).
    BUTTONS = {"a": 0, "b": 1, "x": 2, "y": 3, "back": 4,
               "guide": 5, "start": 6, "l3": 7, "r3": 8,
               "lb": 9, "rb": 10, "up": 11, "down": 12,
               "left": 13, "right": 14}

    def __init__(self):
        self.pg = None
        self.ctl_api = None
        self.dev = None
        self.js = None
        self.mapped = False
        self.name = ""
        self.guid = ""
        self.error = ""
        # SDL2 requiere esta opcion para captar inputs fuera del foco.
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        try:
            import pygame
            self.pg = pygame
            pygame.display.init()
            pygame.display.set_mode((1, 1), pygame.HIDDEN)
            pygame.joystick.init()
            try:
                import pygame._sdl2.controller as controller
                self.ctl_api = controller
                controller.init()
            except (ImportError, pygame.error):
                self.ctl_api = None
            self.scan()
        except ImportError:
            self.error = "Para detectar mandos instala pygame-ce: py -m pip install pygame-ce"
            self.pg = None
        except Exception as exc:
            self.error = f"No se pudo iniciar SDL2: {exc}"
            self.shutdown()
            self.pg = None

    @property
    def connected(self):
        return self.dev is not None

    def _attached(self):
        try:
            if self.mapped:
                return bool(self.dev.attached())
            return bool(self.dev.get_attached())
        except (AttributeError, self.pg.error if self.pg else Exception):
            return False

    def _close_device(self):
        if self.dev is not None:
            try:
                self.dev.quit()
            except Exception:
                pass
        if self.js is not None and self.js is not self.dev:
            try:
                self.js.quit()
            except Exception:
                pass
        self.dev = None
        self.js = None
        self.mapped = False
        self.name = ""
        self.guid = ""

    def scan(self):
        if not self.pg:
            return
        if self.dev is not None and self._attached():
            return
        self._close_device()
        try:
            count = self.pg.joystick.get_count()
            # Prioriza mandos con mapeo SDL, evitando interpretar mal PS/8BitDo.
            indices = list(range(count))
            if self.ctl_api:
                indices.sort(key=lambda n: not self.ctl_api.is_controller(n))
            for i in indices:
                js = None
                try:
                    js = self.pg.joystick.Joystick(i)
                    js.init()
                    name = js.get_name() or "Mando sin nombre"
                    mapped = bool(self.ctl_api and self.ctl_api.is_controller(i))
                    dev = self.ctl_api.Controller(i) if mapped else js
                    self.dev, self.js, self.mapped = dev, js, mapped
                    self.name = name
                    # Identificador SDL (si el driver lo proporciona).
                    # Permite reconocer Sony aunque Windows lo llame "Wireless Controller".
                    try:
                        self.guid = js.get_guid() if hasattr(js, "get_guid") else ""
                    except Exception:
                        self.guid = ""  # el GUID es opcional, no perder la conexion
                    return
                except Exception:
                    if js:
                        try:
                            js.quit()
                        except Exception:
                            pass
        except Exception as exc:
            self.error = f"Error buscando controles: {exc}"

    def poll(self, frame):
        if not self.pg:
            return None
        try:
            # Bombea y vacia eventos sin crear otra ventana visible.
            self.pg.event.get()
            # Reintentar pronto tras una lectura fallida, sin consultar el USB
            # continuamente cuando el control ya esta conectado.
            if (self.dev is None and frame % 8 == 0 or
                    self.dev is not None and (frame % 55 == 0 or not self._attached())):
                self.scan()
            if self.dev is None:
                return None
            if self.mapped:
                b = {name: bool(self.dev.get_button(index))
                     for name, index in self.BUTTONS.items()}
                axes = [self.dev.get_axis(i) / 32767.0 for i in range(4)]
                lt = self.dev.get_axis(4) / 32767.0
                rt = self.dev.get_axis(5) / 32767.0
            else:
                # Fallback de HID no estandar: el orden puede depender del firmware.
                js = self.dev
                def btn(i):
                    return bool(js.get_button(i)) if i < js.get_numbuttons() else False
                def axis(i):
                    return float(js.get_axis(i)) if i < js.get_numaxes() else 0.0
                hat = js.get_hat(0) if js.get_numhats() else (0, 0)
                b = {"a": btn(0), "b": btn(1), "x": btn(2), "y": btn(3),
                     "lb": btn(4), "rb": btn(5), "back": btn(6),
                     "start": btn(7), "guide": btn(10), "l3": btn(8), "r3": btn(9),
                     "up": hat[1] > 0, "down": hat[1] < 0,
                     "left": hat[0] < 0, "right": hat[0] > 0}
                axes = [axis(i) for i in range(4)]
                lt = max(0.0, axis(4)) if js.get_numaxes() > 4 else float(btn(6))
                rt = max(0.0, axis(5)) if js.get_numaxes() > 5 else float(btn(7))
            def limit(v):
                return max(-1.0, min(1.0, v))
            axes = tuple(round(limit(v), 2) for v in axes)
            # Deadzone de stick: evita ruido y redibujados innecesarios.
            axes = tuple(0.0 if abs(v) < 0.08 else v for v in axes)
            return {"buttons": b, "axes": axes,
                    "lt": round(max(0.0, min(1.0, lt)), 2),
                    "rt": round(max(0.0, min(1.0, rt)), 2),
                    "name": self.name, "mapped": self.mapped, "guid": self.guid}
        except Exception:
            self._close_device()
            return None

    def info(self):
        if not self.pg:
            return self.error or "pygame no esta disponible."
        if not self.connected:
            return "No hay mando conectado. Conecta uno por USB o Bluetooth."
        note = "Mapeo SDL2 estandar" if self.mapped else "Joystick generico: mapeo aproximado"
        layout = detect_gamepad_family(self.name, self.guid).upper()
        return f"{self.name}\nLayout: {layout}\n{note}\nUSB o Bluetooth segun configuracion Windows."

    def shutdown(self):
        self._close_device()
        if self.pg:
            try:
                if self.ctl_api:
                    self.ctl_api.quit()
                self.pg.joystick.quit()
                self.pg.display.quit()
            except Exception:
                pass


gamepad = GamepadReader()
st["pad_connected"] = gamepad.connected


def visible_sections():
    if MODE == "keyboard":
        return True, False
    if MODE == "gamepad":
        return False, True
    if MODE == "both":
        return True, True
    # En automático solo se dibuja el dispositivo usado más recientemente.
    if st["active_input"] == "gamepad" and gamepad.connected:
        return False, True
    return True, False


def gamepad_has_new_activity(state, previous):
    """Detecta botones nuevos o movimiento real; ignora ruido analógico leve.

    Compara con la muestra anterior y no con cero: un stick o gatillo mantenido
    no gana continuamente prioridad frente a un teclado que empieza a usarse.
    """
    if state is None:
        return False
    buttons = state["buttons"]
    old_buttons = previous["buttons"] if previous else {}
    if any(down and not old_buttons.get(name, False)
           for name, down in buttons.items()):
        return True
    # El primer sondeo establece una línea base para ejes de mandos genéricos
    # con centros no estándar, evitando activaciones falsas al conectarlos.
    if previous is None:
        return False
    axes = state["axes"]
    old_axes = previous["axes"]
    for i in (0, 2):  # sticks izquierdo y derecho
        current_mag = math.hypot(axes[i], axes[i + 1])
        movement = math.hypot(axes[i] - old_axes[i], axes[i + 1] - old_axes[i + 1])
        if current_mag >= STICK_ACTIVE_DEADZONE and movement >= STICK_CHANGE_THRESHOLD:
            return True
    for name in ("lt", "rt"):
        value, old_value = state[name], previous[name]
        if (value >= TRIGGER_ACTIVE_THRESHOLD and
                abs(value - old_value) >= TRIGGER_CHANGE_THRESHOLD):
            return True
    return False


def stabilize_gamepad_frame(pad_state):
    """Conserva el ultimo frame valido ante cortes breves de SDL/Bluetooth.

    El mando se considera ausente tras PAD_DISCONNECT_GRACE segundos seguidos
    sin lectura. No crea nuevos eventos de pulsacion durante ese intervalo.
    """
    if pad_state is not None:
        st["last_pad_state"] = pad_state
        st["pad_missing_since"] = None
        return pad_state

    last = st["last_pad_state"]
    if last is None:
        return None
    now = time.monotonic()
    if st["pad_missing_since"] is None:
        st["pad_missing_since"] = now
    if now - st["pad_missing_since"] < PAD_DISCONNECT_GRACE:
        return last
    st["last_pad_state"] = None
    st["pad_missing_since"] = None
    return None


def detect_active_input(pad_state, mouse_dx, mouse_dy):
    """Devuelve 'keyboard', 'gamepad' o None a partir de entradas nuevas.

    Lee todas las teclas aunque la vista de teclado esté oculta. Las ruedas
    se detectan por eventos nuevos y el mouse por movimiento acumulado.
    """
    held = {vk for vk in ALL_INPUTS
            if user32.GetAsyncKeyState(vk) & 0x8000}
    just_pressed = held - st["held_inputs"]
    st["held_inputs"] = held

    new_keyboard_key = any(vk in just_pressed for vk in KEY_INPUTS)
    new_mouse_button = any(vk in just_pressed for vk in MOUSE_INPUTS)
    wheel = st["wheel_events"] != st["wheel_seen"]
    st["wheel_seen"] = st["wheel_events"]
    raw_mouse_button = st["mouse_button_events"] != st["mouse_button_seen"]
    st["mouse_button_seen"] = st["mouse_button_events"]
    # El Raw Input puede registrar minimas variaciones/ruido mientras se juega
    # con mando. Exigir movimiento repetido evita cambiar de vista por un
    # unico delta pequeno; sigue detectando cuando realmente mueves el mouse.
    now = time.monotonic()
    samples = st["mouse_motion_samples"]
    samples[:] = [(t, distance) for t, distance in samples
                  if now - t <= MOUSE_MOTION_WINDOW]
    distance = math.hypot(mouse_dx, mouse_dy)
    if distance >= MOUSE_MOTION_MIN_SAMPLE:
        samples.append((now, distance))
    mouse_moved = (len(samples) >= 2 and
                   sum(distance for _, distance in samples) >= MOUSE_MOTION_CONFIRM)
    if mouse_moved:
        samples.clear()

    pad_activity = gamepad_has_new_activity(pad_state, st["prev_pad"])
    st["prev_pad"] = pad_state
    # Si un programa mapea el mando también a teclas/mouse, priorizamos
    # el evento SDL del mando cuando aparecen ambos en el mismo fotograma.
    if pad_activity:
        return "gamepad"
    if new_keyboard_key or new_mouse_button or raw_mouse_button or wheel or mouse_moved:
        return "keyboard"
    return None


def sprite(w, h, r, fill, label="", color=None, outline="theme"):
    """Rectangulo redondeado antialiasing: se dibuja a 4x y se reduce."""
    w, h = round(w), round(h)
    im = Image.new("RGBA", (w * SS, h * SS))
    d = ImageDraw.Draw(im)
    if outline == "theme":
        outline = LINE
    d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, fill=fill,
                        outline=outline, width=LW * SS if outline else 0)
    if label:
        d.text((w * SS / 2, h * SS / 2), label, fill=color, font=FONT, anchor="mm")
    return im.resize((w, h), Image.LANCZOS)


items = {}  # vk -> [x, y, sprite suelto, sprite pulsado, pulsado]


def add(vk, x, y, w, h, r, label=""):
    items[vk] = [round(x), round(y), sprite(w, h, r, OFF, label, TEXT_OFF),
                 sprite(w, h, r, ON, label, TEXT_ON), False]


def key(label, vk, col, row, w=1.0):
    add(vk, PAD + col * U, PAD + row * U, w * U - G, U - G, U // 5, label)


def build_layout(scale):
    """Reconstruye sprites al cambiar tamaño, sin reiniciar la captura de entradas."""
    global SCALE, U, G, PAD, LW, W, H, FONT, HINT_FONT
    global mx, my, WHEEL_X, WHEEL_Y, WHEEL_HALF, wheel_half
    global SX, SY, SR, KR, knob, base, base_move, GRIP_X, GRIP_Y, GRIP_SIZE, grip_sprite
    global KEYBOARD_VISIBLE, GAMEPAD_VISIBLE, PANEL_X, PAD_FONT, PAD_SMALL_FONT, PAD_SYMBOL_FONT

    SCALE = scale
    U = round(40 * SCALE * root.winfo_fpixels("1i") / 96)
    G, PAD, LW = max(2, U // 10), U // 4, max(1, U // 24)
    KEYBOARD_VISIBLE, GAMEPAD_VISIBLE = visible_sections()
    kb_w = PAD * 2 + round(9.1 * U) if KEYBOARD_VISIBLE else 0
    PANEL_X = kb_w + (round(0.12 * U) if KEYBOARD_VISIBLE else PAD)
    W = PANEL_X + round(8.25 * U) + PAD if GAMEPAD_VISIBLE else kb_w
    H = PAD * 2 + 5 * U
    FONT = ImageFont.truetype("segoeuib.ttf", max(1, round(U * 0.3)) * SS)
    HINT_FONT = ImageFont.truetype("segoeui.ttf", max(9, round(U * 0.26)))
    PAD_FONT = ImageFont.truetype("segoeuib.ttf", max(9, round(U * 0.29)))
    PAD_SMALL_FONT = ImageFont.truetype("segoeui.ttf", max(8, round(U * 0.22)))
    PAD_SYMBOL_FONT = ImageFont.truetype("seguisym.ttf", max(11, round(U * 0.40)))

    items.clear()
    base = Image.new("RGBA", (W, H))
    if KEYBOARD_VISIBLE:
        for i in range(5):
            key(str(i + 1), ord("1") + i, 1.5 + i, 0)
        key("TAB", VK_TAB, 0, 1, 1.4)
        for i, c in enumerate("QWE"):
            key(c, ord(c), 1.5 + i, 1)
        for i, c in enumerate("ASDF"):
            key(c, ord(c), 1.5 + i, 2)
        key("SHIFT", VK_SHIFT, 0, 3, 1.9)
        for i, c in enumerate("ZXC"):
            key(c, ord(c), 2 + i, 3)
        key("CTRL", VK_CTRL, 0, 4, 1.4)
        key("ALT", VK_ALT, 1.5, 4, 1.4)
        key("", 0x20, 3, 4, 3.5)

        mx, my = PAD + 7.1 * U, PAD
        add(VK_LMB, mx, my, U - G / 2, 1.3 * U - G, U // 3)
        add(VK_RMB, mx + U + G / 2, my, U - G / 2, 1.3 * U - G, U // 3)
        add(VK_MMB, mx + 0.82 * U, my + 0.25 * U, 0.36 * U, 0.7 * U, U // 8)
        WHEEL_X, WHEEL_Y, WHEEL_HALF = items[VK_MMB][0], items[VK_MMB][1], round(0.7 * U) // 2
        wheel_half = sprite(0.36 * U, WHEEL_HALF, U // 8, ON)
        add(VK_X2, mx - 0.35 * U, my + 1.4 * U, 0.35 * U - G / 2, 0.55 * U, U // 10)
        add(VK_X1, mx - 0.35 * U, my + 2.05 * U, 0.35 * U - G / 2, 0.55 * U, U // 10)

        SX, SY, SR, KR = mx + U, PAD + 4 * U, 0.92 * U, 0.3 * U
        knob = sprite(KR * 2, KR * 2, KR, ON, outline=None)

        base.alpha_composite(sprite(2 * U, 1.6 * U, U // 2, OFF), (round(mx), round(my + 1.3 * U)))
        base.alpha_composite(sprite(SR * 2, SR * 2, SR, OFF), (round(SX - SR), round(SY - SR)))
    else:
        wheel_half = None
        WHEEL_X = WHEEL_Y = WHEEL_HALF = 0
        SX = SY = KR = SR = 0
        knob = None

    # Teclado: la transparencia se precalcula sobre sprites, no por fotograma.
    if KEYBOARD_VISIBLE and KEYBOARD_ALPHA < 0.999:
        base = apply_image_alpha(base, KEYBOARD_ALPHA)
        for it in items.values():
            it[2] = apply_image_alpha(it[2], KEYBOARD_ALPHA)
            it[3] = apply_image_alpha(it[3], KEYBOARD_ALPHA)
        wheel_half = apply_image_alpha(wheel_half, KEYBOARD_ALPHA)
        knob = apply_image_alpha(knob, KEYBOARD_ALPHA)

    base_move = sprite(W, H, U // 3, "#333333")
    base_move.alpha_composite(base)
    # Zona de redimensionamiento: se muestra solo en modo mover.
    # Dibujarla al final del frame evita que el stick la tape.
    GRIP_SIZE = max(19, round(U * 0.65))
    GRIP_X, GRIP_Y = W - GRIP_SIZE - 2, H - GRIP_SIZE - 2
    grip_sprite = Image.new("RGBA", (GRIP_SIZE, GRIP_SIZE), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grip_sprite)
    gd.rounded_rectangle((0, 0, GRIP_SIZE - 1, GRIP_SIZE - 1),
                         radius=max(4, GRIP_SIZE // 5), fill=(60, 60, 60, 230),
                         outline=(245, 245, 245, 230), width=1)
    for inset in (5, 9, 13):
        if GRIP_SIZE - inset - 3 > 3:
            gd.line((GRIP_SIZE - inset - 4, GRIP_SIZE - 4,
                     GRIP_SIZE - 4, GRIP_SIZE - inset - 4),
                    fill=(245, 245, 245, 255), width=2)
    ImageDraw.Draw(base_move).text((PAD, H - max(3, PAD // 2)),
                                   f"{HOTKEYS['move']}: fijar | ↘ tamaño | der.: cerrar",
                                   fill=ON, font=HINT_FONT, anchor="ls")
    st["drawn"] = None


build_layout(SCALE)
try:
    with open(POS_FILE, encoding="utf-8") as f:
        pos = f.read().strip()
    root.geometry(f"{W}x{H}{pos if pos.startswith('+') else '+60+60'}")
except OSError:
    root.geometry(f"{W}x{H}+60+60")
root.update()

hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()


# ---------- Captura de Raw Input / mensajes de la bandeja ----------
def wndproc(window, msg, wparam, lparam):
    if msg == WM_TRAY:
        event = lparam & 0xFFFF
        if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
            show_tray_menu()
        elif event == WM_LBUTTONDBLCLK:
            root.after_idle(toggle_move)
        return 0
    if msg == TASKBAR_CREATED and not st["closing"]:
        add_tray_icon()  # recrear tras reiniciar Explorer
    if msg == 0x00FF:  # WM_INPUT
        raw, size = RAWINPUT(), wt.UINT(ctypes.sizeof(RAWINPUT))
        got = user32.GetRawInputData(lparam, 0x10000003, ctypes.byref(raw),
                                     ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        if got != 0xFFFFFFFF and raw.header.dwType == 0 and not raw.mouse.usFlags & 1:
            st["ax"] += raw.mouse.lLastX
            st["ay"] += raw.mouse.lLastY
        if got != 0xFFFFFFFF and raw.header.dwType == 0:
            if raw.mouse.ulButtons & 0x0400:
                st["wd"] = 1 if ctypes.c_short(raw.mouse.ulButtons >> 16).value > 0 else -1
                st["wt"] = 8
                st["wheel_events"] += 1
            # RI_MOUSE_*_BUTTON_DOWN: captura también clics muy breves.
            if raw.mouse.ulButtons & 0x0155:
                st["mouse_button_events"] += 1
    return user32.CallWindowProcW(old_proc, window, msg, wparam, lparam)


TASKBAR_CREATED = user32.RegisterWindowMessageW("TaskbarCreated")
new_proc = WNDPROC(wndproc)  # mantener referencia para evitar liberacion del callback
old_proc = user32.SetWindowLongPtrW(hwnd, -4, ctypes.cast(new_proc, ctypes.c_void_p))
rid = RAWINPUTDEVICE(1, 2, 0x100, hwnd)  # RIDEV_INPUTSINK: tambien sin foco
user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(rid))


# ---------- Buffer GDI: se actualiza al modificar el tamaño ----------
screen_dc = user32.GetDC(None)
mem_dc = gdi32.CreateCompatibleDC(screen_dc)
bitmap = None
original_bitmap = None
bits = ctypes.c_void_p()
win_size, src_pos = wt.SIZE(W, H), wt.POINT(0, 0)
blend = (ctypes.c_ubyte * 4)(0, 0, round(ALPHA * 255), 1)


def allocate_buffer():
    global bitmap, original_bitmap, bits, win_size
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
    new_bits = ctypes.c_void_p()
    new_bitmap = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0,
                                        ctypes.byref(new_bits), None, 0)
    if not new_bitmap or not new_bits:
        raise OSError("No se pudo reservar la imagen del overlay")
    previous = gdi32.SelectObject(mem_dc, new_bitmap)
    if bitmap:
        gdi32.DeleteObject(bitmap)
    else:
        original_bitmap = previous
    bitmap, bits = new_bitmap, new_bits
    win_size = wt.SIZE(W, H)


allocate_buffer()


def detect_gamepad_family(name, guid=""):
    """Elige el layout fisico del mando, no solo su forma de conectarse.

    Importante: "Wireless Controller" NO significa PlayStation.
    Por ejemplo, "8BitDo Ultimate 2 Wireless Controller for PC" debe
    usar botones ABXY y la silueta Xbox, nunca los simbolos de PS.
    """
    low = (name or "").casefold()

    # 1. Marcas alternativas con layout Xbox: PRIORIDAD sobre palabras
    #    genericas como "wireless", "controller" o "gamepad".
    if any(tag in low for tag in (
            "8bitdo", "8bit do", "gamesir", "game sir", "xbox",
            "xinput", "microsoft", "powera", "gulikit", "turtle beach")):
        return "xbox"

    # 2. Nombres explicitos de controles PlayStation.
    if any(tag in low for tag in (
            "dualsense", "ps5", "playstation 5", "playstation(r)5")):
        return "ps5"
    if any(tag in low for tag in (
            "dualshock", "ps4", "playstation 4", "playstation(r)4")):
        return "ps4"

    # 3. SDL GUID: en mandos USB/Bluetooth el VID Sony es 0x054C.
    #    SDL lo escribe en little-endian (4c05). La parte del producto
    #    diferencia PS5 en los modelos conocidos; si no, usar PS4.
    clean_guid = (guid or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{32}", clean_guid):
        vid = int.from_bytes(bytes.fromhex(clean_guid[8:12]), "little")
        pid = int.from_bytes(bytes.fromhex(clean_guid[16:20]), "little")
        if vid == 0x054C:
            return "ps5" if pid in (0x0CE6, 0x0DF2) else "ps4"

    # Sony identificado por su propio nombre, aun sin un GUID utilizable.
    if "sony" in low:
        return "ps4"

    # 4. En nombres ambiguos ("Wireless Controller") preferir el layout
    #    comun ABXY; clasificar como PS4 sin pruebas fue el bug anterior.
    return "xbox"


# Coordenadas tomadas de los dibujos SVG originales (no del panel anterior).
# Se mantienen incluso al variar la escala: todos los elementos son proporcionales.
CONTROL_LAYOUT = {
    "xbox": {
        "left": (88,70), "right": (244,131),
        "dpad": {"up": (137,115), "down": (137,156), "left": (116,135), "right": (157,135)},
        "face": {"a":(294,97), "b":(320,71), "x":(267,71), "y":(294,44)},
        "back":(162,66), "start":(219,66), "guide":(191,30),
        "left_trigger":(62,16), "right_trigger":(320,16),
    },
    "ps4": {
        "left": (317,237), "right":(510,237),
        "dpad": {"up":(228,123), "down":(226,181), "left":(198,151), "right":(256,153)},
        "face": {"a":(601,196),"b":(644,152),"x":(557,153),"y":(600,108)},
        "back":(292,92),"start":(535,92),"guide":(414,205),
        "left_trigger":(223,53), "right_trigger":(605,53),
    },
    "ps5": {
        "left": (184,175), "right":(349,175),
        "dpad": {"up":(107,79), "down":(107,128), "left":(82,104), "right":(131,104)},
        "face": {"a":(427,142),"b":(464,104),"x":(389,104),"y":(427,66)},
        "back":(146,48), "start":(387,48),"guide":(266,202),
        "left_trigger":(105,18), "right_trigger":(426,18),
    },
}
CONTROL_SIZES = {"xbox": (384,265), "ps4": (829,436), "ps5": (530,353)}
COLOR_BUTTONS = {"a": (129,199,54,255), "b":(243,83,76,255),
                 "x":(72,174,241,255), "y":(247,197,65,255)}


def draw_gamepad(im, state):
    """Silueta fiel y reactiva; CPU minima: capas del SVG en cache, sin desenfoques por frame."""
    if not GAMEPAD_VISIBLE:
        return
    family = detect_gamepad_family(state["name"], state.get("guid", "")) if state else "xbox"
    if family not in CONTROL_LAYOUT:
        family = "xbox"
    meta = SKIN_META[family]
    body, details = get_skin(family, U)
    ox = round(PANEL_X + meta["ox"]*U)
    oy = round(PAD + meta["oy"]*U)
    width, height = body.size
    im.alpha_composite(body,(ox,oy))
    d = ImageDraw.Draw(im)
    layout = CONTROL_LAYOUT[family]
    bx0,by0,bx1,by1 = meta["bounds"]

    def p(xy):
        return (round(ox + (xy[0]-bx0)/(bx1-bx0)*width),round(oy+(xy[1]-by0)/(by1-by0)*height))

    def circle(pos, radius, fill, line=None, lw=2):
        px,py=p(pos)
        r=max(2,round(radius*U))
        d.ellipse((px-r,py-r,px+r,py+r),fill=fill,outline=line,width=max(1,round(lw*U/40)))

    if not state:
        # Mostrar la silueta tambien si se selecciona Solo mando sin conectar ninguno.
        im.alpha_composite(details,(ox,oy))
        font = PAD_SMALL_FONT
        msg = "SIN MANDO" if gamepad.pg else "INSTALA PYGAME-CE"
        d.text(p(((bx0+bx1)/2,by0+(by1-by0)*.83)), msg, font=font, fill=rgba_alpha((213,221,229,255)), anchor="mm",
               stroke_width=1, stroke_fill=rgba_alpha((34,42,50,255)))
        return

    btn=state['buttons']
    axes=state['axes']
    for k,pos in layout['face'].items():
        if btn.get(k,False):
            color = ((210, 216, 224, 255) if THEME == "minimalista" else
                     COLOR_BUTTONS[k] if family == "xbox" else (194, 210, 237, 255))
            circle(pos, .30 if family=='xbox' else .26, rgba_alpha((*color[:3],190)))
    for k,pos in layout['dpad'].items():
        if btn.get(k,False):
            circle(pos, .27 if family=='xbox' else .24, rgba_alpha((205,224,247,195)))
    for k in ('back','start','guide'):
        if btn.get(k,False):
            circle(layout[k],.14 if k!='guide' else .20, rgba_alpha((160,216,255,190)))

    # SDL2 registra LT/RT 0..1; barras discretas adheridas al borde superior.
    for side,value,hold in (("left",state['lt'],'lb'),("right",state['rt'],'rb')):
        anchor=layout[side+'_trigger']
        cx,cy=p(anchor)
        wide=max(10,round(.98*U))
        tall=max(2,round(.11*U))
        x0=cx-wide//2
        y0=cy-tall//2
        d.rounded_rectangle((x0,y0,x0+wide,y0+tall), radius=max(1,tall//2),
                            fill=rgba_alpha((15,20,25,220)), outline=rgba_alpha((117,137,151,240)), width=1)
        if value>.03:
            d.rounded_rectangle((x0,y0,x0+max(2,round(wide*value)),y0+tall),
                                radius=max(1,tall//2), fill=rgba_alpha((140,196,242,255)))
        if btn.get(hold,False):
            d.line((x0,y0+tall+max(1,round(.09*U)),x0+wide,y0+tall+max(1,round(.09*U))),
                   fill=rgba_alpha((189,219,252,255)), width=max(2,round(.06*U)))

    # SVG original conserva todos sus contornos; la iluminación queda debajo de sus marcas.
    im.alpha_composite(details,(ox,oy))
    d=ImageDraw.Draw(im)
    # Los centros siguen la lectura SDL; solo estas dos piezas cambian por fotograma.
    for key,ix in (('left',0),('right',2)):
        px,py=p(layout[key])
        dx=max(-1,min(1,axes[ix])); dy=max(-1,min(1,axes[ix+1]))
        rng=max(2,round(.27*U))
        kx=px+round(dx*rng); ky=py+round(dy*rng)
        radius=max(3,round(.16*U))
        shade = (rgba_alpha((243, 249, 255, 250)) if THEME != "minimalista" else rgba_alpha((219, 219, 219, 250))) if btn.get('l3' if key=='left' else 'r3', False) else rgba_alpha((181, 195, 210, 236))
        d.ellipse((kx-radius,ky-radius,kx+radius,ky+radius), fill=rgba_alpha((30,37,46,252)),
                  outline=shade, width=max(1,round(.055*U)))


def present(kx, ky, wheel, pad_state):
    im = (base_move if st["move"] else base).copy()
    for x, y, off, on, down in items.values():
        im.alpha_composite(on if down else off, (x, y))
    if KEYBOARD_VISIBLE:
        if wheel:
            im.alpha_composite(wheel_half, (WHEEL_X, WHEEL_Y + (0 if wheel > 0 else WHEEL_HALF)))
        im.alpha_composite(knob, (kx, ky))
    draw_gamepad(im, pad_state)
    if st["move"]:
        im.alpha_composite(grip_sprite, (GRIP_X, GRIP_Y))
    ctypes.memmove(bits, im.tobytes("raw", "BGRa"), W * H * 4)
    user32.UpdateLayeredWindow(hwnd, screen_dc, None, ctypes.byref(win_size), mem_dc,
                               ctypes.byref(src_pos), 0, blend, 2)


def set_clickthrough(on):
    ex = user32.GetWindowLongW(hwnd, -20) | 0x80000 | 0x08000000
    user32.SetWindowLongW(hwnd, -20, ex | 0x20 if on else ex & ~0x20)


def save_setting(path, value):
    """Persiste ajustes con un unico formato de escritura (UTF-8)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(value))


def finish_resize():
    """Concluye un gesto de tamaño sin alterar el modo de movimiento."""
    if st["resizing"]:
        st["resizing"] = False
        save_setting(SCALE_FILE, SCALE)


def toggle_move():
    if st["closing"]:
        return
    finish_resize()
    st["move"] = not st["move"]
    set_clickthrough(not st["move"])
    if not st["move"]:
        save_setting(POS_FILE, f"+{root.winfo_x()}+{root.winfo_y()}")
        root.configure(cursor="")
        st["cursor"] = None
    st["drawn"] = None


def apply_layout(scale):
    """Reconstruye dibujo y buffer GDI conservando la ventana y la posicion."""
    x, y = root.winfo_x(), root.winfo_y()
    build_layout(scale)
    allocate_buffer()
    root.geometry(f"{W}x{H}{x:+d}{y:+d}")


def rebuild_for_mode():
    """Actualiza la vista sin reinstalar ventana, Raw Input ni icono."""
    if st["closing"]:
        return
    finish_resize()
    apply_layout(SCALE)


def change_mode(new_mode):
    global MODE
    if MODE == new_mode or new_mode not in MODE_LABELS:
        return
    MODE = new_mode
    try:
        save_setting(MODE_FILE, MODE)
    except OSError:
        pass
    rebuild_for_mode()


def change_size(scale, save=True):
    """Escala uniformemente toda la interfaz; no reinicia Raw Input ni la bandeja."""
    global SCALE
    scale = round(max(MIN_SCALE, min(MAX_SCALE, scale)), 4)
    if st["closing"] or scale == SCALE:
        return
    # Evita regenerar decenas de sprites cuando el arrastre cambia
    # fracciones de pixel sin alterar el tamaño real de las teclas.
    if round(40 * scale * root.winfo_fpixels("1i") / 96) == U:
        SCALE = scale
        if save:
            save_setting(SCALE_FILE, SCALE)
        return
    apply_layout(scale)
    if save:
        save_setting(SCALE_FILE, SCALE)


def over_grip(x, y):
    """Detecta la esquina inferior derecha mientras el panel es interactivo."""
    return st["move"] and x >= GRIP_X - 4 and y >= GRIP_Y - 4


def pointer_motion(e):
    if not st["move"]:
        return
    cursor = "size_nw_se" if st["resizing"] or over_grip(e.x, e.y) else "fleur"
    if cursor != st["cursor"]:
        root.configure(cursor=cursor)
        st["cursor"] = cursor


def drag_start(e):
    if not st["move"]:
        return
    if over_grip(e.x, e.y):
        st["resizing"] = True
        st["start_x"], st["start_y"] = e.x_root, e.y_root
        st["start_w"], st["start_h"] = W, H
        st["start_scale"] = SCALE
        pointer_motion(e)
    else:
        st["resizing"] = False
        st["dx"], st["dy"] = e.x_root - root.winfo_x(), e.y_root - root.winfo_y()


def drag(e):
    if not st["move"]:
        return
    if st["resizing"]:
        # Gesto libre: horizontal, vertical o diagonal, siempre proporcional.
        dx = (e.x_root - st["start_x"]) / max(1, st["start_w"])
        dy = (e.y_root - st["start_y"]) / max(1, st["start_h"])
        delta = dx if abs(dx) >= abs(dy) else dy
        change_size(st["start_scale"] * (1.0 + delta), save=False)
    elif "dx" in st:
        root.geometry(f"+{e.x_root - st['dx']}+{e.y_root - st['dy']}")


def drag_end(e):
    finish_resize()  # guardar solo al soltar: no escribir disco en cada frame
    pointer_motion(e)


# ---------- Icono oculto en la bandeja de Windows ----------
def create_tray_icon():
    """Crea un icono de teclado sin añadir ninguna dependencia."""
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((4, 12, 59, 50), radius=9, fill="#202020", outline="#e6e6e6", width=3)
    for row, cols in ((21, 5), (31, 5), (41, 4)):
        for col in range(cols):
            x = 12 + col * 9
            d.rounded_rectangle((x, row, x + 6, row + 5), radius=1, fill="#eeeeee")
    d.rounded_rectangle((20, 41, 45, 46), radius=2, fill="#eeeeee")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".ico", delete=False) as tmp:
            temp_path = tmp.name
        im.save(temp_path, format="ICO", sizes=[(32, 32), (64, 64)])
        return user32.LoadImageW(None, temp_path, 1, 0, 0, 0x0010 | 0x0040)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


tray_icon = create_tray_icon()
tray_data = NOTIFYICONDATAW()
tray_data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
tray_data.hWnd = hwnd
tray_data.uID = 1
tray_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
tray_data.uCallbackMessage = WM_TRAY
tray_data.hIcon = tray_icon
tray_data.szTip = f"Overlay Teclado v{VERSION} - clic derecho para opciones"
tray_added = False


def add_tray_icon():
    global tray_added
    tray_added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(tray_data)))
    if tray_added:
        tray_data.uTimeoutOrVersion = 4  # NOTIFYICON_VERSION_4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(tray_data))


def show_tray_menu():
    menu = user32.CreatePopupMenu()
    submenu = user32.CreatePopupMenu()
    viewmenu = user32.CreatePopupMenu()
    if not menu or not submenu or not viewmenu:
        if submenu:
            user32.DestroyMenu(submenu)
        if viewmenu:
            user32.DestroyMenu(viewmenu)
        if menu:
            user32.DestroyMenu(menu)
        return
    # MF_POPUP = 0x0010; MF_CHECKED = 0x0008; MF_SEPARATOR = 0x0800
    for cmd, value in CMD_SCALES.items():
        flags = 0x0008 if abs(value - SCALE) < 0.005 else 0
        user32.AppendMenuW(submenu, flags, cmd, f"{round(value * 100)} %")
    for cmd, value in CMD_MODES.items():
        label = MODE_LABELS[value]
        if value == "auto":
            current = "mando" if st["active_input"] == "gamepad" else "teclado/mouse"
            label = f"{label} - {current}"
        user32.AppendMenuW(viewmenu, 0x0008 if MODE == value else 0,
                           cmd, label)
    user32.AppendMenuW(menu, 0x0010, viewmenu, "Vista")
    user32.AppendMenuW(menu, 0x0010, submenu, f"Tamaño actual: {round(SCALE * 100)}%")
    user32.AppendMenuW(menu, 0, CMD_MOVE, "Fijar posición" if st["move"] else f"Mover overlay ({HOTKEYS['move']})")
    user32.AppendMenuW(menu, 0, CMD_HIDE, "Mostrar overlay" if st["hidden"] else f"Ocultar overlay ({HOTKEYS['hide']})")
    user32.AppendMenuW(menu, 0, CMD_SETTINGS, f"Ajustes... ({HOTKEYS['settings']})")
    user32.AppendMenuW(menu, 0, CMD_STATUS, "Estado del mando...")
    user32.AppendMenuW(menu, 0x0800, 0, None)
    user32.AppendMenuW(menu, 0, CMD_EXIT, "Salir")
    point = wt.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    user32.SetForegroundWindow(hwnd)
    # TPM_RIGHTBUTTON | TPM_RETURNCMD: obtenemos la opcion sin WM_COMMAND
    cmd = user32.TrackPopupMenu(menu, 0x0002 | 0x0100, point.x, point.y, 0, hwnd, None)
    user32.PostMessageW(hwnd, 0, 0, 0)
    user32.DestroyMenu(menu)  # elimina tambien el submenu
    if cmd in CMD_MODES:
        root.after_idle(lambda mode=CMD_MODES[cmd]: change_mode(mode))
    elif cmd in CMD_SCALES:
        root.after_idle(lambda new_scale=CMD_SCALES[cmd]: change_size(new_scale))
    elif cmd == CMD_STATUS:
        root.after_idle(lambda: messagebox.showinfo("Estado del mando", gamepad.info()))
    elif cmd == CMD_SETTINGS:
        root.after_idle(show_settings)
    elif cmd == CMD_HIDE:
        root.after_idle(toggle_hidden)
    elif cmd == CMD_MOVE:
        root.after_idle(lambda: toggle_hidden() if st["hidden"] else toggle_move())
    elif cmd == CMD_EXIT:
        root.after_idle(close_overlay)



# ---------- Personalizacion: visibilidad, atajos y panel ----------
KEY_CODES = {"H": ord("H"), "O": ord("O"), "M": ord("M")}
KEY_CODES.update({f"F{i}": 0x6F + i for i in range(1, 13)})
settings_window = None


def is_hotkey_down(combination):
    parts = combination.split("+")
    key = parts[-1]
    vk = KEY_CODES.get(key)
    if vk is None:
        return False
    ctrl = bool(user32.GetAsyncKeyState(VK_CTRL) & 0x8000)
    alt = bool(user32.GetAsyncKeyState(VK_ALT) & 0x8000)
    shift = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
    if "Ctrl" in parts and not ctrl:
        return False
    if "Alt" in parts and not alt:
        return False
    if "Shift" in parts and not shift:
        return False
    if "Ctrl" not in parts and ctrl:
        return False
    if "Shift" not in parts and shift:
        return False
    # Mantiene la compatibilidad con Alt+F8 cuando el atajo de mover es F8.
    if "Alt" not in parts and alt and combination != "F8":
        return False
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def handle_hotkeys():
    active = {action for action, combo in HOTKEYS.items() if is_hotkey_down(combo)}
    newly_pressed = active - st["hotkeys_pressed"]
    st["hotkeys_pressed"] = active
    if "hide" in newly_pressed:
        toggle_hidden()
    if "move" in newly_pressed and not st["hidden"]:
        toggle_move()
    if "settings" in newly_pressed:
        show_settings()
    return bool(newly_pressed)


def toggle_hidden():
    if st["closing"]:
        return
    st["hidden"] = not st["hidden"]
    if st["hidden"]:
        if st["move"]:
            toggle_move()  # deja la posicion guardada antes de ocultar
        root.withdraw()
    else:
        root.deiconify()
        set_clickthrough(not st["move"])
        root.attributes("-topmost", True)
        st["drawn"] = None


def change_opacity(kind, percentage):
    global KEYBOARD_ALPHA, GAMEPAD_ALPHA
    value = float(percentage) / 100.0
    if kind == "keyboard":
        value = max(.20, min(1.0, value))
        if abs(value - KEYBOARD_ALPHA) < .005:
            return
        KEYBOARD_ALPHA = value
        apply_layout(SCALE)
    else:
        value = max(.15, min(1.0, value))
        if abs(value - GAMEPAD_ALPHA) < .005:
            return
        GAMEPAD_ALPHA = value
        _SKIN_CACHE.clear()
        st["drawn"] = None
    save_ui_settings()


def change_theme(theme):
    global THEME
    if theme not in THEME_COLORS or THEME == theme:
        return
    THEME = theme
    update_theme_colors()
    _SKIN_CACHE.clear()
    apply_layout(SCALE)
    save_ui_settings()


def change_hotkeys(choice):
    if set(choice) != set(HOTKEY_DEFAULTS) or any(v not in HOTKEY_CHOICES for v in choice.values()):
        return False
    if len(set(choice.values())) != len(choice):
        return False
    HOTKEYS.update(choice)
    st["hotkeys_pressed"].clear()
    save_ui_settings()
    st["drawn"] = None
    return True


def show_settings():
    global settings_window
    if st["closing"]:
        return
    if settings_window is not None:
        try:
            if settings_window.winfo_exists():
                settings_window.deiconify()
                settings_window.lift()
                settings_window.focus_force()
                return
        except tk.TclError:
            pass

    window = tk.Toplevel(root)
    settings_window = window
    window.title(f"Overlay Teclado · Ajustes v{VERSION}")
    window.geometry("510x555")
    window.minsize(480, 530)
    window.resizable(True, True)
    window.attributes("-topmost", True)
    window.protocol("WM_DELETE_WINDOW", window.destroy)

    style = ttk.Style(window)
    style.theme_use("clam")
    bg, fg = ("#24272e", "#f0f2f6") if THEME != "claro" else ("#f5f7f9", "#203044")
    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TLabelframe", background=bg)
    style.configure("TLabelframe.Label", background=bg, foreground=fg)
    style.configure("TButton", padding=5)
    style.configure("Overlay.TFrame", background=bg)
    style.configure("Overlay.TLabel", background=bg, foreground=fg)
    style.configure("Overlay.TLabelframe", background=bg)
    style.configure("Overlay.TLabelframe.Label", background=bg, foreground=fg)
    style.configure("Overlay.TButton", padding=5)
    window.configure(background=bg)

    frame = ttk.Frame(window, style="Overlay.TFrame", padding=16)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Apariencia y comportamiento", style="Overlay.TLabel",
              font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 10))

    appearance = ttk.LabelFrame(frame, text="Opacidad (se aplica al soltar)", padding=10)
    appearance.pack(fill="x", pady=(0, 10))
    opacity_scales = {}
    for kind, label, initial, minimum in (
        ("keyboard", "Teclado y mouse", KEYBOARD_ALPHA, 20),
        ("gamepad", "Mando", GAMEPAD_ALPHA, 15),
    ):
        line = ttk.Frame(appearance)
        line.pack(fill="x", pady=3)
        ttk.Label(line, text=label, width=19).pack(side="left")
        var = tk.DoubleVar(value=round(initial * 100))
        scale = ttk.Scale(line, from_=minimum, to=100, variable=var)
        scale.pack(side="left", fill="x", expand=True, padx=8)
        percentage = ttk.Label(line, text=f"{round(initial * 100)}%", width=5)
        percentage.pack(side="right")
        def update_label(value, target=percentage):
            target.configure(text=f"{round(float(value))}%")
        scale.configure(command=update_label)
        scale.bind("<ButtonRelease-1>", lambda e, k=kind, v=var: change_opacity(k, round(v.get())))
        scale.bind("<KeyRelease>", lambda e, k=kind, v=var: change_opacity(k, round(v.get())))
        opacity_scales[kind] = scale

    line = ttk.Frame(appearance)
    line.pack(fill="x", pady=(8, 2))
    ttk.Label(line, text="Tema", width=19).pack(side="left")
    theme_var = tk.StringVar(value=THEME)
    theme_select = ttk.Combobox(line, textvariable=theme_var, state="readonly",
                                values=list(THEME_COLORS), width=18)
    theme_select.pack(side="left", fill="x", expand=True, padx=8)
    theme_select.bind("<<ComboboxSelected>>", lambda e: change_theme(theme_var.get()))

    hotkey_section = ttk.LabelFrame(frame, text="Atajos globales", padding=10)
    hotkey_section.pack(fill="x", pady=(0, 10))
    key_vars = {}
    for action, label in (("move", "Mover / fijar"), ("hide", "Mostrar / ocultar"),
                          ("settings", "Abrir ajustes")):
        row = ttk.Frame(hotkey_section)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text=label, width=19).pack(side="left")
        var = tk.StringVar(value=HOTKEYS[action])
        key_vars[action] = var
        combo = ttk.Combobox(row, textvariable=var, state="readonly",
                             values=HOTKEY_CHOICES, width=18)
        combo.pack(side="left", padx=8, fill="x", expand=True)

    def save_keys():
        if not change_hotkeys({name: var.get() for name, var in key_vars.items()}):
            messagebox.showwarning("Atajos", "Cada accion necesita un atajo distinto y valido.", parent=window)
        else:
            messagebox.showinfo("Atajos", "Atajos guardados.", parent=window)
    ttk.Button(hotkey_section, text="Guardar atajos", command=save_keys).pack(anchor="e", pady=(7, 1))

    other = ttk.LabelFrame(frame, text="Vista y tamaño", padding=10)
    other.pack(fill="x", pady=(0, 8))
    other_row = ttk.Frame(other)
    other_row.pack(fill="x")
    ttk.Label(other_row, text="Vista", width=10).pack(side="left")
    names = list(MODE_LABELS.values())
    view_var = tk.StringVar(value=MODE_LABELS[MODE])
    view_select = ttk.Combobox(other_row, state="readonly", textvariable=view_var, values=names, width=24)
    view_select.pack(side="left", padx=6, fill="x", expand=True)
    view_select.bind("<<ComboboxSelected>>", lambda e: change_mode(next(k for k, v in MODE_LABELS.items() if v == view_var.get())))
    size_row = ttk.Frame(other)
    size_row.pack(fill="x", pady=(8, 0))
    ttk.Label(size_row, text="Tamaño", width=10).pack(side="left")
    size_var = tk.StringVar(value=f"{round(SCALE * 100)} %")
    sizes = [f"{round(v * 100)} %" for v in SCALE_OPTIONS]
    size_combo = ttk.Combobox(size_row, state="readonly", textvariable=size_var, values=sizes, width=24)
    size_combo.pack(side="left", padx=6, fill="x", expand=True)
    size_combo.bind("<<ComboboxSelected>>", lambda e: change_size(int(size_var.get().split()[0]) / 100))

    ttk.Label(frame, text="Los cambios se guardan localmente. Sin inicio automatico.",
              style="Overlay.TLabel", font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 8))
    ttk.Button(frame, text="Cerrar", command=window.destroy).pack(anchor="e")


def close_overlay():
    """Un solo cierre para el clic derecho original y para Salir desde la bandeja."""
    global tray_added, bitmap, tray_icon
    if st["closing"]:
        return
    st["closing"] = True
    if settings_window is not None:
        try:
            if settings_window.winfo_exists():
                settings_window.destroy()
        except tk.TclError:
            pass
    gamepad.shutdown()  # misma rutina de salida para bandeja y clic derecho
    if tray_added:
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(tray_data))
        tray_added = False
    if tray_icon:
        user32.DestroyIcon(tray_icon)
        tray_icon = None
    if old_proc:
        user32.SetWindowLongPtrW(hwnd, -4, old_proc)
    if bitmap:
        gdi32.SelectObject(mem_dc, original_bitmap)
        gdi32.DeleteObject(bitmap)
        bitmap = None
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, screen_dc)
    release_single_instance()
    root.destroy()


root.bind("<Motion>", pointer_motion)
root.bind("<Button-1>", drag_start)
root.bind("<B1-Motion>", drag)
root.bind("<ButtonRelease-1>", drag_end)
root.bind("<Button-3>", lambda e: close_overlay())
root.protocol("WM_DELETE_WINDOW", close_overlay)
add_tray_icon()


def tick():
    if st["closing"]:
        return
    pad_state = stabilize_gamepad_frame(gamepad.poll(st["n"]))
    # Basarse en lecturas estabilizadas y no en un sondeo fallido de SDL.
    pad_is_available = pad_state is not None
    if pad_is_available != st["pad_connected"]:
        st["pad_connected"] = pad_is_available
        if not pad_is_available and st["active_input"] == "gamepad":
            # Al desconectar el mando, regresar al teclado de inmediato.
            st["active_input"] = "keyboard"
            st["prev_pad"] = None
            if MODE == "auto":
                rebuild_for_mode()
        st["drawn"] = None

    # Los estados visibles se actualizan igual que antes, en cualquier modo.
    for vk, it in items.items():
        it[4] = bool(user32.GetAsyncKeyState(vk) & 0x8000)
    hotkey_pressed = handle_hotkeys()

    # Guardar el delta antes de que se consuma para animar el stick del mouse.
    activity = detect_active_input(pad_state, st["ax"], st["ay"])
    # Alt+F8 / F8 solo gestionan la ventana; no cambian de dispositivo.
    if (activity and not st["move"] and not hotkey_pressed and
            activity != st["active_input"]):
        st["active_input"] = activity
        if MODE == "auto":
            rebuild_for_mode()

    tx, ty = st["ax"] / STICK_SENS, st["ay"] / STICK_SENS
    st["ax"] = st["ay"] = 0
    mag = math.hypot(tx, ty)
    if mag > 1:
        tx, ty = tx / mag, ty / mag
    st["sx"] += (tx - st["sx"]) * 0.35
    st["sy"] += (ty - st["sy"]) * 0.35
    kx = round(SX + st["sx"] * (SR - KR) - KR)
    ky = round(SY + st["sy"] * (SR - KR) - KR)

    wheel = st["wd"] if st["wt"] > 0 else 0
    st["wt"] = max(0, st["wt"] - 1)
    pad_frame = None
    if GAMEPAD_VISIBLE and pad_state is not None:
        pad_frame = (pad_state["name"], pad_state["mapped"], pad_state.get("guid", ""),
                     pad_state["axes"], pad_state["lt"], pad_state["rt"],
                     tuple(pad_state["buttons"].values()))
    frame = (st["move"], kx, ky, wheel, pad_frame, *(it[4] for it in items.values()))
    if not st["hidden"] and frame != st["drawn"]:
        st["drawn"] = frame
        present(kx, ky, wheel, pad_state)

    st["n"] += 1
    if st["n"] % 120 == 0:
        root.attributes("-topmost", True)
    root.after(65 if st["hidden"] else 16, tick)


set_clickthrough(True)
tick()
root.mainloop()
