"""Pruebas del trazado ortogonal con accesorios/bombas, restricciones serie/paralelo y ejemplos simples."""

from types import SimpleNamespace

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox
import pytest

from ui.dialogos import DialogoSuposicionParalelo
from ui.enrutado_ortogonal import (
    dividir_polilinea_ortogonal,
    longitud_polilinea,
    recombinar_polilineas_ortogonales,
)
from ui.graficos import (
    AccesorioGrafico,
    BombaGrafica,
    NodoUnionGrafico,
    TanqueGrafico,
    TuberiaGrafica,
)
from ui.ventana.principal import MainWindow


@pytest.fixture
def win():
    _ = QApplication.instance() or QApplication([])
    ventana = MainWindow()
    yield ventana
    ventana.close()
    QApplication.processEvents()


def _es_polilinea_ortogonal(puntos, tol=1e-4):
    assert len(puntos) >= 2
    return all(
        abs(a.x() - b.x()) <= tol or abs(a.y() - b.y()) <= tol
        for a, b in zip(puntos, puntos[1:])
    )


def _crear_tuberia_ortogonal_extravagante(scene):
    tq1 = TanqueGrafico(80, 80, id_tanque=1)
    tq2 = TanqueGrafico(520, 320, id_tanque=2)
    scene.addItem(tq1)
    scene.addItem(tq2)

    tub = TuberiaGrafica(tq1, tq2, id_tuberia=1)
    tub.longitud = 100.0
    tub.diametro = 0.15
    tub.rugosidad = 0.00015
    tub.caudal_Q = 0.03
    tub.modo_trazado = "ortogonal"
    tub.direccion_inicial = "V"
    # Trazado con múltiples quiebres en U/Z (forma extravagante entre dos tanques)
    c1 = tq1.sceneBoundingRect().center()
    c2 = tq2.sceneBoundingRect().center()
    tub.vertices_usuario = [
        QPointF(c1.x(), c1.y() + 140),
        QPointF(c1.x() + 180, c1.y() + 140),
        QPointF(c1.x() + 180, c1.y() - 40),
        QPointF(c1.x() + 340, c1.y() - 40),
        QPointF(c1.x() + 340, c2.y()),
    ]
    scene.addItem(tub)
    tub.actualizar_posicion()
    return tq1, tq2, tub


def test_dividir_y_recombinar_polilinea_ortogonal_conserva_quiebres():
    pts = [
        QPointF(0, 0),
        QPointF(0, 140),
        QPointF(180, 140),
        QPointF(180, -40),
        QPointF(340, -40),
        QPointF(340, 200),
        QPointF(500, 200),
    ]
    pt_corte, t_corte, _, pts1, pts2 = dividir_polilinea_ortogonal(pts, QPointF(182, 60))

    assert abs(pt_corte.x() - 180.0) < 1e-6
    assert abs(pt_corte.y() - 60.0) < 1e-6
    assert 0.0 < t_corte < 1.0
    assert _es_polilinea_ortogonal(pts1)
    assert _es_polilinea_ortogonal(pts2)
    assert len(pts1) == 4
    assert len(pts2) == 5

    recombinada = recombinar_polilineas_ortogonales(pts1, pts2)
    assert [(round(p.x(), 4), round(p.y(), 4)) for p in recombinada] == [
        (p.x(), p.y()) for p in pts
    ]
    assert abs(longitud_polilinea(recombinada) - longitud_polilinea(pts)) < 1e-6


def test_accesorio_divisor_conserva_trazado_ortogonal_y_desanclar_restaura(win):
    scene = win.canvas_view.scene()
    tq1, tq2, tub = _crear_tuberia_ortogonal_extravagante(scene)
    pts_original = [QPointF(p) for p in tub._puntos_trazado]
    assert len(pts_original) >= 6

    # 1) Anclar una válvula sobre el tramo vertical medio (c1.x + 180)
    c1 = tq1.sceneBoundingRect().center()
    valvula = AccesorioGrafico(0, 0, forma_visual="Válvula")
    pt_val = QPointF(c1.x() + 180.0, c1.y() + 20.0)
    valvula.setPos(pt_val.x() - valvula.ANCHO / 2.0, pt_val.y() - valvula.ALTO / 2.0)
    scene.addItem(valvula)
    valvula.anclar_a(tub)

    assert tub.modo_trazado == "ortogonal"
    assert len(tub._puntos_trazado) == len(pts_original)

    # 2) Incorporar una reducción en otro tramo sin perder los quiebres ortogonales
    reduccion = AccesorioGrafico(0, 0, forma_visual="Reducción")
    pt_red = QPointF(c1.x() + 340.0, c1.y() + 60.0)
    reduccion.setPos(pt_red.x() - reduccion.ANCHO / 2.0, pt_red.y() - reduccion.ALTO / 2.0)
    scene.addItem(reduccion)
    assert reduccion.insertar_en(tub) is True

    assert len(reduccion.tuberias) == 2
    t1, t2 = reduccion.tuberias
    assert t1.modo_trazado == "ortogonal"
    assert t2.modo_trazado == "ortogonal"
    assert _es_polilinea_ortogonal(t1._puntos_trazado)
    assert _es_polilinea_ortogonal(t2._puntos_trazado)
    assert len(t1._puntos_trazado) > 2
    assert len(t2._puntos_trazado) >= 2
    assert abs((t1.longitud + t2.longitud) - 100.0) < 1e-3
    # La válvula previa debe seguir anclada sobre el sub-tramo ortogonal correspondiente
    assert valvula.tuberia_padre in (t1, t2)
    assert valvula.flags() & valvula.ItemIsMovable

    # 3) Cambiar una válvula anclada a Expansión desde el panel también conserva ortogonal
    win._on_forma_accesorio_cambiada(valvula, "Expansión")
    assert len(valvula.tuberias) == 2
    for sub in valvula.tuberias:
        assert sub.modo_trazado == "ortogonal"
        assert _es_polilinea_ortogonal(sub._puntos_trazado)

    # 4) Eliminar/desanclar recupera la forma ortogonal completa
    valvula.desanclar()
    reduccion.desanclar()
    tuberias_restantes = [i for i in scene.items() if isinstance(i, TuberiaGrafica)]
    assert len(tuberias_restantes) == 1
    unica = tuberias_restantes[0]
    assert unica.modo_trazado == "ortogonal"
    assert _es_polilinea_ortogonal(unica._puntos_trazado)
    assert len(unica._puntos_trazado) == len(pts_original)


def test_bomba_insertada_conserva_trazado_ortogonal_y_anclados(win):
    scene = win.canvas_view.scene()
    tq1, tq2, tub = _crear_tuberia_ortogonal_extravagante(scene)
    c1 = tq1.sceneBoundingRect().center()

    valvula = AccesorioGrafico(0, 0, forma_visual="Válvula")
    pt_val = QPointF(c1.x() + 90.0, c1.y() + 140.0)
    valvula.setPos(pt_val.x() - valvula.ANCHO / 2.0, pt_val.y() - valvula.ALTO / 2.0)
    scene.addItem(valvula)
    valvula.anclar_a(tub)

    bomba = BombaGrafica(0, 0, id_bomba=1)
    pt_b = QPointF(c1.x() + 260.0, c1.y() - 40.0)
    bomba.setPos(pt_b.x() - bomba.ANCHO / 2.0, pt_b.y() - bomba.ALTO / 2.0)
    scene.addItem(bomba)

    assert bomba.insertar_en(tub) is True
    assert bomba.tuberia_succion.modo_trazado == "ortogonal"
    assert bomba.tuberia_descarga.modo_trazado == "ortogonal"
    assert _es_polilinea_ortogonal(bomba.tuberia_succion._puntos_trazado)
    assert _es_polilinea_ortogonal(bomba.tuberia_descarga._puntos_trazado)
    assert len(bomba.tuberia_succion._puntos_trazado) > 2
    assert len(bomba.tuberia_descarga._puntos_trazado) > 2
    assert valvula.tuberia_padre is bomba.tuberia_succion

    # Serialización/deserialización conserva dirección inicial y trazado
    datos = bomba.tuberia_succion.to_dict()
    assert datos["direccion_inicial"] == bomba.tuberia_succion.direccion_inicial
    assert datos["modo_trazado"] == "ortogonal"


def _click_escena(scene, punto):
    scene.mousePressEvent(
        SimpleNamespace(
            button=lambda: Qt.LeftButton,
            scenePos=lambda: punto,
            accept=lambda: None,
        )
    )


def test_trazado_ortogonal_admite_nodos_union_y_solo_restringe_paralelo(win, monkeypatch):
    advertencias = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: advertencias.append(args[1:]) or QMessageBox.Ok),
    )

    scene = win.canvas_view.scene()
    win.combo_trazado_global.setCurrentText("Trazado: Ortogonal")
    assert win.trazado_global == "ortogonal"
    assert scene.trazado_global == "ortogonal"

    # 1) Permitir agregar nodo de unión y conectar red en serie/ramificada en modo ortogonal
    win._add_union()
    uniones = [i for i in scene.items() if isinstance(i, NodoUnionGrafico)]
    assert len(uniones) == 1
    assert len(advertencias) == 0

    union = uniones[0]
    union.setPos(320, 220)
    tq1 = TanqueGrafico(80, 140, id_tanque=1)
    tq2 = TanqueGrafico(560, 140, id_tanque=2)
    tq3 = TanqueGrafico(560, 340, id_tanque=3)
    for tq in (tq1, tq2, tq3):
        scene.addItem(tq)

    scene.modo_conexion = True
    _click_escena(scene, tq1.sceneBoundingRect().center())
    _click_escena(scene, union.sceneBoundingRect().center())
    _click_escena(scene, union.sceneBoundingRect().center())
    _click_escena(scene, tq2.sceneBoundingRect().center())
    _click_escena(scene, union.sceneBoundingRect().center())
    _click_escena(scene, tq3.sceneBoundingRect().center())

    tubs = [i for i in scene.items() if isinstance(i, TuberiaGrafica)]
    assert len(tubs) == 3
    assert all(t.modo_trazado == "ortogonal" for t in tubs)
    assert all(_es_polilinea_ortogonal(t._puntos_trazado) for t in tubs)
    assert len(advertencias) == 0

    # 2) Ejemplos en serie y bomba + ramificada permiten activar Trazado: Ortogonal
    win._cargar_ejemplo_serie()
    win.combo_trazado_global.setCurrentText("Trazado: Ortogonal")
    assert win.trazado_global == "ortogonal"
    assert len(advertencias) == 0

    win._cargar_ejemplo_bomba_ramificada()
    win.combo_trazado_global.setCurrentText("Trazado: Ortogonal")
    assert win.trazado_global == "ortogonal"
    assert len(advertencias) == 0

    # 3) Ejemplo en paralelo sigue rechazando el cambio manual a Ortogonal y revierte a Recto
    win._cargar_ejemplo_paralelo()
    win.combo_trazado_global.setCurrentText("Trazado: Ortogonal")
    assert len(advertencias) == 1
    assert "recto" in win.combo_trazado_global.currentText().lower()
    assert win.trazado_global == "recto"

    # 4) La guía abre sin alertas de compatibilidad ni cambios en la red.
    cant_antes = len(advertencias)
    assert win.btn_ayuda_trazado.text() == "?"
    win.mostrar_ayuda_trazado()
    assert len(advertencias) == cant_antes
    win._guia_trazado.close()


def test_paralelo_desde_ortogonal_cambia_a_recto_y_notifica(win, monkeypatch):
    advertencias = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        staticmethod(lambda *args, **kwargs: advertencias.append(args[1:]) or QMessageBox.Ok),
    )

    scene = win.canvas_view.scene()
    win.combo_trazado_global.setCurrentText("Trazado: Ortogonal")

    # 1) Dos tanques unidos con forma ortogonal + esquina vacía + válvula anclada
    tq1 = TanqueGrafico(80, 120, id_tanque=1)
    tq2 = TanqueGrafico(520, 320, id_tanque=2)
    scene.addItem(tq1)
    scene.addItem(tq2)

    scene.modo_conexion = True
    c1 = tq1.sceneBoundingRect().center()
    c2 = tq2.sceneBoundingRect().center()
    _click_escena(scene, c1)
    _click_escena(scene, QPointF(c1.x() + 140, c1.y() + 180))
    _click_escena(scene, c2)

    tubs = [i for i in scene.items() if isinstance(i, TuberiaGrafica)]
    assert len(tubs) == 1
    tub1 = tubs[0]
    assert tub1.modo_trazado == "ortogonal"
    assert len(tub1._puntos_trazado) > 2

    # Esquina sin pérdida configurada y válvula anclada sobre un tramo ortogonal
    tub1._botones_esquina[0].abrir()
    valvula = AccesorioGrafico(0, 0, forma_visual="Válvula")
    valvula.valor = 2.0
    pt_seg = tub1._puntos_trazado[1]
    valvula.setPos(pt_seg.x() - valvula.ANCHO / 2.0, pt_seg.y() - valvula.ALTO / 2.0)
    scene.addItem(valvula)
    valvula.anclar_a(tub1)

    # 2) Conectar segunda tubería entre los mismos tanques: cambia automáticamente a Recto
    _click_escena(scene, c1)
    _click_escena(scene, QPointF(c1.x() + 200, c1.y() - 40))
    _click_escena(scene, c2)

    tubs = [i for i in scene.items() if isinstance(i, TuberiaGrafica)]
    assert len(tubs) == 2
    assert len(advertencias) == 0
    assert win.trazado_global == "recto"
    assert scene.trazado_global == "recto"
    assert "recto" in win.combo_trazado_global.currentText().lower()

    for t in tubs:
        assert t.modo_trazado == "recto"
        assert t.vertices_usuario == []
        assert t._botones_esquina == []

    # La esquina vacía se limpia y la válvula queda alineada sobre el tramo recto
    assert len([i for i in scene.items() if isinstance(i, AccesorioGrafico)]) == 1
    assert valvula.tuberia_padre is tub1
    assert tub1.distancia_a(valvula.centro_escena()) < 1e-6

    # Notificación corta visible y en barra de estado explicando el motivo
    assert not win.canvas_view.hud_notificacion_frame.isHidden()
    notif_txt = win.canvas_view.lbl_hud_notificacion.text().lower()
    assert "recto" in notif_txt and "paralelo" in notif_txt
    assert "paralelo" in win.statusBar().currentMessage().lower()

    # 3) Ruta previa vía bomba en ortogonal también cambia a recto al agregar ramal paralelo
    win._limpiar_escena_para_nuevo() if hasattr(win, "_limpiar_escena_para_nuevo") else None
    scene.clear()
    win.combo_trazado_global.setCurrentText("Trazado: Ortogonal")
    tq_a = TanqueGrafico(80, 200, id_tanque=1)
    bomba = BombaGrafica(260, 200, id_bomba=1)
    tq_b = TanqueGrafico(440, 200, id_tanque=2)
    scene.addItem(tq_a)
    scene.addItem(bomba)
    scene.addItem(tq_b)
    t_s = TuberiaGrafica(tq_a, bomba, id_tuberia=1)
    t_d = TuberiaGrafica(bomba, tq_b, id_tuberia=2)
    t_s.modo_trazado = "ortogonal"
    t_s.vertices_usuario = [QPointF(160, 140)]
    t_d.modo_trazado = "ortogonal"
    t_d.vertices_usuario = [QPointF(360, 140)]
    scene.addItem(t_s)
    scene.addItem(t_d)
    t_s.actualizar_posicion()
    t_d.actualizar_posicion()

    scene.modo_conexion = True
    _click_escena(scene, tq_a.sceneBoundingRect().center())
    _click_escena(scene, tq_b.sceneBoundingRect().center())

    tubs_bomba = [i for i in scene.items() if isinstance(i, TuberiaGrafica)]
    assert len(tubs_bomba) == 3
    assert len(advertencias) == 0
    assert win.trazado_global == "recto"
    assert all(t.modo_trazado == "recto" for t in tubs_bomba)
    assert all(t.vertices_usuario == [] for t in tubs_bomba)


def test_ejemplos_menu_y_resolucion_completa(win, monkeypatch):
    acciones = [a.text() for a in win.btn_ejemplos.menu().actions() if not a.isSeparator()]
    assert acciones == [
        "Fricción simple",
        "Tuberías en serie",
        "Tuberías en paralelo",
        "Sistema con 1 bomba",
        "Bomba + Red ramificada",
    ]

    # 1) Fricción simple
    win._cargar_ejemplo_friccion_simple()
    win._on_resolver_bernoulli()
    tub = next(i for i in win.canvas_view.scene().items() if isinstance(i, TuberiaGrafica))
    assert tub.hf_calculado is not None and tub.hf_calculado > 0
    assert "PÉRDIDA" in win.texto_resultados.toPlainText().upper() or "HF" in win.texto_resultados.toPlainText().upper()

    # 2) Tuberías en serie
    win._cargar_ejemplo_serie()
    win._on_resolver_bernoulli()
    tubs_serie = [i for i in win.canvas_view.scene().items() if isinstance(i, TuberiaGrafica)]
    union = next(i for i in win.canvas_view.scene().items() if isinstance(i, NodoUnionGrafico))
    assert len(tubs_serie) == 2
    assert all(t.hf_calculado is not None and t.hf_calculado > 0 for t in tubs_serie)
    assert union.hj_calculada is not None

    # 3) Tuberías en paralelo (acepta automáticamente la suposición inicial del diálogo)
    monkeypatch.setattr(DialogoSuposicionParalelo, "exec_", lambda self: QDialog.Accepted)
    win._cargar_ejemplo_paralelo()
    win._on_resolver_bernoulli()
    ramales = [i for i in win.canvas_view.scene().items() if isinstance(i, TuberiaGrafica)]
    assert len(ramales) == 2
    assert abs(sum(r.caudal_Q for r in ramales) - 0.08) < 1e-4

    # 4) Sistema con 1 bomba
    win._cargar_ejemplo_bomba_simple()
    win._on_resolver_bernoulli()
    bomba = next(i for i in win.canvas_view.scene().items() if isinstance(i, BombaGrafica))
    assert bomba.Q_op is not None and bomba.Q_op > 0
    assert bomba.H_op is not None and bomba.H_op > 16.0
    assert "SEGURA" in (bomba.cavitacion or "").upper()


def test_distribucion_perdidas_oculta_sin_resultados(win):
    # Al iniciar no debe mostrarse la barra de distribución de pérdidas
    assert win.contenedor_barras.isHidden()

    # Al calcular un ejemplo válido, debe mostrarse con hf > 0
    win._cargar_ejemplo_friccion_simple()
    assert win.contenedor_barras.isHidden()
    win._on_resolver_bernoulli()
    assert not win.contenedor_barras.isHidden()
    assert win.lbl_hf_bar_total.text() != "hf = 0.00 m"

    # Al cargar otro ejemplo (sin calcular todavía), debe volver a ocultarse y reiniciarse
    win._cargar_ejemplo_paralelo()
    assert win.texto_resultados.toPlainText().strip() == ""
    assert win.contenedor_barras.isHidden()
    assert win.lbl_hf_bar_total.text() == "hf = 0.00 m"
    assert win.bar_distribuida.value() == 0

    # También debe ocultarse si se modifican elementos tras calcular
    win._cargar_ejemplo_serie()
    win._on_resolver_bernoulli()
    assert not win.contenedor_barras.isHidden()
    win._on_elementos_modificados()
    assert win.contenedor_barras.isHidden()
