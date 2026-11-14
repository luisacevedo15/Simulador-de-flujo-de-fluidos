"""Historial privado de cada ejecución, incluidas llamadas anidadas y concurrentes."""

from contextvars import ContextVar
from copy import deepcopy
from functools import wraps

_ejecucion = ContextVar('ejecucion_hidraulica',default=None)


def registrar_iteracion(iteracion):
    historial = _ejecucion.get()
    if historial is not None:
        historial.append(dict(iteracion))


def limpiar_historial_actual():
    """Compatibilidad: limpia solo el cálculo activo, nunca un resultado previo."""
    historial = _ejecucion.get()
    if historial is not None:
        historial.clear()


def ejecucion(funcion):
    @wraps(funcion)
    def ejecutar(*args,**kwargs):
        token = None
        historial = _ejecucion.get()
        if historial is None:
            historial = []
            token = _ejecucion.set(historial)
        try:
            resultado = funcion(*args,**kwargs)
            if hasattr(resultado,'__dict__'):
                resultado.historial_iteraciones = deepcopy(historial)
            return resultado
        except ValueError as error:
            if hasattr(error,'resultado'):
                error.resultado.historial_iteraciones = deepcopy(historial)
            raise
        finally:
            if token is not None:
                _ejecucion.reset(token)
    return ejecutar
