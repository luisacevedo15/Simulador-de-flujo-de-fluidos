"""Pruebas de diagrama de energía (EGL/HGL) para sistemas multitubería y respaldo."""

import os
from pathlib import Path

import pytest
from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QImage, QPainter, QPen
from PyQt5.QtWidgets import QApplication, QDialog

from ui.graficos import NodoUnionGrafico, TanqueGrafico, TuberiaGrafica
from ui.perfil_egl import WidgetPerfilEGLHGL
from ui.ventana import resolucion as mod_resolucion
from ui.ventana.principal import MainWindow


class _DialogoAutoAceptar:
    def __init__(self, ramas, q_total, parent=None):
        self._q_total = q_total

    def exec_(self):
        return QDialog.Accepted

    def valores(self):
        return 0, self._q_total * 0.5


class _PintorCaptura(QPainter):
    """Captura textos y trazos de curvas EGL dibujados fuera de pantalla."""

    def __init__(self, imagen):
        super().__init__(imagen)
        self.textos = []
        self.colores_lineas = []

    def drawText(self, *args):
        if args and isinstance(args[-1], str):
            self.textos.append(args[-1])
        return super().drawText(*args)

    def drawPolyline(self, *args):
        pen = self.pen()
        if isinstance(pen, QPen) and pen.style():
            self.colores_lineas.append((pen.color().name().lower(), int(pen.style())))
        return super().drawPolyline(*args)


def _capturar_dibujo(widget, ancho=1100, alto=620, exportar=False):
    imagen = QImage(ancho, alto, QImage.Format_ARGB32)
    pintor = _PintorCaptura(imagen)
    try:
        widget._dibujar_perfil(pintor, QRectF(0, 0, ancho, alto), para_exportar=exportar)
    finally:
        pintor.end()
    return pintor.textos, pintor.colores_lineas


@pytest.fixture
def ventana():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    yield w
    w.canvas_view.scene().selectionChanged.disconnect()
    w.close()
    w.deleteLater()
    app.processEvents()


def _agregar_tanque(scene, x, y, tid, z):
    t = TanqueGrafico(x, y, id_tanque=tid)
    t.elevacion_z = z
    t.abierto_atmosfera = True
    scene.addItem(t)
    return t


def _agregar_tuberia(scene, n1, n2, tid, nombre, L, D, Q=0.0, eps=0.00015):
    tub = TuberiaGrafica(n1, n2, id_tuberia=tid)
    tub.nombre = nombre
    tub.longitud = L
    tub.diametro = D
    tub.caudal_Q = Q
    tub.rugosidad = eps
    scene.addItem(tub)
    return tub


def test_respaldo_diagrama_energia_existe_y_sin_py_importables():
    raiz = Path(__file__).resolve().parent.parent
    bkp = raiz / "_respaldo_diagrama_energia"
    assert bkp.is_dir()
    esperados = {
        "motor_perfiles.py.bak",
        "ui_perfil_egl.py.bak",
        "ui_ventana_bernoulli.py.bak",
        "ui_ventana_bombas.py.bak",
        "ui_ventana_interfaz.py.bak",
        "ui_ventana_ramificadas.py.bak",
        "ui_ventana_resolucion.py.bak",
        "ui_ventana_vistas.py.bak",
    }
    presentes = {p.name for p in bkp.iterdir()}
    assert esperados <= presentes
    assert not any(p.suffix == ".py" for p in bkp.iterdir())


def test_egl_paralelo_converge_sin_duplicar_destino_colores_y_filtro(ventana, monkeypatch):
    monkeypatch.setattr(mod_resolucion, "DialogoSuposicionParalelo", _DialogoAutoAceptar)
    w = ventana
    scene = w.canvas_view.scene()
    t1 = _agregar_tanque(scene, 100, 200, 1, 20.0)
    t2 = _agregar_tanque(scene, 600, 200, 2, 12.0)
    r1 = _agregar_tuberia(scene, t1, t2, 1, "TUBERÍA 1 (RAMAL A)", L=100.0, D=0.20, Q=0.05)
    r2 = _agregar_tuberia(scene, t1, t2, 2, "TUBERÍA 2 (RAMAL B)", L=120.0, D=0.15, Q=0.03)

    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)
    w.combo_punto2.setCurrentIndex(1)
    w._on_resolver_bernoulli()

    assert len(w.egl_chart.series) == 2
    # Contrato intacto de _series_para_dibujar
    assert w.egl_chart._series_para_dibujar()[0] is w.egl_chart.series[0]["puntos"]
    c0 = w.egl_chart.color_serie(0)
    c1 = w.egl_chart.color_serie(1)
    assert c0 != c1

    # En modo didáctico: convergen a UN único "Entrada a Tanque 2", ambos ramales rotulados
    # con su longitud y hay banda de energía excedente
    w.egl_chart.set_mostrar_valores(False)
    textos, colores = _capturar_dibujo(w.egl_chart)
    assert textos.count("Entrada a Tanque 2") == 1, textos
    assert [etq for etq, _ in w.egl_chart._estaciones_rects].count("Salida de Tanque 1") == 1
    assert textos.count("Salida de Tanque 1") == 2, textos
    assert any("TUBERÍA 1 (RAMAL A)" in t and "L=100 m" in t and "hf =" in t for t in textos), textos
    assert any("TUBERÍA 2 (RAMAL B)" in t and "L=120 m" in t and "hf =" in t for t in textos), textos
    assert any("Nivel Tanque 2" in t for t in textos), textos
    assert any("Energía excedente" in t for t in textos), textos
    egl_solidos = {c for c, st in colores if st == 1}
    assert {c0.lower(), c1.lower()} <= egl_solidos

    # Selector de rutas en UI visible para multi-ruta y funcional
    w._cambiar_vista_central("curvas")
    QApplication.processEvents()
    assert w.barra_rutas_egl.isVisible()
    assert len(w._botones_rutas_egl) == 3  # Todas + Ramal A + Ramal B

    w._on_seleccionar_ruta_egl(1)
    assert w.egl_chart.ruta_seleccionada == 1
    textos_b, _ = _capturar_dibujo(w.egl_chart)
    assert any("TUBERÍA 2 (RAMAL B)" in t for t in textos_b), textos_b
    assert not any("TUBERÍA 1 (RAMAL A)" in t for t in textos_b), textos_b

    w._on_seleccionar_ruta_egl(None)
    assert w.egl_chart.ruta_seleccionada is None

    # En Valores exactos: muestra longitudes físicas reales sin explotar ni solapar
    w.egl_chart.set_mostrar_valores(True)
    textos_ex, _ = _capturar_dibujo(w.egl_chart)
    assert any(t == "100 m" or t.endswith("· 100 m") for t in textos_ex), textos_ex
    assert any(t == "120 m" or t.endswith("· 120 m") for t in textos_ex), textos_ex
    assert any("z₁ = 20.00 m" in t for t in textos_ex), textos_ex
    assert any("z₂ = 12.00 m" in t for t in textos_ex), textos_ex

    # Exportar PNG dibuja leyenda con ambas rutas
    textos_exp, _ = _capturar_dibujo(w.egl_chart, exportar=True)
    assert any("TUBERÍA 1 (RAMAL A)" in t for t in textos_exp)
    assert any("TUBERÍA 2 (RAMAL B)" in t for t in textos_exp)


def test_egl_paralelo_serie_troncal_compartida_colores_y_estaciones(ventana, monkeypatch):
    monkeypatch.setattr(mod_resolucion, "DialogoSuposicionParalelo", _DialogoAutoAceptar)
    w = ventana
    scene = w.canvas_view.scene()
    t1 = _agregar_tanque(scene, 50, 200, 1, 25.0)
    u = NodoUnionGrafico(250, 200, id_union=1)
    scene.addItem(u)
    t2 = _agregar_tanque(scene, 650, 200, 2, 10.0)

    _agregar_tuberia(scene, t1, u, 1, "Troncal 1", L=50.0, D=0.25, Q=0.06)
    _agregar_tuberia(scene, u, t2, 2, "Ramal A", L=100.0, D=0.15, Q=0.04)
    _agregar_tuberia(scene, u, t2, 3, "Ramal B", L=150.0, D=0.12, Q=0.02)

    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)
    w.combo_punto2.setCurrentIndex(1)
    w._on_resolver_bernoulli()

    assert len(w.egl_chart.series) == 2
    assert w.egl_chart.series[0]["nombre"] != w.egl_chart.series[1]["nombre"]
    assert w.egl_chart.color_serie(0) != w.egl_chart.color_serie(1)

    textos, _ = _capturar_dibujo(w.egl_chart)
    assert textos.count("Entrada a Tanque 2") == 1, textos
    # La troncal compartida no se duplica
    chips_troncal = [t for t in textos if "Troncal 1" in t and "hf =" in t]
    assert len(chips_troncal) == 1, chips_troncal
    assert any("Ramal A" in t and "L=100 m" in t for t in textos), textos
    assert any("Ramal B" in t and "L=150 m" in t for t in textos), textos


def test_egl_ramificada_conserva_destinos_cercanos_y_serie_cambio_diametro(ventana):
    w = ventana
    scene = w.canvas_view.scene()
    t1 = _agregar_tanque(scene, 100, 200, 1, 30.0)
    u = NodoUnionGrafico(320, 200, id_union=1)
    scene.addItem(u)
    t2 = _agregar_tanque(scene, 600, 120, 2, 18.0)
    t3 = _agregar_tanque(scene, 600, 300, 3, 12.0)

    _agregar_tuberia(scene, t1, u, 1, "Alimentación", L=100.0, D=0.25)
    # Longitudes muy cercanas a propósito para verificar escalonado sin pérdida de etiqueta
    _agregar_tuberia(scene, u, t2, 2, "Descarga T2", L=100.0, D=0.15)
    _agregar_tuberia(scene, u, t3, 3, "Descarga T3", L=105.0, D=0.15)

    w._refrescar_combos_dashboard()
    w._resolver_union_ramificada(u)

    assert len(w.egl_chart.series) == 2
    assert w.egl_chart.color_serie(0) != w.egl_chart.color_serie(1)
    reg = w.egl_chart._resumen_regimen()
    assert not reg["hay_exceso"]

    textos, _ = _capturar_dibujo(w.egl_chart)
    assert any("Entrada a Tanque 2" in t for t in textos), textos
    assert any("Entrada a Tanque 3" in t for t in textos), textos
    assert any("Descarga T2" in t for t in textos), textos
    assert any("Descarga T3" in t for t in textos), textos

    # Serie con cambio de diámetro muestra Δ(v²/2g)
    w2 = WidgetPerfilEGLHGL()
    from motor.hidraulica import evaluar_tramo
    from motor.perfiles import construir_perfil_ruta, perfil_como_serie

    fluido = dict(rho=1000.0, mu=0.001, g=9.81)
    tr1 = evaluar_tramo(0.04, 80.0, 0.25, 0.00015, 0.0, 0.0, fluido, id="1")
    tr2 = evaluar_tramo(0.04, 80.0, 0.12, 0.00015, 0.0, 0.0, fluido, id="2")
    perfil_s = construir_perfil_ruta(
        [tr1, tr2], 25.0, 25.0 - tr1.hf_total - tr2.hf_total,
        etiquetas=["Tanque 1", "Reducción", "Tanque 2"],
    )
    serie_s = perfil_como_serie(perfil_s)
    serie_s["nombres_tramos"] = {"1": "Tramo grueso", "2": "Tramo angosto"}
    w2.actualizar_datos([serie_s])
    textos_s, _ = _capturar_dibujo(w2)
    assert any("Cambio de diámetro" in t and "Δ(v²/2g)" in t for t in textos_s), textos_s
    w2.close()
