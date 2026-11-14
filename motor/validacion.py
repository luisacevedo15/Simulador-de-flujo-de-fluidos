"""Dominios físicos comunes. Q es magnitud no negativa, no caudal con signo.

La dirección se devuelve aparte (Entra/Sale, j→k, orientación de la serie).
Solo los residuos de continuidad y las cargas/cotas pueden tener signo.
"""

import math


def numero(valor, nombre, *, minimo=None, estricto=False):
    if isinstance(valor,bool):
        raise ValueError(f'{nombre} debe ser un número, no un booleano.')
    try:
        convertido = float(valor)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{nombre} debe ser un número finito.") from error
    if not math.isfinite(convertido):
        raise ValueError(f"{nombre} debe ser finito; NaN e infinito no están permitidos.")
    if minimo is not None and (convertido < minimo or (estricto and convertido == minimo)):
        signo = '>' if estricto else '>='
        raise ValueError(f"{nombre} debe cumplir {signo} {minimo}.")
    return convertido


def caudal(valor, nombre='Q'):
    return numero(valor,nombre,minimo=0.0)


def fluido(rho, mu, g=9.81):
    for nombre, valor in (('rho',rho),('mu',mu),('g',g)):
        numero(valor,nombre,minimo=0.0,estricto=True)


def tramo(datos, rho, mu, g=9.81):
    fluido(rho,mu,g)
    if not isinstance(datos,dict):
        raise ValueError('Cada tramo debe ser un diccionario de datos SI.')
    segmentos = datos.get('segmentos',datos.get('sub_tramos'))
    if segmentos is not None:
        if not segmentos:
            raise ValueError('Cada ramal debe tener al menos un segmento.')
        for segmento in segmentos:
            tramo(segmento,rho,mu,g)
    else:
        if datos.get('D') == 0:
            raise ValueError('Falta un diámetro D conocido (>0). Para calcularlo indique Q y hf o altura disponible y use calcular_D.')
        for clave in ('L','D'):
            numero(datos.get(clave),clave,minimo=0.0,estricto=True)
        for clave in ('eps','K','LeD'):
            numero(datos.get(clave,0.0),clave,minimo=0.0)
    if 'H' in datos:
        numero(datos['H'],'H del tanque')
