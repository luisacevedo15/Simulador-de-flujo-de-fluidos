"""Textos/tablas de curvas; sin ajustes ni evaluaciones hidráulicas."""


def dato(curva,clave,defecto=None):
    return curva.get(clave,defecto) if isinstance(curva,dict) else getattr(curva,clave,defecto)


def usa_puntos(curvas=(),metodo=None):
    return str(metodo).lower()=='lineal' or any(str(dato(c,'metodo','')).lower()=='lineal' for c in curvas)


def puntos_tabla(curva):
    return list(zip(dato(curva,'Q',[]) or [],dato(curva,'H',[]) or []))


def puntos_total(curvas,muestras=()):
    if len(curvas)==1:
        return puntos_tabla(curvas[0])
    return [(p.Q,p.H if p.valido else None) for p in muestras]


def resumen_puntos(puntos,combinacion=False):
    prefijo = 'Combinación por puntos' if combinacion else 'Interpolación lineal'
    if not puntos:
        return f'{prefijo}; sin puntos disponibles'
    qs = [float(q) for q,_ in puntos]
    return f'{prefijo} entre {len(puntos)} puntos; Q de {min(qs)*1000:g} a {max(qs)*1000:g} L/s'


def tabla_tsv(puntos):
    return 'Q (m3/s)\tH (m)\n'+'\n'.join(f'{float(q)!r}\t{float(h)!r}' if h is not None
                                       else f'{float(q)!r}\t' for q,h in puntos)


def nota_joroba(curva):
    return 'curva con joroba; se usa la rama decreciente' if dato(curva,'tiene_joroba',False) else ''


def curvas_estacion(estacion):
    if estacion is None:
        return []
    if hasattr(estacion,'etapas'):
        return [b for etapa in estacion.etapas for b in etapa]
    return list(getattr(estacion,'bombas',[estacion]))
