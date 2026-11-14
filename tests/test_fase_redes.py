"""Regresiones de redes con dobles del grafo: no se crea QApplication ni ventanas."""

import itertools
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QPointF

from motor import MotorFluidos, CurvaBomba
import ui.ventana.ramificadas as ramificadas
import ui.ventana.resolucion as resolucion
import ui.ventana.bombas as bombas
from ui.graficos import TuberiaGrafica
from ui.ventana.bernoulli import BernoulliMixin
from ui.ventana.exportacion import ExportacionMixin
from ui.ventana.panel_propiedades import PanelPropiedadesMixin


class Nodo:
    def __init__(self, nombre, x=0, H=0):
        self.nombre, self.posicion = nombre, QPointF(x, 0)
        self.tuberias = []
        self.elevacion_z = H
        self.abierto_atmosfera, self.presion_P = True, 0.0
        self.energia_supuesta = 0.0
        self.hj_calculada = None
        self.actualizar_etiqueta = lambda: None
        self.scene = lambda: ESCENA


class Tanque(Nodo):
    pass


class Union(Nodo):
    pass


class Accesorio(Nodo):
    def __init__(self, nombre, x=0, tipo='K', valor=0):
        super().__init__(nombre, x)
        self.tipo_perdida, self.valor, self.forma_visual = tipo, valor, nombre
        self.tuberia_padre = None

    def sceneBoundingRect(self):
        return SimpleNamespace(center=lambda: self.posicion)


class Bomba(Nodo):
    def __init__(self, nombre, x=0):
        super().__init__(nombre, x)
        self.Q_op, self.H_op = 123.0, 456.0
        self.actualizar_tooltip = lambda: None


class Tubo:
    _accesorios_asignados = TuberiaGrafica._accesorios_asignados
    _sumar_accesorios = TuberiaGrafica._sumar_accesorios
    sumatoria_K = property(lambda self: self._sumar_accesorios('K'))
    sumatoria_Le_D = property(lambda self: self._sumar_accesorios('Le/D'))
    _diametro_si = lambda self: self.diametro
    _centro = staticmethod(lambda nodo: nodo.posicion)

    def __init__(self, origen, destino, identificador, D=0.01, L=10):
        self.nodo_origen, self.nodo_destino = origen, destino
        self.id_tuberia, self.nombre = identificador, f'Tubo {identificador}'
        self.longitud, self.diametro, self.rugosidad = L, D, 0.0
        self.caudal_Q, self.hf_calculado = 0.0, None
        self.u_Q, self.u_L, self.u_D, self.u_eps = 'm³/s', 'm', 'm', 'm'
        self.accesorios_conectados = []
        self.actualizar_etiqueta = lambda: None
        self.pen = lambda: SimpleNamespace(color=lambda: SimpleNamespace(name=lambda: '#0284c7'))
        origen.tuberias.append(self)
        destino.tuberias.append(self)

    def actualizar_texto_hf(self, hf):
        self.hf_calculado = hf


ESCENA = SimpleNamespace(selectedItems=lambda: [object()])


class Texto:
    def __init__(self):
        self.valor = ''

    def setPlainText(self, texto):
        self.valor = texto

    setHtml = setPlainText
    clear = lambda self: self.setPlainText('')


class Control(resolucion.ResolucionMixin, ramificadas.RamificadasMixin,
              bombas.BombasMixin, BernoulliMixin, PanelPropiedadesMixin, ExportacionMixin):
    _a_si = staticmethod(lambda v, u: v)
    _desde_si = staticmethod(lambda v, u: v)
    _fila_tabla_cad_tuberia = lambda self, t, q, hf: ([t.nombre, str(q), '', '', str(hf)], 100)
    _actualizar_barra_perdidas = lambda *args: None
    _mostrar_tabla_vacia = lambda self: None

    def __init__(self):
        self.fluido_rho, self.fluido_mu = 1000.0, 0.001
        self.texto_resultados = Texto()
        self.tuberia_seleccionada = self.bomba_seleccionada = None
        self.campos_tuberia, self.label_hf_tuberia = {}, None
        self.datos_exportacion, self._tabla_cache = {'viejo': True}, 'viejo'
        self.canvas_view = SimpleNamespace(scene=lambda: ESCENA)
        self.boton_excel = self.contenedor_barras = SimpleNamespace(hide=lambda: None, show=lambda: None)
        self.egl_chart = SimpleNamespace(limpiar_datos=lambda: setattr(self, 'series', []),
            actualizar_datos=lambda series, **kw: setattr(self, 'series', series))
        self.series = []


@pytest.fixture(autouse=True)
def tipos_grafo(monkeypatch):
    import ui.graficos as graficos
    for modulo in (ramificadas, resolucion, bombas, graficos):
        for nombre, tipo in [('TanqueGrafico', Tanque), ('NodoUnionGrafico', Union),
                             ('AccesorioGrafico', Accesorio), ('BombaGrafica', Bomba)]:
            monkeypatch.setattr(modulo, nombre, tipo, raising=False)


def red_tres_ramas(reversiones=(False,)*4, tipo='K', valor=0):
    hf = 0.00326197757390418
    union, acc = Union('J', 20), Accesorio('Divisor', 10, tipo=tipo, valor=valor)
    a, b, c = Tanque('A', 0, H=4*hf), Tanque('B', 30, H=0), Tanque('C', 40, H=0)
    pares = [(a, acc), (acc, union), (union, b), (union, c)]
    tubos = [Tubo(*(par[::-1] if rev else par), i+1)
             for i, (par, rev) in enumerate(zip(pares, reversiones))]
    return union, tubos, (a,b,c), acc


def test_ramal_completo_dos_segmentos_laminares():
    control = Control()
    union, tubos, _, _ = red_tres_ramas()
    analisis = control._analizar_red_union(union)
    assert analisis['valida']
    rama = next(r for r in analisis['ramas'] if len(r['tuberias']) == 2)
    segmentos = control._segmentos_ramal_si(rama)
    q = 7.853982e-7
    una = control._hf_tuberia(tubos[0], q)[0]
    total = MotorFluidos._perdida_tramo(q, {'segmentos': segmentos}, 1000, 0.001)[0]
    assert total == pytest.approx(2*una, rel=1e-12)
    assert MotorFluidos._caudal_tramo(total, {'segmentos': segmentos}, 1000, 0.001) == pytest.approx(q, rel=1e-8)
    control._resolver_union_ramificada(union)
    assert control.datos_exportacion['tipo_sistema'] == 'Sistema Ramificado'
    assert len(control.datos_exportacion['tuberias']) == 4
    assert tubos[0].caudal_Q == pytest.approx(tubos[1].caudal_Q, rel=1e-8)
    assert tubos[0].hf_calculado == pytest.approx(tubos[1].hf_calculado, rel=1e-8)
    assert union.hj_calculada is not None


@pytest.mark.parametrize('tipo', ['K', 'Le/D'])
def test_red_invariante_en_todos_los_sentidos(tipo):
    referencias = None
    for reversiones in itertools.product((False, True), repeat=4):
        control = Control()
        union, tubos, _, acc = red_tres_ramas(reversiones, tipo, 20)
        # Duplicado accidental en una lista: sigue siendo un solo accesorio.
        propietario = min(tubos[:2], key=lambda t: t.id_tuberia)
        propietario.accesorios_conectados = [acc, acc]
        assert sum(t._sumar_accesorios(tipo) for t in tubos) == 20
        control._resolver_union_ramificada(union)
        assert 'tipo_sistema' in control.datos_exportacion, control.texto_resultados.valor
        actual = [(t.caudal_Q, t.hf_calculado) for t in tubos]
        if referencias is None:
            referencias = actual
        for a, b in zip(actual, referencias):
            assert a == pytest.approx(b, rel=1e-8, abs=0)


@pytest.mark.parametrize('reversiones', [(False,)*2, (True,)*2, (False,True), (True,False)])
def test_egl_divisor_se_descuenta_una_vez(reversiones):
    control = Control()
    a, b, acc = Tanque('A', 0, H=1), Tanque('B', 20), Accesorio('Divisor', 10, tipo='Le/D', valor=20)
    tubos = [Tubo(*(par[::-1] if rev else par), i+1)
             for i, (par, rev) in enumerate(zip([(a,acc),(acc,b)], reversiones))]
    q = 7.853982e-7
    for t in tubos:
        hf, dist, loc = control._hf_tuberia(t, q)
        control._guardar_resultado_tuberia(t, q, hf, hf_dist=dist, hf_loc=loc)
    total = sum(t.hf_calculado for t in tubos)
    b.elevacion_z = a.elevacion_z-total
    serie = control._construir_serie_ruta_egl(tubos, a, b)
    assert serie['puntos'][-1]['egl'] == pytest.approx(b.elevacion_z, abs=1e-6)
    assert sum(p['hf_tramo'] or 0 for p in serie['puntos']) == pytest.approx(total, rel=1e-10)
    assert len([p for p in serie['puntos'] if p['causa']=='accesorio']) == 1


def test_bypass_rechazado_sin_calcular(monkeypatch):
    control = Control()
    a, b, bomba = Tanque('A', 0), Tanque('B', 20), Bomba('Bomba', 10)
    Tubo(a,bomba,1)
    Tubo(bomba,b,2)
    Tubo(b,a,3)  # bypass dibujado en sentido inverso
    control.combo_punto1 = SimpleNamespace(currentIndex=lambda: 0)
    control.combo_punto2 = SimpleNamespace(currentIndex=lambda: 1)
    control._tanques_dashboard = [a,b]
    control.boton_ramificado = object()
    control.sender = lambda: None
    def prohibido(*args, **kwargs):
        pytest.fail('Una topología con bypass no debe llegar al solver')
    monkeypatch.setattr(bombas, 'punto_operacion', prohibido)
    control._on_calcular_punto_operacion = prohibido
    control._on_resolver_bernoulli()
    assert 'bypass' in control.texto_resultados.valor.lower()
    assert 'no soportada' in control.texto_resultados.valor.lower()
    assert control.datos_exportacion == {}
    assert bomba.Q_op is bomba.H_op is None
    assert bomba.estado_operacion == 'TOPOLOGIA_NO_SOPORTADA'


def test_busqueda_bomba_valida_solo_cadena_completa():
    control = Control()
    a, b, bomba = Tanque('A'), Tanque('B'), Bomba('B')
    t1, t2 = Tubo(bomba,a,1), Tubo(b,bomba,2)
    assert control._buscar_bomba_en_ruta(a,b) == (bomba,[t1,t2])
    lateral = Tanque('Extra')
    Tubo(bomba,lateral,3)
    with pytest.raises(ValueError, match='no soportada'):
        control._buscar_bomba_en_ruta(a,b)


def test_bomba_ramificada_recibe_segmentos_de_todos_los_ramales(monkeypatch):
    control = Control()
    union, tubos, tanques, acc = red_tres_ramas()
    # Añadir la bomba en la conducción de entrada: A -> bomba -> accesorio -> J.
    a = tanques[0]
    a.tuberias.remove(tubos[0])
    bomba = Bomba('Bomba')
    tubos[0].nodo_origen = bomba
    bomba.tuberias.append(tubos[0])
    Tubo(a,bomba,5)
    # Otro ramal con dos tramos y un diámetro distinto, que no puede colapsarse.
    b = tanques[1]
    segundo = Accesorio('Valvula', valor=3)
    b.tuberias.remove(tubos[2])
    tubos[2].nodo_destino = segundo
    segundo.tuberias.append(tubos[2])
    Tubo(segundo,b,6,D=0.02)
    bomba.curvas = [CurvaBomba([(0,1,0.8),(0.01,0,0.8)], 'lineal', 'B')]
    bomba.arreglo = 'individual'
    recibido = {}
    def capturar(estacion, principal, ramas, **kwargs):
        recibido.update(principal=principal, ramas=ramas)
        raise ValueError('fin de inspección de argumentos')
    monkeypatch.setattr(MotorFluidos, 'resolver_bomba_ramificada', capturar)
    control._resolver_bomba_en_red_ramificada(union, control._analizar_red_union(union))
    assert len(recibido['principal']['sub_tramos']) == 3
    assert sorted(len(r['segmentos']) for r in recibido['ramas']) == [1,2]
    largos = next(r['segmentos'] for r in recibido['ramas'] if len(r['segmentos'])==2)
    assert [s['D'] for s in largos] == [0.01,0.02]
    assert sum(s['K'] for s in largos) == 3


def test_motor_bomba_ramificada_suma_perdidas_por_segmento():
    q = 7.853982e-7
    segmento = dict(L=10.0,D=0.01,eps=0.0,K=0.0,LeD=0.0)
    segmentos = [segmento,dict(segmento)]
    principal = dict(H=0.0, sub_tramos=segmentos)
    ramas = [dict(H=0.0,segmentos=segmentos), dict(H=0.0,segmentos=segmentos)]
    hf_rama = MotorFluidos._perdida_tramo(q,ramas[0],1000,0.001)[0]
    hf_principal = MotorFluidos._perdida_tramo(2*q,principal,1000,0.001)[0]
    res = MotorFluidos.resolver_bomba_ramificada(lambda Q: hf_rama+hf_principal,
        principal,ramas,rho=1000,mu=0.001,Q_manual=2*q)
    assert res.convergio
    assert res.tramo_bomba_resultado['hf'] == pytest.approx(hf_principal,rel=1e-8)
    for rama in res.resultados_ramales:
        assert rama['Q'] == pytest.approx(q,rel=1e-8)
        assert len(rama['perdidas_segmentos']) == 2
        assert sum(p[0] for p in rama['perdidas_segmentos']) == pytest.approx(hf_rama,rel=1e-8)


def test_accesorio_anclado_y_divisor_no_se_duplica():
    a, b = Tanque('A'), Tanque('B')
    acc = Accesorio('Válvula',valor=20)
    t1, t2 = Tubo(a,acc,1,D=0.02), Tubo(acc,b,2,D=0.01)
    assert t1.sumatoria_K == 0 and t2.sumatoria_K == 20
    acc.tuberia_padre = t1
    t1.accesorios_conectados = [acc,acc]
    assert t1.sumatoria_K == 20 and t2.sumatoria_K == 0


@pytest.mark.parametrize('metodo,args', [('_guardar_campo_numerico',('longitud','12.5')),
                                       ('_guardar_unidad',('u_L','cm'))])
def test_edicion_invalida_exportacion_tabla_y_egl(metodo,args):
    control = Control()
    control.series = ['viejo']
    tubo = Tubo(Tanque('A'),Tanque('B'),1)
    getattr(control,metodo)(tubo,*args)
    assert control.datos_exportacion == {}
    assert control._tabla_cache is None
    assert control.series == []
