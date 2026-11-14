"""CURVAS conserva sus controles legibles al reducir la ventana."""

import os
from pathlib import Path

import pytest
from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtGui import QFont, QFontDatabase, QFontMetrics
from PyQt5.QtWidgets import QApplication, QLabel, QStyle, QStyleOptionButton

from ui.ventana.principal import MainWindow
from motor.hidraulica import evaluar_tramo
from motor.perfiles import construir_perfil_ruta, perfil_como_serie


@pytest.fixture
def ventana():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication.instance() or QApplication([])
    if not QFontDatabase().families():
        fuente = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/arial.ttf'
        if fuente.exists():
            QFontDatabase.addApplicationFont(str(fuente))
    w = MainWindow()
    tramo = evaluar_tramo(0.01,100,0.1,0,0,0,dict(rho=1000,mu=0.001,g=9.81),id='T1')
    perfil = construir_perfil_ruta([tramo],20,20-tramo.hf_total,etiquetas=['Tanque 1','Tanque 2'])
    w.egl_chart.actualizar_datos([perfil_como_serie(perfil)])
    w._cambiar_vista_central('curvas')
    w.show()
    yield w
    w.canvas_view.scene().selectionChanged.disconnect()
    w.close()
    w.deleteLater()
    app.processEvents()


def estabilizar():
    for _ in range(4):
        QApplication.processEvents()


@pytest.mark.parametrize('ancho,alto',[(960,640),(1280,800),(1920,1080)])
def test_controles_y_leyenda_caben_sin_solaparse(ventana,ancho,alto):
    w = ventana
    w.resize(ancho,alto)
    estabilizar()
    controles = [w.btn_volver_cad_curvas,w.btn_curvas_egl,w.btn_curvas_bomba,
        w.chk_linea_piezometrica,w.chk_linea_energia,w.btn_modo_didactico,w.btn_modo_exacto]
    rects = []
    for control in controles:
        assert control.isVisible()
        rect = QRect(control.mapTo(w.panel_vista_curvas,QPoint(0,0)),control.size())
        assert rect.left()>=0 and rect.right()<w.panel_vista_curvas.width(),(control.text(),rect)
        assert control.width()>=control.sizeHint().width(),(control.text(),control.width(),control.sizeHint())
        assert not any(rect.intersects(otro) for otro in rects),(control.text(),rects)
        rects.append(rect)
    chips = w.frame_leyenda_curvas.findChildren(QLabel)
    assert chips
    rects_ley = []
    for chip in chips:
        assert chip.isVisible()
        rect_c = QRect(chip.mapTo(w.frame_leyenda_curvas,QPoint(0,0)),chip.size())
        assert rect_c.left()>=0 and rect_c.right()<w.frame_leyenda_curvas.width(),(chip.text(),rect_c)
        assert rect_c.bottom()<w.frame_leyenda_curvas.height(),(chip.text(),rect_c,w.frame_leyenda_curvas.size())
        assert chip.width()>=chip.sizeHint().width(),(chip.text(),chip.width(),chip.sizeHint())
        assert not any(rect_c.intersects(otro) for otro in rects_ley),(chip.text(),rects_ley)
        rects_ley.append(rect_c)
    assert w.size().width()==ancho
    for boton in (w.btn_curvas_egl,w.btn_curvas_bomba,w.btn_modo_didactico,w.btn_modo_exacto):
        opcion = QStyleOptionButton()
        opcion.initFrom(boton)
        rect = boton.style().subElementRect(QStyle.SE_PushButtonContents,opcion,boton)
        fuente = QFont(boton.font())
        fuente.setWeight(QFont.Bold)
        assert rect.width()-boton.iconSize().width()-4 >= QFontMetrics(fuente).horizontalAdvance(boton.text())


def test_redimensionar_conserva_controles_estado_y_resultados(ventana):
    w = ventana
    serie = w.egl_chart.series[0]
    w.chk_linea_piezometrica.setChecked(False)
    for ancho,alto in [(1280,800),(960,640),(1920,1080),(1280,800)]:
        w.resize(ancho,alto)
        estabilizar()
        assert not w.chk_linea_piezometrica.isChecked()
        assert not w.egl_chart.mostrar_hgl
        assert w.egl_chart.series[0] is serie
    assert not hasattr(w,'badge_no_escala')
    assert not hasattr(w,'lbl_egl_nota')
    assert w.btn_modo_didactico.isChecked() and not w.egl_chart.mostrar_valores
    w.btn_modo_exacto.click()
    assert w.btn_modo_exacto.isChecked() and w.egl_chart.mostrar_valores


def test_ventana_baja_permite_llegar_al_final_y_cambiar_modo(ventana):
    w = ventana
    w.resize(960,640)
    estabilizar()
    scroll = w.scroll_vista_curvas
    barra = scroll.verticalScrollBar()
    assert barra.maximum()>0
    barra.setValue(barra.maximum())
    estabilizar()
    fondo = w.panel_vista_curvas.mapTo(scroll.viewport(),QPoint(0,w.panel_vista_curvas.height()-1))
    assert 0<=fondo.y()<scroll.viewport().height()
    w._cambiar_modo_vista_curvas(1)
    estabilizar()
    assert w.stack_modo_curvas.currentIndex()==1
    assert w.btn_curvas_bomba.isChecked()
    assert not w.seg_escala_frame.isVisible()
    assert not w.chk_linea_piezometrica.isVisible()
    assert not w.chk_linea_energia.isVisible()
    w._cambiar_modo_vista_curvas(0)
    estabilizar()
    assert w.seg_escala_frame.isVisible()
    assert w.chk_linea_piezometrica.isVisible()
    assert w.chk_linea_energia.isVisible()
    assert w.egl_chart.series
