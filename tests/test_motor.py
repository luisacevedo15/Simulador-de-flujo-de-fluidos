"""Tests para el motor de cálculo hidráulico (Simulador de Flujo de Fluidos).

Condiciones de referencia para agua:
    rho = 1000 kg/m³
    mu = 0.001 Pa·s
    g = 9.81 m/s²
"""

import math
import pytest

from motor.motor_fluidos import MotorFluidos
from motor.bombas import (
    CurvaBomba,
    combinar_serie,
    combinar_paralelo,
    punto_operacion,
    presion_vapor_agua,
)


# ==============================================================================
# 1. Régimen laminar
# ==============================================================================
def test_laminar():
    """Laminar: D=0.01 m, L=10 m, eps=0, v=0.01 m/s

    Valores esperados:
        Re = 100
        f = 0.64
        hf = 0.003261978 m
        Q = 7.853982e-7 m³/s
    """
    rho = 1000.0
    mu = 0.001
    g = 9.81
    D = 0.01
    L = 10.0
    eps = 0.0
    v = 0.01

    MotorFluidos.g = g

    # Caudal
    area = math.pi * (D ** 2) / 4.0
    Q_esperado = v * area
    assert Q_esperado == pytest.approx(7.853982e-7, rel=1e-5)

    # Reynolds
    Re = rho * v * D / mu
    assert Re == pytest.approx(100.0, rel=1e-6)

    # Factor de fricción Darcy-Weisbach
    f = MotorFluidos._factor_friccion_sustitucion(Re, eps / D)
    assert f == pytest.approx(0.64, rel=1e-6)

    # Pérdida de carga
    hf, hf_dist, hf_loc = MotorFluidos.calcular_hf(Q_esperado, L, D, rho, mu, eps)
    assert hf == pytest.approx(0.003261978, abs=1e-7)
    assert hf_dist == pytest.approx(0.003261978, abs=1e-7)
    assert hf_loc == 0.0

    # Inversiones: recuperación de Q y D
    Q_recuperado = MotorFluidos.calcular_Q(hf, L, D, rho, mu, eps)
    assert Q_recuperado == pytest.approx(Q_esperado, rel=1e-4)

    D_recuperado = MotorFluidos.calcular_D(hf, Q_esperado, L, rho, mu, eps)
    assert D_recuperado == pytest.approx(D, rel=1e-4)


def test_laminar_inversion_f2():
    """F2: Kármán es solo semilla; la inversión final recupera el caudal laminar."""
    rho = 1000.0
    mu = 0.001
    D = 0.01
    L = 10.0
    eps = 0.0
    hf = 0.003261978
    Q_esperado = 7.853982e-7

    Q_final = MotorFluidos.calcular_Q(hf, L, D, rho, mu, eps)
    assert Q_final == pytest.approx(Q_esperado, rel=1e-6)


def test_dos_tramos_serie_laminar_f4():
    """F4: resolución de tramos en serie por energía en régimen laminar."""
    rho = 1000.0
    mu = 0.001
    Q_esperado = 7.853982e-7
    hf_total = 2 * 0.003261978
    tramos = [
        {"L": 10.0, "D": 0.01, "eps": 0.0, "K": 0.0, "LeD": 0.0},
        {"L": 10.0, "D": 0.01, "eps": 0.0, "K": 0.0, "LeD": 0.0},
    ]

    res = MotorFluidos.resolver_serie_por_energia(hf_total, 0.0, tramos, rho, mu)
    assert getattr(res, "Q", None) == pytest.approx(Q_esperado, rel=1e-3)


# ==============================================================================
# 2. Régimen turbulento con accesorios
# ==============================================================================
def test_turbulento_con_accesorios():
    """Turbulento con accesorios: D=0.1, L=100, eps=0, v=1, K=2, Le/D=20

    Colebrook del profesor (0.86·ln).
    Valores esperados:
        f = 0.018312901
        hf distribuida = 0.933379 m
        hf localizada = 0.120604 m
        hf total = 1.053984 m
    """
    rho = 1000.0
    mu = 0.001
    g = 9.81
    D = 0.1
    L = 100.0
    eps = 0.0
    v = 1.0
    K = 2.0
    Le_D = 20.0

    MotorFluidos.g = g

    area = math.pi * (D ** 2) / 4.0
    Q = v * area
    Re = rho * v * D / mu
    assert Re == pytest.approx(100000.0, rel=1e-6)

    # Factor de fricción Colebrook
    f = MotorFluidos._factor_friccion_sustitucion(Re, eps / D)
    assert f == pytest.approx(0.018312901, abs=1e-7)

    # Pérdidas distribuida y localizada
    hf, hf_distribuida, hf_localizada = MotorFluidos.calcular_hf(
        Q, L, D, rho, mu, eps, sumatoria_Le_D=Le_D, sumatoria_K=K
    )
    assert hf_distribuida == pytest.approx(0.933379, abs=1e-5)
    assert hf_localizada == pytest.approx(0.120604, abs=1e-5)
    assert hf == pytest.approx(1.053984, abs=1e-5)


# ==============================================================================
# 3. Bomba individual y punto de operación
# ==============================================================================
def test_bomba_individual():
    """Bomba H=40-1000Q contra Hsistema=10+100000Q², eta=0.8

    Valores esperados:
        Q = 0.013027756 m³/s
        H = 26.972244 m
    """
    rho = 1000.0
    g = 9.81
    MotorFluidos.g = g

    # Puntos tabulados de la curva H(Q) = 40 - 1000Q
    puntos = [(0.0, 40.0, 0.8), (0.02, 20.0, 0.8), (0.04, 0.0, 0.8)]
    bomba = CurvaBomba(puntos, "lineal", "Bomba1")
    H_sistema = lambda Q: 10.0 + 100000.0 * (Q ** 2)

    res = punto_operacion(bomba, H_sistema, rho=rho, g=g)

    assert res.estado == "OK"
    assert res.Q == pytest.approx(0.013027756, abs=1e-6)
    assert res.H_total == pytest.approx(26.972244, abs=1e-5)
    assert res.eta_global == pytest.approx(0.8, abs=1e-3)


# ==============================================================================
# 4. Dos bombas en serie y en paralelo
# ==============================================================================
def test_dos_bombas_en_serie():
    """Dos bombas iguales en serie contra Hsistema=10+100000Q²

    Valores esperados:
        Q = 0.018284271 m³/s
        H = 43.431458 m
    """
    rho = 1000.0
    g = 9.81
    MotorFluidos.g = g

    puntos = [(0.0, 40.0, 0.8), (0.02, 20.0, 0.8), (0.04, 0.0, 0.8)]
    b1 = CurvaBomba(puntos, "lineal", "B1")
    b2 = CurvaBomba(puntos, "lineal", "B2")
    H_sistema = lambda Q: 10.0 + 100000.0 * (Q ** 2)

    est_serie = combinar_serie([b1, b2])
    res = punto_operacion(est_serie, H_sistema, rho=rho, g=g)

    assert res.estado == "OK"
    assert res.Q == pytest.approx(0.018284271, abs=1e-6)
    assert res.H_total == pytest.approx(43.431458, abs=1e-5)


def test_dos_bombas_en_paralelo():
    """Dos bombas iguales en paralelo contra Hsistema=10+100000Q²

    Valores esperados:
        Qtotal = 0.015 m³/s
        H = 32.5 m
    """
    rho = 1000.0
    g = 9.81
    MotorFluidos.g = g

    puntos = [(0.0, 40.0, 0.8), (0.02, 20.0, 0.8), (0.04, 0.0, 0.8)]
    b1 = CurvaBomba(puntos, "lineal", "B1")
    b2 = CurvaBomba(puntos, "lineal", "B2")
    H_sistema = lambda Q: 10.0 + 100000.0 * (Q ** 2)

    est_paralelo = combinar_paralelo([b1, b2])
    res = punto_operacion(est_paralelo, H_sistema, rho=rho, g=g)

    assert res.estado == "OK"
    assert res.Q == pytest.approx(0.015, abs=1e-6)
    assert res.H_total == pytest.approx(32.5, abs=1e-5)


# ==============================================================================
# 5. Bomba inviable por altura estática
# ==============================================================================
def test_bomba_inviable_altura_estatica():
    """Bomba inviable contra Hsistema=45+100000Q²

    Valores esperados:
        estado = NO_ALCANZA_ALTURA_ESTATICA
        Q = 0.0
    """
    puntos = [(0.0, 40.0, 0.8), (0.02, 20.0, 0.8), (0.04, 0.0, 0.8)]
    b1 = CurvaBomba(puntos, "lineal", "B1")
    H_sistema_inviable = lambda Q: 45.0 + 100000.0 * (Q ** 2)

    res = punto_operacion(b1, H_sistema_inviable, rho=1000.0, g=9.81)

    assert res.estado == "NO_ALCANZA_ALTURA_ESTATICA"
    assert res.Q == 0.0


# ==============================================================================
# 6. Regresión: Red ramificada y orden de parámetros K y Le/D
# ==============================================================================
def test_regresion_f1_red_ramificada():
    """Regresión: red ramificada con Q=0.01 m³/s, L=10 m, D=0.1 m, K=20

    Valores esperados:
        hf = 1.796617 m (con viscosidad de referencia en bomba ramificada mu=1.004e-3 Pa·s)
    Verifica que resolver_bomba_ramificada pase K y Le/D con argumentos nombrados
    a calcular_hf(), evitando el intercambio de argumentos.
    """
    tramo_bomba = {
        "H": 0.0,
        "L": 10.0,
        "D": 0.1,
        "eps": 0.0,
        "K": 20.0,
        "LeD": 0.0,
    }
    tramos_ramales = [
        {"H": 10.0, "L": 50.0, "D": 0.1, "eps": 0.0, "K": 1.0, "LeD": 0.0}
    ]
    curva_bomba = lambda Q: 50.0

    # Evaluación en resolver_bomba_ramificada en modo tanteo manual
    res = MotorFluidos.resolver_bomba_ramificada(
        curva_bomba=curva_bomba,
        tramo_bomba=tramo_bomba,
        tramos_ramales=tramos_ramales,
        Q_manual=0.01,
    )

    hf_bomba = res.tramo_bomba_resultado["hf"]
    assert hf_bomba == pytest.approx(1.796617, abs=1e-5)

    # Verificación directa de llamada nombrada a calcular_hf
    hf_directo, _, _ = MotorFluidos.calcular_hf(
        0.01, 10.0, 0.1, 1000.0, 1.004e-3, 0.0, sumatoria_Le_D=0.0, sumatoria_K=20.0
    )
    assert hf_directo == pytest.approx(1.796617, abs=1e-5)


# ==============================================================================
# 7. Comprobación calcular_hf con Q=0
# ==============================================================================
def test_calcular_hf_caudal_cero():
    """calcular_hf(Q=0) debe devolver pérdidas cero (0.0, 0.0, 0.0) sin lanzar error."""
    hf, hf_dist, hf_loc = MotorFluidos.calcular_hf(
        0, 10.0, 0.1, 1000.0, 0.001, 0.0, sumatoria_Le_D=10.0, sumatoria_K=5.0
    )
    assert hf == 0.0
    assert hf_dist == 0.0
    assert hf_loc == 0.0

    # También con argumento nombrado Q=0.0
    hf2, hf2_dist, hf2_loc = MotorFluidos.calcular_hf(
        Q=0.0, L_tub=100.0, D=0.05, rho=1000.0, mu=0.001, epsilon=1e-5
    )
    assert hf2 == 0.0
    assert hf2_dist == 0.0
    assert hf2_loc == 0.0


# ==============================================================================
# 8. Comprobación: Presión de vapor a 70 °C y verificación contra Antoine NIST
# ==============================================================================
def test_presion_vapor_70c_f9():
    """Presión de vapor de agua a 70 °C corregida a 233.7 mmHg (~31.157 kPa).

    Verificación de toda la tabla contra la ecuación de Antoine del NIST
    (A=5.0768, B=1659.793, C=-45.854, para P en bar y T en K, rango 334-363 K).
    """
    # A 70 °C exactos:
    p_70_pa = presion_vapor_agua(70.0)
    p_70_mmhg = p_70_pa / 133.322
    assert p_70_mmhg == pytest.approx(233.7, abs=0.05)
    assert p_70_pa == pytest.approx(31157.35, rel=1e-4)

    # Verificación en el rango de validez NIST (334 a 363 K, aprox. 61 a 90 °C)
    A = 5.0768
    B = 1659.793
    C = -45.854

    for temp_c in [70.0, 80.0, 90.0]:
        t_k = temp_c + 273.15
        log10_p_bar = A - (B / (t_k + C))
        p_bar_antoine = 10 ** log10_p_bar
        p_pa_antoine = p_bar_antoine * 1e5

        p_pa_tabla = presion_vapor_agua(temp_c)
        # La tabla experimental coincide con la formulación de Antoine a menos de 0.25%
        assert p_pa_tabla == pytest.approx(p_pa_antoine, rel=0.0025)


# Regresiones: una sola ley y aceptación por residuos relativos.
def _tramo(D=0.1, L=10.0, K=0.0, LeD=0.0, eps=0.0, **extras):
    return dict(D=D, L=L, K=K, LeD=LeD, eps=eps, **extras)


def _hf(Q, tramo):
    return MotorFluidos.calcular_hf(Q, tramo['L'], tramo['D'], 1000.0, 0.001,
        tramo['eps'], sumatoria_K=tramo['K'], sumatoria_Le_D=tramo['LeD'])


def _assert_balances(resultado):
    assert resultado.estado == 'OK'
    assert resultado.convergio
    assert isinstance(resultado.iteraciones, int)
    assert resultado.iteraciones >= 0
    assert math.isfinite(resultado.residuo_masa)
    assert math.isfinite(resultado.residuo_energia)
    assert resultado.residuo_masa_relativo <= 1e-8
    assert resultado.residuo_energia_relativo <= 1e-8


def test_inversion_con_K20_f2():
    t = _tramo(K=20.0)
    q = MotorFluidos.calcular_Q(1.0, t['L'], t['D'], 1000.0, 0.001, 0.0,
                               sumatoria_K=20.0)
    assert _hf(q, t)[0] == pytest.approx(1.0, rel=1e-6)
    _assert_balances(q)


@pytest.mark.parametrize('Q', [1e-6, 1e-4, 1e-3, 1e-2, 1e-1])
@pytest.mark.parametrize('K,LeD', [(0.0, 0.0), (20.0, 0.0), (0.0, 50.0), (20.0, 50.0)])
def test_ida_vuelta_caudal_f2(Q, K, LeD):
    t = _tramo(K=K, LeD=LeD)
    hf = _hf(Q, t)[0]
    recuperado = MotorFluidos.calcular_Q(hf, 10.0, 0.1, 1000.0, 0.001, 0.0,
                                        sumatoria_K=K, sumatoria_Le_D=LeD)
    assert recuperado == pytest.approx(Q, rel=1e-6, abs=0)
    assert _hf(recuperado, t)[0] == pytest.approx(hf, rel=1e-8, abs=0)
    _assert_balances(recuperado)


def test_karman_es_solo_semilla():
    semilla = MotorFluidos.calcular_Q_karman(1.0, 10.0, 0.1, 1000.0, 0.001, 0.0,
                                           sumatoria_K=20)
    assert semilla.estado == 'ESTIMACION'
    assert not semilla.convergio
    with pytest.raises(ValueError):
        semilla.verificar()


@pytest.mark.parametrize('D2', [0.01, 0.02])
def test_paralelo_laminar_carga_comun_f3(D2):
    carga = 0.003261978
    tramos = [_tramo(D=0.01), _tramo(D=D2)]
    q1 = 7.853982e-7
    q2 = q1 * (D2 / 0.01) ** 4
    total = 1.570796e-6 if D2 == 0.01 else q1 + q2
    res = MotorFluidos.resolver_paralelo(tramos, total, 1000.0, 0.001)
    assert res.hf == pytest.approx(carga, rel=1e-6)
    assert res.caudales == pytest.approx([q1, q2], rel=1e-6, abs=0)
    assert sum(res.caudales) == pytest.approx(total, rel=1e-8, abs=0)
    if D2 == 0.02:
        assert res.caudales[1] == pytest.approx(1.256637e-5, rel=1e-6, abs=0)
        Re2 = 1000.0 * 4 * res.caudales[1] / (math.pi * D2 * 0.001)
        assert Re2 == pytest.approx(800, rel=1e-6)
    for q, t in zip(res.caudales, tramos):
        assert _hf(q, t)[0] == pytest.approx(res.hf, rel=1e-8, abs=0)
    _assert_balances(res)


@pytest.mark.parametrize('K,LeD', [(0.0, 0.0), (20.0, 50.0)])
def test_paralelo_desigual_perdidas_recalculadas_f3(K, LeD):
    tramos = [_tramo(D=0.1, L=100.0, K=K), _tramo(D=0.05, L=100.0, LeD=LeD)]
    res = MotorFluidos.resolver_paralelo(tramos, 0.001, 1000.0, 0.001)
    hf1, hf2 = [_hf(q, t)[0] for q, t in zip(res.caudales, tramos)]
    assert hf1 == pytest.approx(hf2, rel=1e-6, abs=0)
    assert sum(res.caudales) == pytest.approx(0.001, rel=1e-8, abs=0)
    _assert_balances(res)


def test_serie_laminar_perdidas_reales_f4():
    tramos = [_tramo(D=0.01), _tramo(D=0.01)]
    q = 7.853982e-7
    total = sum(_hf(q, t)[0] for t in tramos)
    assert total == pytest.approx(0.006523955, rel=1e-6)
    res = MotorFluidos.resolver_serie_por_energia(0.006523955, 0.0, tramos, 1000.0, 0.001)
    assert res.Q == pytest.approx(q, rel=1e-6, abs=0)
    assert res.perdidas_tramos[0][0] == pytest.approx(res.perdidas_tramos[1][0], rel=1e-8)
    for t, p in zip(tramos, res.perdidas_tramos):
        assert p == pytest.approx(_hf(res.Q, t), rel=1e-8, abs=0)
    assert sum(p[0] for p in res.perdidas_tramos) == pytest.approx(0.006523955, rel=1e-8)
    _assert_balances(res)


def test_serie_invertida_f4():
    res = MotorFluidos.resolver_serie_por_energia(0.0, 1.0, [_tramo(), _tramo()], 1000.0, 0.001)
    assert res.estado == 'ORIENTACION_INVERTIDA'
    assert not res.convergio
    assert res.Q == 0.0
    with pytest.raises(ValueError):
        res.verificar()


@pytest.mark.parametrize('Q', [1e-6, 1e-3, 1e-1])
def test_serie_mixta_y_accesorios_sin_reescalar(Q):
    tramos = [_tramo(D=0.1, K=20), _tramo(D=0.05, L=100, LeD=50)]
    salto = sum(_hf(Q, t)[0] for t in tramos)
    res = MotorFluidos.resolver_serie_por_energia(salto, 0.0, tramos, 1000.0, 0.001)
    assert res.Q == pytest.approx(Q, rel=1e-6, abs=0)
    for t, p in zip(tramos, res.perdidas_tramos):
        assert p == pytest.approx(_hf(res.Q, t), rel=1e-8, abs=0)
    _assert_balances(res)


def test_tanteo_no_equilibrado_no_es_OK_f5():
    tramos = [_tramo(D=0.01), _tramo(D=0.01)]
    res = MotorFluidos.resolver_serie_por_energia(0.006523955, 0.0, tramos, 1000.0, 0.001,
                                                H_j_manual=0.005)
    assert res.estado == 'SIN_CONVERGENCIA'
    assert res.residuo_energia_relativo > 1e-8
    assert res.perdidas_tramos[0] == pytest.approx(_hf(res.Q, tramos[0]), rel=1e-8, abs=0)


@pytest.mark.parametrize('Q', [1e-6, 1e-2])
def test_diametro_comprueba_energia_f5(Q):
    t = _tramo(K=20, LeD=50)
    hf = _hf(Q, t)[0]
    d = MotorFluidos.calcular_D(hf, Q, 10.0, 1000.0, 0.001, 0.0,
                               sumatoria_K=20, sumatoria_Le_D=50)
    assert d == pytest.approx(0.1, rel=1e-6)
    assert _hf(Q, dict(t, D=d))[0] == pytest.approx(hf, rel=1e-8, abs=0)
    _assert_balances(d)


def test_re_limite_laminar_conservado():
    from motor.friccion import RE_LIMITE_LAMINAR
    assert RE_LIMITE_LAMINAR == 2000
    assert MotorFluidos._factor_friccion_sustitucion(1999.0, 0.0) == 64 / 1999.0
    f = MotorFluidos._factor_friccion_sustitucion(2000.0, 0.0)
    x = 1 / math.sqrt(f)
    assert x + 0.86 * math.log(2.51 * x / 2000) == pytest.approx(0.0, abs=1e-12)
    _assert_balances(f)


def test_inversion_no_acepta_salto_Re2000_f5():
    from motor.numerica import ErrorConvergencia
    q_limite = 2000 * math.pi * 0.1 * 0.001 / (4 * 1000)
    bajo = _hf(q_limite * (1 - 1e-9), _tramo())[0]
    alto = _hf(q_limite * (1 + 1e-9), _tramo())[0]
    with pytest.raises(ErrorConvergencia) as error:
        MotorFluidos.calcular_Q((bajo + alto) / 2, 10.0, 0.1, 1000.0, 0.001, 0.0)
    res = error.value.resultado
    assert res.estado == 'SIN_CONVERGENCIA'
    assert res.iteraciones > 0
    assert res.residuo_energia_relativo > 1e-8


def test_no_acepta_agotamiento_iteraciones_f5(monkeypatch):
    import motor.numerica as numerica
    monkeypatch.setattr(numerica, 'MAX_ITERACIONES', 1)
    with pytest.raises(numerica.ErrorConvergencia) as error:
        MotorFluidos.calcular_Q(1.0, 10.0, 0.1, 1000.0, 0.001, 0.0, sumatoria_K=20)
    assert error.value.resultado.estado == 'SIN_CONVERGENCIA'
    assert error.value.resultado.iteraciones == 1


def test_red_ramificada_balances_relativos_f5():
    carga = 0.003261978
    tramos = [_tramo(D=0.01, H=2 * carga, tuberia='entrada'),
              _tramo(D=0.01, H=0.0, tuberia='salida')]
    res = MotorFluidos.resolver_red_ramificada(tramos, 1000.0, 0.001)
    assert res[0] == pytest.approx(carga, rel=1e-8)
    assert res[2][0]['Q'] == pytest.approx(7.853982e-7, rel=1e-6, abs=0)
    _assert_balances(res)
    tanteo = MotorFluidos.resolver_red_ramificada(tramos, 1000.0, 0.001, H_manual=carga / 2)
    assert tanteo.estado == 'SIN_CONVERGENCIA'
    assert tanteo.residuo_masa_relativo > 1e-8


def test_doble_nudo_balances_relativos_f5():
    carga = 0.003261978
    entrada = _tramo(D=0.01, H=3 * carga, tuberia='entrada', id_nudo='j')
    salida = _tramo(D=0.01, H=0.0, tuberia='salida', id_nudo='k')
    central = _tramo(D=0.01, tuberia='central')
    res = MotorFluidos.resolver_doble_nudo([entrada], central, [salida], 1000.0, 0.001)
    assert res[0] == pytest.approx(2 * carga, rel=1e-7)
    assert res[1] == pytest.approx(carga, rel=1e-7)
    for rama in res[3]:
        assert rama['Q'] == pytest.approx(7.853982e-7, rel=1e-6, abs=0)
    _assert_balances(res)


def test_paralelo_semilla_no_cambia_solucion():
    tramos = [_tramo(D=0.1, L=100), _tramo(D=0.05, L=100)]
    base = MotorFluidos.resolver_paralelo(tramos, 0.001, 1000.0, 0.001)
    grande = MotorFluidos.resolver_paralelo(tramos, 0.001, 1000.0, 0.001, hf_inicial=10.0)
    assert grande.caudales == pytest.approx(base.caudales, rel=1e-8, abs=0)
    assert grande.hf == pytest.approx(base.hf, rel=1e-8, abs=0)
    _assert_balances(grande)


def test_paralelo_acota_aunque_un_iterado_caiga_en_salto():
    # La solución es laminar; la cota inicial atraviesa el hueco Re=2000
    # de una rama. Esa aproximación solo puede usarse para acotar.
    tramos = [_tramo(D=0.01), _tramo(D=0.02)]
    q_limite = 2000 * math.pi * 0.01 * 0.001 / (4 * 1000)
    bajo = _hf(q_limite * (1 - 1e-9), tramos[0])[0]
    alto = _hf(q_limite * (1 + 1e-9), tramos[0])[0]
    res = MotorFluidos.resolver_paralelo(tramos, 17 * 7.853982e-7, 1000.0, 0.001,
                                       hf_inicial=(bajo + alto) / 2)
    assert res.caudales[1] == pytest.approx(16 * res.caudales[0], rel=1e-8, abs=0)
    _assert_balances(res)


def test_paralelo_una_rama_y_cero_caudal():
    una = MotorFluidos.resolver_paralelo([_tramo()], 0.001, 1000.0, 0.001)
    assert una.caudales == pytest.approx([0.001], rel=1e-8, abs=0)
    _assert_balances(una)
    cero = MotorFluidos.resolver_paralelo([_tramo(), _tramo()], 0.0, 1000.0, 0.001)
    assert cero.hf == 0.0
    assert cero.caudales == [0.0, 0.0]
    _assert_balances(cero)


def test_serie_con_bomba_verifica_balance_f5():
    bomba = CurvaBomba([(0.0, 40.0, 0.8), (0.02, 20.0, 0.8), (0.04, 0.0, 0.8)], 'lineal', 'B')
    tramos = [_tramo(L=100, K=20), _tramo(D=0.05, L=20, LeD=50)]
    res = MotorFluidos.resolver_serie_por_energia(10.0, 0.0, tramos, 1000.0, 0.001, bomba=bomba)
    _assert_balances(res)
    assert res.iteraciones > 0
    assert res.resultado_bombeo.H_total == pytest.approx(
        -10 + sum(_hf(res.Q, t)[0] for t in tramos), rel=1e-8)


def test_serie_con_bomba_rechaza_balance_inconsistente_f5(monkeypatch):
    from types import SimpleNamespace
    import motor.redes as redes
    bomba = CurvaBomba([(0.0, 40.0, 0.8), (0.04, 0.0, 0.8)], 'lineal', 'B')
    monkeypatch.setattr(redes, 'punto_operacion', lambda *args, **kwargs:
        SimpleNamespace(estado='OK', Q=0.01, H_total=30.0))
    res = MotorFluidos.resolver_serie_por_energia(10.0, 0.0, [_tramo()], 1000.0, 0.001, bomba=bomba)
    assert res.estado == 'SIN_CONVERGENCIA'
    assert res.residuo_energia_relativo > 1e-8


def test_serie_invertida_no_se_acepta_con_bomba_f4():
    bomba = CurvaBomba([(0.0, 40.0, 0.8), (0.04, 0.0, 0.8)], 'lineal', 'B')
    res = MotorFluidos.resolver_serie_por_energia(0.0, 10.0, [_tramo()], 1000.0, 0.001, bomba=bomba)
    assert res.estado == 'ORIENTACION_INVERTIDA'
    assert not res.convergio


def test_serie_sin_convergencia_conserva_balance_del_candidato_f5():
    t = _tramo()
    q_limite = 2000 * math.pi * 0.1 * 0.001 / (4 * 1000)
    bajo = _hf(q_limite * (1 - 1e-9), t)[0]
    alto = _hf(q_limite * (1 + 1e-9), t)[0]
    salto = (bajo + alto) / 2
    res = MotorFluidos.resolver_serie_por_energia(salto, 0.0, [t], 1000.0, 0.001)
    assert res.estado == 'SIN_CONVERGENCIA'
    assert res.residuo_energia_relativo > 1e-8
    assert res.perdidas_tramos[0] == pytest.approx(_hf(res.Q, t), rel=1e-8, abs=0)
    assert res.error_H == pytest.approx(salto - res.perdidas_tramos[0][0], rel=1e-8)
    assert res.H_fin_calculada == pytest.approx(res.error_H, rel=1e-8)
