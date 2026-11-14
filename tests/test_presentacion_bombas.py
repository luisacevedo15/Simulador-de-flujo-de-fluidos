"""Presentación de series y método lineal, con Qt fuera de pantalla."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

from test_grafico_bombas_ui import app, datos_grafico, dibujar
from ui.grafico_bombas import WidgetGraficoBombas, PanelLateralCurvasBomba
from ui.curvas_presentacion import puntos_tabla,tabla_tsv
import io
import openpyxl
import xlsxwriter
import pytest


@pytest.mark.parametrize('ancho', [300, 380])
@pytest.mark.parametrize('caso', ['individual', 'equipos', 'riesgo', 'sin_datos'])
def test_reporte_lateral_no_recorta_ecuacion_ni_equipos(app, ancho, caso):
    from PyQt5.QtGui import QFont, QTextDocument
    from motor.bombas import EcuacionTotal
    from ui.reportes import reporte_bomba
    equipo = dict(bomba='Bomba auxiliar', Q=0.01, H=22.5, eta=0.82,
                  potencia_freno=18460, npsh_d=10.9, npsh_r=3.77)
    reparto = [equipo, dict(equipo, bomba='Bomba de reserva', activa=False,
                           H_cierre=22.499, H_op=22.5)] if caso == 'equipos' else None
    html = reporte_bomba(
        'Bomba 1', 'paralelo' if reparto else 'individual', 0.06855, 22.5,
        None if caso == 'sin_datos' else 0.82, 15130,
        None if caso == 'sin_datos' else 18460,
        1.0 if caso == 'riesgo' else 10.9,
        None if caso == 'sin_datos' else 3.77,
        cavitacion='RIESGO DE CAVITACIÓN' if caso == 'riesgo' else None,
        reparto=reparto, v_succion=2.18,
        ecuacion=EcuacionTotal(a=31.94, b=-17.86, c=-1750, tipo='ajuste',
                             R2=0.998, texto='H(Q) = 31.94 − 17.86·Q − 1750·Q²'),
    )
    doc = QTextDocument()
    doc.setDefaultFont(QFont('Segoe UI', 10))
    doc.setHtml(html)
    doc.setTextWidth(ancho)
    assert doc.size().width() <= ancho + 1
    texto = doc.toPlainText()
    assert '68.55' in texto and '22.50' in texto and '1750·Q²' in texto
    if caso == 'equipos':
        assert 'Bomba de reserva' in texto and 'No aporta caudal.' in texto
        assert 'NPSHr' in texto and 'Cerrada' in texto
    elif caso == 'riesgo':
        assert texto.index('REVISAR SUCCIÓN') < texto.index('RENDIMIENTO Y POTENCIA')
    elif caso == 'sin_datos':
        assert 'NPSHr no ingresado' in texto and '—' in texto


@pytest.mark.parametrize('ancho', [300, 380])
def test_tabla_de_tramos_cabe_en_panel_estrecho(app, ancho):
    from PyQt5.QtGui import QFont, QTextDocument
    from ui.reportes import rpt_tabla
    doc = QTextDocument()
    doc.setDefaultFont(QFont('Segoe UI', 10))
    doc.setHtml(rpt_tabla(
        [['Tubería 1', '0.0685', '2.18', '0.0200', '6.50']],
        ['RAMAL', 'Q (M³/S)', 'V (M/S)', 'F (C-W)', 'HF FRIC. (M)'],
    ))
    doc.setTextWidth(ancho)
    assert doc.size().width() <= ancho + 1
    assert 'HF TOTAL (M)' in doc.toPlainText()
    assert '6.50' in doc.toPlainText()


@pytest.mark.parametrize('metodo',['lineal','cuadratico'])
def test_metodo_condiciona_reporte_excel_propiedades_y_dialogo(app,metodo):
    from ui.reportes import reporte_bomba
    from ui.ventana.exportacion import ExportacionMixin
    from ui.ventana.memoria_calculo import MemoriaCalculoMixin
    from ui.ventana.principal import MainWindow
    from ui.dialogos import DialogoBomba
    from ui.graficos import BombaGrafica
    datos = datos_grafico(metodo=metodo)
    curva,est = datos['curvas'][0],datos['curva_eq']
    reporte = reporte_bomba('Bomba 1','individual',0.01,18,0.8,1765.8,2207.25,10,
        estacion=est,metodo=metodo,ecuacion=datos['ecuacion_total'])
    info = dict(nombre='Bomba 1',metodo=metodo,Q_op=0.01,H_op=18,
        curvas=[dict(nombre='Bomba 1',metodo=metodo,Q=list(curva.Q),H=list(curva.H),
            ecuacion=dict(a=20,b=600,c=-80000,texto='H = 20 + 600·Q - 80000·Q²'))],
        ecuacion_total=dict(texto='H = 20 + 600·Q - 80000·Q²',tipo='exacta'),
        puntos_equivalente=datos['muestras_equivalente'],muestras_bombas=datos['muestras_bombas'])
    class Exportador(ExportacionMixin,MemoriaCalculoMixin):
        pass
    e = Exportador()
    archivo = io.BytesIO()
    libro = xlsxwriter.Workbook(archivo,{'in_memory':True})
    e._hoja_bombas(libro,{'bomba':info})
    ws = libro.add_worksheet('Memoria')
    e._seccion_bombas_paso_a_paso(ws,e._formatos_excel(libro),libro,info,0)
    libro.close()
    wb = openpyxl.load_workbook(archivo,data_only=True)
    textos_excel = '\n'.join(str(c.value) for ws in wb for fila in ws for c in fila if isinstance(c.value,str))
    w = MainWindow()
    b = BombaGrafica()
    b.metodo = metodo
    b.curvas = [curva]
    w.canvas_view.scene().addItem(b)
    b.setSelected(True)
    dialogo = DialogoBomba(b,w)
    textos_ui = '\n'.join(l.text() for l in w.panel_content.findChildren(QLabel))+'\n'+b.toolTip()
    textos_ui += '\n'+'\n'.join(l.text() for l in dialogo.findChildren(QLabel))
    for texto in (reporte,textos_excel,textos_ui):
        if metodo=='lineal':
            assert 'Q²' not in texto and 'error máx. del ajuste' not in texto.lower(),texto
            assert 'Interpolación lineal' in texto
        else:
            assert 'Q²' in texto,texto
    w.canvas_view.scene().selectionChanged.disconnect()
    dialogo.close()
    w.close()


def test_hq_npshr_y_eficiencia_tienen_colores_y_estilos_distintos(app,monkeypatch):
    g = WidgetGraficoBombas()
    g.actualizar_datos(**datos_grafico(npsh=True))
    trazos = {}
    original = g._trazar_muestras
    def registrar(p,plot,muestras,q_max,y_max,color,estilo,*args,**kwargs):
        if muestras is g.muestras_bombas[0]:
            tipo = 'npshr' if kwargs.get('npshr') else 'eficiencia' if kwargs.get('eficiencia') else 'bomba'
            trazos[tipo] = color,estilo
        return original(p,plot,muestras,q_max,y_max,color,estilo,*args,**kwargs)
    monkeypatch.setattr(g,'_trazar_muestras',registrar)
    dibujar(g)
    assert len({color for color,_ in trazos.values()}) == 3
    assert trazos['npshr'][1] == Qt.DotLine
    assert len({estilo for _,estilo in trazos.values()}) == 3
    p = PanelLateralCurvasBomba(g)
    p.actualizar()
    assert 'NPSHr — Bomba 1' in [l.text() for l in p.w_lista_curvas.findChildren(QLabel)]
    from ui.grafico_bombas import SwatchTrazoCurva
    assert p._checks_filas[('npshr',0)].parentWidget().findChild(SwatchTrazoCurva).estilo == 'puntos'
    colores = [g._color_serie(tipo,i) for tipo in ('bomba','npshr','eficiencia') for i in range(8)]
    assert len(colores)==len(set(colores))
    assert g.COLOR_SISTEMA not in colores
    punto,texto = next((pos,t) for pos,t in g._puntos_tooltip if t.startswith('NPSHr — Bomba 1'))
    assert g._tooltip_en_posicion(punto) == texto
    g.limpiar_datos()
    assert g._puntos_tooltip == []
    p.close()
    g.close()


def test_lineal_muestra_puntos_y_copia_tabla_completa(app):
    g = WidgetGraficoBombas()
    datos = datos_grafico(metodo='lineal')
    g.actualizar_datos(**datos)
    p = PanelLateralCurvasBomba(g)
    p.actualizar()
    textos = '\n'.join(l.text() for l in p.findChildren(QLabel))
    assert 'Q²' not in textos and 'error máx.' not in textos.lower()
    assert 'Curva total (por puntos)' in textos
    assert 'Interpolación lineal entre 3 puntos; Q de 0 a 20 L/s' in textos
    assert 'Interpolación lineal · 3 puntos' in textos
    p._copiar_ecuacion()
    assert app.clipboard().text() == tabla_tsv(puntos_tabla(datos['curvas'][0]))
    assert all(datos['curvas'][0].H_de_Q(q)==h for q,h in puntos_tabla(datos['curvas'][0]))
    dibujar(g)
    assert g._ultimo_trazo_bombas_modo[0]['puntos_polilinea'] == puntos_tabla(datos['curvas'][0])
    p.close()
    g.close()
    # Una etapa lineal basta para presentar la combinación por puntos.
    from motor import CurvaBomba
    lineal = datos['curvas'][0]
    cuadratica = CurvaBomba('Bomba 2',[0,0.01,0.02],[20,18,0],metodo='cuadratico')
    assert lineal.metodo=='lineal' and cuadratica.metodo=='cuadratico'
    # El constructor real homogeneiza métodos. Aquí solo comprobamos la vista
    # ante metadatos mixtos, sin fabricar muestras ni resolver esa configuración.
    g = WidgetGraficoBombas()
    g.actualizar_datos([lineal,cuadratica],None,None,0,None,None,metodo='cuadratico')
    p = PanelLateralCurvasBomba(g)
    p.actualizar()
    assert p.lbl_eq_titulo.text() == 'Combinación por puntos'
    assert not any('Q²' in l.text() for l in p.findChildren(QLabel))
    assert 'sin puntos disponibles' in p.lbl_eq_total.text()
    p._copiar_ecuacion()
    assert app.clipboard().text() == tabla_tsv([])
    p.close()
    g.close()


def test_muestras_fuera_dominio_tienen_control_y_motivo_sin_cero(app):
    from motor.resultados import PuntoCurva
    g = WidgetGraficoBombas()
    datos = datos_grafico(metodo='lineal')
    datos['muestras_bombas'][0].append(PuntoCurva(0.021,None,False,'NO_CALCULADO: FUERA_DE_RANGO_CURVA'))
    g.actualizar_datos(**datos)
    p = PanelLateralCurvasBomba(g)
    p.actualizar()
    assert 'fuera_rango' in p._checks_filas
    assert '× Fuera del rango de la bomba' in [l.text() for l in p.w_lista_curvas.findChildren(QLabel)]
    assert 'FUERA_DE_RANGO_CURVA' in p._checks_filas['fuera_rango'].toolTip()
    dibujar(g)
    assert any('FUERA_DE_RANGO_CURVA' in texto for _,texto in g._puntos_tooltip)
    p._checks_filas['fuera_rango'].setChecked(False)
    dibujar(g)
    assert not any('FUERA_DE_RANGO_CURVA' in texto for _,texto in g._puntos_tooltip)
    assert datos['muestras_bombas'][0][-1].H is None
    p.close()
    g.close()


def test_un_solo_titulo_de_eficiencia(app):
    from PyQt5.QtCore import QRectF
    from PyQt5.QtGui import QImage,QPainter
    g = WidgetGraficoBombas()
    g.actualizar_datos(**datos_grafico())
    textos = [l.text() for l in g.findChildren(QLabel)]
    class Pintor(QPainter):
        def drawText(self,*args):
            if isinstance(args[-1],str):
                textos.append(args[-1])
            return super().drawText(*args)
    imagen = QImage(1000,700,QImage.Format_ARGB32)
    p = Pintor(imagen)
    try:
        g._dibujar_grafico_completo(p,QRectF(0,0,1000,700))
    finally:
        p.end()
    assert [t for t in textos if t.startswith('EFICIENCIA')] == ['EFICIENCIA η [%]']
    g.close()


def test_diagnostico_1055_es_rugosidad_en_metros_sin_k_ocultos(app):
    from ui.graficos import TanqueGrafico,BombaGrafica,TuberiaGrafica
    from motor.hidraulica import evaluar_tramo
    from motor import MotorFluidos
    a,b = TanqueGrafico(),TanqueGrafico()
    bomba = BombaGrafica()
    tubos = [TuberiaGrafica(a,bomba,1),TuberiaGrafica(bomba,b,2)]
    tramos,resultados = [],[]
    for t in tubos:
        t.longitud,t.diametro,t.rugosidad = 10,0.2,0.01
        assert t.u_eps == 'm'
        assert t._accesorios_asignados() == []
        assert t.sumatoria_K == t.sumatoria_Le_D == 0
        tramos.append(dict(L=10,D=0.2,eps=0.01,K=t.sumatoria_K,LeD=t.sumatoria_Le_D))
        resultados.append(evaluar_tramo(0.16725,10,0.2,0.01,0,0,dict(rho=1000,mu=0.001,g=9.81)))
    assert all(r.hf_localizada==0 for r in resultados)
    assert all(r.f==pytest.approx(0.07300888103370118,rel=1e-12) for r in resultados)
    total = MotorFluidos.carga_requerida_sistema(0.16725,z1=0,z2=0,rho=1000,mu=0.001,tramos=tramos)
    assert total == sum(r.hf_total for r in resultados)
    assert total == pytest.approx(10.54652039292086,rel=1e-12)
