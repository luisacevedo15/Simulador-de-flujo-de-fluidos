"""Inspección y evaluación independiente de fórmulas; sin Excel, LibreOffice ni UI."""

import ast
import io
import math
import operator
from functools import lru_cache
from types import SimpleNamespace

import openpyxl
from openpyxl.formula import Tokenizer
import pytest
import xlsxwriter

from motor import MotorFluidos
from ui.ventana.exportacion import ExportacionMixin
from ui.ventana.memoria_calculo import MemoriaCalculoMixin


class Exportador(MemoriaCalculoMixin, ExportacionMixin):
    fluido_rho, fluido_mu = 1000.0, 0.001
    _s7 = staticmethod(lambda x: x)
    _datos_si = staticmethod(lambda t: (t.L, t.D, t.eps))
    _z_tuberia = staticmethod(lambda t: 0.0)


class EvaluadorFormulas:
    """Evalúa el subconjunto Excel generado, sin utilizar cachés ni la ley del motor."""
    def __init__(self, libro):
        self.libro = libro

    @lru_cache(maxsize=None)
    def celda(self, hoja, direccion):
        valor = self.libro[hoja][direccion.replace('$','')].value
        if not isinstance(valor, str) or not valor.startswith('='):
            return valor
        referencias, partes = {}, []
        for token in Tokenizer(valor).items:
            if token.type == 'OPERAND' and token.subtype == 'RANGE':
                nombre = f'ref{len(referencias)}'
                referencias[nombre] = token.value
                partes.append(nombre)
            elif token.type == 'OPERAND' and token.subtype == 'LOGICAL':
                partes.append('True' if token.value == 'TRUE' else 'False')
            elif token.type == 'OPERATOR-INFIX' and token.value == '=':
                partes.append('==')
            elif token.type == 'OPERATOR-INFIX' and token.value == '^':
                partes.append('**')
            else:
                partes.append(token.value)

        def rango(texto):
            if '!' in texto:
                otra, direccion = texto.rsplit('!',1)
                otra = otra.strip("'")
            else:
                otra, direccion = hoja, texto
            if ':' in direccion:
                return [self.celda(otra, c.coordinate)
                        for fila in self.libro[otra][direccion.replace('$','')] for c in fila]
            return self.celda(otra, direccion)

        def evaluar(n):
            if isinstance(n, ast.Constant):
                return n.value
            if isinstance(n, ast.Name):
                if n.id in referencias:
                    return rango(referencias[n.id])
                return {'TRUE': True, 'FALSE': False}[n.id]
            if isinstance(n, ast.UnaryOp):
                return (-1 if isinstance(n.op, ast.USub) else 1)*evaluar(n.operand)
            if isinstance(n, ast.BinOp):
                op = {ast.Add:operator.add, ast.Sub:operator.sub, ast.Mult:operator.mul,
                      ast.Div:operator.truediv, ast.Pow:operator.pow}[type(n.op)]
                return op(evaluar(n.left), evaluar(n.right))
            if isinstance(n, ast.Compare):
                op = {ast.Lt:operator.lt, ast.LtE:operator.le, ast.Gt:operator.gt,
                      ast.GtE:operator.ge, ast.Eq:operator.eq}[type(n.ops[0])]
                return op(evaluar(n.left), evaluar(n.comparators[0]))
            if isinstance(n, ast.Call):
                funcion = n.func.id.upper()
                if funcion == 'IF':
                    return evaluar(n.args[1] if evaluar(n.args[0]) else n.args[2])
                if funcion == 'AND':
                    return all(evaluar(a) for a in n.args)
                args = [evaluar(a) for a in n.args]
                if funcion == 'MATCH':
                    return args[1].index(args[0])+1
                if funcion == 'NA':
                    raise AssertionError('La fórmula no ha convergido: NA()')
                return {'ABS':abs, 'LN':math.log, 'SQRT':math.sqrt,
                        'PI':lambda: math.pi}[funcion](*args)
            raise AssertionError(ast.dump(n))
        return evaluar(ast.parse(''.join(partes), mode='eval').body)


def fila(exportador, Q, K, LeD, eps=0.0, identificador=1, rol='colebrook'):
    t = SimpleNamespace(L=10.0, D=0.1, eps=eps, sumatoria_K=K,
                        sumatoria_Le_D=LeD, id_tuberia=identificador, nombre=f'Tubo {identificador}')
    hf = MotorFluidos.calcular_hf(Q, t.L, t.D, 1000, 0.001, eps,
                                 sumatoria_K=K, sumatoria_Le_D=LeD)[0]
    return exportador._fila_exportacion(t, Q, hf, rol=rol)


def verificar_hoja_auxiliar(contenido):
    formulas = openpyxl.load_workbook(io.BytesIO(contenido), data_only=False)
    caches = openpyxl.load_workbook(io.BytesIO(contenido), data_only=True)
    assert formulas['_Hidraulica'].sheet_state == 'hidden'
    evaluador = EvaluadorFormulas(formulas)
    hoja = formulas['_Hidraulica']
    # Evaluar por orden de dependencias las cadenas largas de iteración.
    for row in hoja.iter_rows(min_row=23, max_row=122):
        for c in row:
            if c.data_type == 'f':
                evaluador.celda(hoja.title, c.coordinate)
    for row in hoja:
        for c in row:
            if c.data_type != 'f':
                continue
            obtenido = evaluador.celda(hoja.title, c.coordinate)
            esperado = caches[hoja.title][c.coordinate].value
            if isinstance(obtenido, (float,int)) and not isinstance(obtenido, bool):
                assert obtenido == pytest.approx(esperado, rel=1e-8, abs=1e-14), c.coordinate
            else:
                assert obtenido == esperado, c.coordinate
    return formulas, caches


@pytest.mark.parametrize('Q',[0.0,1e-9,1e-6,1e-3,0.1])
@pytest.mark.parametrize('K,LeD,eps',[(0,0,0),(20,50,0.00003)])
def test_excel_formulas_y_cache_coinciden_con_motor(Q,K,LeD,eps):
    exportador = Exportador()
    t = fila(exportador,Q,K,LeD,eps)
    # Los números no pueden redondearse a siete cifras antes de formular.
    assert t['Q'] == Q
    assert t['K'] == K and t['LeD'] == LeD
    datos = dict(tipo_sistema='Sistema Simple', tuberias=[t], suposiciones={},
        resultados=dict(condicion_final=['Balance de energía'], variacion_Q=0.0,
                        recomendacion='EQUILIBRIO', ok=True))
    destino = io.BytesIO()
    exportador._escribir_libro_excel(destino,datos)
    formulas, caches = verificar_hoja_auxiliar(destino.getvalue())
    hoja = formulas['_Hidraulica']
    assert '+$B$8' in hoja['B19'].value  # Le/D dentro del término multiplicado por f
    assert '+$B$7' in hoja['B19'].value  # K independiente de f
    assert caches['_Hidraulica']['B19'].value == pytest.approx(t['hf'], rel=1e-8, abs=0)
    assert caches['_Hidraulica']['B21'].value == 'OK'
    if t['Re'] >= 2000:
        assert caches['_Hidraulica']['B15'].value > 5
    else:
        assert caches['_Hidraulica']['B15'].value == 0


@pytest.mark.parametrize('tipo', ['Sistema en Paralelo','Sistema Mixto (Paralelo-Serie)',
                                 'Sistema en Serie (por Energía)','Sistema en Paralelo (Ampliación)',
                                 'Sistema Ramificado','Bomba en Red Ramificada'])
def test_memorias_usen_formulas_completas_en_todos_los_casos(tipo):
    e = Exportador()
    tubos = [fila(e,0.001,20,50,identificador=i+1) for i in range(2)]
    hf = tubos[0]['hf']
    sup = dict(Tub_Supuesta='Tubo 1', Q_supuesto=0.001, Q_total=0.002, Iteraciones=10,
               Residuo_masa_relativo=0.0, H_A=2*hf, H_B=0.0, hf_disponible=hf)
    sup['H_J (Calculada)'] = hf
    tubos[0].update(Q_sup=0.001, Re_sup=tubos[0]['Re'], hf_sup=hf, rol='par_sup')
    tubos[1]['rol'] = 'par_karman'
    if tipo == 'Sistema Mixto (Paralelo-Serie)':
        tubos.append(fila(e,0.002,10,30,identificador=3,rol='serie_diseno_d'))
        sup['hf_serie'] = tubos[-1]['hf']
    if tipo == 'Sistema en Paralelo (Ampliación)':
        tubos[0]['rol'], tubos[1]['rol'] = 'diseno_d','karman_amp'
    datos = dict(tipo_sistema=tipo, tuberias=tubos, suposiciones=sup,
                 resultados=dict(condicion_final=['Balance'], variacion_Q=0.0,
                                 recomendacion='EQUILIBRIO', ok=True))
    destino = io.BytesIO()
    libro = xlsxwriter.Workbook(destino,{'in_memory':True})
    if tipo == 'Bomba en Red Ramificada':
        e._hoja_memoria_bomba_ramificada(libro,datos)
    else:
        e._hoja_memoria_calculo(libro,datos)
    libro.close()
    verificar_hoja_auxiliar(destino.getvalue())


def test_colebrook_cache_realmente_converge():
    for Re in (0,100,1999,2000,1e5,1e7):
        props, obtenidos = Exportador._colebrook_cache(Re,0.0003)
        if Re >= 2000:
            assert len(obtenidos) > 5
            x = obtenidos[-1]
            assert abs(x-props[-1]) < 1e-12
            assert abs((x+0.86*math.log(0.0003/3.7+2.51*x/Re))/x) < 1e-8
        else:
            assert len(obtenidos) == 1


def test_memoria_doble_nudo_tambien_incluye_accesorios():
    e = Exportador()
    tubos = [fila(e,0.001,20,50,identificador=i+1,rol=rol)
             for i,rol in enumerate(('j','central','k'))]
    datos = dict(tipo_sistema='Sistema Ramificado (Doble Nudo)',tuberias=tubos,
        suposiciones={'H_j (Supuesta)': 1.0}, resultados_globales={'H_k (Calculada)':0.5},
        resultados=dict(condicion_final=['Balance'],variacion_Q=0.0,recomendacion='EQUILIBRIO',ok=True))
    destino = io.BytesIO()
    e._escribir_libro_excel(destino,datos)
    verificar_hoja_auxiliar(destino.getvalue())
