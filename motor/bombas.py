"""Módulo de cálculo de bombas centrífugas: curvas H-Q, eficiencia, NPSH, estaciones y combinaciones.

Puro cálculo matemático e hidráulico en unidades SI (m, m³/s, Pa, kg/m³), sin dependencias de GUI.
"""

from dataclasses import dataclass, field
import math
import numpy as np
import warnings

from motor.ejecucion import ejecucion
from motor.validacion import numero, caudal, fluido as validar_fluido, tramo as validar_tramo
from motor.numerica import Metadatos, relativo
from motor.resultados import ResultadoBomba, ResultadoEstacion


class CallableList(list):
    """
    Lista que además es invocable como función.
    Permite acceso como lista (len, indexación, iteración en UI y gráficos)
    y como método H(Q) / eta(Q) para cumplir los requerimientos de cálculo.
    """

    def __init__(self, items, func):
        super().__init__(items)
        self._func = func

    def __call__(self, *args, **kwargs):
        return self._func(*args, **kwargs)


@dataclass
class BombaDesglose:
    """Desglose de operación para una bomba individual dentro de una estación de bombeo."""
    id: any
    etapa: int
    Q_i: float
    H_i: float
    eta_i: float | None
    BHP_i: float | None
    activa: bool
    P_hidraulica: float = 0.0
    npsh_d: float | None = None
    npsh_r: float | None = None
    cavitacion: str | None = None

    def __getitem__(self, key):
        if key == "bomba":
            return self.id
        if key == "Q":
            return self.Q_i
        if key == "H":
            return self.H_i
        if key == "eta":
            return self.eta_i
        if key == "potencia_hidraulica":
            return self.P_hidraulica
        if key == "potencia_freno":
            return self.BHP_i
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


@dataclass
class ResultadoBombeo(Metadatos):
    """Resultado del cálculo del punto de operación de una estación de bombeo o bomba individual."""
    estado: str
    mensaje: str
    Q: float
    H_total: float
    P_hidraulica: float
    BHP_total: float | None
    eta_global: float | None
    desglose: list[BombaDesglose] = field(default_factory=list)
    direccion: str = 'Aspiración → descarga'
    historial_iteraciones: list = field(default_factory=list)
    iteraciones: int = 0
    historial: list = field(default_factory=list)

    def __post_init__(self):
        self.balances(iteraciones=self.iteraciones, estado=self.estado, mensaje=self.mensaje)

    @property
    def convergio(self) -> bool:
        """Compatibilidad con la interfaz anterior."""
        return self.estado == "OK"

    @property
    def H(self) -> float:
        """Compatibilidad con res['H']."""
        return self.H_total

    @property
    def eta(self) -> float | None:
        """Compatibilidad con res['eta']."""
        return self.eta_global

    def __getitem__(self, key):
        if key == "convergio":
            return self.convergio
        if key == "H":
            return self.H_total
        if key == "eta":
            return self.eta_global
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        return hasattr(self, key) or key in ("convergio", "H", "eta")


class CurvaBomba:
    """
    Representa la curva característica de una bomba centrífuga real.

    Soporta dos formas de inicialización:
    1) CurvaBomba(puntos): puntos = lista de (Q, H, eta) en SI, con eta en [0, 1].
    2) CurvaBomba(nombre, Q, H, eta=None, npsh_r=None, modo="interpolacion") para compatibilidad.
    """

    def __init__(self, *args, **kwargs):
        self.valida = True
        self.estado = 'OK'
        self.mensaje = 'Curva válida.'
        self.advertencias = []
        self.fuera_de_rango = False
        self.tiene_joroba = False
        self.Q_vertice = 0.0

        puntos = kwargs.get("puntos", None)
        nombre = kwargs.get("nombre", None)
        Q = kwargs.get("Q", None)
        H = kwargs.get("H", None)
        eta = kwargs.get("eta", None)
        npsh_r = kwargs.get("npsh_r", None)
        modo = kwargs.get("modo", None)
        metodo = kwargs.get("metodo", None)

        if len(args) == 1 and puntos is None and Q is None:
            # Caso 1: CurvaBomba(puntos)
            puntos = args[0]
            if modo is None and metodo is None:
                modo = "ajuste"
            if nombre is None:
                nombre = "Bomba"
        elif len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], (list, tuple)) and (
            len(args[1]) > 0 and isinstance(args[1][0], (list, tuple, dict))
        ):
            # Caso: CurvaBomba("Nombre", puntos)
            nombre = args[0]
            puntos = args[1]
            if modo is None and metodo is None:
                modo = "ajuste"
        elif len(args) >= 2 and isinstance(args[0], (list, tuple)) and (
            len(args[0]) > 0 and isinstance(args[0][0], (list, tuple, dict))
        ) and isinstance(args[1], str):
            # Caso: CurvaBomba(puntos, "lineal" / "cuadratico" / nombre)
            puntos = args[0]
            if args[1] in ("cuadratico", "lineal", "ajuste", "interpolacion"):
                if metodo is None:
                    metodo = args[1]
            else:
                nombre = args[1]
            if len(args) > 2 and isinstance(args[2], str):
                if args[2] in ("cuadratico", "lineal", "ajuste", "interpolacion") and metodo is None:
                    metodo = args[2]
                elif nombre is None:
                    nombre = args[2]
            if modo is None and metodo is None:
                modo = "ajuste"
        elif len(args) >= 2 and not (
            isinstance(args[0], (list, tuple)) and len(args[0]) > 0 and isinstance(args[0][0], (list, tuple, dict))
        ):
            # Caso 2 tradicional: CurvaBomba(nombre, Q, H, eta=None, npsh_r=None, modo="interpolacion")
            nombre = args[0]
            Q = args[1]
            H = args[2] if len(args) > 2 else H
            eta = args[3] if len(args) > 3 else eta
            npsh_r = args[4] if len(args) > 4 else npsh_r
            if len(args) > 5:
                modo = args[5]

        if puntos is not None:
            if len(puntos) < 2:
                raise ValueError("Se requieren al menos 2 puntos para definir la curva de la bomba.")
            Q = []
            H = []
            eta_list = []
            tiene_eta_en_puntos = False
            for pt in puntos:
                if isinstance(pt, dict):
                    Q.append(float(pt["Q"]))
                    H.append(float(pt["H"]))
                    if "eta" in pt and pt["eta"] is not None:
                        eta_list.append(float(pt["eta"]))
                        tiene_eta_en_puntos = True
                    else:
                        eta_list.append(None)
                elif isinstance(pt, (list, tuple)):
                    Q.append(float(pt[0]))
                    H.append(float(pt[1]))
                    if len(pt) >= 3 and pt[2] is not None:
                        eta_list.append(float(pt[2]))
                        tiene_eta_en_puntos = True
                    else:
                        eta_list.append(None)
                else:
                    raise ValueError(f"Punto no reconocido: {pt}")
            if tiene_eta_en_puntos and eta is None:
                eta = eta_list

        if nombre is None:
            nombre = "Bomba"
        if metodo is not None:
            m_norm = str(metodo).strip().lower()
            if m_norm in ("cuadratico", "cuadrático", "ajuste"):
                modo = "ajuste"
            elif m_norm in ("lineal", "interpolacion", "interpolación"):
                modo = "interpolacion"
            else:
                raise ValueError("El método debe ser 'cuadratico' o 'lineal'.")
        if modo is None:
            modo = "interpolacion"
        else:
            m_norm = str(modo).strip().lower()
            if m_norm in ("cuadratico", "cuadrático", "ajuste"):
                modo = "ajuste"
            elif m_norm in ("lineal", "interpolacion", "interpolación"):
                modo = "interpolacion"

        if Q is None or H is None:
            raise ValueError("Se requieren listas de Q y H o lista de puntos.")
        if len(Q) < 2:
            raise ValueError("Se requieren al menos 2 puntos para definir la curva de la bomba.")
        if len(Q) != len(H):
            raise ValueError("Las listas de Q y H deben tener la misma longitud.")
        if modo not in ("interpolacion", "ajuste"):
            raise ValueError("El modo debe ser 'interpolacion' o 'ajuste'.")
        for valor in Q:
            caudal(valor,'Q de la curva')
        for valor in H:
            numero(valor,'H de la curva',minimo=0)
        for nombre, valores, maximo in (('η',eta,100.0),('NPSHr',npsh_r,None)):
            if valores is not None:
                if len(valores) != len(Q):
                    raise ValueError(f'{nombre} debe tener la misma longitud que Q.')
                for valor in valores:
                    if valor is not None:
                        numero(valor,nombre,minimo=0)
                        if maximo is not None and float(valor) > maximo:
                            raise ValueError('η debe estar entre 0 y 1, o entre 0 y 100 en porcentaje.')

        self.nombre = str(nombre)
        self._modo = modo

        # Detección de disponibilidad completa de eficiencia y NPSHr
        self.tiene_eficiencia = bool(
            eta is not None and len(eta) == len(Q) and all(e is not None for e in eta)
        )
        self.tiene_npshr = bool(
            npsh_r is not None and len(npsh_r) == len(Q) and all(nr is not None for nr in npsh_r)
        )

        # Ordenar internamente por Q ascendente
        indices = sorted(range(len(Q)), key=lambda idx: float(Q[idx]))
        self.Q = [float(Q[i]) for i in indices]
        H_pts = [float(H[i]) for i in indices]

        if self.tiene_eficiencia:
            self.eta_raw = [float(eta[i]) for i in indices]
            es_porcentaje = any(e > 1.0 for e in self.eta_raw)
            eta_pts = [
                max(0.0, min(1.0, e / 100.0 if es_porcentaje else e))
                for e in self.eta_raw
            ]
        else:
            self.eta_raw = None
            eta_pts = None

        if self.tiene_npshr:
            self.npsh_r = [float(npsh_r[i]) for i in indices]
        else:
            self.npsh_r = None

        # Validar que no haya caudales Q repetidos
        for i in range(len(self.Q) - 1):
            if abs(self.Q[i + 1] - self.Q[i]) < 1e-12:
                raise ValueError(f"No se permiten caudales Q repetidos (Q = {self.Q[i]} m³/s).")

        # Ajuste polinómico de grado 2 para H(Q): H = a·Q² + b·Q + c
        self.poly_a = 0.0
        self.poly_b = 0.0
        self.poly_c = 0.0
        self.coef_a = 0.0
        self.coef_b = 0.0
        self.coef_c = 0.0
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                if len(self.Q) >= 3:
                    a_quad, b_lin, c_const = np.polyfit(self.Q, H_pts, 2)
                else:
                    b_lin, c_const = np.polyfit(self.Q, H_pts, 1)
                    a_quad = 0.0
            for valor in (a_quad,b_lin,c_const):
                numero(valor,'Coeficiente del ajuste H(Q)')
            self.poly_a = float(a_quad)
            self.poly_b = float(b_lin)
            self.poly_c = float(c_const)
            self.coef_a = float(c_const)
            self.coef_b = float(b_lin)
            self.coef_c = float(a_quad)
        except Exception as error:
            self.valida, self.estado = False, 'CURVA_INVALIDA'
            self.mensaje = f'No se pudo ajustar H(Q) de {self.nombre}: {error}'

        # Ajuste polinómico de grado 2 para eta(Q): eta = a·Q² + b·Q + c (limitada a [0, 1])
        self.eta_poly_a = 0.0
        self.eta_poly_b = 0.0
        self.eta_poly_c = 0.0
        if self.tiene_eficiencia and eta_pts is not None:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error')
                    if len(self.Q) >= 3:
                        ea, eb, ec = np.polyfit(self.Q, eta_pts, 2)
                    else:
                        eb, ec = np.polyfit(self.Q, eta_pts, 1)
                        ea = 0.0
                for valor in (ea,eb,ec):
                    numero(valor,'Coeficiente del ajuste η(Q)')
                self.eta_poly_a = float(ea)
                self.eta_poly_b = float(eb)
                self.eta_poly_c = float(ec)
            except Exception as error:
                self.valida, self.estado = False, 'CURVA_INVALIDA'
                self.mensaje = f'No se pudo ajustar η(Q) de {self.nombre}: {error}'

        # Enlazar H y eta como CallableList para compatibilidad total
        self._H_pts = H_pts
        self._eta_pts = eta_pts
        self.H = CallableList(H_pts, self.H_de_Q)
        if eta_pts is not None:
            self.eta = CallableList(eta_pts, self.eta_de_Q)
        else:
            self.eta = None
        self._actualizar_error_y_joroba()
        if not self.valida:
            self.advertencias.append(self.mensaje)

    @property
    def modo(self):
        return self._modo

    @modo.setter
    def modo(self, val):
        m_norm = str(val).strip().lower()
        if m_norm in ("cuadratico", "cuadrático", "ajuste"):
            self._modo = "ajuste"
        elif m_norm in ("lineal", "interpolacion", "interpolación"):
            self._modo = "interpolacion"
        else:
            raise ValueError("El modo debe ser 'interpolacion' o 'ajuste' ('lineal' o 'cuadratico').")
        if hasattr(self, "_H_pts"):
            self._actualizar_error_y_joroba()

    @property
    def metodo(self):
        return "cuadratico" if self._modo == "ajuste" else "lineal"

    @metodo.setter
    def metodo(self, val):
        m_norm = str(val).strip().lower()
        if m_norm in ("cuadratico", "cuadrático", "ajuste"):
            self._modo = "ajuste"
        elif m_norm in ("lineal", "interpolacion", "interpolación"):
            self._modo = "interpolacion"
        else:
            raise ValueError("El método debe ser 'cuadratico' o 'lineal'.")
        if hasattr(self, "_H_pts"):
            self._actualizar_error_y_joroba()

    @property
    def error_max_ajuste(self) -> float:
        """Máximo |H_ajuste - H_tabla| sobre los puntos de la tabla (solo en cuadratico) [m]."""
        if self.metodo != "cuadratico":
            return 0.0
        if not hasattr(self, "_H_pts") or not self._H_pts:
            return 0.0
        return float(
            max(
                abs((self.poly_a * (q ** 2) + self.poly_b * q + self.poly_c) - h)
                for q, h in zip(self.Q, self._H_pts)
            )
        )

    def _actualizar_error_y_joroba(self):
        self.advertencias = []
        self.tiene_joroba = False
        self.Q_vertice = 0.0
        H_pts = self._H_pts
        if self._modo == "ajuste" and self.poly_a < -1e-12 and self.poly_b > 1e-9:
            q_v = -self.poly_b / (2.0 * self.poly_a)
            if 0.0 < q_v < self.Q[-1]:
                self.tiene_joroba = True
                self.Q_vertice = float(q_v)
                self.advertencias.append(
                    f"El ajuste tiene joroba (H crece hasta Q={q_v:.5f} m³/s). "
                    f"Se utiliza únicamente la rama decreciente a partir de Q={q_v:.5f} m³/s."
                )
        elif self._modo == "interpolacion":
            idx_max = int(np.argmax(H_pts))
            if idx_max > 0:
                self.tiene_joroba = True
                self.Q_vertice = float(self.Q[idx_max])
                self.advertencias.append(
                    f"La curva tiene joroba (H crece hasta Q={self.Q_vertice:.5f} m³/s). "
                    f"Se utiliza únicamente la rama decreciente a partir de Q={self.Q_vertice:.5f} m³/s."
                )

    def ecuacion_texto(self):
        """Devuelve la ecuación cuadrática ajustada H_b(Q) = a·Q² + b·Q + c como texto."""
        a = self.poly_a
        b = self.poly_b
        c = self.poly_c
        sig_b = "-" if b < 0 else "+"
        sig_c = "-" if c < 0 else "+"
        return f"H_b(Q) = {a:.2f}·Q² {sig_b} {abs(b):.2f}·Q {sig_c} {abs(c):.2f}"

    @property
    def Q_max(self):
        """Caudal máximo de la tabla [m³/s]."""
        return float(self.Q[-1])

    @property
    def Q_min(self):
        return float(self.Q[0])

    def caudal_en_dominio(self, Q):
        return self.Q_min <= float(Q) <= self.Q_max

    @property
    def H_cierre(self):
        """Carga manométrica a caudal cero H(Q=0) [m]."""
        if self._modo == "interpolacion":
            return float(self.H[0])
        return float(self.H_de_Q(0.0))

    def H_de_Q(self, Q):
        """
        Altura manométrica que entrega la bomba para un caudal Q dado [m].
        """
        caudal(Q)
        if not self.valida:
            raise ValueError(self.mensaje)
        Q = caudal(Q)
        self.fuera_de_rango = not self.caudal_en_dominio(Q)
        if self.fuera_de_rango:
            return float(self.H[0] if Q < self.Q_min else self.H[-1])
        if self._modo == "ajuste":
            h = self.poly_a * (Q ** 2) + self.poly_b * Q + self.poly_c
            return max(0.0, float(h))

        # Modo interpolación lineal por tramos (sin extrapolación)
        if Q < self.Q[0] - 1e-12:
            self.fuera_de_rango = True
            return float(self.H[0])
        if Q > self.Q[-1] + 1e-12:
            self.fuera_de_rango = True
            return float(self.H[-1])

        self.fuera_de_rango = False
        if Q <= self.Q[0]:
            return float(self.H[0])
        if Q >= self.Q[-1]:
            return float(self.H[-1])

        # Búsqueda de intervalo
        for i in range(len(self.Q) - 1):
            q0, q1 = self.Q[i], self.Q[i + 1]
            if q0 <= Q <= q1:
                t = (Q - q0) / (q1 - q0) if q1 > q0 else 0.0
                return float(self.H[i] + t * (self.H[i + 1] - self.H[i]))

        return float(self.H[-1])

    def eta_de_Q(self, Q):
        """
        Eficiencia en fracción (0 a 1), limitada a [0, 1].
        """
        caudal(Q)
        if not self.valida:
            raise ValueError(self.mensaje)
        if not self.tiene_eficiencia or self.eta is None:
            return None

        Q = caudal(Q)
        if self._modo == "ajuste":
            val = self.eta_poly_a * (Q ** 2) + self.eta_poly_b * Q + self.eta_poly_c
            return max(0.0, min(1.0, float(val)))

        # Modo interpolación lineal por tramos
        if Q < self.Q[0] - 1e-12:
            self.fuera_de_rango = True
            val = self.eta[0]
        elif Q > self.Q[-1] + 1e-12:
            self.fuera_de_rango = True
            val = self.eta[-1]
        elif Q <= self.Q[0]:
            val = self.eta[0]
        elif Q >= self.Q[-1]:
            val = self.eta[-1]
        else:
            val = self.eta[-1]
            for i in range(len(self.Q) - 1):
                q0, q1 = self.Q[i], self.Q[i + 1]
                if q0 <= Q <= q1:
                    t = (Q - q0) / (q1 - q0) if q1 > q0 else 0.0
                    val = self.eta[i] + t * (self.eta[i + 1] - self.eta[i])
                    break

        return max(0.0, min(1.0, float(val)))

    def Q_de_H(self, H):
        """
        Caudal que da la bomba a una altura dada [m³/s].
        En modo cuadratico: inversa por bisección sobre [0, Q_max] (o sobre la rama decreciente si tiene joroba).
        En modo lineal: inversa exacta por tramos (H decreciente).
        Si H >= H_cierre devuelve 0 (válvula check: nunca negativo).
        Si H <= H(Q_max) devuelve Q_max y marca fuera_de_rango = True.
        """
        numero(H,'H de la bomba',minimo=0)
        if not self.valida:
            raise ValueError(self.mensaje)
        H = numero(H,'H de la bomba',minimo=0)
        h_cierre = self.H_cierre
        if H >= h_cierre:
            self.fuera_de_rango = False
            return 0.0

        h_qmax = self.H_de_Q(self.Q_max)
        if H < h_qmax:
            self.fuera_de_rango = True
            return float(self.Q_max)
        if H == h_qmax:
            if self._modo == "ajuste":
                self.fuera_de_rango = True
            else:
                self.fuera_de_rango = False
            return float(self.Q_max)

        self.fuera_de_rango = False
        if self._modo == "interpolacion":
            idx_inicio = 0
            if self.tiene_joroba:
                idx_inicio = int(np.argmax(self._H_pts))
            for i in range(idx_inicio, len(self.Q) - 1):
                h0, h1 = self._H_pts[i], self._H_pts[i + 1]
                q0, q1 = self.Q[i], self.Q[i + 1]
                if h0 >= H >= h1:
                    if abs(h0 - h1) < 1e-15:
                        return float(q0)
                    t = (h0 - H) / (h0 - h1)
                    return float(q0 + t * (q1 - q0))

        qa = float(self.Q_vertice if self.tiene_joroba else 0.0)
        qb = float(self.Q_max)

        for _ in range(60):
            qm = (qa + qb) / 2.0
            hm = self.H_de_Q(qm)
            if hm > H:
                qa = qm
            else:
                qb = qm

        return float((qa + qb) / 2.0)

    def npsh_r_de_Q(self, Q):
        caudal(Q)
        if not self.valida:
            raise ValueError(self.mensaje)
        """NPSH requerido interpolado linealmente [m], o None si no hay datos."""
        if not self.tiene_npshr or self.npsh_r is None:
            return None

        Q = caudal(Q)
        if Q <= self.Q[0]:
            return float(self.npsh_r[0])
        if Q >= self.Q[-1]:
            return float(self.npsh_r[-1])

        for i in range(len(self.Q) - 1):
            q0, q1 = self.Q[i], self.Q[i + 1]
            if q0 <= Q <= q1:
                t = (Q - q0) / (q1 - q0) if q1 > q0 else 0.0
                return float(self.npsh_r[i] + t * (self.npsh_r[i + 1] - self.npsh_r[i]))

        return float(self.npsh_r[-1])

    def potencia_hidraulica(self, Q, H, rho=1000.0, g=9.81):
        """
        Potencia hidráulica entregada al fluido [W]:
        P_hid = rho * g * Q * H
        """
        caudal(Q)
        numero(H,'Carga de la bomba',minimo=0)
        validar_fluido(rho,1.0,g)
        return float(rho * g * float(Q) * float(H))

    def potencia_freno(self, Q, H, rho=1000.0, g=9.81):
        """
        Potencia al freno (BHP) requerida en el eje de la bomba [W]:
        P_freno = P_hidraulica / eta.
        Si eta no está disponible o es cero devuelve None.
        """
        eff = self.eta_de_Q(Q)
        if eff is None:
            return None
        if eff <= 0.0:
            return None
        return self.potencia_hidraulica(Q, H, rho, g) / eff

    def reparto(self, Q_op, H_op=None, rho=1000.0, g=9.81):
        """Desglose de variables operativas de la bomba individual en su punto de trabajo."""
        Q_op = caudal(Q_op,'Q de operación')
        if H_op is None:
            H_op = self.H_de_Q(Q_op)
        else:
            H_op = float(H_op)

        eff = self.eta_de_Q(Q_op)
        p_hid = self.potencia_hidraulica(Q_op, H_op, rho, g)
        p_freno = self.potencia_freno(Q_op, H_op, rho, g)
        return [{
            "bomba": self.nombre,
            "Q": Q_op,
            "H": H_op,
            "eta": eff,
            "potencia_hidraulica": p_hid,
            "potencia_freno": p_freno,
        }]


class EtapaBombeo(list):
    """
    Representa una etapa de bombas en PARALELO.
    Hereda de list para soportar iteración, indexación y len() como lista de CurvaBomba.
    """

    def __init__(self, bombas):
        super().__init__(bombas)

    @property
    def bombas(self):
        return list(self)

    @property
    def H_cierre_max(self):
        """Altura máxima de cierre entre todas las bombas de la etapa [m]."""
        if not self:
            return 0.0
        return max(b.H_cierre for b in self)

    @property
    def Q_max_etapa(self):
        """Caudal máximo total que puede entregar la etapa [m³/s]."""
        if not self:
            return 0.0
        return sum(b.Q_max for b in self)

    def Q_etapa(self, H):
        """Q_etapa(H) = suma de Q_de_H(H) de sus bombas en paralelo."""
        return sum(b.Q_de_H(H) for b in self)

    def H_etapa(self, Q):
        """
        H_etapa(Q): inversa de Q_etapa por bisección
        (Q_etapa es monótona decreciente en H) en [0, H_cierre_max].
        """
        caudal(Q)
        Q = caudal(Q)
        h_max = self.H_cierre_max
        if Q <= 0.0:
            return float(h_max)

        q_max = self.Q_max_etapa
        if Q >= q_max:
            if not self:
                return 0.0
            return min(b.H_de_Q(b.Q_max) for b in self)

        ha = 0.0
        hb = float(h_max)
        for _ in range(60):
            hm = (ha + hb) / 2.0
            qm = self.Q_etapa(hm)
            if qm > Q:
                ha = hm
            else:
                hb = hm

        return float((ha + hb) / 2.0)


class EstacionBombeo:
    """
    Estación de bombeo con etapas en SERIE, donde cada etapa consta de bombas en PARALELO.
    """

    def __init__(self, etapas, metodo="cuadratico"):
        if not etapas:
            raise ValueError("La estación de bombeo debe tener al menos una etapa.")
        self.etapas = [
            e if isinstance(e, EtapaBombeo) else EtapaBombeo(e)
            for e in etapas
        ]
        self.nombre = f"Estación ({len(self.etapas)} etapa{'s' if len(self.etapas) > 1 else ''})"

        # Determinar método de la estación ("cuadratico" por defecto o "lineal")
        if metodo is not None and "metodo" in self._init_kwargs_helper(metodo):
            pass
        m_norm = str(metodo).strip().lower() if metodo is not None else "cuadratico"
        if m_norm in ("lineal", "interpolacion", "interpolación"):
            self._metodo = "lineal"
            for e in self.etapas:
                for b in e:
                    if hasattr(b, "metodo"):
                        b.metodo = "lineal"
        elif m_norm in ("cuadratico", "cuadrático", "ajuste"):
            # Si alguna bomba ya fue inicializada explícitamente en lineal y no se forzó, respetar o aplicar
            todas_lineales = all(getattr(b, "metodo", "cuadratico") == "lineal" for e in self.etapas for b in e)
            self._metodo = "lineal" if todas_lineales else "cuadratico"
        else:
            raise ValueError("El método debe ser 'cuadratico' o 'lineal'.")

    @staticmethod
    def _init_kwargs_helper(m):
        return {}

    @property
    def metodo(self):
        return self._metodo

    @metodo.setter
    def metodo(self, val):
        m_norm = str(val).strip().lower()
        if m_norm in ("cuadratico", "cuadrático", "ajuste"):
            self._metodo = "cuadratico"
            for e in self.etapas:
                for b in e:
                    if hasattr(b, "metodo"):
                        b.metodo = "cuadratico"
        elif m_norm in ("lineal", "interpolacion", "interpolación"):
            self._metodo = "lineal"
            for e in self.etapas:
                for b in e:
                    if hasattr(b, "metodo"):
                        b.metodo = "lineal"
        else:
            raise ValueError("El método debe ser 'cuadratico' o 'lineal'.")

    @classmethod
    def en_paralelo(cls, lista_curvas, metodo=None):
        """Constructor auxiliar: 1 etapa con N bombas en paralelo."""
        if metodo is not None:
            for b in lista_curvas:
                if hasattr(b, "metodo"):
                    b.metodo = metodo
            return cls([lista_curvas], metodo=metodo)
        return cls([lista_curvas])

    @classmethod
    def en_serie(cls, lista_curvas, metodo=None):
        """Constructor auxiliar: N etapas de 1 bomba cada una (en serie)."""
        if metodo is not None:
            for b in lista_curvas:
                if hasattr(b, "metodo"):
                    b.metodo = metodo
            return cls([[b] for b in lista_curvas], metodo=metodo)
        return cls([[b] for b in lista_curvas])

    def Q_etapa(self, etapa, H):
        """Evalúa el caudal de una etapa a una altura H dada."""
        if isinstance(etapa, int):
            return self.etapas[etapa].Q_etapa(H)
        return etapa.Q_etapa(H)

    def H_etapa(self, etapa, Q):
        """Evalúa la altura que entrega una etapa para un caudal Q dado."""
        if isinstance(etapa, int):
            return self.etapas[etapa].H_etapa(Q)
        return etapa.H_etapa(Q)

    def H_estacion(self, Q):
        """H_estacion(Q) = suma de H_etapa(Q) de todas las etapas."""
        caudal(Q)
        return sum(etapa.H_etapa(Q) for etapa in self.etapas)

    def H(self, Q):
        """Método abreviado para H_estacion(Q)."""
        return self.H_estacion(Q)

    def validar_dominio(self, Q, desglose=None):
        """Cada bomba activa debe satisfacer SU tabla y la carga de SU etapa.

        Una inversa recortada a Q_max no constituye un punto de operación.
        También se verifica la continuidad por etapa, sin leer flags mutables.
        """
        desglose = desglose if desglose is not None else _calcular_desglose(self, Q, 1000, 9.81)
        indice = 0
        for etapa in self.etapas:
            h = etapa.H_etapa(Q)
            suma = 0.0
            for b in etapa:
                d = desglose[indice]
                indice += 1
                suma += d.Q_i
                if d.activa and (not b.caudal_en_dominio(d.Q_i) or
                    abs(b.H_de_Q(d.Q_i)-h) > 1e-8*max(abs(h),abs(b.H_de_Q(d.Q_i)),1e-30)):
                    return False
            if abs(suma-Q) > 1e-8*max(abs(Q),1e-30):
                return False
        return True

    def eta_de_Q(self, Q):
        desglose = _calcular_desglose(self, Q, 1000.0, 9.81)
        return _potencias_desglose(desglose)[1]

    def evaluar_npsh(self, Q, *, P_atm, P_vap, rho=1000.0, g=9.81,
                     z1=0.0, z_bomba=0.0, hf_succion=0.0, P1=0.0,
                     perdidas_entre_etapas=None, cotas_etapas=None, desglose=None):
        """NPSHd individual: serie acumula carga; paralelo comparte aspiración.

        Las etapas del símbolo de estación están al mismo nivel y sin pérdidas
        intermedias salvo que se suministren pérdidas/cotas explícitas.
        """
        desglose = desglose if desglose is not None else _calcular_desglose(self,Q,rho,g)
        perdidas = perdidas_entre_etapas or [0.0]*(len(self.etapas)-1)
        cotas = cotas_etapas or [z_bomba]*len(self.etapas)
        if len(perdidas) != len(self.etapas)-1 or len(cotas) != len(self.etapas):
            raise ValueError("Se requieren cotas por etapa y pérdidas por conexión entre etapas.")
        if not all(math.isfinite(v) for v in (*perdidas,*cotas)) or any(v < 0 for v in perdidas):
            raise ValueError('Cotas y pérdidas entre etapas inválidas.')
        disponible = npsh_disponible(P_atm=P_atm,P_vap=P_vap,rho=rho,g=g,
            z1=z1,z_bomba=cotas[0],hf_succion=hf_succion,P1=P1)
        indice = 0
        for k, etapa in enumerate(self.etapas):
            if k:
                disponible += self.etapas[k-1].H_etapa(Q)-perdidas[k-1]-(cotas[k]-cotas[k-1])
            for b in etapa:
                d = desglose[indice]
                indice += 1
                d.npsh_d = disponible if d.activa else None
                d.npsh_r = b.npsh_r_de_Q(d.Q_i) if d.activa else None
                d.cavitacion = (verificar_cavitacion(d.npsh_d,d.npsh_r)
                                if d.activa else None)
        return desglose

    def H_de_Q(self, Q):
        """Compatibilidad con la interfaz de CurvaBomba."""
        return self.H_estacion(Q)

    @property
    def Q_max_estacion(self):
        """Q_max_estacion = mínimo de las Q_max_etapa."""
        if not self.etapas:
            return 0.0
        return min(etapa.Q_max_etapa for etapa in self.etapas)

    @property
    def Q_max(self):
        return self.Q_max_estacion

    @property
    def H_cierre_estacion(self):
        """H_cierre_estacion = H_estacion(0)."""
        return self.H_estacion(0.0)

    @property
    def H_cierre(self):
        return self.H_cierre_estacion

    @property
    def tiene_eficiencia(self):
        return all(all(getattr(b, "tiene_eficiencia", False) for b in e) for e in self.etapas)

    @property
    def tiene_npshr(self):
        if self.etapas and self.etapas[0]:
            return getattr(self.etapas[0][0], "tiene_npshr", False)
        return False

    def npsh_r_de_Q(self, Q):
        if not self.tiene_npshr or not self.etapas or not self.etapas[0]:
            return None
        primera_etapa = self.etapas[0]
        h1 = primera_etapa.H_etapa(Q)
        valores = [b.npsh_r_de_Q(b.Q_de_H(h1)) for b in primera_etapa if getattr(b, "tiene_npshr", False)]
        valores_validos = [v for v in valores if v is not None]
        return max(valores_validos) if valores_validos else None

    def reparto(self, Q_op=None, H_op=None, rho=1000.0, g=9.81):
        """Desglose en formato compatible con diccionarios de reporte."""
        if Q_op is None:
            if H_op is None:
                raise ValueError("Se debe proporcionar Q_op o H_op.")
            if len(self.etapas) == 1:
                Q_op = self.etapas[0].Q_etapa(H_op)
            else:
                Q_op = 0.0
        desglose = _calcular_desglose(self, float(Q_op), rho, g)
        return [
            {
                "bomba": d.id,
                "Q": d.Q_i,
                "H": d.H_i,
                "eta": d.eta_i,
                "potencia_hidraulica": float(rho * g * d.Q_i * d.H_i),
                "potencia_freno": d.BHP_i,
                "activa": d.activa,
                "etapa": d.etapa,
            }
            for d in desglose
        ]

    def ecuacion_total(self, Q_op=None, H_op=None):
        """Calcula y devuelve la ecuación total informativa de la estación."""
        if Q_op is None:
            Q_op = getattr(self, "Q_op", None)
        if H_op is None:
            H_op = getattr(self, "H_op", None)
        return ecuacion_total(self, Q_op=Q_op, H_op=H_op)


@dataclass
class EcuacionTotal:
    """Resultado informativo de ecuacion_total(estacion): H(Q) = a + b·Q + c·Q² (H en m, Q en m³/s)."""
    a: float
    b: float
    c: float
    tipo: str
    R2: float | None
    texto: str
    delta_Qop: float = 0.0
    error_max: float = 0.0

    @property
    def r2(self):
        return self.R2

    @property
    def delta_qop(self):
        return self.delta_Qop

    def __getitem__(self, key):
        if isinstance(key, int):
            campos = [self.a, self.b, self.c, self.tipo, self.R2, self.texto, self.delta_Qop, self.error_max]
            return campos[key]
        if key == "r2":
            return self.R2
        if key == "delta_qop":
            return self.delta_Qop
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key):
        return hasattr(self, key) or key in ("r2", "delta_qop")

    def __iter__(self):
        yield self.a
        yield self.b
        yield self.c
        yield self.tipo
        yield self.R2
        yield self.texto
        yield self.delta_Qop
        yield self.error_max


def _formatear_ecuacion_total_texto(a: float, b: float, c: float) -> str:
    """Formatea H(Q) = a + b·Q + c·Q² siguiendo la convención p. ej. 'H(Q) = 23.75 + 18.38·Q − 614.1·Q²'."""
    def _fmt_coef(val: float, dec_default: int = 2) -> str:
        v = abs(val)
        if abs(v - round(v)) < 1e-6:
            return f"{v:.2f}" if v < 100.0 else f"{int(round(v))}"
        if v >= 100.0:
            return f"{v:.1f}"
        return f"{v:.{dec_default}f}"

    str_a = f"{a:.2f}"
    sig_b = "−" if b < -1e-12 else "+"
    str_b = _fmt_coef(b, 2)
    sig_c = "−" if c < -1e-12 else "+"
    str_c = _fmt_coef(c, 2)
    return f"H(Q) = {str_a} {sig_b} {str_b}·Q {sig_c} {str_c}·Q²"


def ecuacion_total(estacion, Q_op=None, H_op=None) -> EcuacionTotal:
    """
    Devuelve la ecuación cuadrática equivalente H(Q) = a + b·Q + c·Q² (H en m, Q en m³/s) de la estación:
    coeficientes a, b, c, tipo ('exacta' o 'ajuste'), R2 y texto listo para mostrar.
    En tipo='ajuste', ajusta por mínimos cuadrados sobre Q en [0, min(1.25*Q_op, Q_max_util)] con 60 puntos.
    Si todavía no hay Q_op, usa el rango completo actual.
    Devuelve además delta_Qop = H_ajuste(Q_op) - H_op (m) y error_max (m) dentro de ese rango.
    El motor NO usa esta ecuación para resolver; es informativa.
    """
    if Q_op is None:
        Q_op = getattr(estacion, "Q_op", None)
    if H_op is None:
        H_op = getattr(estacion, "H_op", None)

    q_op_val = None
    if Q_op is not None:
        try:
            q_op_val = float(Q_op)
        except (ValueError, TypeError):
            q_op_val = None

    h_op_val = None
    if H_op is not None:
        try:
            h_op_val = float(H_op)
        except (ValueError, TypeError):
            h_op_val = None

    if isinstance(estacion, EstacionBombeo):
        est = estacion
    elif isinstance(estacion, CurvaParalelo):
        est = EstacionBombeo.en_paralelo(estacion.bombas)
    elif isinstance(estacion, CurvaSerie):
        est = EstacionBombeo.en_serie(estacion.bombas)
    elif isinstance(estacion, CurvaBomba):
        est = EstacionBombeo.en_paralelo([estacion])
    else:
        if hasattr(estacion, "etapas"):
            est = estacion
        elif hasattr(estacion, "bombas"):
            est = EstacionBombeo.en_paralelo(estacion.bombas)
        else:
            est = EstacionBombeo.en_paralelo([estacion])

    # Verificar si es bomba única cuadrática o serie con todas las bombas cuadráticas
    es_serie_pura = all(len(etapa) == 1 for etapa in est.etapas)
    todas_cuadraticas = (
        getattr(est, "metodo", "cuadratico") == "cuadratico"
        and all(
            getattr(b, "metodo", "cuadratico") == "cuadratico"
            for etapa in est.etapas
            for b in etapa
        )
    )

    if es_serie_pura and todas_cuadraticas and len(est.etapas) >= 1:
        bombas_serie = [etapa[0] for etapa in est.etapas]
        a_tot = float(sum(getattr(b, "coef_a", getattr(b, "poly_c", 0.0)) for b in bombas_serie))
        b_tot = float(sum(getattr(b, "coef_b", getattr(b, "poly_b", 0.0)) for b in bombas_serie))
        c_tot = float(sum(getattr(b, "coef_c", getattr(b, "poly_a", 0.0)) for b in bombas_serie))
        if abs(a_tot) < 1e-12:
            a_tot = 0.0
        if abs(b_tot) < 1e-12:
            b_tot = 0.0
        if abs(c_tot) < 1e-12:
            c_tot = 0.0

        # Calcular R² respecto a la curva real / puntos si se requiere
        r2_val = 1.0
        if len(bombas_serie) == 1:
            b0 = bombas_serie[0]
            if hasattr(b0, "Q") and hasattr(b0, "_H_pts") and len(b0.Q) >= 3:
                q_arr = np.array(b0.Q, dtype=float)
                h_arr = np.array(b0._H_pts, dtype=float)
                h_pred = a_tot + b_tot * q_arr + c_tot * (q_arr ** 2)
                ss_res = float(np.sum((h_arr - h_pred) ** 2))
                ss_tot = float(np.sum((h_arr - np.mean(h_arr)) ** 2))
                r2_val = float(1.0 - ss_res / ss_tot) if ss_tot > 1e-15 else 1.0

        texto = _formatear_ecuacion_total_texto(a_tot, b_tot, c_tot)

        delta_qop_exacta = 0.0
        if q_op_val is not None:
            try:
                h_aj_q = a_tot + b_tot * q_op_val + c_tot * (q_op_val ** 2)
                h_target = h_op_val if h_op_val is not None else float(est.H_estacion(q_op_val))
                delta_qop_exacta = float(h_aj_q - h_target)
            except Exception:
                delta_qop_exacta = 0.0

        return EcuacionTotal(
            a=a_tot,
            b=b_tot,
            c=c_tot,
            tipo="exacta",
            R2=r2_val,
            texto=texto,
            delta_Qop=delta_qop_exacta,
            error_max=0.0,
        )

    # Caso "ajuste": paralelo, mixto o método lineal.
    # Ajuste cuadrático por mínimos cuadrados con 60 puntos entre Q = 0 y min(1.25*Q_op, Q_max_util).
    def _q_valido_max_bomba(b):
        if getattr(b, "metodo", "cuadratico") == "cuadratico" and getattr(b, "poly_a", 0.0) < -1e-12:
            # Raíz positiva donde el polinomio llega a H = 0 (si cae antes de b.Q_max)
            disc = (b.poly_b ** 2) - 4.0 * b.poly_a * b.poly_c
            if disc >= 0.0:
                q_zero = (-b.poly_b - math.sqrt(disc)) / (2.0 * b.poly_a)
                if 0.0 < q_zero < float(b.Q_max):
                    return float(q_zero)
        return float(b.Q_max)

    q_max_cands = []
    for etapa in est.etapas:
        if len(etapa) == 1:
            q_max_cands.append(_q_valido_max_bomba(etapa[0]))
        elif len(etapa) > 1:
            h_mins = []
            for b in etapa:
                qm_b = _q_valido_max_bomba(b)
                h_mins.append(max(0.0, float(b.H_de_Q(qm_b))))
            h_min_etapa = max(h_mins) if h_mins else 0.0
            if h_min_etapa <= 1e-9:
                q_lim_etapa = float(sum(_q_valido_max_bomba(b) for b in etapa))
            else:
                q_lim_etapa = float(sum(b.Q_de_H(h_min_etapa) for b in etapa))
            q_max_cands.append(q_lim_etapa if q_lim_etapa > 0.0 else float(etapa.Q_max_etapa))

    q_max_util = min(q_max_cands) if q_max_cands else float(est.Q_max_estacion)

    if q_op_val is not None and q_op_val > 0.0:
        q_fit_max = min(1.25 * q_op_val, q_max_util)
    else:
        q_fit_max = q_max_util

    if q_fit_max <= 0.0:
        h0 = float(est.H_estacion(0.0))
        return EcuacionTotal(
            a=h0,
            b=0.0,
            c=0.0,
            tipo="ajuste",
            R2=1.0,
            texto=_formatear_ecuacion_total_texto(h0, 0.0, 0.0),
            delta_Qop=0.0,
            error_max=0.0,
        )

    qs = np.linspace(0.0, q_fit_max, 60)
    hs = np.array([float(est.H_estacion(float(q))) for q in qs], dtype=float)
    # Filtrar puntos válidos (donde ninguna bomba haya salido de su rango ni H <= 0 fuera de cierre)
    mask_val = hs >= 0.0
    if np.sum(mask_val) >= 3:
        qs = qs[mask_val]
        hs = hs[mask_val]

    c_quad, b_lin, a_const = np.polyfit(qs, hs, 2)
    a_val = float(a_const)
    b_val = float(b_lin)
    c_val = float(c_quad)
    if abs(a_val) < 1e-12:
        a_val = 0.0
    if abs(b_val) < 1e-12:
        b_val = 0.0
    if abs(c_val) < 1e-12:
        c_val = 0.0

    h_pred = a_val + b_val * qs + c_val * (qs ** 2)
    ss_res = float(np.sum((hs - h_pred) ** 2))
    ss_tot = float(np.sum((hs - np.mean(hs)) ** 2))
    r2 = float(1.0 - (ss_res / ss_tot)) if ss_tot > 1e-15 else 1.0
    r2 = max(0.0, min(1.0, r2))

    error_max = float(np.max(np.abs(hs - h_pred))) if len(hs) > 0 else 0.0

    delta_Qop = 0.0
    if q_op_val is not None:
        h_aj_q = a_val + b_val * q_op_val + c_val * (q_op_val ** 2)
        if h_op_val is not None:
            h_ref = h_op_val
        else:
            try:
                h_ref = float(est.H_estacion(q_op_val))
            except Exception:
                h_ref = h_aj_q
        delta_Qop = float(h_aj_q - h_ref)

    texto = _formatear_ecuacion_total_texto(a_val, b_val, c_val)
    return EcuacionTotal(
        a=a_val,
        b=b_val,
        c=c_val,
        tipo="ajuste",
        R2=r2,
        texto=texto,
        delta_Qop=delta_Qop,
        error_max=error_max,
    )


# --------------------------------------------------------------------------
# Clases de soporte y compatibilidad histórica
# --------------------------------------------------------------------------

class CurvaEquivalente:
    """Clase base para curvas equivalentes de bombas combinadas."""
    pass


class CurvaSerie(CurvaEquivalente):
    """Arreglo de bombas en serie: a igual Q se suman las alturas H_eq(Q) = ΣH_i(Q)."""

    def __init__(self, lista_curvas):
        if not lista_curvas:
            raise ValueError("La lista de bombas para arreglo en serie no puede estar vacía.")
        self.bombas = list(lista_curvas)
        self.nombre = f"Serie ({' + '.join(b.nombre for b in self.bombas)})"

    @property
    def tiene_eficiencia(self):
        return all(getattr(b, "tiene_eficiencia", False) for b in self.bombas)

    @property
    def tiene_npshr(self):
        return getattr(self.bombas[0], "tiene_npshr", False) if self.bombas else False

    @property
    def Q_max(self):
        return min(b.Q_max for b in self.bombas)

    @property
    def H_cierre(self):
        return sum(b.H_cierre for b in self.bombas)

    def H_de_Q(self, Q):
        Q = caudal(Q)
        if Q < 0.0:
            Q = 0.0
        elif Q > self.Q_max:
            Q = self.Q_max
        return sum(b.H_de_Q(Q) for b in self.bombas)

    def H(self, Q):
        return self.H_de_Q(Q)

    def Q_de_H(self, H):
        H = numero(H,'H de la bomba',minimo=0)
        if H >= self.H_cierre:
            return 0.0

        h_min = self.H_de_Q(self.Q_max)
        if H <= h_min:
            return float(self.Q_max)

        qa = 0.0
        qb = float(self.Q_max)
        for _ in range(60):
            qm = (qa + qb) / 2.0
            hm = self.H_de_Q(qm)
            if hm > H:
                qa = qm
            else:
                qb = qm

        return float((qa + qb) / 2.0)

    def eta_de_Q(self, Q):
        caudal(Q)
        if not self.tiene_eficiencia:
            return None
        Q = caudal(Q)
        if Q <= 0.0:
            return 0.0
        h_eq = self.H_de_Q(Q)
        if h_eq <= 0.0:
            return 0.0

        denom = 0.0
        for b in self.bombas:
            hi = b.H_de_Q(Q)
            etai = b.eta_de_Q(Q)
            if etai is None or etai <= 0.0:
                return None
            denom += hi / etai

        if denom <= 0.0:
            return 0.0
        return max(0.0, min(1.0, float(h_eq / denom)))

    def eta(self, Q):
        return self.eta_de_Q(Q)

    def npsh_r_de_Q(self, Q):
        caudal(Q)
        if not self.tiene_npshr:
            return None
        if self.bombas:
            return self.bombas[0].npsh_r_de_Q(Q)
        return None

    def potencia_hidraulica(self, Q, H, rho=1000.0, g=9.81):
        return float(rho * g * float(Q) * float(H))

    def potencia_freno(self, Q, H, rho=1000.0, g=9.81):
        eff = self.eta_de_Q(Q)
        if eff is None:
            return None
        if eff <= 0.0:
            return None
        return self.potencia_hidraulica(Q, H, rho, g) / eff

    def reparto(self, Q_op, H_op=None, rho=1000.0, g=9.81):
        Q_op = caudal(Q_op,'Q de operación')
        desglose = []
        for b in self.bombas:
            hi = b.H_de_Q(Q_op)
            etai = b.eta_de_Q(Q_op)
            p_hid = b.potencia_hidraulica(Q_op, hi, rho, g)
            p_freno = b.potencia_freno(Q_op, hi, rho, g)
            desglose.append({
                "bomba": getattr(b, "nombre", "Bomba"),
                "Q": Q_op,
                "H": float(hi),
                "eta": float(etai) if etai is not None else None,
                "potencia_hidraulica": float(p_hid),
                "potencia_freno": float(p_freno) if p_freno is not None else None,
            })
        return desglose


class CurvaParalelo(CurvaEquivalente):
    """Arreglo de bombas en paralelo: a igual H se suman los caudales Q_eq(H) = ΣQ_i(H)."""

    def __init__(self, lista_curvas):
        if not lista_curvas:
            raise ValueError("La lista de bombas para arreglo en paralelo no puede estar vacía.")
        self.bombas = list(lista_curvas)
        self.nombre = f"Paralelo ({' // '.join(b.nombre for b in self.bombas)})"

    @property
    def tiene_eficiencia(self):
        return all(getattr(b, "tiene_eficiencia", False) for b in self.bombas)

    @property
    def tiene_npshr(self):
        return all(getattr(b, "tiene_npshr", False) for b in self.bombas)

    @property
    def H_cierre(self):
        return max(b.H_cierre for b in self.bombas)

    @property
    def Q_max(self):
        return sum(b.Q_max for b in self.bombas)

    def Q_de_H(self, H):
        H = numero(H,'H de la bomba',minimo=0)
        if H >= self.H_cierre:
            return 0.0
        if H <= 0.0:
            return float(self.Q_max)
        return sum(b.Q_de_H(H) for b in self.bombas)

    def H_de_Q(self, Q):
        Q = caudal(Q)
        if Q <= 0.0:
            return float(self.H_cierre)
        if Q >= self.Q_max:
            return min(b.H_de_Q(b.Q_max) for b in self.bombas)

        ha = min(b.H_de_Q(b.Q_max) for b in self.bombas)
        hb = float(self.H_cierre)
        for _ in range(60):
            hm = (ha + hb) / 2.0
            qm = self.Q_de_H(hm)
            if qm > Q:
                ha = hm
            else:
                hb = hm

        return float((ha + hb) / 2.0)

    def H(self, Q):
        return self.H_de_Q(Q)

    def eta_de_Q(self, Q):
        caudal(Q)
        if not self.tiene_eficiencia:
            return None
        Q = caudal(Q)
        if Q <= 0.0:
            return 0.0
        h_op = self.H_de_Q(Q)
        denom = 0.0
        for b in self.bombas:
            qi = b.Q_de_H(h_op)
            etai = b.eta_de_Q(qi)
            if qi > 0.0:
                if etai is None or etai <= 0.0:
                    return None
                denom += qi / etai

        if denom <= 0.0:
            return 0.0
        return max(0.0, min(1.0, float(Q / denom)))

    def eta(self, Q):
        return self.eta_de_Q(Q)

    def npsh_r_de_Q(self, Q):
        caudal(Q)
        if not self.tiene_npshr:
            return None
        Q = caudal(Q)
        h_op = self.H_de_Q(Q)
        valores = []
        for b in self.bombas:
            qi = b.Q_de_H(h_op)
            nr = b.npsh_r_de_Q(qi)
            if nr is not None:
                valores.append(nr)
        return max(valores) if valores else None

    def potencia_hidraulica(self, Q, H, rho=1000.0, g=9.81):
        return float(rho * g * float(Q) * float(H))

    def potencia_freno(self, Q, H, rho=1000.0, g=9.81):
        eff = self.eta_de_Q(Q)
        if eff is None:
            return None
        if eff <= 0.0:
            return None
        return self.potencia_hidraulica(Q, H, rho, g) / eff

    def reparto(self, Q_op=None, H_op=None, rho=1000.0, g=9.81):
        if H_op is None:
            if Q_op is None:
                raise ValueError("Se debe proporcionar Q_op o H_op para el reparto en paralelo.")
            H_op = self.H_de_Q(float(Q_op))
        else:
            H_op = float(H_op)

        desglose = []
        for b in self.bombas:
            qi = b.Q_de_H(H_op)
            etai = b.eta_de_Q(qi)
            p_hid = b.potencia_hidraulica(qi, H_op, rho, g)
            p_freno = b.potencia_freno(qi, H_op, rho, g)
            desglose.append({
                "bomba": getattr(b, "nombre", "Bomba"),
                "Q": float(qi),
                "H": H_op,
                "eta": float(etai) if etai is not None else None,
                "potencia_hidraulica": float(p_hid),
                "potencia_freno": float(p_freno) if p_freno is not None else None,
            })
        return desglose


def combinar_serie(lista_curvas):
    """Devuelve un objeto CurvaSerie que representa la suma de alturas a igual Q."""
    return CurvaSerie(lista_curvas)


def combinar_paralelo(lista_curvas):
    """Devuelve un objeto CurvaParalelo que representa la suma de caudales a igual H."""
    return CurvaParalelo(lista_curvas)


# --------------------------------------------------------------------------
# Resolución del Punto de Operación
# --------------------------------------------------------------------------

def _calcular_desglose(est, Q, rho, g, *, H=None, curva=None):
    """Calcula el estado y rendimiento de cada bomba en la estación para un caudal Q dado."""
    desglose = []
    etapas = (((etapa.H_etapa(Q),etapa) for etapa in est.etapas) if est is not None
              else ((H,[curva]),))
    for k, (h_etapa, etapa) in enumerate(etapas):
        for idx, b in enumerate(etapa):
            b_id = getattr(b, "id_bomba", getattr(b, "nombre", f"Bomba_{k+1}_{idx+1}"))
            q_i = Q if len(etapa) == 1 else b.Q_de_H(h_etapa)
            activa = bool(q_i > 0.0)
            if not activa:
                q_i = 0.0

            if hasattr(b, "eta_de_Q"):
                eta_i = b.eta_de_Q(q_i)
            elif callable(getattr(b, "eta", None)):
                eta_i = b.eta(q_i)
            else:
                eta_i = None

            p_hid = rho * g * q_i * h_etapa
            if eta_i is not None and eta_i > 0:
                bhp_i = p_hid / eta_i
            else:
                eta_i = None
                bhp_i = 0.0 if p_hid == 0.0 else None

            desglose.append(
                BombaDesglose(
                    id=b_id,
                    etapa=k + 1,
                    Q_i=float(q_i),
                    H_i=float(h_etapa),
                    eta_i=float(eta_i) if eta_i is not None else None,
                    BHP_i=float(bhp_i) if bhp_i is not None else None,
                    activa=activa,
                    P_hidraulica=float(p_hid),
                )
            )
    return desglose


def _potencias_desglose(desglose):
    """Una sola potencia positiva desconocida hace desconocido el total."""
    if any(d.P_hidraulica > 0 and d.BHP_i is None for d in desglose):
        return None, None
    potencia = sum(d.BHP_i or 0.0 for d in desglose)
    hidraulica = sum(d.P_hidraulica for d in desglose)
    return potencia, hidraulica/potencia if potencia > 0 else None


def _estacion_normalizada(estacion):
    if isinstance(estacion, EstacionBombeo):
        return estacion
    if isinstance(estacion, CurvaSerie):
        return EstacionBombeo.en_serie(estacion.bombas)
    if isinstance(estacion, CurvaParalelo):
        return EstacionBombeo.en_paralelo(estacion.bombas)
    return EstacionBombeo.en_paralelo([estacion])


def evaluar_operacion_estacion(estacion, H_sistema=None, *, rho=1000.0, mu=0.001,
        g=9.81, P_atm=None, P_vap=None, z1=0.0, z_bomba=0.0, P1=0.0,
        tramos=(), indices_succion=(), hf_succion=None, Q=None,
        perdidas_entre_etapas=None, cotas_etapas=None, id='estacion'):
    """Una salida SI con operación, tramos, potencias y aspiración POR BOMBA.

    Sin Q resuelve el punto con H_sistema. Q explícito evalúa el punto ya hallado
    por un solver de red, sin buscar una segunda intersección. Las potencias
    proceden exclusivamente de _calcular_desglose/_potencias_desglose.
    """
    from motor.hidraulica import evaluar_tramo
    validar_fluido(rho, mu, g)
    est = _estacion_normalizada(estacion)
    if (P_atm is None) != (P_vap is None):
        raise ValueError('Suministre P_atm y P_vap conjuntamente.')
    if Q is None:
        if H_sistema is None:
            raise ValueError('Falta H_sistema para resolver la estación.')
        sol = punto_operacion(est, H_sistema, rho=rho, g=g)
    else:
        q = caudal(Q)
        desglose = _calcular_desglose(est, q, rho, g)
        eje, eta = _potencias_desglose(desglose)
        valido = est.validar_dominio(q, desglose)
        sol = ResultadoBombeo('OK' if valido else 'FUERA_DE_RANGO_CURVA',
            'Operación evaluada.' if valido else 'Punto fuera del dominio de una bomba.',
            q, est.H_estacion(q), sum(d.P_hidraulica for d in desglose), eje, eta, desglose)
    resultados_tramos = tuple(evaluar_tramo(sol.Q, t['L'], t['D'], t.get('eps',0),
        t.get('K',0), t.get('LeD',0), dict(rho=rho,mu=mu,g=g),
        id=str(t.get('id', i))) for i,t in enumerate(tramos))
    indices_succion = tuple(indices_succion)
    if any(not isinstance(i,int) or i < 0 or i >= len(resultados_tramos) for i in indices_succion):
        raise ValueError('Índice de tramo de succión inválido.')
    hf_suc = (sum(resultados_tramos[i].hf_total for i in indices_succion)
              if hf_succion is None else numero(hf_succion,'hf de succión',minimo=0))
    if P_atm is not None and sol.desglose:
        est.evaluar_npsh(sol.Q,P_atm=P_atm,P_vap=P_vap,rho=rho,g=g,z1=z1,
            z_bomba=z_bomba,hf_succion=hf_suc,P1=P1,desglose=sol.desglose,
            perdidas_entre_etapas=perdidas_entre_etapas,cotas_etapas=cotas_etapas)
    else:
        for b,d in zip((b for e in est.etapas for b in e), sol.desglose):
            d.npsh_r = b.npsh_r_de_Q(d.Q_i) if d.activa else None
    bombas = []
    for b,d in zip((b for e in est.etapas for b in e), sol.desglose):
        dominio = (not d.activa or (b.caudal_en_dominio(d.Q_i) and
            abs(b.H_de_Q(d.Q_i)-d.H_i) <= 1e-8*max(abs(d.H_i),1e-30)))
        cav = ('desconocido' if d.npsh_d is None or d.npsh_r is None else
               'seguro' if d.npsh_d > d.npsh_r else 'riesgo')
        desconocidos = tuple(nombre for nombre,valor in (
            ('potencia_eje',d.BHP_i),('eficiencia',d.eta_i),
            ('NPSHd',d.npsh_d),('NPSHr',d.npsh_r)) if valor is None)
        bombas.append(ResultadoBomba(str(d.id),str(id),d.etapa,d.activa,d.Q_i,d.H_i,
            float(b.Q_min),float(b.Q_max),dominio,d.P_hidraulica,d.BHP_i,d.eta_i,
            d.npsh_d,d.npsh_r,cav,'OK' if dominio else 'FUERA_DE_RANGO_CURVA',desconocidos))
    balances = tuple((sum(d.Q_i for d in sol.desglose if d.etapa==i+1)-sol.Q,
        max((abs(b.H_de_Q(d.Q_i)-d.H_i) for b,d in zip(
            etapa,[v for v in sol.desglose if v.etapa==i+1]) if d.activa),default=0.0))
        for i,etapa in enumerate(est.etapas))
    masa = max((abs(v[0]) for v in balances),default=0.0)
    energia = (sol.H_total-numero(H_sistema(sol.Q),'H del sistema') if H_sistema else
               max((v[1] for v in balances),default=0.0))
    estado = sol.estado
    if estado=='OK' and (relativo(masa,sol.Q)>1e-8 or relativo(energia,sol.H_total)>1e-8):
        estado = 'SIN_CONVERGENCIA'
    return ResultadoEstacion(str(id),tuple(tuple(v.id for v in bombas if v.etapa==i+1)
        for i in range(len(est.etapas))),sol.Q,sol.H_total,
        sum(d.P_hidraulica for d in sol.desglose),sol.BHP_total,sol.eta_global,
        balances,tuple(bombas),estado,sol.mensaje,sol.iteraciones,masa,energia,
        relativo(masa,sol.Q),relativo(energia,sol.H_total),0.0,resultados_tramos,hf_suc,
        tuple(f'{b.id}.{campo}' for b in bombas for campo in b.desconocidos))


def muestrear_sistema_para_exportacion(H_sistema, caudales):
    """Cada fallo conserva Q, H=None y motivo; un error nunca es una altura cero."""
    puntos = []
    for q in caudales:
        q = caudal(q)
        try:
            h = numero(H_sistema(q),'H del sistema')
        except Exception as error:
            puntos.append(dict(Q=q,H=None,estado='NO_CALCULADO',mensaje=str(error)))
        else:
            puntos.append(dict(Q=q,H=h,estado='OK',mensaje=''))
    return puntos


@ejecucion
def punto_operacion(estacion, H_sistema, rho=1000.0, g=9.81, Q_max_busqueda=None):
    """
    Calcula el punto de operación (intersección curva de la estación vs curva del sistema)
    resolviendo f(Q) = H_estacion(Q) - H_sistema(Q) = 0 por bisección.

    Parámetros:
        estacion: EstacionBombeo, CurvaBomba, CurvaSerie o CurvaParalelo.
        H_sistema (callable): función Q -> H requerida por el circuito.
        rho (float): densidad del fluido en kg/m³. Default 1000.0.
        g (float): aceleración de la gravedad en m/s². Default 9.81.
        Q_max_busqueda (float | None): límite opcional superior de búsqueda.

    Retorna:
        ResultadoBombeo: dataclass con estado, mensaje, Q, H_total, P_hidraulica,
                         BHP_total, eta_global y lista desglose por bomba.
    """
    validar_fluido(rho,1.0,g)
    if Q_max_busqueda is not None:
        numero(Q_max_busqueda,'Q máximo de búsqueda',minimo=0,estricto=True)
    if isinstance(estacion, EstacionBombeo):
        est = estacion
    elif isinstance(estacion, CurvaParalelo):
        est = EstacionBombeo.en_paralelo(estacion.bombas)
    elif isinstance(estacion, CurvaSerie):
        est = EstacionBombeo.en_serie(estacion.bombas)
    elif isinstance(estacion, CurvaBomba):
        est = EstacionBombeo.en_paralelo([estacion])
    else:
        if hasattr(estacion, "etapas"):
            est = estacion
        elif hasattr(estacion, "bombas"):
            est = EstacionBombeo.en_paralelo(estacion.bombas)
        else:
            est = EstacionBombeo.en_paralelo([estacion])

    invalidas = [b for e in est.etapas for b in e if not getattr(b,'valida',True)]
    if invalidas:
        return ResultadoBombeo('CURVA_INVALIDA','; '.join(b.mensaje for b in invalidas),0,0,0,None,None)
    sistema_original = H_sistema
    H_sistema = lambda q: numero(sistema_original(q),'H del sistema')
    q_max = float(Q_max_busqueda) if Q_max_busqueda is not None else float(est.Q_max_estacion)

    # 1. Comprobar si la estación vence la altura estática a Q=0
    f_0 = est.H_estacion(0.0) - H_sistema(0.0)
    if f_0 <= 0.0:
        desglose = _calcular_desglose(est, 0.0, rho, g)
        resultado = ResultadoBombeo(
            estado="NO_ALCANZA_ALTURA_ESTATICA",
            mensaje="La bomba no vence la altura estática del sistema",
            Q=0.0,
            H_total=float(est.H_estacion(0.0)),
            P_hidraulica=sum(d.P_hidraulica for d in desglose),
            BHP_total=0.0,
            eta_global=None,
            desglose=desglose,
        )
        return resultado.balances(residuo_energia=f_0,
            escala_energia=max(abs(resultado.H_total),abs(H_sistema(0.0))),
            estado=resultado.estado,mensaje=resultado.mensaje)

    # 2. Comprobar si la estación entrega más de lo que exige el sistema en todo su rango
    f_max = est.H_estacion(q_max) - H_sistema(q_max)
    if f_max > 0.0:
        h_qmax = float(est.H_estacion(q_max))
        desglose = _calcular_desglose(est, q_max, rho, g)
        p_hid = sum(d.P_hidraulica for d in desglose)
        bhp_tot, eta_glob = _potencias_desglose(desglose)
        resultado = ResultadoBombeo(
            estado="FUERA_DE_RANGO_CURVA",
            mensaje="La bomba entrega más que el sistema requiere en todo su rango; el punto de operación está fuera de la curva",
            Q=q_max,
            H_total=h_qmax,
            P_hidraulica=p_hid,
            BHP_total=bhp_tot,
            eta_global=eta_glob,
            desglose=desglose,
        )
        return resultado.balances(residuo_energia=f_max,
            escala_energia=max(abs(h_qmax),abs(H_sistema(q_max))),
            estado=resultado.estado,mensaje=resultado.mensaje)

    # 3. Bisección sobre [0, q_max]
    qa = 0.0
    qb = q_max
    tol_f = 1e-7
    tol_q = 1e-12
    max_iter = 100

    historial = []
    for indice in range(max_iter):
        qm = (qa + qb) / 2.0
        fm = est.H_estacion(qm) - H_sistema(qm)
        historial.append(dict(iteracion=indice+1, Q=qm, residuo_energia=fm))
        if abs(fm) < tol_f or (qb - qa) / 2.0 < tol_q:
            break
        if fm > 0.0:
            qa = qm
        else:
            qb = qm

    q_op = float((qa + qb) / 2.0)
    h_op = float(est.H_estacion(q_op))

    try:
        est.Q_op = q_op
        est.H_op = h_op
    except Exception:
        pass
    if hasattr(estacion, "__dict__"):
        try:
            estacion.Q_op = q_op
            estacion.H_op = h_op
        except Exception:
            pass

    desglose = _calcular_desglose(est, q_op, rho, g)
    p_hid = sum(d.P_hidraulica for d in desglose)
    bhp_tot, eta_glob = _potencias_desglose(desglose)
    valido = est.validar_dominio(q_op, desglose)
    estado = 'OK' if valido else 'FUERA_DE_RANGO_CURVA'
    mensaje = ('Punto de operación encontrado con éxito.' if valido else
               'El punto exige extrapolar al menos una bomba fuera de su tabla de Q/H.')
    if valido and abs(h_op-H_sistema(q_op)) > 1e-8*max(abs(h_op),abs(H_sistema(q_op)),1e-30):
        estado, mensaje = 'SIN_CONVERGENCIA', 'El punto no cumple el balance de energía.'
    if estado != 'OK':
        est.Q_op = est.H_op = None
        if hasattr(estacion, '__dict__'):
            estacion.Q_op = estacion.H_op = None
    resultado = ResultadoBombeo(
        estado=estado,
        mensaje=mensaje,
        Q=q_op,
        H_total=h_op,
        P_hidraulica=p_hid,
        BHP_total=bhp_tot,
        eta_global=eta_glob,
        desglose=desglose,
        iteraciones=len(historial), historial=historial,
    )
    masa = max((abs(sum(d.Q_i for d in desglose if d.etapa == k+1)-q_op)
                for k in range(len(est.etapas))), default=0.0)
    return resultado.balances(iteraciones=len(historial), residuo_masa=masa,
        escala_masa=q_op, residuo_energia=h_op-H_sistema(q_op),
        escala_energia=max(abs(h_op), abs(H_sistema(q_op))), estado=estado, mensaje=mensaje)


# --------------------------------------------------------------------------
# Utilidades de NPSH, Cavitación y Presión de Vapor
# --------------------------------------------------------------------------

def presion_vapor_agua(T_C):
    """
    Calcula la presión de vapor del agua en Pa para una temperatura entre 0 y 100 °C,
    mediante interpolación lineal sobre la tabla experimental estándar.
    1 mmHg = 133.322 Pa.
    """
    T_C = float(T_C)
    if not math.isfinite(T_C) or T_C < 0.0 or T_C > 100.0:
        raise ValueError(f"Temperatura {T_C} °C fuera de rango [0, 100] °C.")

    tabla = [
        (0.0, 4.58),
        (10.0, 9.21),
        (20.0, 17.54),
        (30.0, 31.82),
        (40.0, 55.32),
        (50.0, 92.51),
        (60.0, 149.38),
        (70.0, 233.7),
        (80.0, 355.10),
        (90.0, 525.76),
        (100.0, 760.00),
    ]

    for i in range(len(tabla) - 1):
        t0, p0 = tabla[i]
        t1, p1 = tabla[i + 1]
        if t0 <= T_C <= t1:
            p_mmhg = p0 if t1 == t0 else p0 + (T_C - t0) / (t1 - t0) * (p1 - p0)
            return float(p_mmhg * 133.322)

    return float(tabla[-1][1] * 133.322)


def npsh_disponible(*, P_atm, P_vap, rho=1000.0, z1=0.0, z_bomba=0.0,
                    hf_succion=0.0, P1=0.0, g=9.81):
    """
    Calcula el NPSH disponible [m] en la succión de la bomba:
    NPSH_d = (P_atm + P1 - P_vap)/(rho*g) + z1 - z_bomba - hf_succion.
    P1 es manométrica; P_atm y P_vap son datos explícitos en Pa absolutos.
    """
    if not all(math.isfinite(v) for v in (P_atm,P_vap,rho,g,z1,z_bomba,hf_succion,P1)):
        raise ValueError("Los datos de NPSH deben ser finitos.")
    if P_atm <= 0 or P_vap < 0 or min(rho,g) <= 0 or hf_succion < 0:
        raise ValueError("Presiones absolutas y datos de aspiración inválidos.")
    return float((P_atm + P1 - P_vap)/(rho*g) + z1-z_bomba-hf_succion)


def verificar_cavitacion(npsh_d, npsh_r):
    """
    Determina si existe riesgo de cavitación comparando NPSH disponible con requerido:
    - 'SIN RIESGO' si npsh_d > npsh_r
    - 'RIESGO DE CAVITACIÓN' si npsh_d <= npsh_r
    - 'SIN DATO NPSHr' si npsh_r es None
    """
    if npsh_r is None:
        return "SIN DATO NPSHr"
    if npsh_d > npsh_r:
        return "SIN RIESGO"
    return "RIESGO DE CAVITACIÓN"


# --------------------------------------------------------------------------
# Mixin de integración de Bombas con el Motor de Fluidos
# --------------------------------------------------------------------------

class BombasMixin:
    """Métodos de cálculo del sistema de bombas integrados en MotorFluidos."""

    @classmethod
    def carga_requerida_sistema(
        cls,
        Q,
        z1=0.0,
        z2=0.0,
        P1=0.0,
        P2=0.0,
        rho=1000.0,
        mu=0.001002,
        tramos=None,
        L_tub=None,
        D=None,
        epsilon=0.0,
        sumatoria_K=0.0,
        sumatoria_Le_D=0.0,
        v1=0.0,
        v2=0.0,
        D1=None,
        D2=None,
        hf=None,
        g=None,
    ):
        """
        Calcula la carga que el sistema hidráulico requiere para operar a un caudal Q [m]:
        H_sistema = Δz + ΔP/(ρ·g) + Δ(v²/2g) + hf_total
        """
        grav = g if g is not None else getattr(cls, "g", 9.81)

        caudal(Q)
        validar_fluido(rho,mu,grav)
        for nombre,valor in (('eps',epsilon),('K',sumatoria_K),('LeD',sumatoria_Le_D)):
            numero(valor,nombre,minimo=0)
        for nombre,valor in (('z1',z1),('z2',z2),('P1',P1),('P2',P2)):
            numero(valor,nombre)
        for nombre,valor in (('v1',v1),('v2',v2)):
            numero(valor,nombre,minimo=0)
        for nombre,valor in (('D1',D1),('D2',D2)):
            if valor is not None:
                numero(valor,nombre,minimo=0,estricto=True)
        if hf is not None:
            numero(hf,'hf',minimo=0)
        for tramo in tramos or []:
            datos = dict(L=tramo.get('L',tramo.get('longitud')),D=tramo.get('D',tramo.get('diametro')),
                eps=tramo.get('eps',tramo.get('rugosidad',0)),K=tramo.get('K',tramo.get('sumatoria_K',0)),
                LeD=tramo.get('LeD',tramo.get('sumatoria_Le_D',0)))
            validar_tramo(datos,rho,mu,grav)
        if L_tub is not None or D is not None:
            validar_tramo(dict(L=L_tub,D=D,eps=epsilon,K=sumatoria_K,LeD=sumatoria_Le_D),rho,mu,grav)
        # 1. Velocidades en contornos inicial y final
        vel1 = v1
        if D1 is not None and D1 > 0:
            a1 = math.pi * (D1 ** 2) / 4.0
            vel1 = Q / a1 if a1 > 0 else 0.0

        vel2 = v2
        if D2 is not None and D2 > 0:
            a2 = math.pi * (D2 ** 2) / 4.0
            vel2 = Q / a2 if a2 > 0 else 0.0

        # 2. Pérdidas de carga totales
        if hf is not None:
            hf_total = hf
        elif abs(Q) < 1e-14:
            hf_total = 0.0
        elif tramos:
            hf_total = 0.0
            for t in tramos:
                L_t = t.get("L", t.get("longitud", 0.0))
                D_t = t.get("D", t.get("diametro", 0.0))
                eps_t = t.get("eps", t.get("rugosidad", 0.0))
                K_t = t.get("K", t.get("sumatoria_K", 0.0))
                LeD_t = t.get("LeD", t.get("sumatoria_Le_D", 0.0))
                if D_t > 0 and L_t > 0:
                    hf_tramo, _, _ = cls.calcular_hf(
                        Q, L_t, D_t, rho, mu, eps_t,
                        sumatoria_Le_D=LeD_t, sumatoria_K=K_t, registrar=False
                    )
                    hf_total += hf_tramo
        elif L_tub is not None and D is not None and D > 0 and L_tub > 0:
            hf_total, _, _ = cls.calcular_hf(
                Q, L_tub, D, rho, mu, epsilon,
                sumatoria_Le_D=sumatoria_Le_D, sumatoria_K=sumatoria_K, registrar=False
            )
        else:
            hf_total = 0.0

        # 3. Términos del balance de energía
        delta_z = z2 - z1
        delta_P = (P2 - P1) / (rho * grav)
        delta_v = (vel2 ** 2 - vel1 ** 2) / (2.0 * grav)

        return float(delta_z + delta_P + delta_v + hf_total)

    @classmethod
    def curva_sistema(cls, Q_lista, *args, H_func=None, **kwargs):
        """Genera la lista de cargas requeridas H [m] para una lista de caudales Q [m³/s]."""
        if H_func is not None:
            return [numero(H_func(caudal(q)),'H del sistema') for q in Q_lista]
        return [float(cls.carga_requerida_sistema(q, *args, **kwargs)) for q in Q_lista]

    @classmethod
    def resolver_punto_operacion(
        cls, curva_bomba, *args, H_sistema_de_Q=None, Q_max_busqueda=None, **kwargs
    ):
        """Resuelve el punto de operación de una bomba contra el sistema hidráulico."""
        if H_sistema_de_Q is None:
            def H_sistema_de_Q(q):
                return cls.carga_requerida_sistema(q, *args, **kwargs)

        rho = kwargs.get("rho", 1000.0)
        g = kwargs.get("g", getattr(cls, "g", 9.81))
        return punto_operacion(curva_bomba, H_sistema_de_Q, rho=rho, g=g, Q_max_busqueda=Q_max_busqueda)


