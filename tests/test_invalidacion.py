"""Invalidación y carga con dobles; un test de campos Qt usa offscreen, sin ventanas."""

import builtins
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

from motor import MotorFluidos
import ui.ventana.barra_herramientas as barra
from ui.ventana.bombas import BombasMixin
from ui.ventana.invalidacion import bloquear_senales, invalidar_resultados
from ui.ventana.panel_propiedades import PanelPropiedadesMixin
from ui.ventana.resolucion import ResolucionMixin
from test_validacion_fase import Tanque, Tubo as TuboBase, proyecto_json


class Tubo(TuboBase):
    def __init__(self, a, b, id_tuberia=1):
        super().__init__(a, b, id_tuberia)
        self.hf_calculado = None

    def actualizar_texto_hf(self, hf):
        self.hf_calculado = hf


class Grafico:
    def __init__(self):
        self.datos = ['viejos']
        self.limpiezas = 0

    def limpiar_datos(self):
        self.datos = []
        self.limpiezas += 1


class Texto:
    def __init__(self):
        self.valor = 'resultado viejo'

    def setPlainText(self, valor):
        self.valor = valor

    setHtml = setPlainText
    clear = lambda self: self.setPlainText('')


class Union:
    def __init__(self, x=0, y=0, id_union=1):
        self.id_union = id_union
        self.nombre = f'Union {id_union}'
        self.energia_supuesta = 0.0
        self.hj_calculada = None
        self.pos = lambda: SimpleNamespace(x=lambda:x, y=lambda:y)

    def actualizar_etiqueta(self):
        pass


class Senal:
    def __init__(self, escena):
        self.escena = escena
        self.intentados = self.entregados = 0

    def emit(self):
        self.intentados += 1
        if not self.escena.bloqueada:
            self.entregados += 1
            self.escena.control._on_elementos_modificados()


class Escena:
    def __init__(self, control):
        self.control = control
        self.elementos = []
        self.bloqueada = False
        self.elementos_modificados = Senal(self)

    def blockSignals(self, valor):
        previo = self.bloqueada
        self.bloqueada = valor
        return previo

    def items(self):
        return list(self.elementos)

    def selectedItems(self):
        return [object()]

    def clearSelection(self):
        self.elementos_modificados.emit()

    def addItem(self, elemento):
        self.elementos.append(elemento)
        self.elementos_modificados.emit()

    def eliminar(self, elemento):
        self.elementos.remove(elemento)
        self.elementos_modificados.emit()

    _eliminar_tuberia = _eliminar_tanque = _eliminar_union = _eliminar_bomba = eliminar


class Control(barra.BarraHerramientasMixin, PanelPropiedadesMixin, BombasMixin, ResolucionMixin):
    def __init__(self):
        self.escena = Escena(self)
        self.canvas_view = SimpleNamespace(scene=lambda:self.escena)
        self.fluido_rho, self.fluido_mu = 1000.0, 0.001
        self.fluido_P_atm, self.fluido_P_vap = 101325.0, 2339.0
        self.fluido_temperatura = 20.0
        self.datos_exportacion = {'viejos':True}
        self._tabla_cache = 'tabla vieja'
        self._ultimo_datos_grafico_bombas = {'viejos':True}
        self.egl_chart, self.grafico_bombas = Grafico(), Grafico()
        self.texto_resultados = Texto()
        self.boton_excel = SimpleNamespace(hide=lambda:None)
        self.tuberia_seleccionada = self.bomba_seleccionada = None
        self.campos_tuberia = {}
        self.label_hf_tuberia = None
        self.eventos = []

    def _refrescar_combos_dashboard(self):
        pass

    def _mostrar_tabla_vacia(self):
        pass

    def _mostrar_dashboard(self):
        pass

    def _limpiar_panel_content(self):
        pass

    def _on_elementos_modificados(self):
        if not getattr(self, '_cargando_proyecto', False) and not getattr(self, '_invalidando_resultados', False):
            self.eventos.append('invalidar')
        super()._on_elementos_modificados()

    def resolver(self):
        self.eventos.append('resolver')
        t = next(t for t in self.escena.items() if isinstance(t, Tubo))
        assert t.hf_calculado is None
        assert self.datos_exportacion == {} and self._tabla_cache is None
        q = (MotorFluidos.calcular_Q(10, t.longitud, t.diametro, 1000, 0.001, t.rugosidad)
             if t.caudal_Q == 0 else t.caudal_Q)
        p = MotorFluidos.calcular_hf(q, t.longitud, t.diametro, 1000, 0.001, t.rugosidad)
        self._guardar_resultado_tuberia(t, q, p[0], por_energia=True,
                                        hf_dist=p[1], hf_loc=p[2])
        self.datos_exportacion = {'nuevo':float(q)}
        self._tabla_cache = 'tabla nueva'
        self.egl_chart.datos = ['perfil nuevo']
        self.grafico_bombas.datos = ['curvas nuevas']
        self.texto_resultados.setPlainText('resultado nuevo')


@pytest.fixture
def clases_carga(monkeypatch):
    monkeypatch.setattr(barra, 'TanqueGrafico', Tanque)
    monkeypatch.setattr(barra, 'TuberiaGrafica', Tubo)
    monkeypatch.setattr(barra, 'NodoUnionGrafico', Union)


def tuberia(q_calculado=False, d_calculado=False):
    return SimpleNamespace(longitud=10.0, diametro=0.1, caudal_Q=0.001, rugosidad=1e-5,
        hf_calculado=1.5, hf_dist_calculado=1.0, hf_loc_calculado=0.5,
        desglose=[1], desglose_perdidas={'hf':1}, perdidas_segmentos=(1,),
        resultado_tramo=object(), resultado_tramo_sup=object(), historial_iteraciones=[1],
        hf_dado=4.0, accesorios=['dato'],
        _q_por_energia=q_calculado, _d_por_energia=d_calculado,
        u_Q='L/s', u_D='cm', actualizar_etiqueta=lambda:None)


@pytest.mark.parametrize('calculado_q', [False, True])
@pytest.mark.parametrize('calculado_d', [False, True])
def test_invalidacion_sin_qt_respeta_datos_y_procedencia(calculado_q, calculado_d):
    t = tuberia(calculado_q, calculado_d)
    u = SimpleNamespace(hj_calculada=12.0, energia_supuesta=9.0)
    equipo = {'Q':[0,0.01], 'H':[20,10]}
    b = SimpleNamespace(id_bomba=1, Q_op=0.1, H_op=12, eta_op=0.8,
                        equipos=[equipo], z_bomba=2)
    invalidar_resultados([t,u,b])
    assert t.caudal_Q == (0.0 if calculado_q else 0.001)
    assert t.diametro == (0.0 if calculado_d else 0.1)
    assert t._q_por_energia is calculado_q and t._d_por_energia is calculado_d
    assert (t.hf_calculado, t.hf_dist_calculado, t.hf_loc_calculado) == (None,None,None)
    assert t.desglose == [] and t.desglose_perdidas == {} and t.perdidas_segmentos == ()
    assert t.resultado_tramo is None and t.resultado_tramo_sup is None
    assert t.historial_iteraciones == []
    assert t.hf_dado == 4 and t.accesorios == ['dato']
    assert t.longitud == 10 and t.rugosidad == 1e-5 and t.u_Q == 'L/s' and t.u_D == 'cm'
    assert u.hj_calculada is None and u.energia_supuesta == 9
    assert b.Q_op is None and b.H_op is None and b.eta_op is None
    assert b.equipos == [equipo] and b.z_bomba == 2
    assert b.reparto == [] and b.desglose == [] and b.estado_operacion == 'SIN_CALCULAR'
    invalidar_resultados([t,u,b])  # idempotencia
    assert t.diametro == (0.0 if calculado_d else 0.1)


def test_modulo_puede_importarse_sin_qt(monkeypatch):
    importar = builtins.__import__
    def sin_qt(nombre, *args, **kwargs):
        if nombre.startswith('PyQt'):
            pytest.fail('La invalidación independiente no debe importar Qt.')
        return importar(nombre, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', sin_qt)
    ruta = Path(__file__).resolve().parents[1]/'ui'/'ventana'/'invalidacion.py'
    modulo = runpy.run_path(str(ruta))
    t = tuberia(True, True)
    modulo['invalidar_resultados']([t])
    assert t.caudal_Q == 0 and t.diametro == 0


def test_limpieza_completa_ventana_reutiliza_limpiador_de_bomba():
    c = Control()
    c.grafico_bombas.reparto = [{'Q':123}]
    c.grafico_bombas._marcador_op_hq_pos = (1,2)
    c.grafico_bombas._marcador_op_eta_pos = (3,4)
    tabla = SimpleNamespace(celdas=[123], filas=1, columnas=1)
    tabla.clearContents = lambda:tabla.celdas.clear()
    tabla.setRowCount = lambda n:setattr(tabla,'filas',n)
    tabla.setColumnCount = lambda n:setattr(tabla,'columnas',n)
    c.tabla_excel_preview = tabla
    b = SimpleNamespace(id_bomba=1, Q_op=1, H_op=10, actualizar_tooltip=lambda:None)
    original = c._limpiar_resultados_bomba
    limpiadas = []
    c._limpiar_resultados_bomba = lambda bomba: (limpiadas.append(bomba), original(bomba))
    c.escena.elementos = [tuberia(True,True), b, b]
    c._on_elementos_modificados()
    assert limpiadas == [b]
    assert c.datos_exportacion == {} and c._tabla_cache is None
    assert c.egl_chart.datos == [] and c.grafico_bombas.datos == []
    assert c.grafico_bombas.reparto == []
    assert c.grafico_bombas._marcador_op_hq_pos is None
    assert c.grafico_bombas._marcador_op_eta_pos is None
    assert tabla.celdas == [] and tabla.filas == 0 and tabla.columnas == 0
    assert c.texto_resultados.valor == '' and c._ultimo_datos_grafico_bombas is None


@pytest.mark.parametrize('hf_dist,hf_loc', [(None,None), (2.0,None), (None,3.0), (2.0,3.0)])
def test_guardar_resultado_borra_desglose_anterior(hf_dist, hf_loc):
    c, t = Control(), tuberia()
    t.u_Q = 'm³/s'
    t.actualizar_texto_hf = lambda valor:setattr(t,'hf_calculado',valor)
    c._guardar_resultado_tuberia(t, 0.002, 5, hf_dist=hf_dist, hf_loc=hf_loc)
    assert t.hf_calculado == 5
    assert t.hf_dist_calculado == hf_dist and t.hf_loc_calculado == hf_loc
    assert t.desglose == [] and t.resultado_tramo is None


@pytest.mark.parametrize('cache', [12345, 'caché antigua', float('nan')])
def test_hj_antiguo_se_ignora_y_no_se_guarda(clases_carga, cache):
    c = Control()
    datos = proyecto_json()
    datos['uniones'] = [dict(id_union=1, energia_supuesta=5.0, hj_calculada=cache)]
    c._deserializar_proyecto(datos)
    u = next(u for u in c.escena.items() if isinstance(u, Union))
    assert u.hj_calculada is None and u.energia_supuesta == 5
    assert c.eventos == ['invalidar']
    assert 'hj_calculada' not in c._serializar_proyecto()['uniones'][0]
    assert 'hj_calculada' in datos['uniones'][0]  # no se altera la entrada


@pytest.mark.parametrize('modo', [0,1])
def test_cargar_invalida_una_vez_antes_de_resolver_y_no_borra_resultado(clases_carga, modo):
    c = Control()
    c.escena.elementos = [Tubo(Tanque(), Tanque(id_tanque=2))]
    datos = proyecto_json(_q_por_energia=True)
    datos['dashboard'] = dict(modo=modo)
    c.boton_bernoulli = SimpleNamespace(click=c.resolver)
    c.boton_ramificado = SimpleNamespace(click=c.resolver)
    c._deserializar_proyecto(datos)
    assert c.eventos == ['invalidar','resolver']
    assert not c.escena.bloqueada and not c._cargando_proyecto
    assert c.escena.elementos_modificados.intentados > 0
    assert c.escena.elementos_modificados.entregados == 0
    assert c.egl_chart.limpiezas == 1
    t = next(t for t in c.escena.items() if isinstance(t,Tubo))
    assert t.hf_calculado is not None and t.caudal_Q > 0 and t._q_por_energia
    assert c.datos_exportacion['nuevo'] > 0 and c._tabla_cache == 'tabla nueva'
    assert c.egl_chart.datos == ['perfil nuevo']
    assert c.texto_resultados.valor == 'resultado nuevo'


def test_carga_sin_resolver_borra_q_d_calculados_y_guarda_banderas(clases_carga):
    c = Control()
    c._deserializar_proyecto(proyecto_json(_q_por_energia=True,_d_por_energia=True))
    t = next(t for t in c.escena.items() if isinstance(t,Tubo))
    assert t.caudal_Q == 0 and t.diametro == 0
    guardado = c._serializar_proyecto()['tuberias'][0]
    assert guardado['caudal_Q'] == 0 and guardado['diametro'] == 0
    assert guardado['_q_por_energia'] is True and guardado['_d_por_energia'] is True
    with pytest.raises(ValueError, match='diámetro'):
        MotorFluidos.calcular_hf(0.001,10,t.diametro,1000,0.001,0)


def test_excepcion_de_reconstruccion_restaura_senales_e_invalida(clases_carga, monkeypatch):
    c = Control()
    def fallo(*args, **kwargs):
        raise RuntimeError('fallo de reconstrucción')
    monkeypatch.setattr(barra, 'TanqueGrafico', fallo)
    # No hay objetos previos, por lo que el fallo se produce en el constructor.
    with pytest.raises(RuntimeError):
        c._deserializar_proyecto(proyecto_json())
    assert c.escena.bloqueada is False and c._cargando_proyecto is False
    assert c.datos_exportacion == {} and c._tabla_cache is None
    assert c.eventos == ['invalidar']


def test_bloqueo_restaura_estado_anterior_incluso_si_ya_estaba_bloqueado():
    c = Control()
    c.escena.bloqueada = True
    with pytest.raises(RuntimeError):
        with bloquear_senales(c.escena):
            raise RuntimeError()
    assert c.escena.bloqueada is True


@pytest.mark.parametrize('campo', ['diametro', 'caudal_Q'])
def test_adoptar_el_mismo_valor_calculado_como_dato_es_un_cambio(campo):
    c, t = Control(), tuberia(True, True)
    c.escena.elementos = [t]
    valor = getattr(t, campo)
    c._guardar_campo_numerico(t, campo, str(valor))
    assert c.eventos == ['invalidar']
    assert getattr(t, campo) == valor
    if campo == 'diametro':
        assert t._d_por_energia is False and t.caudal_Q == 0
    else:
        assert t._q_por_energia is False and t.diametro == 0
    assert t.hf_calculado is None


@pytest.mark.parametrize('cambio', ['diametro','unidad','atmosfera','tipo','forma','fluido'])
def test_cualquier_edicion_borra_tabla_perfil_y_resultados(cambio, monkeypatch):
    c, t = Control(), tuberia(True,True)
    c.escena.elementos = [t]
    if cambio == 'diametro':
        c._guardar_campo_numerico(t, 'diametro', '0.2')
        assert t.diametro == 0.2 and t._d_por_energia is False
    elif cambio == 'unidad':
        c._guardar_unidad(t, 'u_D', 'mm')
    elif cambio == 'atmosfera':
        tanque = SimpleNamespace(presion_P=500, abierto_atmosfera=False,
            actualizar_etiqueta=lambda:None, update=lambda:None)
        campo = SimpleNamespace(setText=lambda texto:None, setEnabled=lambda valor:None)
        c._on_atmosfera_toggled(tanque, campo, True)
    elif cambio == 'tipo':
        c._on_tipo_accesorio_cambiado(SimpleNamespace(), 'Le/D')
    elif cambio == 'forma':
        accesorio = SimpleNamespace(tuberia_padre=None, update=lambda:None)
        c._on_forma_accesorio_cambiada(accesorio, 'Válvula')
    else:
        dialogo = SimpleNamespace(exec_=lambda:barra.QDialog.Accepted,
                                  valores=lambda:(950,0.002,90000,3000))
        monkeypatch.setattr(barra, 'DialogoFluido', lambda *a,**kw:dialogo)
        c._on_propiedades_fluido()
    assert c.eventos == ['invalidar']
    assert c.datos_exportacion == {} and c._tabla_cache is None
    assert c.egl_chart.datos == [] and c.grafico_bombas.datos == []
    assert c._ultimo_datos_grafico_bombas is None and c.texto_resultados.valor == ''
    assert t.hf_calculado is None and t.caudal_Q == 0


def test_campo_qt_programatico_no_es_edicion_y_el_usuario_si(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget
    app = QApplication.instance() or QApplication([])
    contenedor = QWidget()  # nunca se muestra ni se ejecuta un event loop
    c = Control()
    t = Tubo(Tanque(),Tanque(id_tanque=2))
    t.sumatoria_K = t.sumatoria_Le_D = 0
    t.hf_calculado = None
    c.escena.elementos = [t]
    c.tuberia_seleccionada = t
    c.panel_content_layout = QVBoxLayout(contenedor)
    c._limpiar_panel_content = lambda:None
    c.UNIDADES_Q, c.UNIDADES_L = ['m³/s','L/s'], ['m','cm']
    c.UNIDADES_D, c.UNIDADES_EPSILON = ['m','cm'], ['m','mm']
    c._mostrar_campos_tuberia(t)
    c._guardar_resultado_tuberia(t,0.002,3,por_energia=True,hf_dist=2,hf_loc=1)
    assert c.eventos == [] and t._q_por_energia is True
    assert t.caudal_Q == 0.002 and t.hf_calculado == 3
    c.campos_tuberia['D'].textEdited.emit('0.2')
    assert c.eventos == ['invalidar']
    assert t.diametro == 0.2 and t.caudal_Q == 0 and t.hf_calculado is None
    assert c.campos_tuberia['Q'].text() == ''
    assert c._tabla_cache is None and c.egl_chart.datos == []
    contenedor.close()
    assert app is not None
