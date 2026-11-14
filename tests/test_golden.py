"""Regresión completa del motor frente a siete capturas de referencia."""

import json
import math
from pathlib import Path
import runpy

import pytest


CARPETA = Path(__file__).resolve().parent / 'golden'
GENERADOR = runpy.run_path(str(CARPETA / 'generar_golden.py'))
NOMBRES = (
    'a_tanque_tanque', 'b_serie_accesorios', 'c_paralelo_distinto', 'd_una_bomba',
    'e_dos_bombas_serie', 'e_dos_bombas_paralelo', 'f_ramificada_bomba',
)


def comparar(actual, esperado, ruta='$'):
    """Comparación estructural; cero exige cero y solo se omite fuentes_sha256."""
    if isinstance(esperado, dict):
        assert isinstance(actual, dict), ruta
        claves = set(esperado) - {'fuentes_sha256'}
        assert set(actual) - {'fuentes_sha256'} == claves, ruta
        for clave in sorted(claves):
            comparar(actual[clave], esperado[clave], f'{ruta}.{clave}')
    elif isinstance(esperado, list):
        assert isinstance(actual, list), ruta
        assert len(actual) == len(esperado), ruta
        for i, (a, e) in enumerate(zip(actual, esperado)):
            comparar(a, e, f'{ruta}[{i}]')
    elif isinstance(esperado, bool) or esperado is None or isinstance(esperado, str):
        assert type(actual) is type(esperado), ruta
        assert actual == esperado, ruta
    elif isinstance(esperado, (int, float)):
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool), ruta
        assert math.isfinite(actual) and math.isfinite(esperado), ruta
        assert math.isclose(actual, esperado, rel_tol=1e-12, abs_tol=0.0), (
            f'{ruta}: actual={actual!r}, dorado={esperado!r}')
    else:
        raise AssertionError(f'{ruta}: tipo inesperado {type(esperado).__name__}')


def test_hay_exactamente_siete_casos_y_siete_archivos():
    assert set(GENERADOR['CASOS']) == set(NOMBRES)
    assert {p.stem for p in CARPETA.glob('*.json')} == set(NOMBRES)


@pytest.mark.parametrize('nombre', NOMBRES)
def test_caso_contra_json_dorado(nombre):
    esperado = json.loads((CARPETA / f'{nombre}.json').read_text(encoding='utf-8'))
    # El constructor no usa generar(), archivos temporales ni resultados dorados
    # como entrada: resuelve otra vez la red y captura todo en memoria.
    actual = GENERADOR['capturar_caso'](nombre)
    comparar(actual, esperado)
