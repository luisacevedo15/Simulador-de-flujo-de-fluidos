"""CAD/Excel/TABLA con dobles simples: no se crea QApplication ni una ventana."""

import io
import json
from pathlib import Path
import re
from types import SimpleNamespace

import openpyxl
import pytest
import xlsxwriter

from motor import MotorFluidos
from motor.hidraulica import evaluar_tramo
import ui.graficos as graficos
from ui.constantes import FACTORES_SI
from ui.reportes import rpt_tabla
from ui.ventana.bernoulli import BernoulliMixin
from ui.ventana.dashboard import DashboardMixin
from ui.ventana.exportacion import ExportacionMixin
from ui.ventana.memoria_calculo import MemoriaCalculoMixin
from ui.ventana.resolucion import ResolucionMixin
from ui.ventana.vistas import VistasMixin
from test_exportacion_fase import verificar_hoja_auxiliar


AGUA = dict(rho=1000.0, mu=0.001, g=9.81)
GOLDEN = Path(__file__).resolve().parent / 'golden'


class Accesorio:
    def __init__(self, tipo, valor, padre):
        self.tipo_perdida, self.valor, self.tuberia_padre = tipo, valor, padre


class Tuberia:
    _accesorios_asignados = graficos.TuberiaGrafica._accesorios_asignados
    _sumar_accesorios = graficos.TuberiaGrafica._sumar_accesorios
    sumatoria_K = property(lambda self: self._sumar_accesorios('K'))
    sumatoria_Le_D = property(lambda self: self._sumar_accesorios('Le/D'))

    def __init__(self, L=100, D=0.1, eps=0, K=2, LeD=20, nombre='T1'):
        self.longitud, self.diametro, self.rugosidad = L, D, eps
        self.nombre, self.id_tuberia = nombre, 1
        self.u_L = self.u_D = self.u_eps = 'm'
        self.u_Q = 'm³/s'
        self.caudal_Q, self.hf_calculado = 0.0, None
        self._q_por_energia = self._d_por_energia = False
        self.nodo_origen = self.nodo_destino = object()
        self.color_personalizado = None
        self.pen = lambda: SimpleNamespace(color=lambda: SimpleNamespace(name=lambda: '#0284c7'))
        self.accesorios_conectados = [Accesorio('K', K, self), Accesorio('Le/D', LeD, self)]
        # Esta fuente incorrecta antigua nunca debe participar en el tooltip.
        self.accesorios = [SimpleNamespace(k=9876)]

    def actualizar_etiqueta(self):
        pass

    def actualizar_texto_hf(self, hf):
        self.hf_calculado = hf


class Control(ExportacionMixin, MemoriaCalculoMixin, DashboardMixin, VistasMixin, BernoulliMixin):
    fluido_rho, fluido_mu = 1000.0, 0.001
    _datos_si = ResolucionMixin._datos_si
    _a_si = staticmethod(lambda v, u: v*FACTORES_SI[u])
    _desde_si = staticmethod(lambda v, u: v/FACTORES_SI[u])
    _z_tuberia = staticmethod(lambda t: 0.0)
    _guardar_resultado_tuberia = ResolucionMixin._guardar_resultado_tuberia
    _refrescar_label_hf = lambda *args: None

    def __init__(self):
        self.boton_excel = self.contenedor_barras = SimpleNamespace(show=lambda: None, hide=lambda: None)
        self.datos_exportacion = {}
        self.tuberia_seleccionada = None
        self.campos_tuberia = {}
        self._tabla_cache = None

    def _s7(self, valor):
        pytest.fail('No se debe redondear antes de presentar.')


@pytest.fixture(autouse=True)
def tipos_accesorios(monkeypatch):
    monkeypatch.setattr(graficos, 'AccesorioGrafico', Accesorio)


def texto(html):
    return re.sub('<[^>]+>', '', html)


@pytest.mark.parametrize('nombre', ['a_tanque_tanque', 'b_serie_accesorios'])
def test_filas_doradas_exportan_floats_exactos_del_resultado(nombre):
    d = json.loads((GOLDEN/f'{nombre}.json').read_text(encoding='utf-8'))
    control = Control()
    for entrada, golden in zip(d['entrada']['tramos'], d['tramos']):
        t = Tuberia(entrada['L'], entrada['D'], entrada['eps'], entrada['K'], entrada['LeD'])
        q = golden['Q']
        r = evaluar_tramo(q, t.longitud, t.diametro, t.rugosidad,
                          t.sumatoria_K, t.sumatoria_Le_D, AGUA, id=t.id_tuberia)
        fila = control._fila_exportacion(t, q, golden['hf_total'])
        for clave, esperado in dict(Area=r.area, V=r.v, Re=r.Re, f=r.f, Q=r.Q,
            hf=r.hf_total, hf_dist=r.hf_distribuida, hf_loc=r.hf_localizada,
            rugosidad_relativa=r.rugosidad_relativa, karman=r.karman,
            inv_raiz_f=r.inv_raiz_f).items():
            assert fila[clave] == esperado  # igualdad float exacta, no approx
        assert fila['regimen'] == r.regimen
        assert fila['resultado_tramo'] == r
        celdas, re_cad = control._fila_tabla_cad_tuberia(t, q, -999)
        assert re_cad == r.Re
        assert texto(celdas[-1]) == f"{fila['hf']:.2f}"


def test_cad_hf_total_y_k_de_accesorios_asignados_una_vez():
    t, c = Tuberia(K=0, LeD=80), Control()
    primero = Accesorio('K', 1.25, t)
    t.accesorios_conectados.extend([primero, primero, Accesorio('K', 2.75, t)])
    fila = c._fila_exportacion(t, 0.007853982, 0)
    celdas, _ = c._fila_tabla_cad_tuberia(t, fila['Q'], fila['hf'])
    assert 'ΣK = 4.00' in celdas[0]
    assert fila['K'] == sum(a.valor for a in t._accesorios_asignados() if a.tipo_perdida=='K') == 4
    assert texto(celdas[-1]) == f"{fila['hf']:.2f}"
    assert texto(celdas[-1]) != f"{fila['hf_dist']:.2f}"
    html = rpt_tabla([celdas], ['RAMAL','Q (M³/S)','V (M/S)','F (C-W)','HF FRIC. (M)'])
    assert 'HF TOTAL (M)' in html and 'HF FRIC.' not in html


@pytest.mark.parametrize(('campo','valor'), [('diametro',0), ('diametro',-1),
    ('longitud',0), ('longitud',float('nan')), ('diametro',float('inf'))])
def test_geometria_invalida_sin_numeros_inventados(campo, valor):
    t = Tuberia()
    setattr(t, campo, valor)
    celdas, re_cad = Control()._fila_tabla_cad_tuberia(t, 0.001, 123)
    assert [texto(c) for c in celdas[1:]] == ['—']*4
    assert re_cad is None
    assert 'Datos inválidos' in celdas[0]


def test_exportacion_supuestos_globales_residuo_sin_redondear():
    c, t = Control(), Tuberia()
    valor, residuo = 1.2345678901234567, 1.2345678901234567e-16
    c._registrar_exportacion('Sistema Simple', [(t, 0.001, 999)],
        dict(numero=valor, texto='dato', vacio=None), ['Balance'], residuo, 'EQUILIBRIO',
        calculos_globales=dict(energia=valor))
    d = c.datos_exportacion
    assert d['suposiciones'] == dict(numero=valor, texto='dato', vacio=None)
    assert d['resultados_globales']['energia'] == valor
    assert d['resultados']['variacion_Q'] == residuo
    assert d['tuberias'][0]['hf_resolucion'] == 999
    assert d['tuberias'][0]['hf'] != 999


@pytest.mark.parametrize('q', [0.0, 1e-6, 0.007853982])
def test_caches_de_formulas_desde_resultado_no_desde_derivados_de_fila(q):
    c = Control()
    t = c._fila_exportacion(Tuberia(), q, None)
    r = t['resultado_tramo']
    t.update(V=12345, Re=12345, f=12345, hf_dist=12345, hf_loc=12345)
    destino = io.BytesIO()
    libro = xlsxwriter.Workbook(destino, {'in_memory':True})
    visible = libro.add_worksheet('Visible')
    campos = ('V','Re','f','hf','hf_dist','hf_loc')
    c._escribir_hidraulica_excel(visible, libro, t,
                                {clave:i for i,clave in enumerate(campos)}, 0, None)
    libro.close()
    _, caches = verificar_hoja_auxiliar(destino.getvalue())
    esperados = dict(V=r.v, Re=r.Re, f=r.f if r.f is not None else 0,
                     hf=r.hf_total, hf_dist=r.hf_distribuida, hf_loc=r.hf_localizada)
    for i, clave in enumerate(campos, 1):
        assert caches['Visible'].cell(i,1).value == esperados[clave]


def test_tabla_conserva_numero_original_de_la_cache():
    c, t = Control(), Tuberia()
    c._registrar_exportacion('Sistema Simple', [(t,0.007853982,None)], {},
                             ['Balance'], 0, 'EQUILIBRIO')
    c.stack_tabla = object()
    c._renderizar_tabla_excel = lambda: None
    c._mostrar_tabla_con_datos = lambda: None
    c._mostrar_tabla_vacia = lambda: pytest.fail('La tabla debe conservar los datos.')
    c._actualizar_vista_tabla_excel()
    valores = [v['valor'] for v in c._tabla_cache['celdas'].values()]
    r = c.datos_exportacion['tuberias'][0]['resultado_tramo']
    for numero in (r.v, r.Re, r.hf_total):
        assert numero in valores
    assert any(v['valor'] == r.v and v['txt'] == f'{r.v:.6g}'
               for v in c._tabla_cache['celdas'].values())


@pytest.mark.parametrize('diseno', [False, True])
def test_bernoulli_simple_mantiene_hf_disponible_en_diseno(diseno):
    c, t = Control(), Tuberia()
    t.caudal_Q = 0.0 if diseno else 0.007853982
    escena = object()
    c.canvas_view = SimpleNamespace(scene=lambda: escena)
    c.sender = lambda: None
    c.boton_ramificado = object()
    c.combo_punto1 = SimpleNamespace(currentIndex=lambda:0)
    c.combo_punto2 = SimpleNamespace(currentIndex=lambda:1)
    c._tanques_dashboard = [SimpleNamespace(elevacion_z=z, presion_P=0.0,
        nombre=nombre, scene=lambda:escena) for z,nombre in ((20,'A'),(5,'B'))]
    c._encontrar_ruta = lambda *args: [[t]]
    c.texto_resultados = SimpleNamespace(setHtml=lambda s:None,
                                         setPlainText=lambda s:pytest.fail(s))
    barras = []
    c._actualizar_barra_perdidas = lambda *args: barras.append(args)
    c._on_resolver_bernoulli()
    r = c.datos_exportacion['tuberias'][0]['resultado_tramo']
    assert barras[0][0] == (15.0 if diseno else r.hf_total)
    assert barras[0][1:] == (r.hf_distribuida, r.hf_localizada, 0.0)
    assert c.datos_exportacion['tuberias'][0]['regimen'] == r.regimen
    assert t._q_por_energia is diseno
