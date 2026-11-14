"""Registro de asociación e ícono en Windows para archivos de proyecto (.sff)."""

import os
import shutil
import sys

from ui.constantes import (
    ARCHIVO_ICONO_PROYECTO,
    DESCRIPCION_TIPO_PROYECTO,
    EXTENSION_PROYECTO,
    PROGID_PROYECTO,
)
from ui.recursos import ruta_recurso

_NOMBRE_CARPETA_LOCAL = "SimuladorFlujoDeFluidos"
_SHCNE_ASSOCCHANGED = 0x08000000
_SHCNF_IDLIST = 0x0000


def _es_entorno_prueba():
    return bool(
        os.environ.get("PYTEST_CURRENT_TEST")
        or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    )


def ruta_icono_persistente(carpeta_destino=None, archivo_origen=None):
    """Copia el ícono a una ruta persistente de usuario (seguro para --onefile)."""
    origen = archivo_origen or ruta_recurso(ARCHIVO_ICONO_PROYECTO)
    if not origen or not os.path.isfile(origen):
        return None

    base = carpeta_destino or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        _NOMBRE_CARPETA_LOCAL,
    )
    destino = os.path.join(base, ARCHIVO_ICONO_PROYECTO)
    try:
        os.makedirs(base, exist_ok=True)
        debe_copiar = not os.path.isfile(destino)
        if not debe_copiar:
            with open(origen, "rb") as f_org, open(destino, "rb") as f_dst:
                debe_copiar = f_org.read() != f_dst.read()
        if debe_copiar:
            shutil.copyfile(origen, destino)
        return destino
    except OSError:
        return origen


def comando_apertura_proyecto():
    """Devuelve el comando de apertura para asociar archivos al simulador."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'

    dir_python = os.path.dirname(os.path.abspath(sys.executable))
    pythonw = os.path.join(dir_python, "pythonw.exe")
    ejecutable = pythonw if os.path.isfile(pythonw) else sys.executable
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta_main = os.path.join(raiz, "main.py")
    return f'"{ejecutable}" "{ruta_main}" "%1"'


def _escribir_registro_si_cambia(modulo_winreg, raiz, subclave, nombre, valor):
    """Actualiza un valor de registro HKCU solo si difiere; retorna True si cambió."""
    try:
        with modulo_winreg.OpenKey(raiz, subclave, 0, modulo_winreg.KEY_READ) as clave:
            actual, _ = modulo_winreg.QueryValueEx(clave, nombre)
            if actual == valor:
                return False
    except OSError:
        pass

    with modulo_winreg.CreateKeyEx(
        raiz, subclave, 0, modulo_winreg.KEY_SET_VALUE
    ) as clave:
        modulo_winreg.SetValueEx(clave, nombre or "", 0, modulo_winreg.REG_SZ, valor)
    return True


def _notificar_shell_windows():
    try:
        import ctypes

        ctypes.windll.shell32.SHChangeNotify(
            _SHCNE_ASSOCCHANGED, _SHCNF_IDLIST, None, None
        )
    except Exception:
        pass


def registrar_asociacion_proyecto(
    forzar=False,
    *,
    modulo_winreg=None,
    raiz_registro=None,
    carpeta_icono=None,
    archivo_origen=None,
    comando=None,
    notificar=True,
):
    """Asocia en Windows (.sff) el ícono de gota de agua y apertura directa en el simulador."""
    if not forzar and (sys.platform != "win32" or _es_entorno_prueba()):
        return False

    if modulo_winreg is None:
        if sys.platform != "win32":
            return False
        import winreg as modulo_winreg

    raiz = (
        raiz_registro
        if raiz_registro is not None
        else modulo_winreg.HKEY_CURRENT_USER
    )
    ruta_icono = ruta_icono_persistente(
        carpeta_destino=carpeta_icono,
        archivo_origen=archivo_origen,
    )
    if not ruta_icono:
        return False

    cmd = comando or comando_apertura_proyecto()
    sub_ext = f"Software\\Classes\\{EXTENSION_PROYECTO}"
    sub_prog = f"Software\\Classes\\{PROGID_PROYECTO}"
    entradas = (
        (sub_ext, None, PROGID_PROYECTO),
        (sub_ext, "Content Type", "application/json"),
        (sub_ext, "PerceivedType", "document"),
        (sub_prog, None, DESCRIPCION_TIPO_PROYECTO),
        (f"{sub_prog}\\DefaultIcon", None, f'"{ruta_icono}",0'),
        (f"{sub_prog}\\shell\\open\\command", None, cmd),
    )

    try:
        cambios = False
        for subclave, nombre, valor in entradas:
            cambios |= _escribir_registro_si_cambia(
                modulo_winreg, raiz, subclave, nombre, valor
            )
    except OSError:
        return False

    if cambios and notificar:
        _notificar_shell_windows()
    return True
