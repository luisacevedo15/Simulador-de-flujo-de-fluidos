"""Las transiciones no deben capturar clics ni modificar la red hidráulica."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QAbstractAnimation, QEvent, QPoint, QRect, Qt
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication, QGraphicsView, QPushButton, QVBoxLayout, QWidget

from ui import animaciones
from ui.escena import GridScene
from ui.graficos import TanqueGrafico, TuberiaGrafica
from ui.widgets import _InterruptorStitch
from ui import transiciones


@pytest.fixture
def interfaz(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(animaciones, "movimiento_permitido", lambda: True)
    monkeypatch.setattr(transiciones, "movimiento_permitido", lambda: True)
    ventana = QWidget()
    ventana.setAttribute(Qt.WA_DontShowOnScreen, True)
    QVBoxLayout(ventana)
    gestor = animaciones.MicroAnimaciones(ventana)
    ventana.show()
    yield app, ventana, gestor
    ventana.close()
    sip.delete(ventana)
    app.processEvents()


def test_boton_dinamico_conserva_clic_geometria_y_estado_deshabilitado(interfaz):
    app, ventana, _ = interfaz
    boton = QPushButton("Calcular")
    ventana.layout().addWidget(boton)
    app.processEvents()
    capa = boton._micro_realce
    geometria = boton.geometry()
    clics = QSignalSpy(boton.clicked)
    QTest.mouseClick(boton, Qt.LeftButton)
    assert len(clics) == 1
    assert capa.testAttribute(Qt.WA_TransparentForMouseEvents)
    assert capa._clic.state() == QAbstractAnimation.Running
    assert capa._efecto.presion > 0
    boton.setEnabled(False)
    assert capa._clic.state() == QAbstractAnimation.Stopped
    assert capa._pulso == 1.0
    assert capa._efecto.presion == capa._efecto.elevacion == 0
    QTest.mouseClick(boton, Qt.LeftButton)
    assert len(clics) == 1
    assert boton.geometry() == geometria


def test_hover_reversible_sin_acumular_animaciones(interfaz):
    app, ventana, _ = interfaz
    boton = QPushButton("Guardar")
    ventana.layout().addWidget(boton)
    app.processEvents()
    capa = boton._micro_realce
    app.sendEvent(boton, QEvent(QEvent.Enter))
    capa._hover.setCurrentTime(80)
    nivel = capa._nivel
    assert 0 < nivel < 1
    app.sendEvent(boton, QEvent(QEvent.Leave))
    assert capa._hover.startValue() == nivel
    capa._hover.setCurrentTime(capa._hover.duration())
    assert capa._nivel == 0
    assert capa._hover.state() == QAbstractAnimation.Stopped


def test_interruptor_rapido_y_oculto_sin_desincronizar_valor(interfaz):
    app, ventana, _ = interfaz
    interruptor = _InterruptorStitch()
    ventana.layout().addWidget(interruptor)
    app.processEvents()
    cambios = QSignalSpy(interruptor.toggled)
    interruptor.setChecked(True)
    interruptor._deslizamiento.setCurrentTime(80)
    assert 0 < interruptor._posicion < 1
    interruptor.setChecked(False)
    interruptor._deslizamiento.setCurrentTime(180)
    assert interruptor._posicion == 0
    interruptor.setChecked(True)
    interruptor.hide()
    assert interruptor._posicion == 1
    assert len(cambios) == 3
    assert interruptor._deslizamiento.state() == QAbstractAnimation.Stopped


def test_realce_no_modifica_geometria_ni_emite_cambios_hidraulicos(interfaz):
    app, _, _ = interfaz
    escena = GridScene()
    origen, destino = TanqueGrafico(100, 100), TanqueGrafico(400, 100)
    tubo = TuberiaGrafica(origen, destino)
    for item in (origen, destino, tubo):
        escena.addItem(item)
    cambios = QSignalSpy(escena.elementos_modificados)
    posicion, trazado = origen.pos(), tubo.path()
    origen.setSelected(True)
    origen._animar_realce(1.0)
    origen._animacion_realce.setCurrentTime(180)
    assert origen._realce == 1
    assert origen.pos() == posicion
    assert tubo.path() == trazado
    assert origen.isSelected()
    assert len(cambios) == 0
    origen._animar_realce(0.0)
    escena.removeItem(origen)
    assert origen._animacion_realce.state() == QAbstractAnimation.Stopped
    assert origen._realce == 0
    tubo._animar_realce(1.0)
    escena.clear()
    QTest.qWait(220)  # Eliminar durante la animación no debe tocar wrappers C++ borrados.
    sip.delete(origen)


def test_movimiento_reducido_aplica_estado_inmediato(interfaz, monkeypatch):
    app, ventana, _ = interfaz
    monkeypatch.setattr(animaciones, "movimiento_permitido", lambda: False)
    monkeypatch.setattr(transiciones, "movimiento_permitido", lambda: False)
    interruptor = _InterruptorStitch()
    ventana.layout().addWidget(interruptor)
    app.processEvents()
    interruptor.setChecked(True)
    assert interruptor._posicion == 1
    assert interruptor._deslizamiento.state() == QAbstractAnimation.Stopped
    transiciones.revelar_contenido(ventana)
    assert not hasattr(ventana, "_entrada_contenido")
    boton = QPushButton("Acción")
    ventana.layout().addWidget(boton)
    app.processEvents()
    app.sendEvent(boton, QEvent(QEvent.Enter))
    QTest.mouseClick(boton, Qt.LeftButton)
    assert boton._micro_realce._efecto.presion == 0
    assert boton._micro_realce._efecto.elevacion == 0


def test_transicion_agrupa_cambios_y_no_intercepta_clics(interfaz):
    app, ventana, _ = interfaz
    boton = QPushButton("Antes")
    ventana.layout().addWidget(boton)
    app.processEvents()
    transiciones.revelar_contenido(ventana)
    boton.setText("Después")
    transiciones.revelar_contenido(ventana)
    ventana.resize(420, 200)
    app.processEvents()
    capa = ventana._entrada_contenido
    assert capa.isVisible()
    assert not capa._imagen.isNull()
    assert capa.geometry() == ventana.rect()
    assert capa.testAttribute(Qt.WA_TransparentForMouseEvents)
    clics = QSignalSpy(boton.clicked)
    QTest.mouseClick(boton, Qt.LeftButton)
    assert len(clics) == 1
    assert not capa.isVisible()
    assert capa._imagen.isNull()
    assert capa._animacion.state() == QAbstractAnimation.Stopped
    transiciones.revelar_contenido(ventana)
    ventana.hide()
    app.processEvents()
    assert not capa._pendiente.isActive()
    assert capa._imagen.isNull()


def test_entrada_de_objeto_conserva_anclajes_y_se_puede_eliminar(interfaz):
    app, ventana, _ = interfaz
    escena = GridScene()
    vista = QGraphicsView(escena)
    ventana.layout().addWidget(vista)
    a, b = TanqueGrafico(0, 0), TanqueGrafico(300, 0)
    tubo = TuberiaGrafica(a, b)
    for item in (a, b, tubo):
        escena.addItem(item)
    app.processEvents()
    rect, transform, path = a.sceneBoundingRect(), a.transform(), tubo.path()
    cambios = QSignalSpy(escena.elementos_modificados)
    transiciones.animar_entrada_item(a)
    efecto = a.graphicsEffect()
    efecto._animacion.setCurrentTime(100)
    assert efecto.isEnabled()
    assert a.sceneBoundingRect() == rect
    assert a.transform() == transform
    assert tubo.path() == path
    assert len(cambios) == 0
    efecto._animacion.setCurrentTime(460)
    assert not efecto.isEnabled()
    transiciones.animar_entrada_item(b)
    efecto_b = b.graphicsEffect()
    escena.removeItem(b)
    efecto_b._animacion.setCurrentTime(100)
    assert not efecto_b.isEnabled()
    assert efecto_b._animacion.state() == QAbstractAnimation.Stopped
    transiciones.animar_entrada_item(a)
    escena.clear()
    app.processEvents()
    sip.delete(b)


def test_navegacion_rapida_conserva_efectos_y_termina_en_vista_actual(interfaz):
    from ui.ventana.principal import MainWindow

    app, _, _ = interfaz
    w = MainWindow()
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.show()
    app.processEvents()
    efecto = w.btn_nav_cad.graphicsEffect()

    def captura_boton(boton):
        return w.grab().copy(QRect(boton.mapTo(w, QPoint()), boton.size())).toImage()

    boton_union = w.main_toolbar.widgetForAction(w.main_toolbar.actions()[1])
    inicial_union = captura_boton(boton_union)
    inicial_nav = captura_boton(w.btn_nav_cad)
    for modo in ("curvas", "tabla", "cad"):
        w._cambiar_vista_central(modo)
        app.processEvents()
    assert captura_boton(boton_union) == inicial_union, 'La barra debe seguir dibujando sus botones al volver a CAD'
    assert captura_boton(w.btn_nav_cad) == inicial_nav, 'El icono no debe desplazarse con cada cambio de vista'
    w._cambiar_vista_central("curvas")
    app.processEvents()
    assert w.stack_central.currentIndex() == 2
    assert w.btn_nav_cad.graphicsEffect() is efecto
    indicador = w.indicador_nav
    indicador._movimiento.setCurrentTime(340)
    assert indicador.geometry().center().y() == w.btn_nav_curvas.geometry().center().y()
    capa = w.stack_central._entrada_contenido
    capa._animacion.setCurrentTime(320)
    assert not capa.isVisible()
    assert capa._imagen.isNull()
    w.canvas_view.scene().selectionChanged.disconnect()
    w.close()
    sip.delete(w)
