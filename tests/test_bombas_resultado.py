"""Evaluación única por bomba/estación y presentación, sin crear QApplication."""

from dataclasses import FrozenInstanceError, fields, replace
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest
import xlsxwriter

from motor import (MotorFluidos, CurvaBomba, EstacionBombeo, evaluar_operacion_estacion,
                   muestrear_sistema_para_exportacion, punto_operacion)
from motor.resultados import ResultadoBomba, ResultadoEstacion
from ui.ventana.bombas import BombasMixin
from ui.ventana.exportacion import ExportacionMixin


GOLDEN = Path(__file__).resolve().parent/'golden'


def datos(nombre):
    return json.loads((GOLDEN/f'{nombre}.json').read_text(encoding='utf-8'))


def estacion_de_curvas(curvas, arreglo):
    bombas = [CurvaBomba(c['nombre'],c['Q'],c['H'],eta=c['eta'],
        npsh_r=c['npsh_r'],metodo=c['metodo']) for c in curvas]
    return EstacionBombeo.en_serie(bombas) if arreglo=='serie' else EstacionBombeo.en_paralelo(bombas)


def evaluar_dorado(nombre, editar=None):
    d = datos(nombre)
    entrada = d['entrada']
    if editar:
        editar(entrada['curvas'])
    est = estacion_de_curvas(entrada['curvas'],entrada['arreglo'])
    def sistema(q):
        return MotorFluidos.carga_requerida_sistema(q,z1=entrada['z_inicio'],
            z2=entrada['z_fin'],rho=1000,mu=0.001,tramos=entrada['tramos'])
    n = entrada['npsh']
    r = evaluar_operacion_estacion(est,sistema,rho=1000,mu=0.001,g=9.81,
        tramos=entrada['tramos'],indices_succion=(0,),P_atm=n['P_atm'],P_vap=n['P_vap'],
        z1=n['z1'],z_bomba=n['z_bomba'],P1=n['P1'])
    return r,est,d


def test_una_bomba_operacion_potencias_y_dorado():
    r,est,d = evaluar_dorado('d_una_bomba')
    b = r.bombas[0]
    assert r.estado == b.estado == 'OK'
    assert r.H == pytest.approx(est.etapas[0][0].H_de_Q(r.Q),rel=1e-9)
    assert b.potencia_hidraulica == 1000*9.81*b.Q*b.H
    assert b.potencia_eje == b.potencia_hidraulica/b.eficiencia
    assert r.potencia_hidraulica == sum(v.potencia_hidraulica for v in r.bombas)
    assert r.Q == pytest.approx(d['resultado']['Q'],rel=1e-12)
    assert r.H == pytest.approx(d['resultado']['H_total'],rel=1e-12)


def test_dos_bombas_serie_acumulan_aspiracion():
    r,_,d = evaluar_dorado('e_dos_bombas_serie')
    b1,b2 = r.bombas
    assert b1.Q == b2.Q == r.Q
    assert r.H == b1.H+b2.H
    assert b2.NPSHd-b1.NPSHd == pytest.approx(b1.H,rel=1e-12)
    assert b1.NPSHd != b2.NPSHd
    assert r.Q == pytest.approx(d['resultado']['Q'],rel=1e-12)


def test_dos_bombas_paralelo_comparten_aspiracion():
    r,_,d = evaluar_dorado('e_dos_bombas_paralelo')
    a,b = r.bombas
    assert a.H == b.H == r.H
    assert a.Q+b.Q == pytest.approx(r.Q,rel=1e-12)
    assert a.Q == pytest.approx(r.Q/2,rel=1e-12)
    assert a.NPSHd == b.NPSHd
    assert r.Q == pytest.approx(d['resultado']['Q'],rel=1e-12)


def test_eta_ausente_no_es_eficiencia_cero_ni_potencia_hidraulica():
    r,_,_ = evaluar_dorado('d_una_bomba',lambda c:c[0].update(eta=None))
    assert r.potencia_hidraulica > 0
    assert r.potencia_eje is None and r.eficiencia is None
    assert r.bombas[0].potencia_eje is None and r.bombas[0].eficiencia is None
    assert 'potencia_eje' in r.bombas[0].desconocidos


def test_npshr_ausente_en_una_bomba_no_se_oculta_en_el_maximo():
    r,_,_ = evaluar_dorado('e_dos_bombas_paralelo',lambda c:c[1].update(npsh_r=None))
    assert r.bombas[0].NPSHr is not None
    assert r.bombas[0].cavitacion == 'seguro'
    assert r.bombas[1].NPSHr is None and r.bombas[1].cavitacion == 'desconocido'
    assert r.cavitacion == 'desconocido' and r.NPSHr is None


def resolver_f(tol=None):
    d = datos('f_ramificada_bomba')
    e = d['entrada']
    est = estacion_de_curvas(e['curvas'],'individual')
    opciones = {} if tol is None else dict(tol=tol)
    r = MotorFluidos.resolver_bomba_ramificada(est,e['principal'],e['ramas'],
        rho=1000,mu=0.001,P_atm=101325,P_vap=2339,**opciones)
    return r,d


def test_tolerancia_relativa_ramificada_por_defecto():
    r,d = resolver_f()
    estricto,_ = resolver_f(1e-15)
    assert r.estado == estricto.estado == 'OK'
    assert abs(r.error_Q) <= max(1e-15,1e-8*max(r.Q,r.Q_ref))
    assert r.Q == pytest.approx(estricto.Q,rel=1e-8)
    assert estricto.Q == pytest.approx(d['resultado']['Q'],rel=1e-12)
    assert r.estacion_resultado.potencia_hidraulica == sum(
        b.potencia_hidraulica for b in r.estacion_resultado.bombas)


def test_metadatos_uniformes_y_historial_separado():
    r,est,_ = evaluar_dorado('d_una_bomba')
    sol = punto_operacion(est,lambda q:10+100000*q*q)
    ram,_ = resolver_f()
    for resultado in (r,sol,ram):
        assert isinstance(resultado.iteraciones,int) and resultado.iteraciones>=0
        for campo in ('residuo_masa','residuo_energia','residuo_masa_relativo',
                      'residuo_energia_relativo','residuo_ecuacion'):
            assert math.isfinite(getattr(resultado,campo))
        assert resultado.residuo_masa_relativo <= 1e-8
        assert resultado.residuo_energia_relativo <= 1e-8
    assert isinstance(ram.historial,list) and ram.iteraciones == len(ram.historial)
    assert sol.iteraciones == len(sol.historial) > 0
    assert ram.to_dict()['iteraciones'] == ram.iteraciones
    assert ram.to_dict()['residuo_masa_relativo'] == ram.residuo_masa_relativo


def test_contratos_frozen_serializan_completos_sin_no_finitos():
    r,_,_ = evaluar_dorado('d_una_bomba')
    salida = json.loads(json.dumps(r.to_dict(),allow_nan=False))
    assert set(salida) == {f.name for f in fields(ResultadoEstacion)}
    assert set(salida['bombas'][0]) == {f.name for f in fields(ResultadoBomba)}
    with pytest.raises(FrozenInstanceError):
        r.Q = 0
    with pytest.raises(FrozenInstanceError):
        r.bombas[0].H = 0
    with pytest.raises(ValueError,match='finito'):
        replace(r,bombas=(replace(r.bombas[0],NPSHd=float('nan')),)).to_dict()
    desconocido = replace(r.bombas[0],potencia_eje=None,eficiencia=None)
    assert json.loads(json.dumps(desconocido.to_dict()))['potencia_eje'] is None


def test_punto_fallido_conserva_estado_y_excel_no_inventa_cero():
    def sistema(q):
        if q == 0.001:
            raise RuntimeError('punto sin convergencia')
        return q*1000
    puntos = muestrear_sistema_para_exportacion(sistema,[0,0.001,0.002])
    assert puntos[0]['H'] == 0 and puntos[0]['estado'] == 'OK'
    assert puntos[1]['H'] is None and puntos[1]['estado'] == 'NO_CALCULADO'
    assert 'sin convergencia' in puntos[1]['mensaje']
    destino = io.BytesIO()
    libro = xlsxwriter.Workbook(destino,{'in_memory':True})
    ExportacionMixin()._hoja_bombas(libro,dict(bomba=dict(puntos_sistema=puntos)))
    libro.close()
    valores = [c.value for fila in openpyxl.load_workbook(io.BytesIO(destino.getvalue()),
                data_only=True)['Bombas'] for c in fila]
    assert 'No calculado (NO_CALCULADO)' in valores


def test_ui_copia_resultados_y_preserva_desconocidos():
    r,_,_ = evaluar_dorado('e_dos_bombas_paralelo',lambda c:c[1].update(npsh_r=None,eta=None))
    grafico = SimpleNamespace(curvas=[],actualizar_tooltip=lambda:None)
    BombasMixin()._aplicar_resultado_estacion(grafico,r)
    assert grafico.potencia_freno_op is None and grafico.eta_op is None
    assert grafico.npsh_r is None and grafico.cavitacion == 'SIN DATO NPSHr'
    assert grafico.reparto[1]['npsh_r'] is None
    assert grafico.reparto[1]['potencia_freno'] is None
    assert grafico.reparto[1]['potencia_hidraulica'] == r.bombas[1].potencia_hidraulica


def test_etapas_con_cota_y_perdidas_intermedias_explicitas():
    r,est,_ = evaluar_dorado('e_dos_bombas_serie')
    otro = evaluar_operacion_estacion(est,Q=r.Q,rho=1000,mu=0.001,P_atm=101325,P_vap=2339,
        hf_succion=0.5,cotas_etapas=[0,2],perdidas_entre_etapas=[0.3])
    assert otro.bombas[1].NPSHd-otro.bombas[0].NPSHd == pytest.approx(
        otro.bombas[0].H-2-0.3,rel=1e-12)


def test_metadatos_de_un_punto_rechazado_tambien_tienen_residuo():
    curva = CurvaBomba('B',[0,0.01],[50,40],eta=[0.8,0.8],metodo='lineal')
    r = punto_operacion(curva,lambda q:30)
    assert r.estado == 'FUERA_DE_RANGO_CURVA'
    assert r.residuo_energia == 10 and r.residuo_energia_relativo > 0
    assert isinstance(r.iteraciones,int)


@pytest.mark.parametrize('ramificada',[False,True])
def test_handlers_ui_consumen_la_evaluacion_sin_recalcular_hf(monkeypatch, ramificada):
    import ui.ventana.bombas as ui_b
    import ui.ventana.ramificadas as ui_r
    import motor.bomba_ramificada as motor_r
    from test_fase_redes import Control, Tanque, Union, Bomba, Tubo
    for modulo in (ui_b,ui_r):
        monkeypatch.setattr(modulo,'TanqueGrafico',Tanque)
        monkeypatch.setattr(modulo,'BombaGrafica',Bomba)
    monkeypatch.setattr(ui_r,'NodoUnionGrafico',Union)
    llamadas = []
    modulo = motor_r if ramificada else ui_b
    evaluar = modulo.evaluar_operacion_estacion
    def una_evaluacion(*args,**kwargs):
        llamadas.append(True)
        return evaluar(*args,**kwargs)
    monkeypatch.setattr(modulo,'evaluar_operacion_estacion',una_evaluacion)
    c = Control()
    c.fluido_P_atm,c.fluido_P_vap = 101325,2339
    c._hf_tuberia = lambda *a,**k:pytest.fail('La UI no debe reevaluar hf en el punto resuelto.')
    a,b = Tanque('A',H=0),Tanque('B',H=0 if ramificada else 10)
    bomba = Bomba('Bomba 1',x=5)
    bomba.id_bomba,bomba.z_bomba,bomba.metodo,bomba.arreglo = 1,0,'lineal','individual'
    curva = (CurvaBomba('B1',[0,1e-5],[0.01,0],eta=[0.8,0.8],npsh_r=[2,2],metodo='lineal')
             if ramificada else CurvaBomba('B1',[0,0.04],[40,0],eta=[0.8,0.8],
                                           npsh_r=[2,3],metodo='lineal'))
    bomba.curvas = [curva]
    bomba.equipos = [dict(curva=curva)]
    Tubo(a,bomba,1,D=0.02 if ramificada else 0.15,L=10)
    if ramificada:
        j = Union('J',x=10)
        bomba.tuberia_descarga = Tubo(bomba,j,2,D=0.02,L=10)
        # Incluso las cotas exploratorias de la curva deben quedar fuera del
        # hueco de hf del salto Re=2000; ese criterio se mantiene fijo.
        Tubo(j,b,3,D=0.02,L=20000)
        Tubo(j,Tanque('C',H=0),4,D=0.02,L=30000)
        c._resolver_bomba_en_red_ramificada(j,c._analizar_red_union(j))
    else:
        bomba.tuberia_descarga = Tubo(bomba,b,2,D=0.1,L=100)
        c._tanques_dashboard = [a,b]
        c.combo_punto1 = SimpleNamespace(currentIndex=lambda:0)
        c.combo_punto2 = SimpleNamespace(currentIndex=lambda:1)
        c._on_calcular_punto_operacion()
    assert getattr(bomba,'estado_operacion',None) == 'OK', c.texto_resultados.valor
    assert bomba.Q_op > 0 and bomba.H_op > 0
    assert all(isinstance(v,ResultadoBomba) for v in bomba.desglose)
    assert bomba.potencia_hidraulica_op == sum(b.potencia_hidraulica for b in bomba.desglose)
    assert c.datos_exportacion['bomba']['potencia_hidraulica'] == bomba.potencia_hidraulica_op
    assert len(llamadas) == 1
