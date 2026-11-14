"""Pruebas de extensión propia .sff, ícono gota de agua en Windows y apertura CLI."""

import json
import os
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication

from main import cargar_archivo_desde_argumentos
from ui import asociacion_archivos as mod_asoc
from ui.constantes import (
    ARCHIVO_ICONO_PROYECTO,
    DESCRIPCION_TIPO_PROYECTO,
    EXTENSION_PROYECTO,
    PROGID_PROYECTO,
)
from ui.ventana.principal import MainWindow


class _FakeRegKey:
    def __init__(self, store, subclave):
        self._store = store
        self._subclave = subclave

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeWinreg:
    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.datos = {}
        self.escrituras = 0

    def OpenKey(self, raiz, subclave, _res, _sam):
        if subclave not in self.datos:
            raise FileNotFoundError(subclave)
        return _FakeRegKey(self.datos, subclave)

    def QueryValueEx(self, key, nombre):
        clave_nombre = nombre or ""
        if clave_nombre not in self.datos[key._subclave]:
            raise FileNotFoundError(clave_nombre)
        return self.datos[key._subclave][clave_nombre], self.REG_SZ

    def CreateKeyEx(self, raiz, subclave, _res, _sam):
        self.datos.setdefault(subclave, {})
        return _FakeRegKey(self.datos, subclave)

    def SetValueEx(self, key, nombre, _res, _tipo, valor):
        self.escrituras += 1
        self.datos[key._subclave][nombre or ""] = valor


@pytest.fixture
def ventana():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def test_registrar_asociacion_no_muta_en_entorno_test():
    assert mod_asoc.registrar_asociacion_proyecto(forzar=False) is False


def test_registrar_asociacion_sff_y_copia_persistente_icono(tmp_path, monkeypatch):
    fake_reg = _FakeWinreg()
    notificaciones = []
    monkeypatch.setattr(mod_asoc, "_notificar_shell_windows", lambda: notificaciones.append(True))

    carpeta_local = tmp_path / "appdata"
    icono_fuente = tmp_path / ARCHIVO_ICONO_PROYECTO
    icono_fuente.write_bytes(b"ico-gota-v1")

    ok = mod_asoc.registrar_asociacion_proyecto(
        forzar=True,
        modulo_winreg=fake_reg,
        raiz_registro=fake_reg.HKEY_CURRENT_USER,
        carpeta_icono=str(carpeta_local),
        archivo_origen=str(icono_fuente),
        comando='"C:\\app\\Simulador.exe" "%1"',
    )
    assert ok is True
    assert len(notificaciones) == 1

    icono_destino = carpeta_local / ARCHIVO_ICONO_PROYECTO
    assert icono_destino.is_file()
    assert icono_destino.read_bytes() == b"ico-gota-v1"

    ext_key = fake_reg.datos[f"Software\\Classes\\{EXTENSION_PROYECTO}"]
    assert ext_key[""] == PROGID_PROYECTO
    assert ext_key["Content Type"] == "application/json"
    assert ext_key["PerceivedType"] == "document"

    prog_sub = f"Software\\Classes\\{PROGID_PROYECTO}"
    assert fake_reg.datos[prog_sub][""] == DESCRIPCION_TIPO_PROYECTO
    assert fake_reg.datos[f"{prog_sub}\\DefaultIcon"][""] == f'"{icono_destino}",0'
    assert fake_reg.datos[f"{prog_sub}\\shell\\open\\command"][""] == '"C:\\app\\Simulador.exe" "%1"'

    # Idempotente: una segunda ejecución sin cambios no reescribe registro ni vuelve a notificar
    escrituras_previas = fake_reg.escrituras
    ok2 = mod_asoc.registrar_asociacion_proyecto(
        forzar=True,
        modulo_winreg=fake_reg,
        raiz_registro=fake_reg.HKEY_CURRENT_USER,
        carpeta_icono=str(carpeta_local),
        archivo_origen=str(icono_fuente),
        comando='"C:\\app\\Simulador.exe" "%1"',
    )
    assert ok2 is True
    assert fake_reg.escrituras == escrituras_previas
    assert len(notificaciones) == 1


def test_guardar_dialogo_usa_extension_sff_y_recarga_ambos_formatos(tmp_path, monkeypatch, ventana):
    w = ventana
    w._cargar_ejemplo_friccion_simple()

    destino_sin_ext = tmp_path / "red_prueba"
    monkeypatch.setattr(
        "ui.ventana.barra_herramientas.QFileDialog.getSaveFileName",
        lambda *_a, **_kw: (
            str(destino_sin_ext),
            f"Proyecto de Simulador (*{EXTENSION_PROYECTO})",
        ),
    )

    assert w.guardar_proyecto() is True
    archivo_sff = tmp_path / f"red_prueba{EXTENSION_PROYECTO}"
    assert archivo_sff.is_file()
    datos = json.loads(archivo_sff.read_text(encoding="utf-8"))
    assert len(datos["tanques"]) == 2

    # Si elige explícitamente JSON sin extensión, respeta .json
    destino_json_sin_ext = tmp_path / "red_legacy"
    monkeypatch.setattr(
        "ui.ventana.barra_herramientas.QFileDialog.getSaveFileName",
        lambda *_a, **_kw: (str(destino_json_sin_ext), "Archivos JSON (*.json)"),
    )
    assert w.guardar_proyecto() is True
    archivo_json_auto = tmp_path / "red_legacy.json"
    assert archivo_json_auto.is_file()

    # Cargar vía CLI (doble clic desde Windows) y compatibilidad con .json heredados
    assert cargar_archivo_desde_argumentos(w, ["main.py", "--flag", str(archivo_sff)]) is True
    assert len(w._serializar_proyecto()["tanques"]) == 2
    assert cargar_archivo_desde_argumentos(w, ["main.py", str(archivo_json_auto)]) is True
    assert cargar_archivo_desde_argumentos(w, ["main.py", str(tmp_path / "no_existe.sff")]) is False


def test_build_exe_incluye_icono_gota_para_archivos():
    build_py = (Path(__file__).resolve().parent.parent / "build_exe.py").read_text(encoding="utf-8")
    assert f"--add-data={ARCHIVO_ICONO_PROYECTO};." in build_py
