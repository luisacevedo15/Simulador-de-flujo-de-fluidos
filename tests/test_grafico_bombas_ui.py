"""Presentación de bombas: pruebas Qt fuera de pantalla, sin cambiar el motor."""

import math
import os
from pathlib import Path

import pytest
from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtGui import QImage, QPainter, QFontDatabase
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton

from motor import CurvaBomba, EstacionBombeo
from motor.curvas import construir_curvas_estacion
from ui.grafico_bombas import PanelLateralCurvasBomba, WidgetGraficoBombas


@pytest.fixture
def app():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    instancia = QApplication.instance() or QApplication([])
    # El plugin offscreen de Windows puede arrancar sin ninguna fuente registrada.
    if not QFontDatabase().families():
        fuente = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/arial.ttf'
        if fuente.exists():
            QFontDatabase.addApplicationFont(str(fuente))
    yield instancia


def datos_grafico(eta=True,npsh=False,metodo='cuadratico'):
    bomba = CurvaBomba('Bomba 1',[0,0.01,0.02],[20,18,0],
        eta=[0.5,0.8,0.6] if eta else None,npsh_r=[2,3,4] if npsh else None,metodo=metodo)
    est = EstacionBombeo.en_serie([bomba],metodo=metodo)
    muestras = construir_curvas_estacion(est,lambda q:20+1e8*q*q,Q_op=0.01)
    return dict(curvas=[bomba],curva_eq=est,H_sistema=None,Q_op=0.01,H_op=18,
                eta_op=0.8 if eta else None,metodo=metodo,**muestras)


@pytest.mark.parametrize('altura',[8,230,2000])
def test_marcas_y_bonitas_limitadas_y_sin_unidad_repetida(app,altura):
    grafico = WidgetGraficoBombas()
    imagen = QImage(800,500,QImage.Format_ARGB32)
    textos = []
    class Pintor(QPainter):
        def drawText(self,*args):
            if isinstance(args[-1],str):
                textos.append(args[-1])
            return super().drawText(*args)
    pintor = Pintor(imagen)
    plot = QRectF(80,40,650,220)
    try:
        grafico._dibujar_ejes_y_textos(pintor,plot,QRectF(80,300,650,60),0.02,altura)
    finally:
        pintor.end()
    ticks = grafico._ticks_y_hq
    assert 2 <= len(ticks) <= 10
    posiciones = [grafico._map_y(t,plot,altura) for t in ticks]
    assert all(abs(a-b)>=22 for a,b in zip(posiciones,posiciones[1:]))
    assert not any(t.endswith(' m') or t.endswith(' %') for t in textos)
    paso = ticks[1]-ticks[0]
    mantisa = paso/10**math.floor(math.log10(paso))
    assert mantisa == pytest.approx(min((1,2,5,10),key=lambda n:abs(n-mantisa)))
    grafico.close()


def test_rango_inicial_solo_bombas_y_restablecer_vista(app):
    datos = datos_grafico()
    grafico = WidgetGraficoBombas()
    grafico.actualizar_datos(**datos)
    puntos = [p for lista in datos['muestras_bombas']+[datos['muestras_equivalente']]
              for p in lista if p.valido and p.H is not None]
    assert grafico.h_max_escala_base == 1.25*max([p.H for p in puntos]+[datos['H_op']])
    assert grafico.q_max_escala_base == pytest.approx(1.15*max(p.Q for p in puntos))
    grafico.zoom_factor,grafico.pan_offset = 3,QPointF(22,40)
    grafico.restablecer_vista()
    assert grafico.zoom_factor == 1 and grafico.pan_offset == QPointF(0,0)
    grafico.close()


def test_rango_caudal_pequeno_y_marcas_tras_zoom_desplazamiento(app):
    from motor.resultados import PuntoCurva
    b = CurvaBomba('B',[0,1e-6],[1,0])
    g = WidgetGraficoBombas()
    g.actualizar_datos([b],None,None,5e-7,0.5,None,
        muestras_bombas=[[PuntoCurva(0,1,True,'OK'),PuntoCurva(1e-6,0,True,'OK')]])
    assert g.q_max_escala_base == pytest.approx(1.15e-6)
    assert g.h_max_escala_base == 1.25
    g.zoom_factor,g.pan_offset = 4,QPointF(0,45)
    plot = QRectF(80,50,600,220)
    ticks = g._marcas_y(plot,1.25)
    assert len(ticks)<=10
    posiciones = [g._map_y(t,plot,1.25) for t in ticks]
    assert all(plot.top()-1e-6<=y<=plot.bottom()+1e-6 for y in posiciones)
    assert all(abs(a-b)>=22 for a,b in zip(posiciones,posiciones[1:]))
    g.close()


@pytest.mark.parametrize('npsh',[False,True])
def test_nombre_hq_y_entrada_npshr_separados(app,npsh):
    datos = datos_grafico(npsh=npsh)
    grafico = WidgetGraficoBombas()
    grafico.actualizar_datos(**datos)
    panel = PanelLateralCurvasBomba(grafico)
    panel.actualizar()
    nombres = [l.text() for l in panel.w_lista_curvas.findChildren(QLabel)]
    assert 'Bomba 1' in nombres
    assert ('NPSHr — Bomba 1' in nombres) == npsh
    assert (('npshr',0) in panel._checks_filas) == npsh
    panel.close()
    grafico.close()


def test_nombre_equipo_y_dialogo_no_confunden_encabezado_npshr(app):
    from ui.graficos import BombaGrafica
    from ui.dialogos import DialogoBomba
    from test_interfaz_regresiones import MainWindow
    w = MainWindow()
    b = BombaGrafica(nombre='Bomba 7')
    w.canvas_view.scene().addItem(b)
    b.curvas = datos_grafico(npsh=True)['curvas']
    b.setSelected(True)
    textos = [l.text() for l in w.panel_content.findChildren(QLabel)]
    assert '<b>Bomba 7</b>' in textos
    assert '<b>NPSHr</b>' not in textos
    dialogo = DialogoBomba(b,w)
    assert dialogo.tabs_bombas.tabText(0) == 'Bomba 7'
    dialogo._validar_y_aceptar()
    assert b.curvas[0].nombre == 'Bomba 7'
    assert b.equipos[0]['nombre'] == 'Bomba 7'
    w.canvas_view.scene().selectionChanged.disconnect()
    w.close()


@pytest.mark.parametrize('metodo',['cuadratico','lineal'])
def test_detalle_ecuacion_distingue_ajuste_de_interpolacion(app,metodo,monkeypatch):
    datos = datos_grafico(metodo=metodo)
    monkeypatch.setattr(CurvaBomba,'error_max_ajuste',property(lambda self:0.1234))
    g = WidgetGraficoBombas()
    g.actualizar_datos(**datos)
    p = PanelLateralCurvasBomba(g)
    p.actualizar()
    detalle = p.lbl_eq_detalle.text()
    if metodo == 'cuadratico':
        assert detalle == 'Ajuste cuadrático — error máx. 0.1234 m'
    else:
        assert detalle == ''
        assert 'Interpolación lineal' in p.lbl_eq_total.text()
        assert 'Q²' not in p.lbl_eq_total.text()
    p.close()
    g.close()


def test_ecuacion_larga_se_puede_leer_y_copiar_completa(app):
    g = WidgetGraficoBombas()
    p = PanelLateralCurvasBomba(g)
    p.resize(340,650)
    texto = 'H(Q) = 123456789.123456 + 123456789012345.6789·Q − 98765432109876543210.12345·Q²'
    p.lbl_eq_total.setText(texto)
    p.show()
    app.processEvents()
    assert hasattr(p,'scroll_ecuacion')
    assert p.scroll_ecuacion.horizontalScrollBar().maximum()>0
    assert p.lbl_eq_total.width() >= p.lbl_eq_total.fontMetrics().horizontalAdvance(texto)
    p._copiar_ecuacion()
    assert app.clipboard().text() == texto
    p.close()
    g.close()


def dibujar(g):
    imagen = QImage(1000,700,QImage.Format_ARGB32)
    p = QPainter(imagen)
    try:
        g._dibujar_grafico_completo(p,QRectF(0,0,1000,700))
    finally:
        p.end()
    return imagen


def test_boton_eficiencia_conserva_estado_y_panel_sin_controles_eliminados(app):
    datos = datos_grafico()
    g = WidgetGraficoBombas()
    g.actualizar_datos(**datos)
    p = PanelLateralCurvasBomba(g)
    p.actualizar()
    assert not hasattr(p, 'btn_todas')
    assert not hasattr(p, 'btn_solo_total')
    assert not hasattr(p, '_activar_todas')
    assert not hasattr(p, '_activar_solo_total_sistema')
    assert {b.text() for b in p.findChildren(QPushButton)} == {'Copiar'}
    assert 'panel_eficiencia' not in p._checks_filas
    assert 'Panel de eficiencia' not in [l.text() for l in p.w_lista_curvas.findChildren(QLabel)]
    dibujar(g)
    alto_con_panel = g._ultimo_plot_hq.height()
    assert g.btn_eficiencia.isEnabled() and g.btn_eficiencia.isChecked()
    g.btn_eficiencia.click()
    assert not g.btn_eficiencia.isChecked()
    dibujar(g)
    assert g._ultimo_plot_eta is None and g._ultimo_plot_hq.height()>alto_con_panel
    g.btn_eficiencia.click()
    assert g.btn_eficiencia.isChecked()
    dibujar(g)
    assert g._ultimo_plot_eta is not None
    g.btn_eficiencia.click()
    g.limpiar_datos()
    g.actualizar_datos(**datos)
    p.actualizar()
    assert not g.btn_eficiencia.isChecked()
    assert 'panel_eficiencia' not in p._checks_filas
    g.actualizar_datos(**datos_grafico(eta=False))
    assert not g.btn_eficiencia.isEnabled()
    assert 'datos de eficiencia' in g.btn_eficiencia.toolTip()
    p.close()
    g.close()


def test_descargas_independientes_con_contenido_y_nombres_correctos(app,tmp_path,monkeypatch):
    from PyQt5.QtWidgets import QFileDialog
    g = WidgetGraficoBombas()
    g.actualizar_datos(**datos_grafico())
    dibujar(g)
    nombres = []
    def destino(parent,titulo,nombre,filtro):
        nombres.append(nombre)
        return str(tmp_path/nombre),'PNG'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',destino)
    trazos = []
    sistema,eficiencia = g._trazar_curva_sistema,g._trazar_curva_eficiencia
    def trazar_sistema(*a,**k):
        trazos.append('hq')
        return sistema(*a,**k)
    def trazar_eficiencia(*a,**k):
        trazos.append('eta')
        return eficiencia(*a,**k)
    monkeypatch.setattr(g,'_trazar_curva_sistema',trazar_sistema)
    monkeypatch.setattr(g,'_trazar_curva_eficiencia',trazar_eficiencia)
    g.btn_exportar.click()
    assert 'hq' in trazos and 'eta' not in trazos
    trazos.clear()
    g.btn_exportar_eficiencia.click()
    assert 'eta' in trazos and 'hq' not in trazos
    assert nombres == ['curva_HQ.png','curva_eficiencia.png']
    archivos = [tmp_path/n for n in nombres]
    imagenes = [QImage(str(f)) for f in archivos]
    assert all(not i.isNull() and i.width()>=2500 and i.height()>=1500 for i in imagenes)
    assert imagenes[0].size() == imagenes[1].size()
    assert archivos[0].read_bytes() != archivos[1].read_bytes()
    g.set_visibilidad('panel_eficiencia',False)
    assert g.btn_exportar_eficiencia.isHidden()
    g.close()
