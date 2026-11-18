"""Verificación, descarga, validación SHA256 y actualización silenciosa desde GitHub Releases."""

from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

from PyQt5.QtCore import QObject, pyqtSignal

from ui.constantes import REPOSITORIO_GITHUB, VERSION_APP


APPMODEL_ERROR_NO_PACKAGE = 15700
ERROR_INSUFFICIENT_BUFFER = 122

TIMEOUT_API_SEGUNDOS = 6.0
TIMEOUT_SHA256_SEGUNDOS = 10.0
TIMEOUT_DESCARGA_SEGUNDOS = 30.0


def _configurar_logger():
    """Configura un logger silencioso en archivo para registrar diagnósticos del actualizador."""
    logger = logging.getLogger("simulador.actualizador")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    base_local = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    carpeta_log = os.path.join(base_local, "Simulador_Flujo_de_Fluidos", "logs")
    ruta_log = os.path.join(carpeta_log, "actualizador.log")
    try:
        os.makedirs(carpeta_log, exist_ok=True)
        handler = RotatingFileHandler(
            ruta_log, maxBytes=512 * 1024, backupCount=2, encoding="utf-8"
        )
    except OSError:
        ruta_log = os.path.join(tempfile.gettempdir(), "simulador_actualizador.log")
        try:
            handler = RotatingFileHandler(
                ruta_log, maxBytes=512 * 1024, backupCount=1, encoding="utf-8"
            )
        except OSError:
            handler = logging.NullHandler()

    formato = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    handler.setFormatter(formato)
    logger.addHandler(handler)
    logger.ruta_archivo = ruta_log
    return logger


LOGGER = _configurar_logger()


def ruta_log_actualizador():
    """Devuelve la ruta del archivo de log usado por el actualizador."""
    return getattr(
        LOGGER,
        "ruta_archivo",
        os.path.join(tempfile.gettempdir(), "simulador_actualizador.log"),
    )


def es_paquete_microsoft_store(ejecutable=None):
    """Detecta si el proceso se ejecuta dentro de un contenedor MSIX / Microsoft Store."""
    override = os.environ.get("SIMULADOR_MODO_STORE", "").strip().lower()
    if override in ("1", "true", "si"):
        return True
    if override in ("0", "false", "no"):
        return False

    ruta_exe = os.path.abspath(ejecutable or sys.executable or "").lower()
    if "windowsapps" in ruta_exe.replace("/", "\\").split("\\"):
        return True

    if sys.platform == "win32" and ejecutable is None:
        try:
            import ctypes

            largo = ctypes.c_uint32(0)
            rc = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(largo), None)
            if rc in (0, ERROR_INSUFFICIENT_BUFFER) and largo.value > 0:
                return True
            if rc == APPMODEL_ERROR_NO_PACKAGE:
                return False
        except Exception:
            pass
    return False


@dataclass(frozen=True)
class InfoActualizacion:
    """Metadatos de una versión consultada en GitHub Releases."""

    version_remota: str
    url_release: str
    notas: str
    nombre_asset: str
    url_descarga: str
    tamano_bytes: int
    nombre_sha256: str = ""
    url_sha256: str = ""


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


def seleccionar_asset_sha256(release_json, nombre_instalador=""):
    """Elige el archivo .sha256 correspondiente al instalador dentro de los assets del release."""
    assets = release_json.get("assets") or []
    candidatos = [
        asset
        for asset in assets
        if str(asset.get("name", "")).lower().endswith(".sha256")
        and asset.get("browser_download_url")
    ]
    if not candidatos:
        return None

    objetivo = f"{str(nombre_instalador or '').lower()}.sha256"
    for asset in candidatos:
        if str(asset.get("name", "")).lower() == objetivo:
            return asset
    for asset in candidatos:
        nombre = str(asset.get("name", "")).lower()
        if "setup" in nombre or "instalador" in nombre:
            return asset
    return candidatos[0]


def extraer_hash_sha256(texto_sha256, nombre_archivo=""):
    """Extrae el hash hexadecimal de 64 caracteres desde el contenido de un archivo .sha256."""
    texto = str(texto_sha256 or "").strip()
    if not texto:
        return None

    lineas = [lin.strip() for lin in texto.splitlines() if lin.strip()]
    nombre_lower = str(nombre_archivo or "").strip().lower()

    if nombre_lower and len(lineas) > 1:
        for linea in lineas:
            if nombre_lower in linea.lower():
                m = re.search(r"\b([a-fA-F0-9]{64})\b", linea)
                if m:
                    return m.group(1).lower()

    for linea in lineas:
        m = re.search(r"\b([a-fA-F0-9]{64})\b", linea)
        if m:
            return m.group(1).lower()
    return None


def calcular_sha256_archivo(ruta_archivo):
    """Calcula el resumen SHA256 en minúsculas de un archivo en disco."""
    h = hashlib.sha256()
    with open(ruta_archivo, "rb") as f:
        while True:
            bloque = f.read(65536)
            if not bloque:
                break
            h.update(bloque)
    return h.hexdigest().lower()


def descargar_texto_sha256(
    url_sha256,
    *,
    version_actual=VERSION_APP,
    timeout=TIMEOUT_SHA256_SEGUNDOS,
    urlopen=None,
):
    """Descarga el contenido de texto del archivo .sha256 publicado en el release."""
    if not url_sha256:
        raise ValueError("El release no contiene archivo .sha256.")
    req = urllib.request.Request(
        url_sha256,
        headers={"User-Agent": f"SimuladorFlujoDeFluidos/{version_actual}"},
    )
    lector = urlopen or urllib.request.urlopen
    with lector(req, timeout=timeout) as resp:
        raw = resp.read(65536)
    return raw.decode("utf-8", errors="replace").strip()


def verificar_sha256_instalador(ruta_instalador, sha256_esperado, nombre_archivo=""):
    """Verifica el SHA256 del instalador; si falta o no coincide, borra el archivo y retorna False."""
    hash_limpio = extraer_hash_sha256(sha256_esperado, nombre_archivo=nombre_archivo)
    if not hash_limpio or not os.path.isfile(ruta_instalador):
        if ruta_instalador and os.path.exists(ruta_instalador):
            try:
                os.remove(ruta_instalador)
            except OSError:
                pass
        LOGGER.error("Verificación SHA256 abortada: hash esperado vacío o archivo inexistente.")
        return False

    try:
        hash_actual = calcular_sha256_archivo(ruta_instalador)
    except OSError as exc:
        LOGGER.error("No se pudo leer el instalador para calcular SHA256: %s", exc)
        return False

    if not hmac.compare_digest(hash_actual, hash_limpio):
        LOGGER.error(
            "SHA256 inválido para %s (esperado=%s, calculado=%s). Borrando archivo.",
            ruta_instalador,
            hash_limpio,
            hash_actual,
        )
        try:
            os.remove(ruta_instalador)
        except OSError:
            pass
        return False

    LOGGER.info("SHA256 verificado correctamente para %s (%s).", ruta_instalador, hash_actual)
    return True


def consultar_ultima_version(
    repositorio=REPOSITORIO_GITHUB,
    version_actual=VERSION_APP,
    timeout=TIMEOUT_API_SEGUNDOS,
    urlopen=None,
):
    """Consulta la API de GitHub Releases; retorna InfoActualizacion si hay mejora."""
    if es_paquete_microsoft_store():
        return None

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

    nombre_asset = str(asset.get("name") or "Simulador_Flujo_de_Fluidos_Setup.exe")
    asset_sha = seleccionar_asset_sha256(datos, nombre_instalador=nombre_asset)

    return InfoActualizacion(
        version_remota=version_remota,
        url_release=str(datos.get("html_url") or f"https://github.com/{repositorio}/releases/latest"),
        notas=str(datos.get("body") or "").strip(),
        nombre_asset=nombre_asset,
        url_descarga=str(asset.get("browser_download_url")),
        tamano_bytes=int(asset.get("size") or 0),
        nombre_sha256=str(asset_sha.get("name") or "") if asset_sha else "",
        url_sha256=str(asset_sha.get("browser_download_url") or "") if asset_sha else "",
    )


def descargar_instalador(
    url_descarga,
    ruta_destino,
    *,
    version_actual=VERSION_APP,
    timeout=TIMEOUT_DESCARGA_SEGUNDOS,
    progreso_cb=None,
    cancelado_cb=None,
    urlopen=None,
    sha256_esperado=None,
):
    """Descarga el instalador .exe a un archivo .part, lo renombra y valida SHA256 si se indica."""
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
    except Exception:
        for ruta_limpiar in (parcial, ruta_destino):
            if os.path.exists(ruta_limpiar):
                try:
                    os.remove(ruta_limpiar)
                except OSError:
                    pass
        raise

    if sha256_esperado is not None:
        if not verificar_sha256_instalador(
            ruta_destino, sha256_esperado, nombre_archivo=os.path.basename(ruta_destino)
        ):
            raise ValueError("El hash SHA256 del instalador no coincide con el archivo .sha256 oficial.")

    return ruta_destino


def descargar_y_verificar_actualizacion(
    info,
    directorio_destino=None,
    *,
    version_actual=VERSION_APP,
    timeout_sha=TIMEOUT_SHA256_SEGUNDOS,
    timeout_descarga=TIMEOUT_DESCARGA_SEGUNDOS,
    progreso_cb=None,
    cancelado_cb=None,
    urlopen=None,
):
    """Descarga el .sha256 y el Setup.exe, verifica el hash y devuelve la ruta lista para instalar."""
    if info is None:
        raise ValueError("No hay información de actualización.")
    if not getattr(info, "url_sha256", ""):
        raise ValueError(
            f"La versión v{info.version_remota} no tiene archivo .sha256 publicado en el release."
        )

    texto_sha = descargar_texto_sha256(
        info.url_sha256,
        version_actual=version_actual,
        timeout=timeout_sha,
        urlopen=urlopen,
    )
    hash_esperado = extraer_hash_sha256(texto_sha, nombre_archivo=info.nombre_asset)
    if not hash_esperado:
        raise ValueError("El archivo .sha256 publicado no contiene un hash SHA256 válido.")

    carpeta = directorio_destino or tempfile.gettempdir()
    os.makedirs(carpeta, exist_ok=True)
    ruta_destino = os.path.join(carpeta, info.nombre_asset)

    return descargar_instalador(
        info.url_descarga,
        ruta_destino,
        version_actual=version_actual,
        timeout=timeout_descarga,
        progreso_cb=progreso_cb,
        cancelado_cb=cancelado_cb,
        urlopen=urlopen,
        sha256_esperado=hash_esperado,
    )


def lanzar_actualizacion_silenciosa(ruta_instalador, ruta_app_reiniciar=None):
    """Lanza el instalador de Inno Setup con /VERYSILENT /SUPPRESSMSGBOXES /NORESTART."""
    if sys.platform != "win32":
        raise RuntimeError("La actualización automática por instalador solo está disponible en Windows.")
    if not ruta_instalador or not os.path.isfile(ruta_instalador):
        raise FileNotFoundError(f"No existe el instalador: {ruta_instalador}")

    creationflags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    cmd = [
        ruta_instalador,
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
    ]
    LOGGER.info("Lanzando instalador silencioso: %s", " ".join(cmd))
    subprocess.Popen(
        cmd,
        creationflags=creationflags,
        close_fds=True,
    )
    return ruta_instalador


class TrabajadorAutoActualizacion(QObject):
    """Hilo completo en segundo plano: consulta, descarga .part -> .exe y verifica SHA256."""

    actualizacion_lista = pyqtSignal(object, str)
    sin_actualizacion = pyqtSignal()
    fallo_silencioso = pyqtSignal(str)

    def __init__(
        self,
        repositorio=REPOSITORIO_GITHUB,
        version_actual=VERSION_APP,
        directorio_destino=None,
        urlopen=None,
    ):
        super().__init__()
        self._repositorio = repositorio
        self._version_actual = version_actual
        self._directorio_destino = directorio_destino
        self._urlopen = urlopen
        self._cancelado = False

    def cancelar(self):
        self._cancelado = True

    def ejecutar(self):
        if es_paquete_microsoft_store():
            self.sin_actualizacion.emit()
            return

        try:
            info = consultar_ultima_version(
                repositorio=self._repositorio,
                version_actual=self._version_actual,
                urlopen=self._urlopen,
            )
            if info is None:
                LOGGER.info("Sin actualizaciones disponibles (versión actual v%s).", self._version_actual)
                self.sin_actualizacion.emit()
                return

            LOGGER.info(
                "Nueva versión v%s detectada. Descargando y verificando SHA256...",
                info.version_remota,
            )
            ruta = descargar_y_verificar_actualizacion(
                info,
                directorio_destino=self._directorio_destino,
                version_actual=self._version_actual,
                cancelado_cb=lambda: self._cancelado,
                urlopen=self._urlopen,
            )
            self.actualizacion_lista.emit(info, ruta)
        except Exception as exc:
            LOGGER.warning("Actualización automática abortada silenciosamente: %s", exc)
            self.fallo_silencioso.emit(str(exc))


class TrabajadorConsultaActualizacion(QObject):
    """Consulta en segundo plano sin bloquear la interfaz (compatibilidad)."""

    finalizado = pyqtSignal(object, str)

    def __init__(self, repositorio=REPOSITORIO_GITHUB, version_actual=VERSION_APP):
        super().__init__()
        self._repositorio = repositorio
        self._version_actual = version_actual

    def ejecutar(self):
        if es_paquete_microsoft_store():
            self.finalizado.emit(None, "")
            return
        try:
            info = consultar_ultima_version(
                repositorio=self._repositorio,
                version_actual=self._version_actual,
            )
            self.finalizado.emit(info, "")
        except Exception as exc:
            LOGGER.warning("Fallo al consultar actualizaciones: %s", exc)
            self.finalizado.emit(None, str(exc))


class TrabajadorDescargaActualizacion(QObject):
    """Descarga el instalador en un hilo separado reportando porcentaje (compatibilidad)."""

    progreso = pyqtSignal(int, int)
    completado = pyqtSignal(str)
    fallido = pyqtSignal(str)

    def __init__(self, url_descarga, ruta_destino, sha256_esperado=None):
        super().__init__()
        self._url_descarga = url_descarga
        self._ruta_destino = ruta_destino
        self._sha256_esperado = sha256_esperado
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
                sha256_esperado=self._sha256_esperado,
            )
            self.completado.emit(ruta)
        except Exception as exc:
            LOGGER.warning("Fallo al descargar actualización: %s", exc)
            self.fallido.emit(str(exc))
