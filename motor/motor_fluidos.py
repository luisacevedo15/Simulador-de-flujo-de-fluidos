"""Motor de cálculo para el simulador de redes de tuberías.
Clase central: une los métodos de fricción (friccion.py), redes (redes.py) y bombas (bombas.py).
"""

from motor.bomba_ramificada import BombaRamificadaMixin, ResultadoBombaRamificada
from motor.bombas import (
    BombaDesglose,
    BombasMixin,
    CurvaBomba,
    CurvaEquivalente,
    CurvaParalelo,
    CurvaSerie,
    EstacionBombeo,
    EtapaBombeo,
    ResultadoBombeo,
    combinar_paralelo,
    combinar_serie,
    npsh_disponible,
    presion_vapor_agua,
    punto_operacion,
    verificar_cavitacion,
)
from motor.friccion import FriccionMixin
from motor.redes import RedesMixin, ResultadoResolucion


class MotorFluidos(FriccionMixin, RedesMixin, BombasMixin, BombaRamificadaMixin):
    """
    Motor de cálculo para el simulador de redes de tuberías.
    Módulo 1: constantes físicas y cálculo del factor de fricción de Darcy.
    Módulo 2: redes ramificadas, doble nudo y series por energía.
    Módulo 3: bombas centrífugas, curvas H-Q, punto de operación y NPSH.
    Módulo 4: bombas en redes ramificadas (balance en nudo j).
    """

    # Constante de gravedad estándar (m/s^2)
    g = 9.81

    # No hay estado numérico mutable de clase. Cada resultado posee su propio
    # historial_iteraciones; motor.ejecucion aísla incluso cálculos concurrentes.

    # Exposición de clases y utilidades de bombas
    CurvaBomba = CurvaBomba
    CurvaEquivalente = CurvaEquivalente
    CurvaSerie = CurvaSerie
    CurvaParalelo = CurvaParalelo
    EstacionBombeo = EstacionBombeo
    EtapaBombeo = EtapaBombeo
    ResultadoBombeo = ResultadoBombeo
    BombaDesglose = BombaDesglose
    ResultadoResolucion = ResultadoResolucion
    ResultadoBombaRamificada = ResultadoBombaRamificada
    combinar_serie = staticmethod(combinar_serie)
    combinar_paralelo = staticmethod(combinar_paralelo)
    punto_operacion = staticmethod(punto_operacion)
    presion_vapor_agua = staticmethod(presion_vapor_agua)
    npsh_disponible = staticmethod(npsh_disponible)
    verificar_cavitacion = staticmethod(verificar_cavitacion)

