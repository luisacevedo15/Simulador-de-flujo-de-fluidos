"""Evaluación de un tramo SI con la ley existente, independiente de PyQt."""

from collections.abc import Mapping
import math

from motor.friccion import (
    FriccionMixin, RE_LIMITE_LAMINAR, RE_LIMITE_TURBULENTO, clasificar_regimen,
)
from motor.resultados import PerdidaAccesorio, ResultadoTramo
from motor.validacion import numero


def resultado_tramo_desde_perdidas(Q, L, D, eps, K, LeD, fluido, hf_total,
                                   hf_distribuida, hf_localizada, id=None):
    """Completa un resultado histórico ya resuelto sin volver a calcular hf."""
    rho,mu,g = (numero(fluido[n],n,minimo=0,estricto=True) for n in ('rho','mu','g'))
    q = numero(Q,'Q',minimo=0)
    L,D = numero(L,'L',minimo=0,estricto=True),numero(D,'D',minimo=0,estricto=True)
    eps,K,LeD = (numero(v,n,minimo=0) for v,n in ((eps,'eps'),(K,'K'),(LeD,'LeD')))
    hf,hd,hl = (numero(v,n,minimo=0) for v,n in (
        (hf_total,'hf'),(hf_distribuida,'hf distribuida'),(hf_localizada,'hf localizada')))
    class FriccionSI(FriccionMixin):
        pass
    FriccionSI.g = g
    f,re = FriccionSI.calcular_f_y_Re(q,D,rho,mu,eps)
    v = 4*q/(math.pi*D**2)
    return ResultadoTramo(id,None,None,None,L,D,eps,K,LeD,q,'calculado','dato',
        math.pi*D**2/4,v,re,float(f) if f is not None else None,
        'reposo' if q==0 else 'laminar' if re<RE_LIMITE_LAMINAR else 'colebrook',
        clasificar_regimen(re),hd,hl,hf,())


def desglosar_accesorios_calculados(resultado, accesorios, *, g=9.81):
    """Distribuye hf localizada existente según K/LeD; no reevalúa Darcy.

    accesorios: (id, posición física, K, LeD). Solo se asigna la parte ya
    calculada a cada accesorio con el f y la velocidad del resultado.
    """
    from dataclasses import replace
    datos = tuple(accesorios)
    if not datos:
        return resultado
    pesos = [numero(k,'K',minimo=0)+(resultado.f or 0)*numero(led,'LeD',minimo=0)
             for _,_,k,led in datos]
    total = sum(pesos)
    if total==0 and resultado.hf_localizada:
        raise ValueError('No hay coeficientes para distribuir la pérdida localizada.')
    perdidas = [resultado.hf_localizada*p/total if total else 0.0 for p in pesos]
    return replace(resultado,accesorios=tuple(PerdidaAccesorio(str(id),str(resultado.id),
        x,k,led,hf) for (id,x,k,led),hf in zip(datos,perdidas)))


def evaluar_tramo(Q, L, D, eps, K, LeD, fluido, id=None, *, ramal_id=None,
                  origen=None, destino=None, Q_procedencia='dato',
                  D_procedencia='dato',
                  accesorios: tuple[PerdidaAccesorio, ...] = ()) -> ResultadoTramo:
    """Evalúa sin redondeo ni alteración del motor/elementos gráficos.

    fluido es un mapping u objeto con rho [kg/m³], mu [Pa*s] y g [m/s²].
    Los tres datos son explícitos. Q [m³/s] es magnitud; origen/destino
    identifican el sentido cuando el llamador dispone de esos datos.

    accesorios contiene desgloses ya calculados, si se conocen sus identidades;
    K/LeD son los totales del segmento y NO se les suman otra vez esos objetos.
    Sin desglose se conserva la tupla vacía, incluso con K/LeD agregados.
    """
    def dato_fluido(nombre):
        valor = fluido.get(nombre) if isinstance(fluido, Mapping) else getattr(fluido, nombre, None)
        return numero(valor, f'fluido.{nombre}', minimo=0.0, estricto=True)

    rho, mu, gravedad = (dato_fluido(nombre) for nombre in ('rho', 'mu', 'g'))
    q = numero(Q, 'Q', minimo=0.0)
    longitud = numero(L, 'L', minimo=0.0, estricto=True)
    diametro = numero(D, 'D', minimo=0.0, estricto=True)
    rugosidad = numero(eps, 'eps', minimo=0.0)
    k = numero(K, 'K', minimo=0.0)
    led = numero(LeD, 'LeD', minimo=0.0)
    for nombre, valor in (('Q_procedencia', Q_procedencia), ('D_procedencia', D_procedencia)):
        if valor not in ('dato', 'calculado'):
            raise ValueError(f'{nombre} debe ser dato o calculado.')

    # Una gravedad por evaluación, sin mutar MotorFluidos.g ni compartir estado.
    class FriccionSI(FriccionMixin):
        g = gravedad

    perdida = FriccionSI.calcular_hf(q, longitud, diametro, rho, mu, rugosidad,
        sumatoria_K=k, sumatoria_Le_D=led)
    f, re = FriccionSI.calcular_f_y_Re(q, diametro, rho, mu, rugosidad)
    area = math.pi * diametro ** 2 / 4.0
    v = 4 * q / (math.pi * diametro ** 2)
    return ResultadoTramo(
        id=id, ramal_id=ramal_id, origen=origen, destino=destino,
        L=longitud, D=diametro, eps=rugosidad, K=k, LeD=led, Q=q,
        Q_procedencia=Q_procedencia, D_procedencia=D_procedencia,
        area=area, v=v, Re=re, f=None if f is None else float(f),
        ley='reposo' if q == 0 else 'laminar' if re < RE_LIMITE_LAMINAR else 'colebrook',
        regimen=clasificar_regimen(re), hf_distribuida=float(perdida[1]),
        hf_localizada=float(perdida[2]), hf_total=float(perdida[0]),
        accesorios=accesorios,
    )
