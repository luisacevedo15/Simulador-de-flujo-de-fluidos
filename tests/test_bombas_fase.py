"""Fluido explícito, dominios, eficiencia y NPSH. Sin QApplication ni interfaz."""

import json
import math
from types import SimpleNamespace

import pytest

from motor import MotorFluidos
from motor.bombas import (CurvaBomba, EstacionBombeo, punto_operacion,
                          presion_vapor_agua, npsh_disponible)
from ui.constantes import FACTORES_SI
from ui.dialogos import DialogoFluido
from ui.ventana.barra_herramientas import BarraHerramientasMixin, normalizar_datos_fluido


def curva(nombre='B', eta=0.8, qmax=0.1, h0=50, h1=0, nr=None, metodo='lineal'):
    return CurvaBomba(nombre,[0,qmax],[h0,h1],None if eta is None else [eta,eta],
                     npsh_r=None if nr is None else [nr,nr],metodo=metodo)


def test_npsh_presiones_explicitas_y_atmosfera_local():
    nd = npsh_disponible(P_atm=101325,P_vap=2339,z1=2,hf_succion=0.5)
    assert nd == pytest.approx(11.59,abs=0.01)
    bajo = npsh_disponible(P_atm=80000,P_vap=2339,z1=2,hf_succion=0.5)
    assert nd-bajo == pytest.approx((101325-80000)/(1000*9.81))
    presurizado = npsh_disponible(P_atm=80000,P_vap=2339,P1=20000,z1=2,hf_succion=0.5)
    assert presurizado-bajo == pytest.approx(20000/(1000*9.81))
    with pytest.raises(TypeError):
        npsh_disponible()


@pytest.mark.parametrize('metodo',['lineal','cuadratico'])
@pytest.mark.parametrize('arreglo',['serie','paralelo'])
def test_f6_cada_bomba_conserva_su_dominio(metodo,arreglo):
    b1 = curva('B1',qmax=0.01,h0=50,h1=40,metodo=metodo)
    b2 = curva('B2',qmax=0.1,h0=50,h1=0,metodo=metodo)
    estacion = (EstacionBombeo.en_serie if arreglo=='serie' else EstacionBombeo.en_paralelo)([b1,b2])
    res = punto_operacion(estacion,lambda q:30.0)
    assert res.estado == 'FUERA_DE_RANGO_CURVA'
    assert not res.convergio
    assert b1.Q_max == 0.01 and b2.Q_max == 0.1


def test_f6_extremo_real_de_tabla_sigue_siendo_valido():
    b = curva(qmax=0.01,h1=40)
    res = punto_operacion(b,lambda q:40.0)
    assert res.estado == 'OK'
    assert res.Q == pytest.approx(0.01,rel=1e-7)
    assert res.H_total == pytest.approx(40,rel=1e-8)


@pytest.mark.parametrize('eta',[None,0.0])
def test_f7_sin_eficiencia_valida_no_hay_potencia_al_eje(eta):
    b = curva(eta=eta)
    res = punto_operacion(b,lambda q:30)
    assert res.estado == 'OK'
    assert res.P_hidraulica > 0
    assert res.BHP_total is None and res.eta_global is None
    assert res.desglose[0].BHP_i is None
    assert b.potencia_freno(res.Q,res.H_total) is None
    assert res.desglose[0]['potencia_hidraulica'] == pytest.approx(res.P_hidraulica)


def test_f7_no_se_completa_una_eta_faltante_con_uno():
    b = CurvaBomba([(0,50,0.8),(0.1,0,None)],'lineal','Incompleta')
    assert b.eta_de_Q(0.02) is None
    res = punto_operacion(EstacionBombeo.en_paralelo([b,curva('Otra')]),lambda q:30)
    assert res.BHP_total is None and res.eta_global is None


def test_f7_bomba_cerrada_sin_eta_no_invalida_las_activas():
    estacion = EstacionBombeo.en_paralelo([curva('Activa'),curva('Cerrada',eta=None,h0=20)])
    res = punto_operacion(estacion,lambda q:30)
    assert res.estado == 'OK'
    assert res.desglose[1].activa is False
    assert res.eta_global == pytest.approx(0.8)


def test_f8_npsh_por_etapa_y_aspiracion_compartida():
    b1,b2 = curva('Primera',nr=2),curva('Segunda',nr=30)
    serie = EstacionBombeo.en_serie([b1,b2])
    q = 0.02
    desglose = serie.evaluar_npsh(q,P_atm=101325,P_vap=2339,z1=2,hf_succion=0.5)
    assert desglose[1].npsh_d-desglose[0].npsh_d == pytest.approx(b1.H_de_Q(q))
    assert all(d.cavitacion=='SIN RIESGO' for d in desglose)
    assert desglose[0].npsh_d < desglose[1].npsh_r  # comparar extremos globales daría un falso riesgo
    intermedio = serie.evaluar_npsh(q,P_atm=101325,P_vap=2339,z1=2,
        hf_succion=0.5,perdidas_entre_etapas=[0.7],cotas_etapas=[0,1.5])
    assert intermedio[1].npsh_d-intermedio[0].npsh_d == pytest.approx(b1.H_de_Q(q)-0.7-1.5)
    paralelo = EstacionBombeo.en_paralelo([b1,b2])
    ds = paralelo.evaluar_npsh(2*q,P_atm=101325,P_vap=2339,z1=2,hf_succion=0.5)
    assert ds[0].npsh_d == ds[1].npsh_d


def test_ramificada_eta_global_y_npsh_con_datos_del_fluido(monkeypatch):
    q = 0.001
    tubo = dict(L=10,D=0.1,eps=0,K=0,LeD=0)
    hf = MotorFluidos._perdida_tramo(q,tubo,1000,0.001)[0]
    b1,b2 = curva('B1',eta=0.8,qmax=0.01,h0=10,h1=5,nr=2),curva('B2',eta=0.7,qmax=0.01,h0=12,h1=8,nr=3)
    estacion = EstacionBombeo.en_serie([b1,b2])
    H = estacion.H_estacion(q)
    principal = dict(tubo,H=2,z_bomba=0)
    ramal = dict(tubo,H=2+H-2*hf)
    monkeypatch.setattr(MotorFluidos,'presion_vapor_agua',lambda *a: pytest.fail('El solver no debe deducir Pv desde una T fija'))
    res = MotorFluidos.resolver_bomba_ramificada(estacion,principal,[ramal],rho=1000,mu=0.001,
        Q_manual=q,P_atm=80000,P_vap=5000)
    assert res.estado == 'OK'
    eta = H/(b1.H_de_Q(q)/0.8+b2.H_de_Q(q)/0.7)
    assert res.eta == pytest.approx(eta)
    assert res.potencia_freno == pytest.approx(res.potencia_hidraulica/eta)
    assert res.npsh_d == pytest.approx((80000-5000)/(1000*9.81)+2-hf)
    assert res.desglose[1].npsh_d-res.desglose[0].npsh_d == pytest.approx(b1.H_de_Q(q))


@pytest.mark.parametrize('marcar',[False,True])
def test_npsh_ramificado_no_descuenta_la_descarga(marcar):
    bomba_obj = object()
    aspiracion = dict(L=10,D=0.1,eps=0,K=0,LeD=0,
                     tuberia=SimpleNamespace(nodo_origen=object(),nodo_destino=bomba_obj))
    descarga = dict(L=100,D=0.1,eps=0,K=20,LeD=50,
                   tuberia=SimpleNamespace(nodo_origen=bomba_obj,nodo_destino=object()))
    if marcar:
        aspiracion['es_succion'],descarga['es_succion'] = True,False
    tramo = dict(H=2,z_bomba=0,sub_tramos=[aspiracion,descarga],bomba_obj=bomba_obj)
    estacion = EstacionBombeo.en_paralelo([curva()])
    q = 0.001
    metricas = MotorFluidos._metricas_ramificada(estacion,estacion,tramo,q,estacion.H_estacion(q),
                                                1000,0.001,101325,2339)
    hf_suc = MotorFluidos._perdida_tramo(q,aspiracion,1000,0.001)[0]
    assert metricas['hf_succion'] == pytest.approx(hf_suc)
    assert metricas['npsh_d'] == pytest.approx((101325-2339)/(1000*9.81)+2-hf_suc)


@pytest.mark.parametrize('unidad',DialogoFluido.UNIDADES_PRESION)
def test_conversion_presion_dialogo_en_pa_absolutos(unidad):
    assert DialogoFluido._presion_si(str(101325/FACTORES_SI[unidad]),unidad) == pytest.approx(101325)
    assert DialogoFluido._presion_si('0',unidad,True) == 0
    with pytest.raises(ValueError):
        DialogoFluido._presion_si('-1',unidad)


@pytest.mark.parametrize('T',[-1,101,float('nan'),float('inf')])
def test_tabla_agua_valida_rango(T):
    with pytest.raises(ValueError):
        presion_vapor_agua(T)


def test_tabla_agua_interpola_y_pvap_guardada_no_depende_de_T():
    assert presion_vapor_agua(75) == pytest.approx((presion_vapor_agua(70)+presion_vapor_agua(80))/2)
    datos = normalizar_datos_fluido(dict(temperatura=-30,P_vap=12345,P_atm=70000))
    assert datos['P_vap'] == 12345  # fluido cualquiera: T no limita Pv editable


class ProyectoSinUI(BarraHerramientasMixin):
    def __init__(self):
        scene = SimpleNamespace(items=lambda:[],clearSelection=lambda:None,
                                elementos_modificados=SimpleNamespace(emit=lambda:None))
        self.canvas_view = SimpleNamespace(scene=lambda:scene)
        self._refrescar_combos_dashboard = lambda:None
        self._reset_selector_trazado = lambda:None


@pytest.mark.parametrize('T',[None,70.0,75.0])
def test_d_carga_json_antiguo_rellena_presiones(tmp_path,T):
    fluido = dict(rho=1000,mu=0.001)
    if T is not None:
        fluido['temperatura'] = T
    ruta = tmp_path/'antiguo.json'
    ruta.write_text(json.dumps(dict(fluido=fluido)),encoding='utf-8')
    proyecto = ProyectoSinUI()
    assert proyecto.cargar_proyecto(str(ruta))
    assert proyecto.fluido_P_atm == 101325
    assert proyecto.fluido_P_vap == pytest.approx(presion_vapor_agua(20 if T is None else T))
    guardado = proyecto._serializar_proyecto()['fluido']
    assert guardado['P_atm'] == 101325 and guardado['P_vap'] == proyecto.fluido_P_vap


def test_json_nuevo_conserva_presiones_de_otro_fluido(tmp_path):
    ruta = tmp_path/'nuevo.json'
    ruta.write_text(json.dumps(dict(fluido=dict(temperatura=-30,P_atm=70000,P_vap=12345))),encoding='utf-8')
    proyecto = ProyectoSinUI()
    assert proyecto.cargar_proyecto(str(ruta))
    assert proyecto.fluido_P_atm == 70000 and proyecto.fluido_P_vap == 12345
