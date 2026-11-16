"""Pruebas de cabecera sin duplicados, íconos multi-tamaño y auto-actualizador."""

import io
import json
import os
from pathlib import Path

import pytest
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QLabel

from ui.actualizador import (
    InfoActualizacion,
    consultar_ultima_version,
    descargar_instalador,
    es_version_mayor,
    parsear_version,
    seleccionar_asset_instalador,
)
from ui.constantes import ARCHIVO_ICONO, ARCHIVO_ICONO_PROYECTO, VERSION_APP
from ui.recursos import ruta_recurso
from ui.ventana.principal import MainWindow


class _FakeResponse:
    def __init__(self, payload, headers=None):
        self._buf = io.BytesIO(payload)
        self.headers = headers or {}

    def read(self, size=-1):
        return self._buf.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


@pytest.fixture
def ventana():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def test_cabecera_sin_titulo_duplicado_y_con_version(ventana):
    w = ventana
    assert w.windowTitle() == "Simulador de Fluidos  /  Ingeniería Química CAD"

    etiquetas_header = [lbl.text() for lbl in w.header_bar.findChildren(QLabel)]
    assert not any("Simulador de Fluidos" in texto for texto in etiquetas_header)
    assert not any("Ingeniería Química CAD" in texto for texto in etiquetas_header)
    assert w.lbl_version.text() == f"Versión {VERSION_APP}"
    assert w.btn_buscar_actualizacion.text() == "Buscar actualizaciones"

    info = InfoActualizacion(
        version_remota="9.9.9",
        url_release="https://github.com/luisacevedo15/Simulador-de-fluidos/releases/tag/v9.9.9",
        notas="Mejoras de prueba",
        nombre_asset="Simulador_Flujo_de_Fluidos_Setup.exe",
        url_descarga="https://example.com/Setup.exe",
        tamano_bytes=1024,
    )
    w._verificacion_manual_act = False
    w._on_resultado_actualizacion(info, "")
    assert w.btn_buscar_actualizacion.text() == "Actualizar a v9.9.9"
    assert w.btn_buscar_actualizacion.property("updateAvailable") == "true"


def test_iconos_contienen_multiples_resoluciones_windows(ventana):
    esperados = {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}
    for archivo in (ARCHIVO_ICONO, ARCHIVO_ICONO_PROYECTO):
        icono = QIcon(ruta_recurso(archivo))
        assert not icono.isNull()
        tamanos = {(sz.width(), sz.height()) for sz in icono.availableSizes()}
        assert esperados.issubset(tamanos), f"{archivo} solo tiene {tamanos}"


def test_comparacion_versiones_semver():
    assert parsear_version("v1.0.2") == (1, 0, 2)
    assert es_version_mayor("v1.0.2", "1.0.1") is True
    assert es_version_mayor("1.10.0", "1.2.0") is True
    assert es_version_mayor("v1.0.1", "1.0.1") is False
    assert es_version_mayor("v1.0.0", "1.0.1") is False


def test_seleccionar_asset_prefiere_setup():
    release = {
        "assets": [
            {"name": "Simulador.exe", "browser_download_url": "https://example.com/a.exe", "size": 10},
            {
                "name": "Simulador_Flujo_de_Fluidos_Setup.exe",
                "browser_download_url": "https://example.com/setup.exe",
                "size": 20,
            },
        ]
    }
    elegido = seleccionar_asset_instalador(release)
    assert elegido["name"] == "Simulador_Flujo_de_Fluidos_Setup.exe"
    assert seleccionar_asset_instalador({"assets": [{"name": "codigo.zip", "browser_download_url": "x"}]}) is None


def test_consultar_ultima_version_mock():
    payload = json.dumps(
        {
            "tag_name": "v2.0.0",
            "html_url": "https://github.com/luisacevedo15/Simulador-de-fluidos/releases/tag/v2.0.0",
            "body": "Notas de versión",
            "assets": [
                {
                    "name": "Simulador_Flujo_de_Fluidos_Setup.exe",
                    "browser_download_url": "https://example.com/setup.exe",
                    "size": 12345,
                }
            ],
        }
    ).encode("utf-8")

    info = consultar_ultima_version(
        version_actual="1.0.1",
        urlopen=lambda *_a, **_kw: _FakeResponse(payload),
    )
    assert info is not None
    assert info.version_remota == "2.0.0"
    assert info.nombre_asset == "Simulador_Flujo_de_Fluidos_Setup.exe"

    sin_cambio = consultar_ultima_version(
        version_actual="2.0.0",
        urlopen=lambda *_a, **_kw: _FakeResponse(payload),
    )
    assert sin_cambio is None


def test_descargar_instalador_valida_pe(tmp_path):
    destino = tmp_path / "Setup.exe"
    contenido = b"MZ" + b"\x00" * 1024
    progresos = []
    resultado = descargar_instalador(
        "https://example.com/Setup.exe",
        str(destino),
        progreso_cb=lambda rec, tot: progresos.append((rec, tot)),
        urlopen=lambda *_a, **_kw: _FakeResponse(contenido, {"Content-Length": str(len(contenido))}),
    )
    assert Path(resultado).read_bytes() == contenido
    assert progresos == [(len(contenido), len(contenido))]

    destino_bad = tmp_path / "Bad.exe"
    with pytest.raises(ValueError):
        descargar_instalador(
            "https://example.com/Bad.exe",
            str(destino_bad),
            urlopen=lambda *_a, **_kw: _FakeResponse(b"<html>not an exe</html>"),
        )
    assert not destino_bad.exists()
    assert not (tmp_path / "Bad.exe.part").exists()
