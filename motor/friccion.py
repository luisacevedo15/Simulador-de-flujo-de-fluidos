"""Ley única Darcy-Weisbach + Colebrook del profesor (0.86·ln).

Los resultados conservan las operaciones de float/tuple y añaden estado,
iteraciones y residuos. ErrorConvergencia contiene el resultado fallido;
ningún solver entrega un falso OK por agotar sus iteraciones.
"""

import math

from motor.ejecucion import ejecucion, registrar_iteracion, limpiar_historial_actual
from motor.validacion import numero, tramo as validar_tramo

from motor.numerica import (
    ErrorConvergencia, ResultadoEscalar, ResultadoTupla, biseccion, relativo,
)

# Convención del profesor: Re < 2000 usa 64/Re; Re >= 2000 usa Colebrook.
# Criterio hidráulico: conservar el salto en Re=2000, sin interpolación.
# Para eps/D=0, f pasa de 0.032 (64/2000) a aproximadamente 0.050.
RE_LIMITE_LAMINAR = 2000
# Solo clasificación de presentación: no cambia la ley aplicada desde Re=2000.
RE_LIMITE_TURBULENTO = 4000


def clasificar_regimen(Re):
    """Etiquetas actuales de la UI; independientes de la elección de ley."""
    re = numero(Re, 'Re', minimo=0.0)
    if re < RE_LIMITE_LAMINAR:
        return 'Laminar'
    if re < RE_LIMITE_TURBULENTO:
        return 'Transición'
    return 'Turbulento'


def calcular_f_y_Re(Q, D, rho, mu, epsilon=0.0, registrar=False):
    """Acceso funcional a MotorFluidos.calcular_f_y_Re; devuelve (f, Re).

    Importación local para no introducir un ciclo al componer MotorFluidos.
    En reposo f es None y Re es cero.
    """
    from motor.motor_fluidos import MotorFluidos
    return MotorFluidos.calcular_f_y_Re(Q, D, rho, mu, epsilon, registrar)


class FriccionMixin:
    @classmethod
    def limpiar_iteraciones(cls):
        limpiar_historial_actual()

    @classmethod
    def _validar_tramo(cls, L, D, rho, mu, epsilon, K, LeD):
        validar_tramo(dict(L=L,D=D,eps=epsilon,K=K,LeD=LeD),rho,mu,cls.g)

    @classmethod
    @ejecucion
    def calcular_f_y_Re(cls, Q, D, rho, mu, epsilon=0.0, registrar=False):
        """Devuelve (f, Re) por la misma ruta que calcular_hf, sin otro Colebrook.

        Q es magnitud no negativa. En Q=0 no se evalúa un factor indefinido.
        El factor conserva sus metadatos; la tupla añade estado e historial.
        """
        cls._validar_tramo(1.0, D, rho, mu, epsilon, 0.0, 0.0)
        if not math.isfinite(Q) or Q < 0:
            raise ValueError("Q debe ser finito y no negativo; la orientación la define la red.")
        if Q == 0:
            return ResultadoTupla((None, 0.0))
        v = 4 * Q / (math.pi * D ** 2)
        Re = rho * v * D / mu
        f = cls._factor_friccion_sustitucion(Re, epsilon / D, registrar)
        return ResultadoTupla((f, Re), iteraciones=f.iteraciones,
                              residuo_ecuacion=f.residuo_ecuacion)

    @classmethod
    @ejecucion
    def calcular_hf(cls, Q, L_tub, D, rho, mu, epsilon, sumatoria_Le_D=0,
                    sumatoria_K=0, registrar=False):
        """Retorna (hf, hf_distribuida, hf_localizada), en m, sin reescalado."""
        cls._validar_tramo(L_tub, D, rho, mu, epsilon, sumatoria_K, sumatoria_Le_D)
        if not math.isfinite(Q) or Q < 0:
            raise ValueError("Q debe ser finito y no negativo; la orientación la define la red.")
        if Q == 0:
            return ResultadoTupla((0.0, 0.0, 0.0))
        v = 4 * Q / (math.pi * D ** 2)
        f, Re = cls.calcular_f_y_Re(Q, D, rho, mu, epsilon, registrar)
        hf_dist = f * (L_tub / D) * v ** 2 / (2 * cls.g)
        hf_loc = (f * sumatoria_Le_D + sumatoria_K) * v ** 2 / (2 * cls.g)
        hf = hf_dist + hf_loc
        return ResultadoTupla((hf, hf_dist, hf_loc), iteraciones=f.iteraciones,
                              residuo_ecuacion=f.residuo_ecuacion)

    @classmethod
    @ejecucion
    def _factor_friccion_sustitucion(cls, reynolds, rugosidad_relativa, registrar=False,
                                    *, traza=None):
        """Darcy f: 64/Re o x=-0.86·ln(eps/D/3.7+2.51·x/Re), x=1/√f.

        Se verifica el residuo de Colebrook además del cambio entre iterados.
        Los balances hidráulicos no aplican a f y se imponen como cero.
        """
        if not math.isfinite(reynolds) or reynolds <= 0 or not math.isfinite(rugosidad_relativa) or rugosidad_relativa < 0:
            raise ValueError("Re debe ser positivo y eps/D no negativo, ambos finitos.")
        if reynolds < RE_LIMITE_LAMINAR:
            return ResultadoEscalar(64 / reynolds)
        x = 1.0
        for iteracion in range(1, 101):
            x_nuevo = -0.86 * math.log(rugosidad_relativa / 3.7 + 2.51 * x / reynolds)
            if x_nuevo <= 0:
                raise ValueError("Colebrook no da un factor físico con esta rugosidad.")
            if traza is not None:
                traza.append((x, x_nuevo))
            if registrar:
                registrar_iteracion({
                    'propuesto': float(f"{x:.7g}"),
                    'obtenido': float(f"{x_nuevo:.7g}"),
                    'f_final': float(f"{1 / x_nuevo ** 2:.7g}"),
                })
            residuo = x_nuevo + 0.86 * math.log(rugosidad_relativa / 3.7 + 2.51 * x_nuevo / reynolds)
            resultado = ResultadoEscalar(1 / x_nuevo ** 2, iteraciones=iteracion,
                                         residuo_ecuacion=relativo(residuo, x_nuevo))
            if abs(x_nuevo - x) < 1e-12 and resultado.convergio:
                return resultado
            x = x_nuevo
        resultado.estado = "SIN_CONVERGENCIA"
        resultado.mensaje = "Colebrook no convergió en 100 iteraciones."
        raise ErrorConvergencia(resultado)

    @classmethod
    @ejecucion
    def iteraciones_colebrook(cls, reynolds, rugosidad_relativa):
        """Propuestos/obtenidos sin redondear de la única iteración del motor.

        El historial tradicional a siete cifras y todos los resultados existentes
        se mantienen. La traza completa permite auditar las fórmulas de Excel.
        """
        numero(reynolds, 'Re', minimo=0.0)
        numero(rugosidad_relativa, 'eps/D', minimo=0.0)
        if reynolds == 0:
            return ResultadoTupla(([0.0], [0.0]))
        pasos = []
        f = cls._factor_friccion_sustitucion(reynolds, rugosidad_relativa,
                                            registrar=True, traza=pasos)
        if not pasos:
            x = math.sqrt(reynolds / 64)
            pasos = [(x, x)]
        return ResultadoTupla(([p[0] for p in pasos], [p[1] for p in pasos]),
                              iteraciones=f.iteraciones, residuo_ecuacion=f.residuo_ecuacion)

    @classmethod
    @ejecucion
    def calcular_Q(cls, hf_objetivo, L_tub, D, rho, mu, epsilon,
                   sumatoria_K=0.0, sumatoria_Le_D=0.0):
        """Invierte hf(Q) por bisección con K y Le/D y f real, en ambos regímenes.

        Kármán es únicamente la semilla. hf=0 retorna Q=0. La convergencia
        depende del residuo de energía, nunca solo del ancho del intervalo.
        """
        cls._validar_tramo(L_tub, D, rho, mu, epsilon, sumatoria_K, sumatoria_Le_D)
        if not math.isfinite(hf_objetivo) or hf_objetivo < 0:
            raise ValueError("hf debe ser finita y no negativa.")
        if L_tub / D + sumatoria_Le_D + sumatoria_K <= 0:
            raise ValueError("No se puede invertir un tramo sin resistencia.")
        if hf_objetivo == 0:
            resultado = ResultadoEscalar(0.0)
            resultado.direccion = 'Según la orientación declarada del tramo'
            return resultado

        def perdida(q):
            return cls.calcular_hf(q, L_tub, D, rho, mu, epsilon,
                                  sumatoria_Le_D=sumatoria_Le_D, sumatoria_K=sumatoria_K)[0]

        semilla = cls.calcular_Q_karman(hf_objetivo, L_tub, D, rho, mu, epsilon,
                                       sumatoria_K, sumatoria_Le_D)
        superior = max(float(semilla), 1e-30)
        for expansion in range(201):
            if perdida(superior) >= hf_objetivo:
                break
            superior *= 2
        else:
            raise ErrorConvergencia(ResultadoEscalar(superior, estado="SIN_CONVERGENCIA",
                iteraciones=200, mensaje="No se pudo acotar el caudal.",
                residuo_energia=perdida(superior) - hf_objetivo, escala_energia=hf_objetivo))
        try:
            resultado = biseccion(lambda q: perdida(q) - hf_objetivo, 0.0, superior, hf_objetivo)
        except ErrorConvergencia as error:
            Re = 4 * rho * float(error.resultado) / (math.pi * D * mu)
            error.resultado.salto_regimen = abs(Re / RE_LIMITE_LAMINAR - 1) < 1e-10
            raise
        resultado.iteraciones += expansion
        resultado.direccion = 'Según la orientación declarada del tramo'
        return resultado.verificar()

    @classmethod
    @ejecucion
    def calcular_Q_karman(cls, hf, L_tub, D, rho, mu, epsilon,
                          sumatoria_K=0.0, sumatoria_Le_D=0.0):
        """Estimación inicial, marcada ESTIMACION; no es un caudal final.

        Semilla laminar a bajo Re y Kármán para estimar f a alto Re. K entra
        directamente, sin convertirlo a Le/D mediante un factor fijo.
        calcular_Q corrige siempre con la ley real.
        """
        cls._validar_tramo(L_tub, D, rho, mu, epsilon, sumatoria_K, sumatoria_Le_D)
        if not math.isfinite(hf) or hf < 0:
            raise ValueError("hf debe ser finita y no negativa.")
        longitud = L_tub / D + sumatoria_Le_D
        if longitud + sumatoria_K <= 0:
            raise ValueError("Se requiere resistencia positiva.")
        a = sumatoria_K / (2 * cls.g)
        b = 32 * mu * longitud / (rho * D * cls.g)
        v = 0.0 if hf == 0 else 2 * hf / (b + math.sqrt(b * b + 4 * a * hf))
        if rho * v * D / mu >= RE_LIMITE_LAMINAR and longitud > 0:
            Ka = D * rho / mu * math.sqrt(2 * cls.g * hf / longitud)
            x = -0.86 * math.log(epsilon / D / 3.7 + 2.51 / Ka)
            if x > 0:
                v = math.sqrt(2 * cls.g * hf / (longitud / x ** 2 + sumatoria_K))
        q = v * math.pi * D ** 2 / 4
        real = cls.calcular_hf(q, L_tub, D, rho, mu, epsilon,
                               sumatoria_Le_D=sumatoria_Le_D, sumatoria_K=sumatoria_K)[0]
        return ResultadoEscalar(q, estado="ESTIMACION", residuo_energia=real - hf,
                                escala_energia=hf, mensaje="Semilla para calcular_Q; no es una solución verificada.")

    @classmethod
    @ejecucion
    def calcular_D(cls, hf_objetivo, Q, L_tub, rho, mu, epsilon,
                   sumatoria_K=0.0, sumatoria_Le_D=0.0):
        """Invierte hf(D) y comprueba la energía real, incluidos K y Le/D."""
        cls._validar_tramo(L_tub, 1.0, rho, mu, epsilon, sumatoria_K, sumatoria_Le_D)
        if not math.isfinite(hf_objetivo) or not math.isfinite(Q) or min(hf_objetivo, Q) <= 0:
            raise ValueError("hf y Q deben ser positivos y finitos.")
        if L_tub + sumatoria_K + sumatoria_Le_D <= 0:
            raise ValueError("Se requiere resistencia positiva.")

        def residual(d):
            return hf_objetivo - cls.calcular_hf(Q, L_tub, d, rho, mu, epsilon,
                sumatoria_Le_D=sumatoria_Le_D, sumatoria_K=sumatoria_K)[0]

        inferior = superior = max(0.1, epsilon)
        for expansion in range(200):
            if residual(inferior) <= 0 and residual(superior) >= 0:
                break
            if residual(inferior) > 0:
                inferior /= 2
            if residual(superior) < 0:
                superior *= 2
        else:
            raise ErrorConvergencia(ResultadoEscalar(superior, estado="SIN_CONVERGENCIA",
                iteraciones=200, mensaje="No se pudo acotar el diámetro.",
                residuo_energia=-residual(superior), escala_energia=hf_objetivo))
        resultado = biseccion(residual, inferior, superior, hf_objetivo)
        resultado.residuo_energia *= -1
        resultado.iteraciones += expansion
        return resultado.verificar()
