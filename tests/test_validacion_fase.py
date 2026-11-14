"""Validación, procedencia e historiales: sin crear QApplication ni ventanas."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from PyQt5.QtCore import QPointF

from motor import MotorFluidos
from motor.bombas import CurvaBomba, EstacionBombeo, combinar_serie, punto_operacion
import ui.ventana.barra_herramientas as barra
from ui.ventana.panel_propiedades import PanelPropiedadesMixin
from ui.graficos import TuberiaGrafica
from ui.validacion_datos import validar_proyecto


def tramo(**cambios):
    return dict(dict(L=10.0,D=0.1,eps=0.0,K=0.0,LeD=0.0,H=0.0),**cambios)


@pytest.mark.parametrize('campo,valor',[('Q',float('nan')),('Q',float('inf')),('Q',-1),
    ('L_tub',0),('L_tub',-1),('D',0),('D',-1),('epsilon',-1),('rho',0),('mu',0),
    ('sumatoria_K',-1),('sumatoria_Le_D',float('inf'))])
def test_perdidas_rechazan_datos_invalidos(campo,valor):
    datos = dict(Q=0.001,L_tub=10,D=0.1,rho=1000,mu=0.001,epsilon=0)
    datos[campo] = valor
    with pytest.raises(ValueError,match='finito|>|diámetro|positivo'):
        MotorFluidos.calcular_hf(**datos)


@pytest.mark.parametrize('metodo',[
    lambda: MotorFluidos.calcular_Q(float('nan'),10,0.1,1000,0.001,0),
    lambda: MotorFluidos.calcular_D(1,-1,10,1000,0.001,0),
    lambda: MotorFluidos.resolver_serie_por_energia(1,0,[tramo(D=0)],1000,0.001),
    lambda: MotorFluidos.resolver_red_ramificada([tramo()],1000,0.001,H_manual=float('nan')),
    lambda: MotorFluidos.resolver_paralelo([tramo(K=-1)],0.0,1000,0.001),
    lambda: MotorFluidos.carga_requerida_sistema(-0.001),
    lambda: MotorFluidos.carga_requerida_sistema(0.0,tramos=[tramo(D=0)]),
    lambda: MotorFluidos.carga_requerida_sistema(0.0,hf=1,sumatoria_K=-1),
    lambda: MotorFluidos.resolver_bomba_ramificada(lambda q:10,tramo(),[tramo()],Q_manual=-1),
    lambda: MotorFluidos.calcular_curva_sistema_ramificada(lambda q:10,tramo(),[tramo()],1000,-1,0.001),
    lambda: punto_operacion(CurvaBomba([(0,10),(0.1,0)]),lambda q:float('nan')),
])
def test_entradas_del_motor_rechazan_invalidos(metodo):
    with pytest.raises(ValueError):
        metodo()


@pytest.mark.parametrize('valores',[[0,float('nan')],[0,float('inf')],[0,-0.1]])
def test_curva_rechaza_caudales_invalidos(valores):
    with pytest.raises(ValueError):
        CurvaBomba('Inválida',valores,[10,0])


def test_ajuste_fallido_se_informa_y_no_se_resuelve(monkeypatch):
    def falla(*args,**kwargs):
        raise np.linalg.LinAlgError('ajuste singular de prueba')
    monkeypatch.setattr(np,'polyfit',falla)
    curva = CurvaBomba([(0,10),(0.1,0)])
    assert curva.valida is False
    assert curva.estado == 'CURVA_INVALIDA'
    assert 'singular de prueba' in curva.mensaje
    res = punto_operacion(curva,lambda q:5)
    assert res.estado == 'CURVA_INVALIDA' and not res.convergio
    with pytest.raises(ValueError,match='singular'):
        curva.H_de_Q(0.01)


def test_dos_ejecuciones_no_comparten_historial():
    a = MotorFluidos.calcular_hf(0.01,10,0.1,1000,0.001,0,registrar=True)
    copia = deepcopy(a.historial_iteraciones)
    b = MotorFluidos.calcular_hf(0.02,10,0.1,1000,0.001,0,registrar=True)
    assert a.historial_iteraciones and b.historial_iteraciones
    assert a.historial_iteraciones is not b.historial_iteraciones
    b.historial_iteraciones[0]['propuesto'] = -999
    MotorFluidos.limpiar_iteraciones()
    assert a.historial_iteraciones == copia
    assert 'historial_iteraciones' not in MotorFluidos.__dict__


def test_historiales_concurrentes_son_independientes():
    def calcular(q):
        return MotorFluidos.calcular_hf(q,10,0.1,1000,0.001,0,registrar=True)
    caudales = [0.01,0.02,0.03]
    esperados = [calcular(q).historial_iteraciones for q in caudales]
    with ThreadPoolExecutor(max_workers=3) as pool:
        resultados = list(pool.map(calcular,caudales))
    assert [r.historial_iteraciones for r in resultados] == esperados
    assert len({id(r.historial_iteraciones) for r in resultados}) == 3


def test_curva_sistema_expande_alturas_y_valida_residuos():
    b = CurvaBomba([(0,20000),(1e-5,0)],'lineal','B')
    principal = tramo(L=1,D=0.02)
    ramas = [tramo(L=1e6,D=0.01,H=1500),tramo(L=1e6,D=0.01,H=1500)]
    res = MotorFluidos.calcular_curva_sistema_ramificada(b,principal,ramas,1000,0.001,1e-5,num_puntos=6)
    assert res.estado == 'OK'
    assert len(res)==6 and res[-1][0] >= 1.4e-5
    for (q,h),d in zip(res,res.diagnosticos):
        esperado = 1500+MotorFluidos._perdida_tramo(q/2,ramas[0],1000,0.001)[0]
        esperado += MotorFluidos._perdida_tramo(q,principal,1000,0.001)[0]
        assert h == pytest.approx(esperado,rel=1e-8)
        assert d['residuo_masa_relativo'] <= 1e-8
        assert d['residuo_energia_relativo'] <= 1e-8
        assert all(r['Q'] >= 0 and 'direccion' in r for r in d['ramas'])
    assert res[-1][1] > 2000  # supera las antiguas cotas Hmax+500


@pytest.mark.parametrize('operacion',[
    lambda b: b.H_de_Q(-1),lambda b:b.eta_de_Q(-1),lambda b:b.npsh_r_de_Q(-1),
    lambda b: combinar_serie([b]).H_de_Q(-1),lambda b:EstacionBombeo.en_serie([b]).H_estacion(-1)])
def test_signo_de_Q_no_se_convierte_silenciosamente(operacion):
    with pytest.raises(ValueError):
        operacion(CurvaBomba([(0,10),(0.1,0)],'lineal','B'))


class Panel(PanelPropiedadesMixin):
    def __init__(self):
        self.fluido_rho = 1000
        self.mensaje = ''
        self.texto_resultados = SimpleNamespace(setPlainText=lambda t:setattr(self,'mensaje',t))
        self._on_elementos_modificados = lambda:None


@pytest.mark.parametrize('atributo,texto',[('longitud','nan'),('diametro','inf'),('caudal_Q','-1'),
                                        ('rugosidad','-1'),('valor','-1'),('longitud','0')])
def test_panel_no_guarda_un_numero_invalido(atributo,texto):
    panel = Panel()
    objeto = SimpleNamespace(**{atributo:1.0})
    assert panel._guardar_campo_numerico(objeto,atributo,texto) is False
    assert getattr(objeto,atributo)==1.0
    assert panel.mensaje.startswith('Dato inválido:')


def proyecto_json(diametro=0.1,q=0.001,**banderas):
    return dict(tanques=[dict(id_tanque=1,nombre='A',elevacion_z=10),
                         dict(id_tanque=2,nombre='B',elevacion_z=0)],
        tuberias=[dict(id_tuberia=1,longitud=10,diametro=diametro,rugosidad=0,caudal_Q=q,
                      nodo_origen=dict(tipo='tanque',id=1),nodo_destino=dict(tipo='tanque',id=2),**banderas)])


def test_D_cero_solo_como_incognita_con_datos_suficientes():
    validar_proyecto(proyecto_json(diametro=0),1000)
    with pytest.raises(ValueError,match='D=0'):
        validar_proyecto(proyecto_json(diametro=0,q=0),1000)
    with pytest.raises(ValueError,match='D=0'):
        validar_proyecto(proyecto_json(diametro=0,_q_por_energia=True),1000)


class Tanque:
    def __init__(self,x=0,y=0,id_tanque=1):
        self.id_tanque,self.nombre = id_tanque,f'Tanque {id_tanque}'
        self.punto = QPointF(x,y)
        self.elevacion_z,self.presion_P,self.abierto_atmosfera = 0,0,True
        self.color_fondo = SimpleNamespace(name=lambda:'#ffffff')
    pos = lambda self:self.punto
    actualizar_etiqueta = lambda self:None


class Tubo:
    to_dict = TuberiaGrafica.to_dict
    from_dict = TuberiaGrafica.from_dict
    def __init__(self,a,b,id_tuberia=1):
        self.nodo_origen,self.nodo_destino = a,b
        self.id_tuberia,self.nombre = id_tuberia,'Tubo'
        self.longitud,self.diametro,self.rugosidad,self.caudal_Q = 10,0.1,0,0
        self.u_Q,self.u_D,self.u_L,self.u_eps = 'm³/s','m','m','m'
    actualizar_etiqueta = actualizar_posicion = lambda self:None


class Proyecto(barra.BarraHerramientasMixin):
    def __init__(self):
        self.elementos = []
        self.escena = SimpleNamespace(items=lambda:self.elementos,clearSelection=lambda:None,
            addItem=self.elementos.append,elementos_modificados=SimpleNamespace(emit=lambda:None),
            _eliminar_tuberia=self.elementos.remove,_eliminar_tanque=self.elementos.remove)
        self.canvas_view = SimpleNamespace(scene=lambda:self.escena)
        self._refrescar_combos_dashboard = lambda:None


@pytest.mark.parametrize('calculado',[False,True])
def test_guardar_cargar_conserva_procedencia(monkeypatch,calculado):
    monkeypatch.setattr(barra,'TanqueGrafico',Tanque)
    monkeypatch.setattr(barra,'TuberiaGrafica',Tubo)
    datos = proyecto_json(_q_por_energia=calculado,_d_por_energia=calculado)
    p = Proyecto()
    p._deserializar_proyecto(datos)
    guardado = p._serializar_proyecto()
    assert guardado['tuberias'][0]['_q_por_energia'] is calculado
    assert guardado['tuberias'][0]['_d_por_energia'] is calculado
    p._deserializar_proyecto(guardado)
    tubo = next(t for t in p.elementos if isinstance(t,Tubo))
    assert tubo._q_por_energia is calculado and tubo._d_por_energia is calculado


def test_legacy_sin_banderas_es_compatible(monkeypatch):
    monkeypatch.setattr(barra,'TanqueGrafico',Tanque)
    monkeypatch.setattr(barra,'TuberiaGrafica',Tubo)
    p = Proyecto()
    p._deserializar_proyecto(proyecto_json())
    tubo = next(t for t in p.elementos if isinstance(t,Tubo))
    assert tubo._q_por_energia is False and tubo._d_por_energia is False


@pytest.mark.parametrize('campo,valor',[('diametro',-1),('longitud',0),('rugosidad',-1),
                                     ('caudal_Q',float('nan')),('diametro',float('inf'))])
def test_json_invalido_no_destruye_proyecto_actual(campo,valor):
    datos = proyecto_json()
    datos['tuberias'][0][campo] = valor
    p = Proyecto()
    viejo = object()
    p.elementos.append(viejo)
    with pytest.raises(ValueError):
        p._deserializar_proyecto(datos)
    assert p.elementos == [viejo]
