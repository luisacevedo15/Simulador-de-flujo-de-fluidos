"""Resultados compatibles con float/tuple y verificación relativa de los balances.

Los residuos absolutos usan m³/s (masa) y m (energía); los relativos se
normalizan por el caudal/carga del problema, nunca por un mínimo de 1 SI.
En cálculos que imponen continuidad por construcción, el residuo de masa es 0.
"""

import math
from motor.validacion import numero

TOLERANCIA_RELATIVA = 1e-8
TOLERANCIA_INTERNA = 1e-11  # margen para solvers anidados
MAX_ITERACIONES = 200


def relativo(residuo, escala):
    return abs(residuo) / abs(escala) if escala else (0.0 if residuo == 0 else math.inf)


class Metadatos:
    @property
    def convergio(self):
        return self.estado == "OK"

    def verificar(self):
        """Impide utilizar como solución una estimación o un balance fallido."""
        if not self.convergio:
            raise ErrorConvergencia(self)
        return self

    def get(self, key, default=None):
        return getattr(self, key, default)

    def balances(self, iteraciones=0, residuo_masa=0.0, residuo_energia=0.0,
                 escala_masa=0.0, escala_energia=0.0, estado="OK", mensaje="",
                 residuo_ecuacion=0.0):
        self.iteraciones = iteraciones
        self.historial_iteraciones = []
        self.residuo_masa = float(residuo_masa)
        self.residuo_energia = float(residuo_energia)
        self.residuo_masa_relativo = relativo(residuo_masa, escala_masa)
        self.residuo_energia_relativo = relativo(residuo_energia, escala_energia)
        self.residuo_ecuacion = abs(residuo_ecuacion)
        self.estado = estado
        if estado == "OK" and (not all(math.isfinite(r) for r in (
                self.residuo_masa_relativo, self.residuo_energia_relativo,
                self.residuo_ecuacion)) or max(self.residuo_masa_relativo,
                self.residuo_energia_relativo, self.residuo_ecuacion) > TOLERANCIA_RELATIVA):
            self.estado = "SIN_CONVERGENCIA"
        self.mensaje = mensaje or ("Balances verificados." if self.convergio else
                                  "No se cumple la tolerancia relativa de 1e-8.")
        return self


class ResultadoEscalar(float, Metadatos):
    def __new__(cls, valor, **metadatos):
        return float.__new__(cls, valor).balances(**metadatos)


class ResultadoTupla(tuple, Metadatos):
    def __new__(cls, valores, **metadatos):
        return tuple.__new__(cls, valores).balances(**metadatos)

    def __getitem__(self, key):
        return getattr(self, key) if isinstance(key, str) else super().__getitem__(key)


class ErrorConvergencia(ValueError):
    def __init__(self, resultado):
        self.resultado = resultado
        super().__init__(resultado.mensaje)


def biseccion(funcion, inferior, superior, escala, *, tolerancia=TOLERANCIA_INTERNA):
    """Raíz de una función creciente; solo acepta convergencia por residuo.

    Un intervalo pequeño no implica convergencia (hay un salto en Re=2000).
    El llamador debe aportar un intervalo que encierre el cero.
    """
    for nombre, valor in (('límite inferior',inferior),('límite superior',superior),('escala',escala)):
        numero(valor,nombre)
    numero(tolerancia,'tolerancia',minimo=0,estricto=True)
    if inferior > superior:
        raise ValueError('Los límites de bisección están invertidos.')
    fa, fb = numero(funcion(inferior),'residuo inferior'), numero(funcion(superior),'residuo superior')
    for extremo, valor in ((inferior, fa), (superior, fb)):
        if relativo(valor, escala) <= tolerancia:
            return ResultadoEscalar(extremo, residuo_energia=valor, escala_energia=escala)
    if fa > 0 or fb < 0:
        raise ValueError("El intervalo de bisección no encierra una raíz.")
    for iteracion in range(1, MAX_ITERACIONES + 1):
        medio = (inferior + superior) / 2
        valor = numero(funcion(medio),'residuo de bisección')
        resultado = ResultadoEscalar(medio, iteraciones=iteracion,
                                    residuo_energia=valor, escala_energia=escala)
        if relativo(valor, escala) <= tolerancia:
            return resultado
        if medio == inferior or medio == superior:
            break
        if valor < 0:
            inferior = medio
        else:
            superior = medio
    resultado.estado = "SIN_CONVERGENCIA"
    resultado.mensaje = "La bisección no alcanza el residuo exigido; revise el salto en Re=2000."
    raise ErrorConvergencia(resultado)
