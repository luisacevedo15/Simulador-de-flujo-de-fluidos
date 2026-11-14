"""Interacción y persistencia de pérdidas en quiebres ortogonales."""

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QToolButton
import pytest

from test_trazado_ortogonal_y_ejemplos import win, _crear_tuberia_ortogonal_extravagante
from ui.catalogo_accesorios import CatalogoAccesorios
from ui.graficos import AccesorioGrafico, TuberiaGrafica


def test_mas_abre_panel_sin_duplicar_y_suma_perdida(win):
    w = win
    w.show()
    a, b, t = _crear_tuberia_ortogonal_extravagante(w.canvas_view.scene())
    assert len(t._botones_esquina) == len(t._puntos_trazado) - 2
    w.canvas_view.centerOn(t._puntos_trazado[1])
    w.canvas_view.setFocus()
    QTest.qWait(30)
    boton = t._botones_esquina[0]
    assert not boton._hover and not boton.configurada
    QTest.mouseMove(w.canvas_view.viewport(), w.canvas_view.mapFromScene(boton.scenePos()) + QPointF(90, 90).toPoint())
    QTest.mouseMove(w.canvas_view.viewport(), w.canvas_view.mapFromScene(boton.scenePos()))
    QTest.qWait(20)
    assert boton._hover
    QTest.mouseClick(w.canvas_view.viewport(), Qt.LeftButton,
                    pos=w.canvas_view.mapFromScene(boton.scenePos()) + boton.centro_boton.toPoint())
    acc = w.accesorio_seleccionado
    assert acc is not None and acc.esquina_indice == 1
    assert w.lbl_panel_title.text() == 'Pérdida en esquina'
    w.campos_accesorio['valor'].setText('1.25')
    assert t.sumatoria_K_accesorios == 1.25
    assert boton.configurada
    assert boton.abrir() is acc and len(t.accesorios_conectados) == 1
    w.campos_accesorio['tipo'].setCurrentText('Le/D')
    w.campos_accesorio['valor'].setText('30')
    assert t.sumatoria_K_accesorios == 0 and t.sumatoria_Le_D == 30
    assert 'Le/D = 30' in boton.toolTip()
    a.setPos(a.pos() + QPointF(30, 20))
    assert acc.centro_escena() == t._puntos_trazado[1]


@pytest.mark.parametrize('zoom', [0.5, 1.0, 2.0])
def test_hover_sale_del_codo_y_el_mas_no_bloquea_el_trazo(win, zoom):
    w = win
    w.show()
    a, b, t = _crear_tuberia_ortogonal_extravagante(w.canvas_view.scene())
    boton = t._botones_esquina[0]
    w.canvas_view.resetTransform()
    w.canvas_view.scale(zoom, zoom)
    w.canvas_view.centerOn(boton.scenePos())
    QTest.qWait(30)
    esquina = w.canvas_view.mapFromScene(boton.scenePos())
    QTest.mouseMove(w.canvas_view.viewport(), esquina + QPointF(90, 90).toPoint())
    QTest.mouseMove(w.canvas_view.viewport(), esquina)
    QTest.qWait(20)
    assert boton._hover
    flotante = esquina + boton.centro_boton.toPoint()
    QTest.mouseMove(w.canvas_view.viewport(), (esquina + flotante) / 2)
    QTest.mouseMove(w.canvas_view.viewport(), flotante)
    assert boton._hover
    assert boton.centro_boton.manhattanLength() == 44
    QTest.mouseMove(w.canvas_view.viewport(), esquina + QPointF(90, 90).toPoint())
    QTest.qWait(20)
    assert not boton._hover
    assert t.accesorios_conectados == []
    perdida = boton.abrir()
    w.campos_accesorio['valor'].setText('2')
    assert boton.configurada
    w.campos_accesorio['valor'].setText('0')
    assert not boton.configurada and perdida.valor == 0


def test_esquina_persiste_y_deshacer_restaura_valor(win):
    w = win
    a, b, t = _crear_tuberia_ortogonal_extravagante(w.canvas_view.scene())
    w.historial.registrar()
    acc = t._botones_esquina[0].abrir()
    w.campos_accesorio['valor'].setText('0.75')
    w.historial.registrar()
    datos = w._serializar_proyecto()
    w.campos_accesorio['valor'].setText('2')
    w.historial.deshacer()
    t = next(i for i in w.canvas_view.scene().items() if isinstance(i, TuberiaGrafica))
    assert t.sumatoria_K_accesorios == 0.75
    assert len(t.accesorios_conectados) == 1
    assert t._botones_esquina[0].abrir().valor == 0.75
    w._deserializar_proyecto(datos)
    t = next(i for i in w.canvas_view.scene().items() if isinstance(i, TuberiaGrafica))
    assert t._botones_esquina[0].abrir().valor == 0.75
    assert t.sumatoria_K_accesorios == 0.75


def test_catalogo_sin_codos_y_colocacion_directa_en_ortogonal(win):
    d = CatalogoAccesorios(win)
    botones = d.findChildren(QToolButton)
    assert len(botones) == 3
    assert all('Codo' not in b.text() for b in botones)
    botones[0].click()
    assert d.forma_elegida == 'Válvula'
    a, b, t = _crear_tuberia_ortogonal_extravagante(win.canvas_view.scene())
    ruta = list(t._puntos_trazado)
    t.setSelected(True)
    acc = win._add_accesorio('Válvula')
    assert acc.tuberia_padre is t
    assert t._puntos_trazado == ruta
    assert t.distancia_a(acc.centro_escena()) < 1e-6
    assert 'Codo' not in AccesorioGrafico.FORMAS


def test_reduccion_conserva_perdida_de_esquina(win):
    a, b, t = _crear_tuberia_ortogonal_extravagante(win.canvas_view.scene())
    perdida = t._botones_esquina[0].abrir()
    perdida.valor = 2
    win.canvas_view.scene().clearSelection()
    t.setSelected(True)
    acc = win._add_accesorio('Reducción')
    tubos = [i for i in win.canvas_view.scene().items() if isinstance(i, TuberiaGrafica)]
    assert len(tubos) == 2 and len(acc.tuberias) == 2
    assert sum(t.sumatoria_K_accesorios for t in tubos) == 2
    assert perdida.tuberia_padre in tubos


def test_soltar_cerca_del_trazo_ancla_aunque_no_colisione(win):
    w = win
    w.show()
    scene = w.canvas_view.scene()
    a, b, t = _crear_tuberia_ortogonal_extravagante(scene)
    p0, p1 = t._puntos_trazado[:2]
    centro = (p0 + p1) / 2 + QPointF(22, 0)
    acc = AccesorioGrafico(centro.x() - 15, centro.y() - 15)
    scene.addItem(acc)
    w.canvas_view.centerOn(centro)
    QTest.qWait(30)
    assert t not in acc.collidingItems()
    QTest.mouseClick(w.canvas_view.viewport(), Qt.LeftButton,
                    pos=w.canvas_view.mapFromScene(centro))
    assert acc.tuberia_padre is t
    assert t.distancia_a(acc.centro_escena()) < 1e-6
