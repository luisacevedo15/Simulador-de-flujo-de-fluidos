"""Deshacer restaura entradas y conexiones sin ejecutar cálculos automáticamente."""

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLabel, QPushButton

from test_interfaz_regresiones import ventana, red_con_bomba
from ui.dialogos import DialogoFluido
from ui.graficos import TanqueGrafico, TuberiaGrafica, BombaGrafica


def elementos(w, tipo):
    return [i for i in w.canvas_view.scene().items() if isinstance(i, tipo)]


def test_fluido_solo_propiedades_y_presiones(ventana):
    d = DialogoFluido(1000, 0.001, ventana, P_atm=90000, P_vap=3000)
    etiquetas = ' '.join(i.text() for i in d.findChildren(QLabel))
    botones = ' '.join(i.text() for i in d.findChildren(QPushButton))
    assert 'Temperatura' not in etiquetas and 'Agua a' not in botones
    assert 'Densidad' in etiquetas and 'Viscosidad dinámica' in etiquetas
    assert 'Presión de vapor' in etiquetas and 'Presión atmosférica' in etiquetas
    d.unidad_vap.setCurrentText('kPa')
    d.campo_vap.setText('4,5')
    d._validar_y_aceptar()
    assert d.valores() == (1000, 0.001, 90000, 4500)
    assert 'temperatura' not in ventana._serializar_proyecto()['fluido']


def test_ctrl_z_deshace_creacion_y_rehacer_la_recupera(ventana):
    w = ventana
    w._add_tanque()
    w.canvas_view.setFocus()
    QTest.keyClick(w.canvas_view, Qt.Key_Z, Qt.ControlModifier)
    assert elementos(w, TanqueGrafico) == []
    w.historial.rehacer()
    assert len(elementos(w, TanqueGrafico)) == 1
    w.historial.deshacer()
    assert elementos(w, TanqueGrafico) == []


def test_eliminar_y_deshacer_recupera_tuberias_y_extremos(ventana):
    w = ventana
    scene, a, b, bomba, tubos = red_con_bomba(w, completa=True)
    w.historial.registrar()
    bomba.setSelected(True)
    scene.borrar_seleccion()
    assert elementos(w, TuberiaGrafica) == []
    w.historial.deshacer()
    assert len(elementos(w, BombaGrafica)) == 1
    assert len(elementos(w, TuberiaGrafica)) == 2
    for t in elementos(w, TuberiaGrafica):
        assert t.nodo_origen.scene() is scene and t.nodo_destino.scene() is scene
        assert t in t.nodo_origen.tuberias and t in t.nodo_destino.tuberias


def test_movimiento_varios_pasos_es_un_solo_cambio(ventana):
    w = ventana
    w._add_tanque()
    w.historial.registrar()
    posicion = elementos(w, TanqueGrafico)[0].pos()
    for i in range(10):
        elementos(w, TanqueGrafico)[0].setPos(posicion + QPointF(i * 10, 30))
    w.historial.deshacer()
    assert elementos(w, TanqueGrafico)[0].pos() == posicion
    w.historial.rehacer()
    assert elementos(w, TanqueGrafico)[0].pos() == posicion + QPointF(90, 30)


def test_propiedades_fluido_y_nueva_rama_de_historial(ventana):
    w = ventana
    w.fluido_P_vap = 6000
    w._on_elementos_modificados()
    w.historial.registrar()
    w.fluido_rho = 850
    w.historial.deshacer()
    assert w.fluido_rho == 1000 and w.fluido_P_vap == 6000
    w.historial.deshacer()
    assert w.fluido_P_vap != 6000
    w._add_tanque()
    w.historial.registrar()
    w.historial.rehacer()
    assert w.fluido_rho == 1000 and len(elementos(w, TanqueGrafico)) == 1
