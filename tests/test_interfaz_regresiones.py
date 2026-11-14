"""Regresiones de selección y paneles con Qt fuera de pantalla."""

import os
import json
from pathlib import Path
from dataclasses import replace

import pytest
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication, QLabel

from ui.graficos import BombaGrafica, TanqueGrafico, TuberiaGrafica
from ui.ventana.principal import MainWindow
from motor.hidraulica import evaluar_tramo
from motor.perfiles import construir_perfil_ruta, perfil_como_serie
from motor.resultados import PerdidaAccesorio


@pytest.fixture
def ventana():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    yield w
    w.canvas_view.scene().selectionChanged.disconnect()
    w.close()
    w.deleteLater()
    app.processEvents()


def red_con_bomba(w, completa=False):
    scene = w.canvas_view.scene()
    a = TanqueGrafico(100,100,id_tanque=1)
    b = TanqueGrafico(700,100,id_tanque=2)
    bomba = BombaGrafica(400,100)
    for item in (a,b,bomba):
        scene.addItem(item)
    tubos = [TuberiaGrafica(a,bomba,id_tuberia=1)]
    if completa:
        tubos.append(TuberiaGrafica(bomba,b,id_tuberia=2))
    for tubo in tubos:
        scene.addItem(tubo)
    w.canvas_view.centerOn(350,250)
    return scene,a,b,bomba,tubos


def widgets_panel(w):
    return [w.panel_content_layout.itemAt(i).widget()
            for i in range(w.panel_content_layout.count())]


def test_bomba_vacio_panel_base_sin_fusion_ni_dashboard_duplicado(ventana):
    w = ventana
    scene,_,_,bomba,_ = red_con_bomba(w)
    dashboard = w.dashboard_widget
    for _ in range(3):
        bomba.setSelected(True)
        assert w.bomba_seleccionada is bomba
        assert dashboard.isHidden()
        assert dashboard not in widgets_panel(w)
        assert 'Propiedades' in w.lbl_panel_title.text()
        QTest.mouseClick(w.canvas_view.viewport(),Qt.LeftButton,
                        pos=w.canvas_view.mapFromScene(QPointF(350,350)))
        assert scene.selectedItems() == []
        assert widgets_panel(w) == [dashboard]
        assert w.lbl_panel_title.text() == 'Análisis del Sistema (Bernoulli)'
        assert not dashboard.isHidden()
        assert w.bomba_seleccionada is None
    assert len([label for label in w.panel_scroll.findChildren(QLabel)
                if label.text() == 'MODO DE ANÁLISIS']) == 1


def test_refrescar_boton_no_invalida_resultados_ni_reconstruye_panel(ventana,monkeypatch):
    w = ventana
    scene,_,_,bomba,_ = red_con_bomba(w)
    bomba.setSelected(True)
    campo = w.campos_bomba['z_bomba']
    bomba.Q_op,bomba.H_op = 0.01,20
    llamadas = []
    monkeypatch.setattr(w,'_limpiar_resultados_bomba',lambda *args,**kwargs:llamadas.append(args))
    w._refrescar_combos_dashboard()
    assert llamadas == [], 'Refrescar el texto del botón no puede limpiar resultados ni paneles'
    assert w.campos_bomba['z_bomba'] is campo
    assert bomba.Q_op == 0.01 and bomba.H_op == 20
    assert scene.selectedItems() == [bomba]


@pytest.mark.parametrize('confirmacion',['enter','foco'])
def test_editar_tanque_con_bomba_conserva_panel_y_seleccion(ventana,confirmacion):
    w = ventana
    scene,tanque,_,bomba,tubos = red_con_bomba(w,completa=True)
    bomba.setSelected(True)
    QTest.mouseClick(w.canvas_view.viewport(),Qt.LeftButton,
                    pos=w.canvas_view.mapFromScene(tanque.sceneBoundingRect().center()))
    QApplication.processEvents()
    assert scene.selectedItems() == [tanque]
    campo = w.campos_tanque['z']
    bomba.Q_op,bomba.H_op = 0.01,20
    tubos[0].hf_calculado = 2
    w.datos_exportacion = {'viejo':True}
    w._tabla_cache = {'viejo':True}
    w._perfiles_calculados = {'viejo':True}
    cambios_seleccion = QSignalSpy(scene.selectionChanged)
    campo.setText('12.5')
    assert w.campos_tanque.get('z') is campo
    assert w.bomba_seleccionada is None
    campo.setFocus()
    campo.selectAll()
    QTest.keyClicks(campo,'13.75')
    if confirmacion == 'enter':
        QTest.keyClick(campo,Qt.Key_Return)
    else:
        w.campos_tanque['atmosfera'].setFocus()
    QApplication.processEvents()
    assert tanque.elevacion_z == 13.75
    assert scene.selectedItems() == [tanque]
    assert len(cambios_seleccion) == 0
    assert w.tanque_seleccionado is tanque
    assert w.campos_tanque['z'] is campo and not campo.isHidden()
    assert w.lbl_panel_title.text() == 'Propiedades del Tanque 1'
    assert w.datos_exportacion == {} and w._tabla_cache is None
    assert w._perfiles_calculados == {}
    assert tubos[0].hf_calculado is None
    assert bomba.Q_op is None and bomba.H_op is None


def test_invalidar_no_destruye_editor_de_la_bomba_actual(ventana):
    w = ventana
    _,_,_,bomba,_ = red_con_bomba(w,completa=True)
    bomba.setSelected(True)
    QApplication.processEvents()
    campo = w.campos_bomba['z_bomba']
    campo.setFocus()
    campo.selectAll()
    QTest.keyClicks(campo,'3.25')
    assert bomba.z_bomba == 3.25
    assert w.campos_bomba['z_bomba'] is campo
    assert not campo.isHidden()


def perfil_dorado_a():
    d = json.loads((Path(__file__).parent/'golden/a_tanque_tanque.json').read_text(encoding='utf-8'))
    e,t = d['entrada'],d['entrada']['tramos'][0]
    r = evaluar_tramo(d['tramos'][0]['Q'],t['L'],t['D'],t['eps'],t['K'],t['LeD'],d['fluido'],id='T1')
    return construir_perfil_ruta([r],e['H_inicio'],e['H_fin'],
                                etiquetas=['Tanque 1','Tanque 2'])


def dibujar_textos(widget,serie):
    from PyQt5.QtCore import QRectF
    from PyQt5.QtGui import QImage,QPainter
    textos = []
    class Pintor(QPainter):
        def drawText(self,*args):
            if args and isinstance(args[-1],str):
                textos.append(args[-1])
            return super().drawText(*args)
    widget.actualizar_datos([serie])
    imagen = QImage(1100,650,QImage.Format_ARGB32)
    pintor = Pintor(imagen)
    try:
        widget._dibujar_perfil(pintor,QRectF(0,0,1100,650))
    finally:
        pintor.end()
    return textos


def test_rotulo_de_friccion_identifica_tuberia_y_no_tanque_destino(ventana):
    perfil = perfil_dorado_a()
    textos = dibujar_textos(ventana.egl_chart,perfil_como_serie(perfil))
    assert any('Tubería (Tanque 1 -> Tanque 2)' in t and 'Pérdida por fricción' in t
               and 'hf = 15.00 m' in t for t in textos),textos
    assert any('Salida de Tanque 1' in t for t in textos)
    assert any('Entrada a Tanque 2' in t for t in textos)
    assert not any(t.startswith('Tanque 2: hf') for t in textos)


def test_anotaciones_corresponden_a_eventos_y_no_al_total_del_resumen(ventana):
    perfil = perfil_dorado_a()
    serie = perfil_como_serie(perfil)
    widget = ventana.egl_chart
    anotaciones = widget._anotaciones_eventos(serie)
    assert len(anotaciones) == 3
    assert [i for i,_,_ in anotaciones] == [0,2,3]
    for indice,evento,texto in anotaciones:
        assert evento is perfil.puntos[indice]
        assert texto.startswith(evento.etiqueta)
        assert serie['puntos'][indice]['tipo_evento'] == evento.tipo
        assert serie['puntos'][indice]['indice_evento'] == indice
    assert anotaciones[0][2] == 'Salida de Tanque 1'
    assert anotaciones[1][2] == 'Tubería (Tanque 1 -> Tanque 2): Pérdida por fricción — hf = 15.00 m'
    assert anotaciones[2][2] == 'Entrada a Tanque 2'
    widget.actualizar_datos([serie],resumen={'hf_total':999})
    assert widget._anotaciones_eventos(serie) == anotaciones
    chips = ventana.frame_leyenda_curvas.findChildren(QLabel)
    textos_ley = [c.text() for c in chips]
    assert any('Cinética' in t and 'v²/2g' not in t for t in textos_ley)
    assert any('Fricción' in t for t in textos_ley)
    assert not any('Entrada / Salida' in t for t in textos_ley)
    assert not any('Σhf' in t for t in textos_ley)
    assert not any('Accesorios' in t or 'Bomba' in t for t in textos_ley)
    friccion_item = next(it for it in widget.elementos_leyenda() if it[0] == 'friccion')
    assert friccion_item[3] == '#e74c3c'
    assert widget.COLORES_CAUSA['friccion'] == '#e74c3c'
    ventana.chk_linea_piezometrica.setChecked(False)
    assert not any('Cinética' in c.text() for c in ventana.frame_leyenda_curvas.findChildren(QLabel))


def test_accesorio_y_friccion_partida_tienen_eventos_independientes(ventana):
    fluido = dict(rho=1000,mu=0.001,g=9.81)
    tramo = evaluar_tramo(0.001,10,0.05,0,2,0,fluido,id='T1')
    tramo = replace(tramo,accesorios=(PerdidaAccesorio('Válvula','T1',5,2,0,tramo.hf_localizada),))
    perfil = construir_perfil_ruta([tramo],10,10-tramo.hf_total,etiquetas=['Tanque 1','Tanque 2'])
    serie = perfil_como_serie(perfil)
    anotaciones = ventana.egl_chart._anotaciones_eventos(serie)
    friccion = [(i,e,t) for i,e,t in anotaciones if e.tipo == 'tubería']
    assert len(friccion) == 2  # Mismo nombre de tubería: no se deduplica ni agrega hf.
    assert friccion[0][0] != friccion[1][0]
    assert all(e.perdida == tramo.hf_distribuida/2 for _,e,_ in friccion)
    accesorios = [(i,e,t) for i,e,t in anotaciones if e.tipo == 'accesorio']
    assert len(accesorios) == 1
    assert accesorios[0][1].perdida == tramo.hf_localizada
    assert accesorios[0][2].startswith('Accesorio Válvula — hf')
    assert sum(e.perdida for _,e,_ in anotaciones) == pytest.approx(tramo.hf_total,rel=1e-15)
    assert perfil.estado == 'OK'
