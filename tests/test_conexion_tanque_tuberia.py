"""Pruebas de conexión Entrada/Salida entre tanque y tubería (UI, hidráulica, EGL, JSON y lienzo)."""

import os

import pytest
from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtWidgets import QApplication

from motor.hidraulica import evaluar_tramo
from ui.graficos import AccesorioGrafico, TanqueGrafico, TuberiaGrafica
from ui.validacion_datos import validar_proyecto
from ui.ventana.principal import MainWindow


class _PintorCanvas(QPainter):
    def __init__(self, img):
        super().__init__(img)
        self.textos = []

    def drawText(self, *args):
        if args and isinstance(args[-1], str):
            self.textos.append(args[-1])
        return super().drawText(*args)


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


def _armar_tanque_tuberia_tanque(w, z1=20.0, z2=12.0, L=100.0, D=0.20, Q=0.05):
    sc = w.canvas_view.scene()
    t1 = TanqueGrafico(80, 180, id_tanque=1)
    t1.elevacion_z = z1
    t1.abierto_atmosfera = True
    t1.actualizar_etiqueta()
    sc.addItem(t1)

    t2 = TanqueGrafico(520, 180, id_tanque=2)
    t2.elevacion_z = z2
    t2.abierto_atmosfera = True
    t2.actualizar_etiqueta()
    sc.addItem(t2)

    tub = TuberiaGrafica(t1, t2, id_tuberia=1)
    tub.longitud = L
    tub.diametro = D
    tub.caudal_Q = Q
    tub.rugosidad = 0.00015
    tub.actualizar_etiqueta()
    sc.addItem(tub)
    return sc, t1, t2, tub


def test_ui_conexion_entrada_salida_en_tuberia_y_tanque(ventana):
    w = ventana
    sc, t1, t2, tub = _armar_tanque_tuberia_tanque(w)
    assert tub.sumatoria_K == 0.0

    # Seleccionar la tubería NO debe mostrar controles de conexión tanque-tubería ni mezclar K de borde en accesorios
    sc.clearSelection()
    tub.setSelected(True)
    QApplication.processEvents()

    assert "conexiones_tanque" not in w.campos_tuberia
    assert "K total = 0," in w.label_accesorios_tuberia.text()

    # Seleccionar Tanque 1: solo muestra condición entre tanque y tubería y valor de K (sin tipo de borde)
    sc.clearSelection()
    t1.setSelected(True)
    QApplication.processEvents()

    conns_t1 = w.campos_tanque["conexiones"]
    assert len(conns_t1) == 1
    c_orig = conns_t1[0]
    assert set(c_orig) == {"card", "modo", "k", "panel_k", "info_entrada"}
    assert c_orig["modo"].currentData() == "ninguno"
    assert c_orig["panel_k"].isHidden()

    # Elegir Salida en Tanque 1 (Tanque 1 -> Tubería)
    idx_sal = c_orig["modo"].findData("salida")
    c_orig["modo"].setCurrentIndex(idx_sal)
    QApplication.processEvents()

    assert not c_orig["panel_k"].isHidden()
    assert c_orig["k"].isEnabled()
    assert tub.conexion_origen["modo"] == "salida"
    assert tub.conexion_origen["tipo_borde"] == ""
    assert tub.conexion_origen["K"] == pytest.approx(0.5)
    assert tub.sumatoria_K == pytest.approx(0.5)

    # Editar K directamente sin selector de borde
    c_orig["k"].setText("0.35")
    c_orig["k"].textEdited.emit("0.35")

    assert tub.conexion_origen == {
        "modo": "salida",
        "tipo_borde": "",
        "K": 0.35,
    }

    # Valor inválido de K no sobrescribe el válido
    c_orig["k"].textEdited.emit("-1")
    assert w._ultimo_error_validacion is not None
    assert tub.conexion_origen["K"] == pytest.approx(0.35)

    # Seleccionar Tanque 2 y elegir Entrada (Tubería -> Tanque 2): K = 1 fijo
    sc.clearSelection()
    t2.setSelected(True)
    QApplication.processEvents()
    c_dest = w.campos_tanque["conexiones"][0]
    idx_ent = c_dest["modo"].findData("entrada")
    c_dest["modo"].setCurrentIndex(idx_ent)
    QApplication.processEvents()

    assert not c_dest["panel_k"].isHidden()
    assert not c_dest["k"].isEnabled()
    assert float(c_dest["k"].text()) == pytest.approx(1.0)
    assert tub.conexion_destino == {"modo": "entrada", "tipo_borde": "", "K": 1.0}
    assert tub.sumatoria_K == pytest.approx(1.35)
    assert tub.sumatoria_K_bordes == pytest.approx(1.35)
    assert tub.sumatoria_K_accesorios == pytest.approx(0.0)

    # Al volver a la tubería, la etiqueta de accesorios no incluye las pérdidas por bordes
    sc.clearSelection()
    tub.setSelected(True)
    QApplication.processEvents()
    assert "K total = 0," in w.label_accesorios_tuberia.text()


def test_calculo_egl_y_canvas_con_entrada_salida(ventana):
    w = ventana
    sc, t1, t2, tub = _armar_tanque_tuberia_tanque(w)
    tub.establecer_conexion_tanque("origen", "salida", "Arista viva / borde recto", 0.5)
    tub.establecer_conexion_tanque("destino", "entrada")

    valvula = AccesorioGrafico(300, 180, forma_visual="Válvula", tipo_perdida="K", valor=2.0)
    sc.addItem(valvula)
    valvula.anclar_a(tub)

    assert tub.sumatoria_K == pytest.approx(3.5)

    esperado = evaluar_tramo(
        0.05, 100.0, 0.20, 0.00015, 3.5, 0.0,
        dict(rho=w.fluido_rho, mu=w.fluido_mu, g=9.81), id="1",
    )
    t2.elevacion_z = 20.0 - esperado.hf_total
    t2.actualizar_etiqueta()

    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)
    w.combo_punto2.setCurrentIndex(1)
    w._on_resolver_bernoulli()

    assert tub.hf_loc_calculado == pytest.approx(esperado.hf_localizada, rel=1e-12)
    assert tub.hf_calculado == pytest.approx(esperado.hf_total, rel=1e-12)

    # Tabla CAD refleja ΣK completo
    celdas, _ = w._fila_tabla_cad_tuberia(tub, 0.05, tub.hf_calculado)
    assert "ΣK = 3.50" in celdas[0]

    # Perfil EGL separa las pérdidas por bordes de los accesorios y simplifica sus etiquetas
    assert len(w.egl_chart.series) == 1
    perfil = w.egl_chart.series[0]["perfil"]
    assert perfil.estado == "OK"
    etiq_acc = [pt.etiqueta for pt in perfil.puntos if pt.tipo == "accesorio"]
    etiq_bordes = [pt.etiqueta for pt in perfil.puntos if pt.tipo == "borde"]
    assert etiq_acc == ["Accesorio Válvula"]
    assert etiq_bordes == ["Pérdida de salida de Tanque 1", "Pérdida de entrada a Tanque 2"]

    # La leyenda incluye Entrada / Salida cuando existen pérdidas por bordes y la barra separa las 3 pérdidas
    claves_ley = [item[0] for item in w.egl_chart.elementos_leyenda()]
    assert "entrada_salida" in claves_ley
    assert "Bordes (Ent./Sal.):" in w.lbl_bordes.text()
    assert "0.0%" not in w.lbl_bordes.text()
    assert "Accesorios:" in w.lbl_localizada.text()
    assert "0.0%" not in w.lbl_localizada.text()

    # Renderizado en el lienzo dibuja las pastillas Sal. K=0.5 y Ent. K=1 sin errores
    img = QImage(900, 500, QImage.Format_ARGB32)
    p = _PintorCanvas(img)
    try:
        sc.render(p, QRectF(0, 0, 900, 500), QRectF(0, 0, 900, 500))
    finally:
        p.end()
    assert any("Sal. K=0.5" in txt for txt in p.textos), p.textos
    assert any("Ent. K=1" in txt for txt in p.textos), p.textos


def test_persistencia_json_validacion_y_dividir_recombinar(ventana):
    w = ventana
    sc, t1, t2, tub = _armar_tanque_tuberia_tanque(w)
    tub.establecer_conexion_tanque("origen", "salida", "Tubería reentrante (proyectada)", 0.8)
    tub.establecer_conexion_tanque("destino", "entrada")

    proyecto = w._serializar_proyecto()
    assert proyecto["tuberias"][0]["conexion_origen"]["modo"] == "salida"
    assert proyecto["tuberias"][0]["conexion_origen"]["K"] == pytest.approx(0.8)
    assert proyecto["tuberias"][0]["conexion_destino"]["modo"] == "entrada"
    assert proyecto["tuberias"][0]["conexion_destino"]["K"] == pytest.approx(1.0)

    # Validación rechaza modos o K negativos en conexiones de tanque
    invalido = {**proyecto, "tuberias": [{**proyecto["tuberias"][0], "conexion_origen": {"modo": "salida", "K": -0.5}}]}
    with pytest.raises(ValueError):
        validar_proyecto(invalido, 1000.0)
    invalido_modo = {**proyecto, "tuberias": [{**proyecto["tuberias"][0], "conexion_origen": {"modo": "raro", "K": 0.5}}]}
    with pytest.raises(ValueError):
        validar_proyecto(invalido_modo, 1000.0)

    # Deserializar restaura exactamente las conexiones y la sumatoria K
    w._deserializar_proyecto(proyecto)
    tub_rest = next(i for i in w.canvas_view.scene().items() if isinstance(i, TuberiaGrafica))
    assert tub_rest.conexion_origen["modo"] == "salida"
    assert tub_rest.conexion_origen["K"] == pytest.approx(0.8)
    assert tub_rest.conexion_destino["modo"] == "entrada"
    assert tub_rest.sumatoria_K == pytest.approx(1.8)

    # Dividir con una reducción conserva origen en tramo 1 y destino en tramo 2; recombinar los reúne
    sc2 = w.canvas_view.scene()
    red = AccesorioGrafico(300, 180, forma_visual="Reducción", tipo_perdida="K", valor=0.3)
    sc2.addItem(red)
    t_izq, t_der = tub_rest.dividir_por_nodo(red, sc2)
    assert t_izq.conexion_origen["modo"] == "salida"
    assert t_izq.conexion_origen["K"] == pytest.approx(0.8)
    assert t_izq.conexion_destino["modo"] == "ninguno"
    assert t_der.conexion_origen["modo"] == "ninguno"
    assert t_der.conexion_destino["modo"] == "entrada"
    assert t_der.conexion_destino["K"] == pytest.approx(1.0)

    recomb = TuberiaGrafica.recombinar_desde_nodo(red, sc2)
    assert recomb.conexion_origen["modo"] == "salida"
    assert recomb.conexion_origen["K"] == pytest.approx(0.8)
    assert recomb.conexion_destino["modo"] == "entrada"
    assert recomb.conexion_destino["K"] == pytest.approx(1.0)


def test_egl_etiquetas_bordes_y_distribucion_tres_perdidas(ventana):
    w = ventana
    sc, t1, t2, tub = _armar_tanque_tuberia_tanque(w, z1=10.0, z2=0.0, L=10.0, D=0.10, Q=0.06297)
    tub.establecer_conexion_tanque("origen", "salida", "", 0.8)
    tub.establecer_conexion_tanque("destino", "entrada")

    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)
    w.combo_punto2.setCurrentIndex(1)
    w._on_resolver_bernoulli()

    # Distribución de pérdidas: Fricción > 0, Accesorios == 0%, Bordes > 0%
    assert "0.0% (0.00 m)" in w.lbl_localizada.text()
    assert "0.0% (0.00 m)" not in w.lbl_bordes.text()
    assert "Fricción:" in w.lbl_distribuida.text()

    # Leyenda: Cinética (sin v²/2g), Fricción en rojo (#e74c3c), Entrada / Salida activo, sin Accesorios ni Σhf
    items = w.egl_chart.elementos_leyenda()
    por_clave = {it[0]: it for it in items}
    assert por_clave["cinetica"][2] == "Cinética"
    assert por_clave["friccion"][3] == "#e74c3c"
    assert por_clave["entrada_salida"][3] == "#0d9488"
    assert "accesorio" not in por_clave

    from PyQt5.QtWidgets import QLabel
    chips_txt = [c.text() for c in w.frame_leyenda_curvas.findChildren(QLabel)]
    assert not any("Σhf" in txt for txt in chips_txt)

    # Capturar dibujo de EGL/HGL
    img = QImage(1100, 600, QImage.Format_ARGB32)
    painter = _PintorCanvas(img)
    colores_pen = []
    orig_setPen = painter.setPen

    def track_setPen(arg):
        if hasattr(arg, "color"):
            colores_pen.append((arg.color().name().lower(), arg.widthF()))
        return orig_setPen(arg)

    painter.setPen = track_setPen
    try:
        w.egl_chart._dibujar_perfil(painter, QRectF(0, 0, 1100, 600))
    finally:
        painter.end()

    # Eje X: solo Estaciones limpias (Salida de Tanque 1, Entrada a Tanque 2), sin "Pérdida de..." ni "Accesorio..."
    estaciones = [etq for etq, _ in w.egl_chart._estaciones_rects]
    assert estaciones == ["Salida de Tanque 1", "Entrada a Tanque 2"], estaciones

    # Callouts simplificados en el área de trazado
    assert "Salida de Tanque 1" in painter.textos
    assert any(t.startswith("Pérdida de salida de Tanque 1 — hf = ") for t in painter.textos), painter.textos
    assert any(t.startswith("Tubería 1: Pérdida por fricción — hf = ") for t in painter.textos), painter.textos
    assert any(t.startswith("Pérdida de entrada a Tanque 2 — hf = ") for t in painter.textos), painter.textos
    assert not any("hf < 0.01 m" in t or "Ligeramente" in t or "Accesorio" in t for t in painter.textos), painter.textos

    # Caídas de entrada/salida dibujadas en color propio (#0d9488) y grosor >= 5
    assert any(c == "#0d9488" and ancho >= 5.0 for c, ancho in colores_pen), colores_pen

    # Si se desactivan bordes (K=0), Entrada / Salida desaparece de la leyenda y Bordes vuelve a 0.0%
    tub.establecer_conexion_tanque("origen", "ninguno")
    tub.establecer_conexion_tanque("destino", "ninguno")
    w._on_resolver_bernoulli()
    claves_sin_bordes = {it[0] for it in w.egl_chart.elementos_leyenda()}
    assert "entrada_salida" not in claves_sin_bordes
    assert "0.0% (0.00 m)" in w.lbl_bordes.text()
