"""Pruebas de flechas de sentido de flujo en tuberías (solo tras cálculo válido)."""

import math
import os

import pytest
from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtGui import QImage, QPainter, QPolygonF
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from ui.dialogos import DialogoSuposicionParalelo
from ui.graficos import (
    AccesorioGrafico,
    BombaGrafica,
    NodoUnionGrafico,
    TanqueGrafico,
    TuberiaGrafica,
)
from ui.ventana.principal import MainWindow


class _PintorPoligonos(QPainter):
    def __init__(self, img):
        super().__init__(img)
        self.poligonos = []

    def drawPolygon(self, polygon, *args, **kwargs):
        if isinstance(polygon, QPolygonF):
            pts = [self.worldTransform().map(polygon.at(i)) for i in range(polygon.count())]
            self.poligonos.append(pts)
        return super().drawPolygon(polygon, *args, **kwargs)


def _capturar_poligonos(tuberia):
    img = QImage(900, 600, QImage.Format_ARGB32)
    painter = _PintorPoligonos(img)
    try:
        tuberia.paint(painter, None)
    finally:
        painter.end()
    return painter.poligonos


def _vector_unitario(ang_grados):
    rad = math.radians(ang_grados)
    return math.cos(rad), math.sin(rad)


@pytest.fixture
def ventana(monkeypatch):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    yield w
    w.canvas_view.scene().selectionChanged.disconnect()
    w.close()
    w.deleteLater()
    app.processEvents()


def _tanque(scene, x, y, tid, z=0.0):
    t = TanqueGrafico(x, y, id_tanque=tid)
    t.elevacion_z = z
    t.abierto_atmosfera = True
    t.actualizar_etiqueta()
    scene.addItem(t)
    return t


def _tubo(scene, n1, n2, tid, L=100.0, D=0.20, Q=0.0, eps=0.00015):
    tub = TuberiaGrafica(n1, n2, id_tuberia=tid)
    tub.longitud = L
    tub.diametro = D
    tub.rugosidad = eps
    tub.caudal_Q = Q
    scene.addItem(tub)
    tub.actualizar_posicion()
    tub.actualizar_etiqueta()
    return tub


def test_sin_flechas_antes_de_calcular_y_tras_invalidar(ventana):
    w = ventana
    scene = w.canvas_view.scene()
    w._cargar_ejemplo_friccion_simple()
    tub = next(i for i in scene.items() if isinstance(i, TuberiaGrafica))

    # Tiene Q ingresado, pero aún NO se ha ejecutado el cálculo
    assert tub.caudal_Q > 0
    assert tub.sentido_flujo_calculado is None
    assert tub._ubicaciones_flechas_flujo() == []
    assert _capturar_poligonos(tub) == []

    # Al calcular, aparecen las flechas y se dibujan polígonos reales
    w._on_resolver_bernoulli()
    assert tub.sentido_flujo_calculado == 1
    ubicaciones = tub._ubicaciones_flechas_flujo()
    assert len(ubicaciones) >= 1
    poligonos = _capturar_poligonos(tub)
    assert len(poligonos) == len(ubicaciones)

    # Cada flecha debe quedar fuera de la etiqueta de la tubería y alineada con el tramo
    p_ini, p_fin = tub._puntos_trazado[0], tub._puntos_trazado[-1]
    dx, dy = p_fin.x() - p_ini.x(), p_fin.y() - p_ini.y()
    norm = math.hypot(dx, dy)
    r_etq = QRectF(tub.etiqueta.pos(), tub.etiqueta.boundingRect().size())
    for pt, ang in ubicaciones:
        assert not r_etq.contains(pt)
        ux, uy = _vector_unitario(ang)
        assert ux == pytest.approx(dx / norm, abs=1e-4)
        assert uy == pytest.approx(dy / norm, abs=1e-4)

    # No se serializa en JSON
    proy = w._serializar_proyecto()
    assert "sentido_flujo_calculado" not in proy["tuberias"][0]

    # Al editar el circuito o deshacer, las flechas desaparecen inmediatamente
    w.historial.registrar()
    tub.diametro = 0.25
    w._on_elementos_modificados()
    assert tub.sentido_flujo_calculado is None
    assert tub._ubicaciones_flechas_flujo() == []
    assert _capturar_poligonos(tub) == []

    w.historial.deshacer()
    tub_rest = next(i for i in scene.items() if isinstance(i, TuberiaGrafica))
    assert tub_rest.sentido_flujo_calculado is None
    assert tub_rest._ubicaciones_flechas_flujo() == []


def test_tuberia_invertida_en_cad_y_fallo_limpia_flechas(ventana):
    w = ventana
    scene = w.canvas_view.scene()
    t1 = _tanque(scene, 100, 220, 1, z=25.0)
    t2 = _tanque(scene, 560, 220, 2, z=5.0)
    # Dibujada topológicamente al revés (t2 -> t1), aunque el flujo es t1 -> t2
    tub = _tubo(scene, t2, t1, 1, L=100.0, D=0.20, Q=0.0)
    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)  # Tanque 1
    w.combo_punto2.setCurrentIndex(1)  # Tanque 2
    w._on_resolver_bernoulli()

    assert tub.sentido_flujo_calculado == -1
    ubicaciones = tub._ubicaciones_flechas_flujo()
    assert len(ubicaciones) >= 1
    for _pt, ang in ubicaciones:
        ux, uy = _vector_unitario(ang)
        assert ux == pytest.approx(1.0, abs=1e-4)
        assert uy == pytest.approx(0.0, abs=1e-4)

    # Si se invierten los tanques y falla por gravedad (Flujo imposible), no quedan flechas
    w.combo_punto1.setCurrentIndex(1)  # Tanque 2 (z=5)
    w.combo_punto2.setCurrentIndex(0)  # Tanque 1 (z=25)
    w._on_resolver_bernoulli()
    assert tub.sentido_flujo_calculado is None
    assert tub._ubicaciones_flechas_flujo() == []


def test_flechas_serie_paralelo_mixto_y_bomba(ventana, monkeypatch):
    monkeypatch.setattr(DialogoSuposicionParalelo, "exec_", lambda self: QDialog.Accepted)
    w = ventana
    scene = w.canvas_view.scene()

    # 1) Serie
    w._cargar_ejemplo_serie()
    w._on_resolver_bernoulli()
    for t in scene.items():
        if isinstance(t, TuberiaGrafica):
            assert t.sentido_flujo_calculado == 1
            assert len(t._ubicaciones_flechas_flujo()) >= 1

    # 2) Paralelo (ramales puente desplazados)
    w._cargar_ejemplo_paralelo()
    w._on_resolver_bernoulli()
    for t in scene.items():
        if isinstance(t, TuberiaGrafica):
            assert t.sentido_flujo_calculado == 1
            p_ini, p_fin = t._puntos_trazado[0], t._puntos_trazado[-1]
            dx, dy = p_fin.x() - p_ini.x(), p_fin.y() - p_ini.y()
            norm = math.hypot(dx, dy)
            flechas = t._ubicaciones_flechas_flujo()
            assert len(flechas) >= 1
            # Al menos una flecha sigue la pendiente principal T1 -> T2 en sentido positivo
            assert any(
                math.isclose(_vector_unitario(ang)[0], dx / norm, abs_tol=1e-4)
                and math.isclose(_vector_unitario(ang)[1], dy / norm, abs_tol=1e-4)
                for _, ang in flechas
            )
            for pt, _ang in flechas:
                for esquina in t._puntos_trazado[1:-1]:
                    assert math.hypot(pt.x() - esquina.x(), pt.y() - esquina.y()) >= 14.0

    # 3) Mixto Paralelo-Serie con tramo serie dibujado invertido
    w._preparar_escena_ejemplo()
    t1 = _tanque(scene, 60, 240, 1, z=30.0)
    u = NodoUnionGrafico(300, 240, id_union=1)
    scene.addItem(u)
    t2 = _tanque(scene, 700, 240, 2, z=10.0)
    tub_ser = _tubo(scene, u, t1, 1, L=60.0, D=0.25, Q=0.06)  # Invertida u -> t1
    r_a = _tubo(scene, u, t2, 2, L=100.0, D=0.15, Q=0.04)
    r_b = _tubo(scene, t2, u, 3, L=120.0, D=0.12, Q=0.02)     # Invertida t2 -> u
    w._finalizar_ejemplo(modo_dashboard=0)
    w._on_resolver_bernoulli()

    assert tub_ser.sentido_flujo_calculado == -1
    assert r_a.sentido_flujo_calculado == 1
    assert r_b.sentido_flujo_calculado == -1

    # 4) Sistema con 1 bomba
    w._cargar_ejemplo_bomba_simple()
    w._on_resolver_bernoulli()
    for t in scene.items():
        if isinstance(t, TuberiaGrafica):
            assert t.sentido_flujo_calculado == 1
            assert len(t._ubicaciones_flechas_flujo()) >= 1


def test_flechas_ramificadas_doble_nudo_y_bomba_ramificada(ventana):
    w = ventana
    scene = w.canvas_view.scene()

    # 1) Tres reservorios con ramal compuesto y segmento invertido
    w._preparar_escena_ejemplo()
    a = _tanque(scene, 60, 240, 1, z=40.0)
    acc = AccesorioGrafico(200, 225, forma_visual="Reducción", tipo_perdida="K", valor=0.5)
    scene.addItem(acc)
    u = NodoUnionGrafico(360, 240, id_union=1)
    scene.addItem(u)
    b = _tanque(scene, 660, 120, 2, z=15.0)
    c = _tanque(scene, 660, 360, 3, z=5.0)

    t_a1 = _tubo(scene, acc, a, 1, L=60.0, D=0.25)   # Invertida (acc -> a), flujo real a -> acc
    t_a2 = _tubo(scene, acc, u, 2, L=60.0, D=0.25)   # Normal (acc -> u)
    t_b = _tubo(scene, b, u, 3, L=100.0, D=0.15)     # Invertida (b -> u), flujo real u -> b
    t_c = _tubo(scene, u, c, 4, L=100.0, D=0.15)     # Normal (u -> c)
    w._finalizar_ejemplo(modo_dashboard=1)
    w._resolver_union_ramificada(u)

    assert t_a1.sentido_flujo_calculado == -1
    assert t_a2.sentido_flujo_calculado == 1
    assert t_b.sentido_flujo_calculado == -1
    assert t_c.sentido_flujo_calculado == 1

    # 2) Doble nudo: verificar dirección según sentido de flujo (incluido tramo central)
    w._preparar_escena_ejemplo()
    tq1 = _tanque(scene, 60, 140, 1, z=50.0)
    tq2 = _tanque(scene, 60, 340, 2, z=35.0)
    j = NodoUnionGrafico(260, 240, id_union=1)
    k = NodoUnionGrafico(480, 240, id_union=2)
    scene.addItem(j)
    scene.addItem(k)
    tq3 = _tanque(scene, 700, 140, 3, z=10.0)
    tq4 = _tanque(scene, 700, 340, 4, z=5.0)

    tj1 = _tubo(scene, tq1, j, 1, L=80.0, D=0.20)
    tj2 = _tubo(scene, j, tq2, 2, L=80.0, D=0.20)
    tc = _tubo(scene, k, j, 3, L=120.0, D=0.20)     # Dibujado k -> j; flujo real j -> k
    tk1 = _tubo(scene, k, tq3, 4, L=80.0, D=0.20)
    tk2 = _tubo(scene, tq4, k, 5, L=80.0, D=0.20)    # Dibujado tq4 -> k; flujo real k -> tq4
    w._finalizar_ejemplo(modo_dashboard=1)
    w._resolver_doble_nudo(j, k)

    assert tc.sentido_flujo_calculado == -1
    assert tk1.sentido_flujo_calculado == 1
    assert tk2.sentido_flujo_calculado == -1
    for _pt, ang in tc._ubicaciones_flechas_flujo():
        ux, _ = _vector_unitario(ang)
        assert ux == pytest.approx(1.0, abs=1e-4)

    # 3) Bomba en red ramificada
    w._cargar_ejemplo_bomba_ramificada()
    u_br = next(i for i in scene.items() if isinstance(i, NodoUnionGrafico))
    w._resolver_union_ramificada(u_br)
    tubs_br = sorted(
        (i for i in scene.items() if isinstance(i, TuberiaGrafica)),
        key=lambda t: t.id_tuberia,
    )
    assert len(tubs_br) == 4
    # Succión e impulsión siempre apuntan hacia la unión (1); ambos ramales salen a tanques (1)
    assert all(t.sentido_flujo_calculado in (1, -1) for t in tubs_br)
    assert tubs_br[0].sentido_flujo_calculado == 1
    assert tubs_br[1].sentido_flujo_calculado == 1


def test_flechas_en_trazado_ortogonal_respetan_segmentos_y_esquinas(ventana):
    w = ventana
    scene = w.canvas_view.scene()
    t1 = _tanque(scene, 80, 100, 1, z=30.0)
    t2 = _tanque(scene, 600, 340, 2, z=10.0)
    tub = _tubo(scene, t1, t2, 1, L=150.0, D=0.20, Q=0.0)
    tub.modo_trazado = "ortogonal"
    tub.direccion_inicial = "H"
    tub.vertices_usuario = [QPointF(340, 140), QPointF(340, 380)]
    tub.actualizar_posicion()
    tub.actualizar_etiqueta()

    assert tub._ubicaciones_flechas_flujo() == []

    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)
    w.combo_punto2.setCurrentIndex(1)
    w._on_resolver_bernoulli()

    ubicaciones = tub._ubicaciones_flechas_flujo()
    assert len(ubicaciones) >= 1
    for pt, ang in ubicaciones:
        ux, uy = _vector_unitario(ang)
        # En segmentos ortogonales, la dirección debe ser puramente H o V
        assert abs(abs(ux) - 1.0) < 1e-4 or abs(abs(uy) - 1.0) < 1e-4
        for esquina in tub._puntos_trazado[1:-1]:
            assert math.hypot(pt.x() - esquina.x(), pt.y() - esquina.y()) >= 14.0
