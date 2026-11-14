"""Resultados SI sin UI y equivalencia con la ley y las capturas existentes."""

from dataclasses import FrozenInstanceError, fields, replace
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from motor import MotorFluidos
from motor.friccion import (
    RE_LIMITE_LAMINAR, RE_LIMITE_TURBULENTO, calcular_f_y_Re, clasificar_regimen,
)
from motor.hidraulica import evaluar_tramo
from motor.resultados import PerdidaAccesorio, ResultadoTramo


AGUA = dict(rho=1000.0, mu=0.001, g=9.81)
GOLDEN = Path(__file__).resolve().parent / 'golden'


def test_laminar_de_referencia():
    r = evaluar_tramo(7.853982e-7, 10.0, 0.01, 0.0, 0.0, 0.0, AGUA)
    assert r.v == pytest.approx(0.01, rel=1e-7)
    assert r.Re == pytest.approx(100.0, rel=1e-7)
    assert r.f == pytest.approx(0.64, rel=1e-7)
    assert r.ley == 'laminar'
    assert r.regimen == 'Laminar'
    assert r.hf_total == pytest.approx(0.003261978, abs=5e-10, rel=0)


def test_colebrook_con_accesorios_de_referencia():
    r = evaluar_tramo(0.007853982, 100.0, 0.1, 0.0, 2.0, 20.0, AGUA)
    # Q y las referencias del enunciado están redondeados: no son constantes
    # exactas. Las comparaciones de ley/golden de abajo sí exigen 1e-12.
    assert r.v == pytest.approx(1.0, rel=1e-7)
    assert r.f == pytest.approx(0.018312901, abs=1e-9, rel=0)
    assert r.hf_distribuida == pytest.approx(0.933379, abs=5e-7, rel=0)
    assert r.hf_localizada == pytest.approx(0.120604, abs=5e-7, rel=0)
    assert r.hf_total == pytest.approx(1.053984, abs=5e-7, rel=0)
    assert r.ley == 'colebrook'
    assert r.regimen == 'Turbulento'


@pytest.mark.parametrize('q', [0.0, 1e-6, 1e-4, 1e-3, 1e-2, 1e-1])
def test_perdidas_exactamente_iguales_al_motor(q):
    r = evaluar_tramo(q, 100.0, 0.1, 1e-5, 2.0, 20.0, AGUA)
    p = MotorFluidos.calcular_hf(q, 100.0, 0.1, 1000.0, 0.001, 1e-5,
                               sumatoria_K=2.0, sumatoria_Le_D=20.0)
    assert r.hf_total == p[0]
    assert r.hf_distribuida == p[1]
    assert r.hf_localizada == p[2]
    assert r.hf_total == pytest.approx(r.hf_distribuida+r.hf_localizada, rel=1e-12, abs=0)


def test_reposo():
    r = evaluar_tramo(0, 10, 0.01, 0, 2, 20, AGUA)
    assert r.ley == 'reposo'
    assert r.f is None
    assert (r.v, r.Re, r.hf_distribuida, r.hf_localizada, r.hf_total) == (0, 0, 0, 0, 0)
    assert r.regimen == 'Laminar'  # etiqueta UI, independiente de la ley reposo
    assert calcular_f_y_Re(0, 0.01, 1000, 0.001) == (None, 0.0)


@pytest.mark.parametrize(('re', 'etiqueta'), [
    (0, 'Laminar'), (1999.999, 'Laminar'), (2000, 'Transición'),
    (3999.999, 'Transición'), (4000, 'Turbulento'),
])
def test_limites_de_regimen_solo_etiquetan(re, etiqueta):
    assert RE_LIMITE_LAMINAR == 2000
    assert RE_LIMITE_TURBULENTO == 4000
    assert clasificar_regimen(re) == etiqueta


def test_transicion_sigue_usando_colebrook_y_salto():
    r = evaluar_tramo(3000*0.001*math.pi*0.1/(4*1000), 10, 0.1, 0, 0, 0, AGUA)
    assert r.regimen == 'Transición'
    assert r.ley == 'colebrook'
    f, re = calcular_f_y_Re(r.Q, r.D, 1000, 0.001)
    assert re == r.Re
    assert f == r.f
    q2000 = 2000*0.001*math.pi*0.1/(4*1000)
    bajo, _ = calcular_f_y_Re(q2000*(1-1e-10), 0.1, 1000, 0.001)
    alto, _ = calcular_f_y_Re(q2000*(1+1e-10), 0.1, 1000, 0.001)
    assert alto > bajo


@pytest.mark.parametrize('nombre', ['a_tanque_tanque', 'b_serie_accesorios', 'c_paralelo_distinto'])
def test_evaluar_tramos_coincide_con_dorados(nombre):
    d = json.loads((GOLDEN / f'{nombre}.json').read_text(encoding='utf-8'))
    entradas = d['entrada'].get('tramos', d['entrada'].get('ramas'))
    valores = d.get('tramos', d.get('ramas'))
    assert len(entradas) == len(valores)
    for entrada, esperado in zip(entradas, valores):
        r = evaluar_tramo(esperado['Q'], entrada['L'], entrada['D'], entrada['eps'],
                          entrada['K'], entrada['LeD'], d['fluido'], id=entrada['tuberia'],
                          Q_procedencia='calculado')
        for campo in ('Q', 'area', 'v', 'Re', 'hf_total', 'hf_distribuida', 'hf_localizada'):
            assert getattr(r, campo) == pytest.approx(esperado[campo], rel=1e-12, abs=0)
        assert r.f == pytest.approx(esperado['f']['valor'], rel=1e-12, abs=0)
        assert r.ley == esperado['ley_motor']
        assert r.regimen == esperado['regimen_ui']


def test_serializacion_completa_inmutable_y_sin_redondeo():
    r = evaluar_tramo(0.007853982, 100, 0.1, 0, 2, 20, AGUA,
                      id='T1', ramal_id='R1', origen='A', destino='B',
                      Q_procedencia='calculado', D_procedencia='dato')
    a = PerdidaAccesorio('Acc1', 'T1', None, 2.0, 20.0, r.hf_localizada)
    lista = [a]
    r = replace(r, accesorios=lista)
    lista.clear()
    assert r.accesorios == (a,)
    with pytest.raises(FrozenInstanceError):
        r.Q = 0
    with pytest.raises(FrozenInstanceError):
        a.hf = 0
    salida = json.loads(json.dumps(r.to_dict(), allow_nan=False))
    assert set(salida) == {campo.name for campo in fields(ResultadoTramo)}
    assert salida['accesorios'] == [a.to_dict()]
    assert set(salida['accesorios'][0]) == {campo.name for campo in fields(PerdidaAccesorio)}
    for campo in fields(r):
        if campo.name != 'accesorios':
            assert salida[campo.name] == getattr(r, campo.name)
    assert salida['accesorios'][0]['x'] is None
    reposo = evaluar_tramo(0, 1, 0.1, 0, 0, 0, AGUA)
    assert json.loads(json.dumps(reposo.to_dict()))['f'] is None


@pytest.mark.parametrize('invalido', [float('nan'), float('inf'), -float('inf')])
def test_to_dict_rechaza_no_finitos_incluso_en_accesorios(invalido):
    r = evaluar_tramo(1e-6, 10, 0.01, 0, 0, 0, AGUA)
    with pytest.raises(ValueError, match='finito'):
        replace(r, hf_total=invalido).to_dict()
    a = PerdidaAccesorio('A1', 'T1', None, 0, 0, invalido)
    with pytest.raises(ValueError, match='finito'):
        a.to_dict()
    with pytest.raises(ValueError, match='finito'):
        replace(r, accesorios=(a,)).to_dict()


def test_fluido_con_gravedad_propia_no_muta_el_motor():
    g_original = MotorFluidos.g
    r = evaluar_tramo(1e-6, 10, 0.01, 0, 0, 0, AGUA)
    otro = evaluar_tramo(1e-6, 10, 0.01, 0, 0, 0,
                         SimpleNamespace(rho=1000, mu=0.001, g=2*AGUA['g']))
    assert otro.hf_total == r.hf_total/2
    assert otro.f == r.f
    assert MotorFluidos.g == g_original


@pytest.mark.parametrize(('campo', 'valor'), [
    ('Q', -1), ('Q', float('nan')), ('D', 0), ('L', -1), ('eps', -1),
    ('K', -1), ('LeD', -1), ('D', float('inf')),
])
def test_evaluacion_rechaza_datos_invalidos(campo, valor):
    datos = dict(Q=1e-6, L=10, D=0.01, eps=0, K=0, LeD=0, fluido=AGUA)
    datos[campo] = valor
    with pytest.raises(ValueError):
        evaluar_tramo(**datos)
