"""Nombres de presentación; no modifica curvas ni resultados hidráulicos."""


def nombre_equipo_bomba(equipo=None, *, curva=None, indice=0, nombre_estacion=None):
    candidatos = [(equipo or {}).get('nombre'),getattr(curva,'nombre',None),nombre_estacion]
    for nombre in candidatos:
        if nombre and str(nombre).strip().casefold() not in ('npshr','npshr (m)','η'):
            return str(nombre).strip()
    return f'Bomba {indice+1}'
