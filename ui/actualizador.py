"""Verificación y descarga de actualizaciones desde GitHub Releases."""

from dataclasses import dataclass
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from ui.constantes import REPOSITORIO_GITHUB, VERSION_APP


@dataclass(frozen=True)
class InfoActualizacion:
    """Metadatos de una versión consultada en GitHub Releases."""

    version_remota: str
    url_release: str
    notas: str
    nombre_asset: str
    url_descarga: str
    tamano_bytes: int


def parsear_version(texto):
    """Convierte una etiqueta tipo 'v1.0.2' o '1.0.2' en tupla numérica comparable."""
    limpio = str(texto or "").strip().lstrip("vV")
    limpio = limpio.split("-", 1)[0].split("+", 1)[0]
    if not limpio:
        return (0,)
    partes = []
    for segmento in limpio.split("."):
        match = re.match(r"^(\d+)", segmento.strip())
        if not match:
            break
        partes.append(int(match.group(1)))
    return tuple(partes) if partes else (0,)


def es_version_mayor(version_remota, version_local=VERSION_APP):
    """Devuelve True si version_remota es estrictamente superior a version_local."""
    remota = list(parsear_version(version_remota))
    local = list(parsear_version(version_local))
    largo = max(len(remota), len(local))
    remota.extend([0] * (largo - len(remota)))
    local.extend([0] * (largo - len(local)))
    return tuple(remota) > tuple(local)


def seleccionar_asset_instalador(release_json):
    """Elige el archivo de instalador (.exe) dentro de los assets del release."""
    assets = release_json.get("assets") or []
    ejecutables = [
        asset
        for asset in assets
        if str(asset.get("name", "")).lower().endswith(".exe")
        and asset.get("browser_download_url")
    ]
    if not ejecutables:
        return None

    for asset in ejecutables:
        nombre = str(asset.get("name", "")).lower()
        if "setup" in nombre or "instalador" in nombre:
            return asset
    return ejecutables[0]


def consultar_ultima_version(
    repositorio=REPOSITORIO_GITHUB,
    version_actual=VERSION_APP,
    timeout=6.0,
    urlopen=None,
):
    """Consulta la API de GitHub Releases; retorna InfoActualizacion si hay mejora."""
    url = f"https://api.github.com/repos/{repositorio}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SimuladorFlujoDeFluidos/{version_actual}",
        },
    )
    lector = urlopen or urllib.request.urlopen
    with lector(req, timeout=timeout) as resp:
        datos = json.loads(resp.read().decode("utf-8"))

    tag = str(datos.get("tag_name") or "").strip()
    version_remota = tag.lstrip("vV")
    if not version_remota or not es_version_mayor(version_remota, version_actual):
        return None

    asset = seleccionar_asset_instalador(datos)
    if asset is None:
        return None

    return InfoActualizacion(
        version_remota=version_remota,
        url_release=str(datos.get("html_url") or f"https://github.com/{repositorio}/releases/latest"),
        notas=str(datos.get("body") or "").strip(),
        nombre_asset=str(asset.get("name") or "Simulador_Flujo_de_Fluidos_Setup.exe"),
        url_descarga=str(asset.get("browser_download_url")),
        tamano_bytes=int(asset.get("size") or 0),
    )


def descargar_instalador(
    url_descarga,
    ruta_destino,
    *,
    version_actual=VERSION_APP,
    timeout=30.0,
    progreso_cb=None,
    cancelado_cb=None,
    urlopen=None,
):
    """Descarga el instalador .exe validando cabecera PE ('MZ')."""
    req = urllib.request.Request(
        url_descarga,
        headers={"User-Agent": f"SimuladorFlujoDeFluidos/{version_actual}"},
    )
    lector = urlopen or urllib.request.urlopen
    parcial = f"{ruta_destino}.part"
    descargado = 0

    try:
        with lector(req, timeout=timeout) as resp, open(parcial, "wb") as salida:
            total_hdr = resp.headers.get("Content-Length") if getattr(resp, "headers", None) else None
            total = int(total_hdr) if total_hdr and str(total_hdr).isdigit() else 0
            primer_bloque = True
            while True:
                if cancelado_cb and cancelado_cb():
                    raise InterruptedError("Descarga cancelada por el usuario.")
                bloque = resp.read(65536)
                if not bloque:
                    break
                if primer_bloque:
                    if not bloque.startswith(b"MZ"):
                        raise ValueError("El archivo descargado no es un ejecutable de Windows válido.")
                    primer_bloque = False
                salida.write(bloque)
                descargado += len(bloque)
                if progreso_cb:
                    progreso_cb(descargado, total)
        if descargado == 0:
            raise ValueError("El instalador descargado está vacío.")
        os.replace(parcial, ruta_destino)
        return ruta_destino
    except Exception:
        if os.path.exists(parcial):
            try:
                os.remove(parcial)
            except OSError:
                pass
        raise


def lanzar_actualizacion_silenciosa(ruta_instalador, ruta_app_reiniciar=None):
    """Ejecuta el instalador en segundo plano tras cerrar la aplicación y la relanza."""
    if sys.platform != "win32":
        raise RuntimeError("La actualización automática por instalador solo está disponible en Windows.")

    fd, ruta_cmd = tempfile.mkstemp(prefix="simulador_update_", suffix=".cmd")
    os.close(fd)
    lineas = [
        "@echo off",
        "timeout /t 2 /nobreak > nul",
        f'"{ruta_instalador}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
        f'del /f /q "{ruta_instalador}" > nul 2>&1',
    ]
    if ruta_app_reiniciar and os.path.isfile(ruta_app_reiniciar):
        lineas.append(f'start "" "{ruta_app_reiniciar}"')
    lineas.append('del /f /q "%~f0" > nul 2>&1')

    with open(ruta_cmd, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lineas) + "\r\n")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(
        ["cmd.exe", "/c", ruta_cmd],
        creationflags=creationflags,
        close_fds=True,
    )
    return ruta_cmd


class TrabajadorConsultaActualizacion(QObject):
    """Consulta en segundo plano sin bloquear la interfaz."""

    finalizado = pyqtSignal(object, str)

    def __init__(self, repositorio=REPOSITORIO_GITHUB, version_actual=VERSION_APP):
        super().__init__()
        self._repositorio = repositorio
        self._version_actual = version_actual

    def ejecutar(self):
        try:
            info = consultar_ultima_version(
                repositorio=self._repositorio,
                version_actual=self._version_actual,
            )
            self.finalizado.emit(info, "")
        except urllib.error.URLError as exc:
            self.finalizado.emit(None, f"No se pudo conectar con GitHub: {exc.reason}")
        except Exception as exc:
            self.finalizado.emit(None, str(exc))


class TrabajadorDescargaActualizacion(QObject):
    """Descarga el instalador en un hilo separado reportando porcentaje."""

    progreso = pyqtSignal(int, int)
    completado = pyqtSignal(str)
    fallido = pyqtSignal(str)

    def __init__(self, url_descarga, ruta_destino):
        super().__init__()
        self._url_descarga = url_descarga
        self._ruta_destino = ruta_destino
        self._cancelado = False

    def cancelar(self):
        self._cancelado = True

    def ejecutar(self):
        try:
            ruta = descargar_instalador(
                self._url_descarga,
                self._ruta_destino,
                progreso_cb=lambda rec, tot: self.progreso.emit(rec, tot),
                cancelado_cb=lambda: self._cancelado,
            )
            self.completado.emit(ruta)
        except Exception as exc:
            self.fallido.emit(str(exc))
