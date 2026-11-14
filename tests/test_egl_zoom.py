"""Pruebas de zoom interactivo, paneo y recorte visual del perfil EGL/HGL."""

import os
from pathlib import Path

import pytest
from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QFontDatabase,
    QImage,
    QMouseEvent,
    QPainter,
    QWheelEvent,
)
from PyQt5.QtWidgets import QApplication

from motor.hidraulica import evaluar_tramo
from motor.perfiles import construir_perfil_ruta, perfil_como_serie
from motor.resultados import PerdidaAccesorio
from ui.perfil_egl import WidgetPerfilEGLHGL


class _PintorCapturaZoom(QPainter):
    """Captura textos y rectángulos trazados por WidgetPerfilEGLHGL."""

    def __init__(self, imagen):
        super().__init__(imagen)
        self.textos = []
        self.rects_dibujados = []
        self.polylines_count = 0

    def drawText(self, *args):
        if args and isinstance(args[-1], str):
            self.textos.append(args[-1])
        return super().drawText(*args)

    def drawRect(self, *args):
        if args:
            self.rects_dibujados.append(QRectF(args[0]))
        return super().drawRect(*args)

    def drawPolyline(self, *args):
        self.polylines_count += 1
        return super().drawPolyline(*args)


def _serie_con_perdida_borde_pequena():
    """Genera un sistema donde la pérdida de salida es muy pequeña respecto al desnivel total."""
    prop = dict(rho=1000.0, mu=0.001, g=9.81)
    base = evaluar_tramo(0.02, 100.0, 0.15, 1e-6, 0.0, 0.0, prop, id="T1")
    hv = (base.v ** 2) / (2.0 * prop["g"])
    acc_sal = PerdidaAccesorio("Pérdida de salida de Tanque 1", "T1", 0.0, 0.05, 0.0, 0.05 * hv)
    acc_ent = PerdidaAccesorio("Pérdida de entrada a Tanque 2", "T1", 100.0, 1.0, 0.0, 1.0 * hv)
    tramo = evaluar_tramo(
        0.02,
        100.0,
        0.15,
        1e-6,
        1.05,
        0.0,
        prop,
        id="T1",
        accesorios=(acc_sal, acc_ent),
    )
    perfil = construir_perfil_ruta(
        [tramo],
        20.0,
        10.0,
        etiquetas=["Tanque 1", "Tanque 2"],
    )
    return perfil_como_serie(perfil)


@pytest.fixture
def widget_zoom():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])
    if not QFontDatabase().families():
        fuente = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf"
        if fuente.exists():
            QFontDatabase.addApplicationFont(str(fuente))

    w = WidgetPerfilEGLHGL()
    w.resize(960, 540)
    w.show()
    app.processEvents()
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def _dibujar_en_imagen(w, ancho=960, alto=540, para_exportar=False):
    img = QImage(ancho, alto, QImage.Format_ARGB32)
    pintor = _PintorCapturaZoom(img)
    try:
        w._dibujar_perfil(pintor, QRectF(0, 0, ancho, alto), para_exportar=para_exportar)
    finally:
        pintor.end()
    return pintor.textos, pintor.rects_dibujados


def _enviar_rueda(widget, pos_local, delta_y):
    pos_f = QPointF(pos_local)
    ev = QWheelEvent(
        pos_f,
        QPointF(widget.mapToGlobal(pos_local)),
        QPoint(0, 0),
        QPoint(0, delta_y),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )
    widget.wheelEvent(ev)
    return ev


def test_hud_zoom_visibilidad_y_botones(widget_zoom):
    w = widget_zoom
    assert not w.hud_zoom_frame.isVisible()
    assert w.zoom_factor() == pytest.approx(1.0)
    assert w.lbl_zoom_pct.text() == "100%"

    w.actualizar_datos([_serie_con_perdida_borde_pequena()])
    QApplication.processEvents()
    assert w.hud_zoom_frame.isVisible()
    assert w.btn_ocultar_textos.isVisible()
    assert w.btn_exportar.isVisible()
    assert w.hud_zoom_frame.geometry().right() < w.btn_ocultar_textos.geometry().left()
    assert w.btn_ocultar_textos.geometry().right() < w.btn_exportar.geometry().left()
    assert w.lbl_zoom_pct.text() == "100%"

    w.btn_zoom_in.click()
    assert w.zoom_factor() == pytest.approx(1.25)
    assert w.lbl_zoom_pct.text() == "125%"

    w.btn_zoom_out.click()
    assert w.zoom_factor() == pytest.approx(1.0)
    assert w.lbl_zoom_pct.text() == "100%"

    for _ in range(6):
        w.btn_zoom_in.click()
    assert w.zoom_factor() > 3.5

    w.btn_zoom_reset.click()
    assert w.zoom_factor() == pytest.approx(1.0)
    assert w.lbl_zoom_pct.text() == "100%"

    w.limpiar_datos()
    assert not w.hud_zoom_frame.isVisible()


def test_rueda_mouse_ancla_cursor_y_respeta_scroll_sin_zoom(widget_zoom):
    w = widget_zoom
    w.actualizar_datos([_serie_con_perdida_borde_pequena()])
    _dibujar_en_imagen(w)
    plot = w._ultimo_plot_rect
    assert not plot.isEmpty()

    # Con zoom al 100%, desplazar rueda hacia abajo no debe bloquear scroll padre
    ev_down_100 = _enviar_rueda(w, plot.center().toPoint(), -120)
    assert not ev_down_100.isAccepted()
    assert w.zoom_factor() == pytest.approx(1.0)

    # Desplazar rueda fuera del área de gráfico tampoco consume el evento
    ev_fuera = _enviar_rueda(w, QPoint(10, 10), 120)
    assert not ev_fuera.isAccepted()

    # Al hacer zoom in sobre un punto concreto del gráfico, su coordenada normalizada queda fija bajo el cursor
    cursor = QPoint(int(plot.left() + plot.width() * 0.25), int(plot.top() + plot.height() * 0.20))
    ax, ay = w._punto_a_frac_plot(QPointF(cursor))
    wx_antes = w._vx0 + ax * (w._vx1 - w._vx0)
    wy_antes = w._vy0 + ay * (w._vy1 - w._vy0)

    for _ in range(5):
        ev_up = _enviar_rueda(w, cursor, 120)
        assert ev_up.isAccepted()

    assert w.zoom_factor() == pytest.approx(1.25 ** 5, rel=1e-4)
    wx_despues = w._vx0 + ax * (w._vx1 - w._vx0)
    wy_despues = w._vy0 + ay * (w._vy1 - w._vy0)
    assert wx_despues == pytest.approx(wx_antes, abs=1e-6)
    assert wy_despues == pytest.approx(wy_antes, abs=1e-6)

    # Estando con zoom activo, rueda hacia abajo acerca de vuelta hasta 100%
    for _ in range(5):
        ev_down = _enviar_rueda(w, cursor, -120)
        assert ev_down.isAccepted()
    assert w.zoom_factor() == pytest.approx(1.0)


def test_paneo_arrastre_izquierdo_y_limites(widget_zoom):
    w = widget_zoom
    w.actualizar_datos([_serie_con_perdida_borde_pequena()])
    _dibujar_en_imagen(w)
    plot = w._ultimo_plot_rect

    # Hacer zoom 4x en el centro
    w._fijar_viewport(0.375, 0.625, 0.375, 0.625)
    vx0_ini = w._vx0
    vy0_ini = w._vy0

    p0 = plot.center().toPoint()
    w.mousePressEvent(
        QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(p0), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    )
    assert w._modo_arrastre == "pan"
    assert w.cursor().shape() == Qt.ClosedHandCursor

    # Arrastrar hacia la derecha y abajo: la vista debe desplazarse hacia X menor y Y mayor
    p1 = QPoint(p0.x() + 60, p0.y() + 40)
    w.mouseMoveEvent(
        QMouseEvent(QMouseEvent.MouseMove, QPointF(p1), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    )
    assert w._vx0 < vx0_ini
    assert w._vy0 > vy0_ini
    assert (w._vx1 - w._vx0) == pytest.approx(0.25)
    assert (w._vy1 - w._vy0) == pytest.approx(0.25)

    w.mouseReleaseEvent(
        QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(p1), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    )
    assert w._modo_arrastre is None

    # Arrastrar en exceso no debe salir del dominio [0, 1]
    w.mousePressEvent(
        QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(p0), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    )
    p_ext = QPoint(p0.x() + 5000, p0.y() - 5000)
    w.mouseMoveEvent(
        QMouseEvent(QMouseEvent.MouseMove, QPointF(p_ext), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)
    )
    w.mouseReleaseEvent(
        QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(p_ext), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    )
    assert w._vx0 >= 0.0 and w._vx1 <= 1.0
    assert w._vy0 >= 0.0 and w._vy1 <= 1.0


def test_caja_zoom_boton_derecho_doble_clic_y_cambio_vista(widget_zoom):
    w = widget_zoom
    w.actualizar_datos([_serie_con_perdida_borde_pequena()])
    _dibujar_en_imagen(w)
    plot = w._ultimo_plot_rect

    # Dibujar recuadro en esquina superior izquierda (pérdida de salida del Tanque 1)
    p0 = QPoint(int(plot.left() + 4), int(plot.top() + 10))
    p1 = QPoint(int(plot.left() + plot.width() * 0.12), int(plot.top() + plot.height() * 0.18))

    w.mousePressEvent(
        QMouseEvent(QMouseEvent.MouseButtonPress, QPointF(p0), Qt.RightButton, Qt.RightButton, Qt.NoModifier)
    )
    assert w._modo_arrastre == "box"
    w.mouseMoveEvent(
        QMouseEvent(QMouseEvent.MouseMove, QPointF(p1), Qt.NoButton, Qt.RightButton, Qt.NoModifier)
    )
    _, rects_durante = _dibujar_en_imagen(w, para_exportar=False)
    _, rects_export = _dibujar_en_imagen(w, para_exportar=True)
    assert rects_durante, "Durante el arrastre de caja debe trazarse el recuadro de selección"
    assert not rects_export, "El recuadro de selección no debe dibujarse al exportar PNG"

    w.mouseReleaseEvent(
        QMouseEvent(QMouseEvent.MouseButtonRelease, QPointF(p1), Qt.RightButton, Qt.NoButton, Qt.NoModifier)
    )
    assert w._modo_arrastre is None
    assert w._vx0 == pytest.approx(4.0 / plot.width(), abs=1e-3)
    assert w._vx1 == pytest.approx((plot.width() * 0.12) / plot.width(), abs=1e-2)
    assert w.zoom_factor() > 5.0

    # Cambiar opciones de visualización preserva el zoom actual
    z_antes = w.zoom_factor()
    w.set_mostrar_valores(True)
    w.set_mostrar_hgl(False)
    w.set_mostrar_egl(True)
    assert w.zoom_factor() == pytest.approx(z_antes)

    # Doble clic restablece a 100%
    w.mouseDoubleClickEvent(
        QMouseEvent(QMouseEvent.MouseButtonDblClick, plot.center(), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    )
    assert w.zoom_factor() == pytest.approx(1.0)
    assert w.lbl_zoom_pct.text() == "100%"


def test_zoom_en_perdida_pequena_filtra_estaciones_fuera_y_muestra_escala_fina(widget_zoom):
    w = widget_zoom
    w.actualizar_datos([_serie_con_perdida_borde_pequena()])

    # Hacer zoom intenso alrededor de la esquina de salida (Tanque 1, x cercano a 0, cota ~20 m)
    w._fijar_viewport(0.0, 0.04, 0.80, 0.96)
    textos_zoom_ent, _ = _dibujar_en_imagen(w)

    assert any("Salida de Tanque 1" in t for t in textos_zoom_ent)
    assert not any("Entrada a Tanque 2" in t for t in textos_zoom_ent), (
        f"Las estaciones fuera de la ventana de zoom no deben aparecer: {textos_zoom_ent}"
    )
    # Debe mostrar cotas con precisión fina (>= 2 decimales) y nunca el texto falso "Datum (Ref.)"
    assert any("." in t and " m" in t for t in textos_zoom_ent)
    assert not any("Datum (Ref.)" in t for t in textos_zoom_ent)

    # Hacer zoom en la mitad intermedia de la tubería (sin tanques visibles): debe mostrar ticks X en metros
    w._fijar_viewport(0.35, 0.65, 0.25, 0.75)
    textos_medio, _ = _dibujar_en_imagen(w)
    assert not any("Salida de Tanque 1" in t for t in textos_medio)
    assert not any("Entrada a Tanque 2" in t for t in textos_medio)
    assert any(t.endswith(" m") and t[0].isdigit() for t in textos_medio)


def test_boton_ocultar_textos_muestra_solo_el_grafico(widget_zoom):
    w = widget_zoom
    assert not w.btn_ocultar_textos.isVisible()
    assert not w.ocultar_textos

    serie = _serie_con_perdida_borde_pequena()
    w.actualizar_datos([serie], resumen={"z1": 20.0, "z2": 10.0, "hf_total": 4.0, "deficit": 0.0, "excedente": 6.0})
    w.set_mostrar_valores(True)
    w._fijar_viewport(0.0, 0.8, 0.0, 1.0)
    QApplication.processEvents()

    assert w.btn_ocultar_textos.isVisible()
    textos_con, _ = _dibujar_en_imagen(w)
    assert any("Pérdida por fricción" in t for t in textos_con)
    assert textos_con.count("Salida de Tanque 1") == 2

    # Al pulsar el botón se ocultan las etiquetas/anotaciones sobre el gráfico pero se mantienen ejes y estaciones
    w.btn_ocultar_textos.click()
    assert w.btn_ocultar_textos.isChecked()
    assert w.ocultar_textos is True
    assert w.zoom_factor() == pytest.approx(1.0 / 0.8)

    for exportar in (False, True):
        img = QImage(960, 540, QImage.Format_ARGB32)
        pintor = _PintorCapturaZoom(img)
        try:
            w._dibujar_perfil(pintor, QRectF(0, 0, 960, 540), para_exportar=exportar)
        finally:
            pintor.end()
        assert "Altura / Cota Hidráulica [m]" in pintor.textos
        assert "Estaciones del Sistema Hidráulico" in pintor.textos
        assert pintor.textos.count("Salida de Tanque 1") == 1
        assert any(t.endswith(" m") and "z₁" not in t and "z₂" not in t or "(z₁)" in t for t in pintor.textos)
        for texto_oculto in (
            "Pérdida por fricción",
            "Pérdida de salida",
            "Energía excedente",
            "Nivel Inicial",
            "Esquemático",
        ):
            assert not any(texto_oculto in t for t in pintor.textos), (
                f"No debía mostrarse '{texto_oculto}' con Ocultar textos activo: {pintor.textos}"
            )
        assert pintor.polylines_count >= 2, "Las líneas EGL y HGL deben seguir trazándose"

    # Con régimen de déficit también mantiene ejes/estaciones y oculta textos internos sobre el gráfico
    w.actualizar_datos(
        [serie],
        resumen={"z1": 10.0, "z2": 20.0, "hf_total": 12.0, "deficit": 22.0, "excedente": 0.0},
    )
    img_def = QImage(960, 540, QImage.Format_ARGB32)
    pintor_def = _PintorCapturaZoom(img_def)
    try:
        w._dibujar_perfil(pintor_def, QRectF(0, 0, 960, 540), para_exportar=False)
    finally:
        pintor_def.end()
    assert "Altura / Cota Hidráulica [m]" in pintor_def.textos
    assert pintor_def.textos.count("Salida de Tanque 1") == 1
    assert not any("Energía faltante" in t or "Nivel Tanque 2" in t for t in pintor_def.textos)
    assert pintor_def.polylines_count >= 2

    # Al desactivar vuelven todas las etiquetas flotantes sobre las curvas
    w.btn_ocultar_textos.click()
    assert not w.ocultar_textos
    textos_restaurados, _ = _dibujar_en_imagen(w)
    assert any("Pérdida por fricción" in t for t in textos_restaurados)
    assert textos_restaurados.count("Salida de Tanque 1") == 2

    w.limpiar_datos()
    assert not w.btn_ocultar_textos.isVisible()

