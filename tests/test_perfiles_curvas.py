"""Perfiles y muestras SI únicos; QWidget solo se dibuja fuera de pantalla."""

from dataclasses import FrozenInstanceError, fields, replace
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
import xlsxwriter

from motor import CurvaBomba, EstacionBombeo, MotorFluidos, evaluar_operacion_estacion
from motor.curvas import (construir_curvas_estacion, curva_equivalente_estacion,
                          evaluar_carga_sistema_ramificada, muestrear_curva_bomba,
                          muestrear_curva_sistema)
from motor.hidraulica import evaluar_tramo
from motor.perfiles import construir_perfil_ruta, construir_perfiles_red, perfil_como_serie
from motor.resultados import PerfilRuta, PuntoCurva, PuntoPerfil
from ui.ventana.exportacion import ExportacionMixin


CARPETA = Path(__file__).resolve().parent / 'golden'
AGUA = dict(rho=1000.0, mu=0.001, g=9.81)


def dorado(nombre):
    return json.loads((CARPETA / f'{nombre}.json').read_text(encoding='utf-8'))


def estacion(entrada):
    bombas = [CurvaBomba(c['nombre'], c['Q'], c['H'], eta=c['eta'],
              npsh_r=c['npsh_r'], metodo=c['metodo']) for c in entrada['curvas']]
    construir = (EstacionBombeo.en_serie if entrada.get('arreglo') == 'serie'
                 else EstacionBombeo.en_paralelo)
    return construir(bombas)


def tramos_capturados(d):
    return tuple(evaluar_tramo(t['Q'], e['L'], e['D'], e['eps'], e['K'], e['LeD'],
                              AGUA, id=t['id']) for t,e in zip(d['tramos'],d['entrada']['tramos']))


def sistema_serie(e):
    return lambda q: MotorFluidos.carga_requerida_sistema(q, z1=e['z_inicio'],
        z2=e['z_fin'], rho=1000, mu=0.001, tramos=e['tramos'])


def resolver_estacion(nombre='d_una_bomba'):
    d = dorado(nombre)
    e = d['entrada']
    est = estacion(e)
    n = e['npsh']
    sistema = sistema_serie(e)
    r = evaluar_operacion_estacion(est, sistema, **AGUA, tramos=e['tramos'],
        indices_succion=(0,), P_atm=n['P_atm'], P_vap=n['P_vap'],
        z1=n['z1'], z_bomba=n['z_bomba'], P1=n['P1'])
    assert r.estado == 'OK'
    return r, est, sistema, d


def comprobar_hgl(perfil):
    for p in perfil.puntos:
        assert p.HGL == p.EGL - p.v**2 / (2 * 9.81)


@pytest.mark.parametrize('nombre', ['a_tanque_tanque', 'b_serie_accesorios'])
def test_perfil_dorados_gravedad_sin_recalcular(nombre, monkeypatch):
    d = dorado(nombre)
    e = d['entrada']
    tramos = tramos_capturados(d)
    for t, esperado in zip(tramos, d['tramos']):
        assert t.hf_total == pytest.approx(esperado['hf_total'], rel=1e-12)

    def prohibido(*args, **kwargs):
        pytest.fail('El perfil no puede recalcular pérdidas')
    monkeypatch.setattr(MotorFluidos, 'calcular_hf', prohibido)
    p = construir_perfil_ruta(tramos, e['H_inicio'], e['H_fin'],
        cotas=[20] + [None]*(len(tramos)-1) + [5])
    assert p.estado == 'OK', p.mensaje
    assert p.H_inicio - sum(t.hf_total for t in tramos) == pytest.approx(p.H_final, rel=1e-9)
    assert p.H_final_calculada == pytest.approx(p.H_final, rel=1e-9)
    assert p.puntos[-1].EGL == p.H_final_calculada
    comprobar_hgl(p)
    if len(tramos) == 2:
        i = next(i for i, pt in enumerate(p.puntos) if pt.tipo == 'cambio de diámetro')
        antes, despues = p.puntos[i-1:i+1]
        assert antes.s == despues.s == tramos[0].L
        assert antes.EGL == despues.EGL
        assert antes.HGL != despues.HGL
        assert antes.z is None and despues.z is None


def test_perfil_bomba_sube_exactamente_altura_resuelta():
    r, _, _, d = resolver_estacion()
    p = construir_perfil_ruta(r.tramos, d['entrada']['z_inicio'], d['entrada']['z_fin'],
                             bombas=[(0, r.bombas[0])])
    assert p.estado == 'OK', p.mensaje
    i = next(i for i, pt in enumerate(p.puntos) if pt.tipo == 'bomba')
    assert p.puntos[i].EGL - p.puntos[i-1].EGL == r.H
    assert p.H_bombas == r.H
    comprobar_hgl(p)


def test_perfil_no_fuerza_el_final_si_falla_balance():
    t = tramos_capturados(dorado('a_tanque_tanque'))
    p = construir_perfil_ruta(t, 20, 6)
    assert p.estado == 'SIN_BALANCE'
    assert p.residuo_energia_relativo > 1e-9
    assert p.H_final_calculada != p.H_final
    assert p.puntos[-1].EGL == p.H_final_calculada


def test_bombas_paralelas_no_duplican_salto():
    r, _, _, d = resolver_estacion('e_dos_bombas_paralelo')
    p = construir_perfil_ruta(r.tramos, 0, d['entrada']['z_fin'],
                             bombas=[(0,b) for b in r.bombas])
    assert p.H_bombas == r.H
    assert len([pt for pt in p.puntos if pt.tipo == 'bomba']) == 1
    # El punto histórico tiene residuo >1e-9: no se modifica para cerrar el perfil.
    assert p.estado == 'SIN_BALANCE'


def test_bomba_cerrada_no_oculta_el_salto_de_su_etapa():
    r,_,_,_ = resolver_estacion('e_dos_bombas_paralelo')
    cerrada = replace(r.bombas[0],activa=False,Q=0,H=0)
    perfil = construir_perfil_ruta(r.tramos,0,10,bombas=[(0,cerrada),(0,r.bombas[1])])
    assert perfil.H_bombas == r.H
    assert len([p for p in perfil.puntos if p.tipo == 'bomba']) == 1


def test_ramificada_todas_las_salidas_comparten_valores():
    d = dorado('f_ramificada_bomba')
    e = d['entrada']
    r = MotorFluidos.resolver_bomba_ramificada(estacion(e), e['principal'], e['ramas'],
        rho=1000, mu=0.001, P_atm=101325, P_vap=2339, tol=1e-15, generar_curva=False)
    assert r.estado == 'OK'
    assert r.Q == pytest.approx(d['resultado']['Q'], rel=1e-12)
    rutas = [dict(id=str(rama['id_ramal']),
        tramos=r.resultados_tramos_principal + tuple(resultado['resultados_tramos']),
        H_inicio=e['principal']['H'], H_final=rama['H'],
        bombas=[(0,r.estacion_resultado)]) for rama,resultado in zip(e['ramas'],r.resultados_ramales)]
    perfiles = construir_perfiles_red(rutas)
    assert len(perfiles) == len(e['ramas']) == 2
    for p in perfiles:
        assert p.estado == 'OK', p.mensaje
        comprobar_hgl(p)
    # Prefijo hasta el final del tronco; el siguiente punto cambia la velocidad del ramal.
    longitud = sum(t.L for t in r.resultados_tramos_principal)
    compartidos = []
    for perfil in perfiles:
        fin = next(i for i,p in enumerate(perfil.puntos) if p.s == longitud and p.tipo == 'cambio de diámetro')
        compartidos.append(perfil.puntos[:fin])
    assert compartidos[0] == compartidos[1]
    assert all(a is b for a,b in zip(*compartidos))
    assert sum(p.H_bomba for p in perfiles[0].puntos) == r.H_bomba
    h, _ = evaluar_carga_sistema_ramificada(r.Q, e['principal'], e['ramas'], 1000, 0.001)
    assert abs(h-r.H_bomba) <= 1e-6


@pytest.mark.parametrize('nombre', ['d_una_bomba','e_dos_bombas_serie','e_dos_bombas_paralelo'])
def test_muestras_comparten_malla_y_operacion(nombre):
    r, est, sistema, _ = resolver_estacion(nombre)
    paquete = construir_curvas_estacion(est, sistema, Q_op=r.Q)
    conjuntos = [paquete['muestras_sistema'], paquete['muestras_equivalente']] + paquete['muestras_bombas']
    assert all(len(c) == 101 for c in conjuntos)
    assert all([p.Q for p in c] == [p.Q for p in conjuntos[0]] for c in conjuntos)
    hs = next(p.H for p in conjuntos[0] if p.Q == r.Q)
    hb = next(p.H for p in conjuntos[1] if p.Q == r.Q)
    assert abs(hs - hb) <= 1e-6
    assert len(construir_curvas_estacion(est, sistema, N=17)['muestras_sistema']) == 17


def test_fallos_conservan_indice_estado_y_no_cero():
    def sistema(q):
        if q == 0.5:
            raise RuntimeError('sin convergencia')
        return 10+q
    puntos = muestrear_curva_sistema(sistema, 1, N=3)
    assert len(puntos) == 3
    assert puntos[1].Q == 0.5 and puntos[1].H is None
    assert not puntos[1].valido and 'sin convergencia' in puntos[1].estado
    bomba = CurvaBomba('B',[0,1],[20,10])
    for puntos in (muestrear_curva_bomba(bomba,2,N=3),
                   curva_equivalente_estacion(EstacionBombeo.en_serie([bomba]),2,N=3)):
        assert len(puntos) == 3
        assert puntos[-1].H is None and not puntos[-1].valido
        assert 'FUERA_DE_RANGO' in puntos[-1].estado


def test_contratos_inmutables_completos_finitos():
    punto = PuntoPerfil(0,None,2,2,0,'entrada','A')
    perfil = construir_perfil_ruta(tramos_capturados(dorado('a_tanque_tanque')),20,5)
    for obj in (punto,perfil,PuntoCurva(0,None,False,'NO_CALCULADO')):
        salida = json.loads(json.dumps(obj.to_dict(),allow_nan=False))
        assert set(salida) == {f.name for f in fields(obj)}
        with pytest.raises(FrozenInstanceError):
            obj.nuevo = 1
    assert punto.to_dict()['z'] is None
    for obj in (replace(punto,EGL=float('nan')),replace(perfil,H_inicio=float('inf')),
                PuntoCurva(float('inf'),None,False,'NO_CALCULADO')):
        with pytest.raises(ValueError,match='finito'):
            obj.to_dict()


def test_excel_contiene_todas_las_rutas_y_los_mismos_puntos():
    t = tramos_capturados(dorado('b_serie_accesorios'))
    perfiles = construir_perfiles_red([dict(id=f'A → {dest}',tramos=t,H_inicio=20,H_final=5)
                                     for dest in ('B','C')])
    salida = io.BytesIO()
    libro = xlsxwriter.Workbook(salida,{'in_memory':True})
    ExportacionMixin()._hoja_perfil_egl_hgl(libro,dict(perfiles=perfiles))
    libro.close()
    ws = openpyxl.load_workbook(salida,data_only=True)['Perfil EGL-HGL']
    filas = list(ws.values)
    for perfil in perfiles:
        inicio = next(i for i,f in enumerate(filas) if f[1] == f'{perfil.id} · OK')
        for fila,p in zip(filas[inicio+1:],perfil.puntos):
            assert fila[2] == p.s
            assert fila[3] == pytest.approx(p.EGL,rel=1e-15)
            assert fila[4] == pytest.approx(p.HGL,rel=1e-15)


@pytest.fixture
def qt_app():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_grafico_excel_usan_mismas_listas_sin_evaluar(qt_app, monkeypatch):
    from PyQt5.QtCore import QRectF
    from PyQt5.QtGui import QImage, QPainter
    from ui.grafico_bombas import WidgetGraficoBombas, PanelLateralCurvasBomba
    r,est,sistema,d = resolver_estacion()
    paquete = construir_curvas_estacion(est,sistema,Q_op=r.Q)
    # Fallo interior visible: no debe unir los puntos a ambos lados del fallo.
    paquete['muestras_sistema'][50] = PuntoCurva(paquete['muestras_sistema'][50].Q,None,False,'FALLO_PRUEBA')
    info = dict(curvas=d['entrada']['curvas'],puntos_sistema=paquete['muestras_sistema'],
        puntos_equivalente=paquete['muestras_equivalente'],muestras_bombas=paquete['muestras_bombas'])
    def prohibido(*args,**kwargs):
        pytest.fail('El dibujante/exportador no puede evaluar curvas')
    monkeypatch.setattr(est,'H_estacion',prohibido)
    monkeypatch.setattr(est.etapas[0][0],'H_de_Q',prohibido)
    monkeypatch.setattr(est.etapas[0][0],'eta_de_Q',prohibido)
    grafico = WidgetGraficoBombas()
    grafico.actualizar_datos([est.etapas[0][0]],est,prohibido,r.Q,r.H,r.eficiencia,**paquete)
    panel = PanelLateralCurvasBomba(grafico)
    panel.actualizar()
    assert grafico.muestras_sistema is info['puntos_sistema']
    assert grafico.muestras_equivalente is info['puntos_equivalente']
    assert grafico.muestras_bombas is info['muestras_bombas']
    imagen = QImage(900,650,QImage.Format_ARGB32)
    pintor = QPainter(imagen)
    try:
        grafico._dibujar_grafico_completo(pintor,QRectF(0,0,900,650))
    finally:
        pintor.end()
    salida = io.BytesIO()
    libro = xlsxwriter.Workbook(salida,{'in_memory':True})
    exportador = ExportacionMixin()
    for funcion in (exportador._hoja_bombas,exportador._hoja_curvas_individuales,
                    exportador._hoja_curva_equivalente):
        funcion(libro,dict(bomba=info))
    libro.close()
    wb = openpyxl.load_workbook(salida,data_only=True)
    for hoja,colq,colh,muestras in (
            ('Bombas',2,4,info['puntos_sistema']),
            ('Curva Equivalente',2,4,info['puntos_equivalente']),
            ('Curvas Individuales',2,4,info['muestras_bombas'][0])):
        filas = list(wb[hoja].values)
        inicio = next(i for i,f in enumerate(filas) if f[1] == 1 and f[colq] == 0)
        assert len(filas[inicio:inicio+101]) == 101
        for fila,p in zip(filas[inicio:inicio+101],muestras):
            assert fila[colq] == pytest.approx(p.Q,rel=1e-15)
            if p.valido:
                assert fila[colh] == pytest.approx(p.H,rel=1e-15)
            else:
                assert 'No calculado' in fila[colh] and p.estado in fila[colh]
    grafico.limpiar_datos()
    assert grafico.muestras_sistema == []
    panel.close()
    grafico.close()


@pytest.mark.parametrize('ramificada',[False,True])
def test_handlers_entregan_mismas_muestras_y_todas_las_rutas(monkeypatch,ramificada):
    import ui.ventana.bombas as ui_b
    import ui.ventana.ramificadas as ui_r
    import ui.ventana.resolucion as ui_p
    from test_fase_redes import Control, Tanque, Union, Bomba, Tubo
    for modulo in (ui_b,ui_r,ui_p):
        for nombre,tipo in [('TanqueGrafico',Tanque),('NodoUnionGrafico',Union),('BombaGrafica',Bomba)]:
            monkeypatch.setattr(modulo,nombre,tipo,raising=False)
    c = Control()
    c.fluido_P_atm,c.fluido_P_vap = 101325,2339
    capturas = []
    c.grafico_bombas = SimpleNamespace(actualizar_datos=lambda **datos:capturas.append(datos))
    a,b = Tanque('A',H=0),Tanque('B',H=0 if ramificada else 10)
    bomba = Bomba('Bomba 1',x=5)
    bomba.id_bomba,bomba.z_bomba,bomba.metodo,bomba.arreglo = 1,0,'lineal','individual'
    curva = (CurvaBomba('B1',[0,1e-5],[0.01,0],eta=[0.8,0.8],metodo='lineal')
             if ramificada else CurvaBomba('B1',[0,0.04],[40,0],eta=[0.8,0.8],metodo='lineal'))
    bomba.curvas,bomba.equipos = [curva],[dict(curva=curva)]
    Tubo(a,bomba,1,D=0.02 if ramificada else 0.15,L=10)
    if ramificada:
        j = Union('J',x=10)
        bomba.tuberia_descarga = Tubo(bomba,j,2,D=0.02,L=10)
        Tubo(j,b,3,D=0.02,L=20000)
        Tubo(j,Tanque('C',H=0),4,D=0.02,L=30000)
        c._resolver_bomba_en_red_ramificada(j,c._analizar_red_union(j))
    else:
        bomba.tuberia_descarga = Tubo(bomba,b,2,D=0.1,L=100)
        c._tanques_dashboard = [a,b]
        c.combo_punto1 = SimpleNamespace(currentIndex=lambda:0)
        c.combo_punto2 = SimpleNamespace(currentIndex=lambda:1)
        c._on_calcular_punto_operacion()
    assert bomba.estado_operacion == 'OK',c.texto_resultados.valor
    assert len(capturas) == 1
    datos_excel,datos_grafico = c.datos_exportacion['bomba'],capturas[0]
    for excel,grafico in [('puntos_sistema','muestras_sistema'),
                           ('puntos_equivalente','muestras_equivalente'),('muestras_bombas','muestras_bombas')]:
        assert datos_excel[excel] is datos_grafico[grafico]
    assert len(datos_excel['puntos_sistema']) == 101
    assert len(c.datos_exportacion['perfiles']) == (2 if ramificada else 1)
    assert [s['perfil'] for s in c.series] == c.datos_exportacion['perfiles']
    for p in c.datos_exportacion['perfiles']:
        assert p.estado == ('OK' if p.residuo_energia_relativo<=1e-9 else 'SIN_BALANCE')


def test_dibujante_perfil_no_redistribuye_energia_y_limpia_estado(qt_app):
    from PyQt5.QtCore import QRectF
    from PyQt5.QtGui import QImage, QPainter
    from ui.perfil_egl import WidgetPerfilEGLHGL
    t = tramos_capturados(dorado('b_serie_accesorios'))
    widget = WidgetPerfilEGLHGL()
    for fin in (5,30):
        perfil = construir_perfil_ruta(t,20,fin)
        serie = perfil_como_serie(perfil)
        esperado = json.dumps(serie['puntos'],allow_nan=False)
        widget.actualizar_perfil(perfil)
        for rotulos in (False,True):
            widget.set_mostrar_valores(rotulos)
            assert json.dumps(widget._series_para_dibujar()[0],allow_nan=False) == esperado
            assert widget._series_para_dibujar()[0] is widget.series[0]['puntos']
            imagen = QImage(900,650,QImage.Format_ARGB32)
            pintor = QPainter(imagen)
            try:
                widget._dibujar_perfil(pintor,QRectF(0,0,900,650))
            finally:
                pintor.end()
        if perfil.estado != 'OK':
            assert perfil.mensaje in widget.toolTip()
    widget.limpiar_datos()
    assert widget.series == [] and widget.toolTip() == ''
    widget.close()
