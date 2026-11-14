"""Redes de tuberías: ramificadas, doble nudo y serie por energía con integración de bombas."""

import math

from motor.ejecucion import ejecucion
from motor.validacion import numero, caudal, fluido as validar_fluido, tramo as validar_tramo

from motor.numerica import (
    ErrorConvergencia, Metadatos, ResultadoEscalar, ResultadoTupla, TOLERANCIA_RELATIVA,
    biseccion,
)

from motor.bombas import (
    CurvaBomba,
    CurvaParalelo,
    CurvaSerie,
    EstacionBombeo,
    punto_operacion,
)


class ResultadoResolucion(tuple, Metadatos):
    """
    Tupla de 5 elementos (Q, alturas_nodos, perdidas_tramos, H_fin_calculada, error_H)
    compatible con la firma histórica de resolver_serie_por_energia y extendida con metadatos
    de bombeo, estado y mensaje.
    """

    def __new__(
        cls,
        Q,
        alturas_nodos,
        perdidas_tramos,
        H_fin_calculada,
        error_H,
        estado="OK",
        mensaje="",
        bomba_info=None,
        resultado_bombeo=None,
        iteraciones=0,
        escala_energia=None,
    ):
        instance = super().__new__(
            cls,
            (
                float(Q),
                list(alturas_nodos),
                list(perdidas_tramos),
                float(H_fin_calculada),
                float(error_H),
            ),
        )
        instance.Q = float(Q)
        instance.direccion = 'Desde H_inicio hacia H_fin'
        instance.alturas_nodos = list(alturas_nodos)
        instance.perdidas_tramos = list(perdidas_tramos)
        instance.H_fin_calculada = float(H_fin_calculada)
        instance.error_H = float(error_H)
        instance.estado = str(estado)
        instance.mensaje = str(mensaje)
        instance.bomba_info = bomba_info
        instance.resultado_bombeo = resultado_bombeo
        instance.balances(
            iteraciones=iteraciones, residuo_energia=error_H,
            escala_energia=(sum(abs(p[0]) for p in perdidas_tramos)
                            if escala_energia is None else escala_energia),
            estado=estado, mensaje=mensaje,
        )
        return instance

    @property
    def convergio(self) -> bool:
        return self.estado == "OK"

    def __getitem__(self, key):
        if isinstance(key, str):
            if hasattr(self, key):
                return getattr(self, key)
            raise KeyError(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError, TypeError):
            return default

    def __contains__(self, key):
        return hasattr(self, key) or key in ("convergio", "estado", "mensaje", "Q")


class RedesMixin:
    """Redes de tuberías: ramificadas, doble nudo y serie por energía."""

    @classmethod
    @ejecucion
    def _perdida_tramo(cls, Q, t, rho, mu, registrar=False):
        caudal(Q)
        validar_tramo(t,rho,mu,cls.g)
        segmentos = t.get('segmentos', t.get('sub_tramos'))
        if segmentos is not None:
            if not segmentos:
                raise ValueError("Un ramal debe contener al menos un segmento.")
            perdidas = [cls._perdida_tramo(Q, s, rho, mu, registrar) for s in segmentos]
            return ResultadoTupla(tuple(sum(p[i] for p in perdidas) for i in range(3)),
                iteraciones=sum(p.iteraciones for p in perdidas),
                residuo_ecuacion=max(p.residuo_ecuacion for p in perdidas))
        return cls.calcular_hf(Q, t['L'], t['D'], rho, mu, t.get('eps', 0.0),
            sumatoria_K=t.get('K', 0.0), sumatoria_Le_D=t.get('LeD', 0.0),
            registrar=registrar)

    @classmethod
    @ejecucion
    def _caudal_tramo(cls, hf, t, rho, mu):
        numero(hf,'hf',minimo=0)
        validar_tramo(t,rho,mu,cls.g)
        segmentos = t.get('segmentos', t.get('sub_tramos'))
        if segmentos is not None:
            if not segmentos:
                raise ValueError("Un ramal debe contener al menos un segmento.")
            if not math.isfinite(hf) or hf < 0:
                raise ValueError("La carga del ramal debe ser finita y no negativa.")
            if hf == 0:
                cls._perdida_tramo(0.0, t, rho, mu)
                return ResultadoEscalar(0.0)
            superior = max(min(float(cls.calcular_Q_karman(hf, s['L'], s['D'], rho, mu,
                s.get('eps', 0.0), s.get('K', 0.0), s.get('LeD', 0.0))) for s in segmentos), 1e-30)
            for _ in range(200):
                if cls._perdida_tramo(superior, t, rho, mu)[0] >= hf:
                    break
                superior *= 2
            return biseccion(lambda q: cls._perdida_tramo(q, t, rho, mu)[0] - hf,
                             0.0, superior, hf).verificar()
        return cls.calcular_Q(hf, t['L'], t['D'], rho, mu, t.get('eps', 0.0),
            sumatoria_K=t.get('K', 0.0), sumatoria_Le_D=t.get('LeD', 0.0))

    @classmethod
    def _caudal_para_acotar(cls, hf, t, rho, mu):
        """Inversa generalizada SOLO para acotar la carga en un paralelo.

        En el hueco de hf causado por Re=2000, el límite de Q permite orientar
        la búsqueda exterior hacia una carga factible. Ese valor nunca se
        acepta: al final se invierten y verifican todas las ramas estrictamente.
        Otros fallos de convergencia se propagan sin excepción.
        """
        try:
            return cls._caudal_tramo(hf, t, rho, mu)
        except ErrorConvergencia as error:
            if not getattr(error.resultado, 'salto_regimen', False):
                raise
            return error.resultado

    @classmethod
    @ejecucion
    def resolver_paralelo(cls, tramos, Q_total, rho, mu, hf_inicial=None):
        """Carga común tal que ΣQ_i(hf)=Q_total, con Darcy en cada rama.

        Retorna (hf, caudales, perdidas_tramos), con metadatos de balances.
        Las pérdidas de cada rama se recalculan; no se escalan con Q².
        La masa se normaliza por Q_total y la energía por la carga común.
        hf_inicial solo ayuda a acotar la búsqueda y no altera la solución.
        """
        if not tramos or not math.isfinite(Q_total) or Q_total < 0:
            raise ValueError("Se requieren ramas y un Q_total finito no negativo.")
        if hf_inicial is not None:
            numero(hf_inicial,'hf inicial',minimo=0)
        for t in tramos:
            cls._caudal_tramo(0.0, t, rho, mu)
        if Q_total == 0:
            superior = 0.0
            raiz = None
            hf = 0.0
        else:
            superior = min(cls._perdida_tramo(Q_total, t, rho, mu)[0] for t in tramos)
            if hf_inicial is not None and math.isfinite(hf_inicial) and hf_inicial > 0:
                superior = max(superior, hf_inicial)
            raiz = biseccion(lambda h: sum(cls._caudal_para_acotar(h, t, rho, mu)
                for t in tramos) - Q_total, 0.0, superior, Q_total)
            hf = float(raiz)
        caudales = [cls._caudal_tramo(hf, t, rho, mu) for t in tramos]
        perdidas = [cls._perdida_tramo(q, t, rho, mu) for q, t in zip(caudales, tramos)]
        residuo_energia = max((abs(p[0] - hf) for p in perdidas), default=0.0)
        resultado = ResultadoTupla((hf, caudales, perdidas),
            iteraciones=0 if raiz is None else raiz.iteraciones,
            residuo_masa=sum(caudales) - Q_total, escala_masa=Q_total,
            residuo_energia=residuo_energia, escala_energia=hf)
        resultado.hf = hf
        resultado.direccion = 'Desde el nudo de entrada hacia el nudo de salida'
        resultado.caudales = caudales
        resultado.perdidas_tramos = perdidas
        return resultado.verificar()

    # ------------------------------------------------------------------
    # Tuberías ramificadas (Problema de los 3 Reservorios)
    # ------------------------------------------------------------------
    @classmethod
    @ejecucion
    def resolver_red_ramificada(cls, tramos, rho, mu, H_manual=None):
        """
        Resuelve una unión de tuberías ramificadas (p. ej. 3 reservorios) hallando la energía
        total Hj en la unión que cumple la continuidad: sum(Q que entran) = sum(Q que salen).

        Parámetros:
            tramos (list[dict]): un diccionario por tubería, todo en SI:
                {'tuberia': obj, 'H': float, 'L': float, 'D': float,
                 'eps': float, 'K': float, 'LeD': float}
                donde 'H' es la energía total del tanque extremo (Z + P/gamma, en m).
                Para un ramal compuesto, usar 'segmentos': lista completa de
                diccionarios L/D/eps/K/LeD. Su pérdida es la suma en serie a Q común.
            rho (float): Densidad del fluido (kg/m^3).
            mu (float): Viscosidad dinámica del fluido (Pa*s).
            H_manual (float | None): Energía supuesta en la unión (m).
                - None  -> Modo Automático: bisección iterativa sobre Hj.
                - float -> Modo Tanteo: una sola pasada con el valor del usuario.

        Retorna:
            tuple: (H_j, error_Q, resultados)
                error_Q = Q_entra - Q_sale (m^3/s); es 0 cuando se cumple la continuidad.
                resultados es una lista de {'tuberia', 'Q', 'direccion'}.
        """
        validar_fluido(rho,mu,cls.g)
        for tramo in tramos:
            validar_tramo(tramo,rho,mu,cls.g)
        if H_manual is not None:
            numero(H_manual,'H manual')
            # Modo Tanteo: una sola pasada con el valor del usuario
            return cls._evaluar_junta(tramos, rho, mu, H_manual)

        if not tramos:
            raise ValueError("Se requiere al menos un tramo.")

        # Modo Automático: bisección iterativa entre la menor y la mayor energía de los tanques
        H_max = max(t['H'] for t in tramos)
        H_min = min(t['H'] for t in tramos)

        for iteracion in range(1, 201):
            H_j = (H_max + H_min) / 2.0
            resultado = cls._evaluar_junta(tramos, rho, mu, H_j)
            H_j_calc, error_Q, resultados = resultado
            resultado.iteraciones = iteracion

            if resultado.convergio:
                return resultado

            if error_Q > 0:  # Entra más de lo que sale: Hj es muy baja
                H_min = H_j
            else:
                H_max = H_j

        return resultado

    @classmethod
    @ejecucion
    def _evaluar_junta(cls, tramos, rho, mu, H_j):
        """
        Evalúa la unión para una energía Hj dada: calcula el caudal de cada tubería con
        hf = |H - Hj| (inversión de Darcy) y el error de continuidad error_Q = Q_entra - Q_sale.
        Una tubería cuyo tanque tiene H > Hj aporta a la unión; si no, se lleva caudal de ella.
        """
        numero(H_j,'H de la unión')
        error_Q = 0.0
        resultados = []
        errores_energia = []
        cargas = []
        for t in tramos:
            hf = abs(t['H'] - H_j)
            Q = cls._caudal_tramo(hf, t, rho, mu)
            errores_energia.append(abs(cls._perdida_tramo(Q, t, rho, mu)[0] - hf))
            cargas.append(hf)
            if t['H'] > H_j:
                error_Q += Q
                resultados.append({'tuberia': t['tuberia'], 'Q': Q, 'direccion': 'Entra a la unión'})
            else:
                error_Q -= Q
                resultados.append({'tuberia': t['tuberia'], 'Q': Q, 'direccion': 'Sale de la unión'})
        resultado = ResultadoTupla((H_j, error_Q, resultados),
            residuo_masa=error_Q, escala_masa=sum(r['Q'] for r in resultados),
            residuo_energia=max(errores_energia, default=0.0),
            escala_energia=max(cargas, default=0.0))
        # Se comprueba además cada rama: una carga grande no oculta el error de otra.
        if any(q.residuo_energia_relativo > TOLERANCIA_RELATIVA for q in
               (r['Q'] for r in resultados)):
            resultado.estado = "SIN_CONVERGENCIA"
        return resultado

    # ------------------------------------------------------------------
    # Tuberías ramificadas: Doble Nudo (2 uniones j y k unidas por una tubería central)
    # ------------------------------------------------------------------
    @classmethod
    @ejecucion
    def resolver_doble_nudo(cls, tramos_j, tubo_central, tramos_k, rho, mu, H_manual=None):
        """Resuelve una red de Doble Nudo."""
        for tramo in tramos_j + [tubo_central] + tramos_k:
            validar_tramo(tramo,rho,mu,cls.g)
        if H_manual is not None:
            numero(H_manual,'H manual')
            return cls._evaluar_doble_nudo(tramos_j, tubo_central, tramos_k, rho, mu, H_manual)

        energias = [t['H'] for t in tramos_j] + [t['H'] for t in tramos_k]
        if not energias:
            raise ValueError("Se requieren tramos extremos para el doble nudo.")
        H_max = max(energias)
        H_min = min(energias)

        H_j_calc = H_k_calc = error_k = None
        resultados = []

        # PASO 8: El error (Diferencia de caudales en k) dirige la iteración:
        # si no es cero (dentro de 1e-8), variar Hj por bisección y repetir.
        for iteracion in range(1, 201):
            H_j = (H_max + H_min) / 2.0
            resultado = cls._evaluar_doble_nudo(
                tramos_j, tubo_central, tramos_k, rho, mu, H_j
            )
            H_j_calc, H_k_calc, error_k, resultados = resultado
            resultado.iteraciones = iteracion

            if resultado.convergio:
                break

            if error_k > 0:
                H_min = H_j
            else:
                H_max = H_j

        return resultado

    @classmethod
    @ejecucion
    def _evaluar_doble_nudo(cls, tramos_j, tubo_central, tramos_k, rho, mu, H_j):
        """
        Evalúa el Doble Nudo para una Hj dada siguiendo la secuencia estricta requerida.
        Devuelve (H_j, H_k, error_k, resultados); ver resolver_doble_nudo.
        """
        numero(H_j,'H de la unión')
        validar_tramo(tubo_central,rho,mu,cls.g)
        resultados = []

        # PASO 1: Suponer una altura piezométrica en la primera unión (H_j ya viene como argumento).

        # PASO 2: Calcular los caudales de las tuberías conectadas directamente a j usando Hj.
        Q_j_total = 0.0
        for t in tramos_j:
            hf = abs(t['H'] - H_j)
            Q = cls._caudal_tramo(hf, t, rho, mu)
            if t['H'] > H_j:
                Q_j_total += Q
                resultados.append({'tuberia': t['tuberia'], 'Q': Q, 'direccion': f"Entra al Nudo {t['id_nudo']}"})
            else:
                Q_j_total -= Q
                resultados.append({'tuberia': t['tuberia'], 'Q': Q, 'direccion': f"Sale del Nudo {t['id_nudo']}"})

        # PASO 3: Imponer continuidad en j para hallar el caudal en la tubería central (Q_3).
        Q_central_jk = Q_j_total

        # PASO 4: Con los datos del tubo central y Q_3, determinar su pérdida de carga (hf_3).
        if Q_central_jk == 0.0:
            hf_central = 0.0
        else:
            hf_central, _, _ = cls.calcular_hf(
                abs(Q_central_jk), tubo_central['L'], tubo_central['D'], rho, mu,
                tubo_central['eps'],
                sumatoria_Le_D=tubo_central['LeD'], sumatoria_K=tubo_central['K'],
            )

        # PASO 5: Calcular la altura piezométrica en k (Hk).
        if Q_central_jk > 0:
            H_k = H_j - hf_central
            dir_central = "De j a k"
        else:
            H_k = H_j + hf_central
            dir_central = "De k a j"

        resultados.append({'tuberia': tubo_central['tuberia'], 'Q': abs(Q_central_jk), 'direccion': dir_central})

        # PASO 6: Con Hk, calcular caudales de tuberías conectadas a k.
        Q_k_total = 0.0
        for t in tramos_k:
            hf = abs(t['H'] - H_k)
            Q = cls._caudal_tramo(hf, t, rho, mu)
            if t['H'] > H_k:
                Q_k_total += Q
                resultados.append({'tuberia': t['tuberia'], 'Q': Q, 'direccion': f"Entra al Nudo {t['id_nudo']}"})
            else:
                Q_k_total -= Q
                resultados.append({'tuberia': t['tuberia'], 'Q': Q, 'direccion': f"Sale del Nudo {t['id_nudo']}"})

        # PASO 7: Verificar continuidad en k.
        error_k = Q_central_jk + Q_k_total

        errores_energia = []
        cargas = []
        cargas_ramas = ([abs(t['H'] - H_j) for t in tramos_j] +
                        [abs(H_j - H_k)] + [abs(t['H'] - H_k) for t in tramos_k])
        for t, r, hf in zip(tramos_j + [tubo_central] + tramos_k, resultados, cargas_ramas):
            errores_energia.append(abs(cls._perdida_tramo(r['Q'], t, rho, mu)[0] - hf))
            cargas.append(hf)
        resultado = ResultadoTupla((H_j, H_k, error_k, resultados),
            residuo_masa=error_k,
            escala_masa=abs(Q_central_jk) + sum(r['Q'] for r in resultados[len(tramos_j) + 1:]),
            residuo_energia=max(errores_energia, default=0.0),
            escala_energia=max(cargas, default=0.0))
        # Continuidad en j y la energía del tubo central están impuestas por construcción.
        if any(isinstance(r['Q'], Metadatos) and not r['Q'].convergio for r in resultados):
            resultado.estado = "SIN_CONVERGENCIA"
        return resultado

    # ------------------------------------------------------------------
    # Tuberías en serie por energía (con o sin estación de bombeo)
    # ------------------------------------------------------------------
    @classmethod
    @ejecucion
    def resolver_serie_por_energia(
        cls,
        H_inicio,
        H_fin,
        tramos,
        rho,
        mu,
        H_j_manual=None,
        bomba=None,
        estacion=None,
        z_inicio=None,
        z_fin=None,
        P_inicio=0.0,
        P_fin=0.0,
        **kwargs,
    ):
        """
        Resuelve un sistema de tuberías en serie entre dos tanques.

        Si el circuito no contiene bomba, resuelve el flujo por gravedad mediante bisección sobre
        Q tal que la suma de pérdidas reales iguale H_inicio - H_fin.

        Si el circuito contiene bomba o estación de bombeo:
        - Construye H_sistema(Q) sumando la carga estática (ΔZ + ΔP/(ρ·g)) y las pérdidas hf(Q).
        - Evalúa f(0); si la bomba no vence la carga estática, detiene limpiamente el cálculo.
        - Resuelve el punto de operación con EstacionBombeo.H_estacion(Q) y punto_operacion().
        - Aplica el salto de energía (+H_total) una sola vez en el nodo de la estación en EGL/HGL.
        - Retorna un ResultadoResolucion compatible con tupla de 5 elementos.
        """
        if not tramos:
            raise ValueError("Se requiere al menos un tramo para resolver el sistema en serie.")
        for tramo in tramos:
            validar_tramo(tramo,rho,mu,cls.g)
        for nombre, valor in (('H_j_manual',H_j_manual),('z_inicio',z_inicio),('z_fin',z_fin),
                              ('P_inicio',P_inicio),('P_fin',P_fin)):
            if valor is not None:
                numero(valor,nombre)
        if not all(math.isfinite(h) for h in (H_inicio, H_fin)):
            raise ValueError("Las energías extremas deben ser finitas.")
        # La orientación declarada nunca se acepta como OK si está invertida,
        # incluso si el llamador suministra una bomba.
        if H_inicio < H_fin:
            return ResultadoResolucion(0.0, [], [], H_inicio, H_inicio - H_fin,
                estado="ORIENTACION_INVERTIDA",
                mensaje="H_inicio es menor que H_fin; invierta la orientación de la serie.",
                escala_energia=H_fin - H_inicio)

        # Identificar si hay bomba o estación en los argumentos o dentro de los tramos
        pump_obj = estacion if estacion is not None else bomba
        idx_bomba = kwargs.get("bomba_idx", None)

        if pump_obj is None:
            for idx, t in enumerate(tramos):
                cand = t.get("bomba") or t.get("estacion")
                if cand is not None:
                    pump_obj = cand
                    idx_bomba = idx
                    break
                nodo = t.get("nodo_salida")
                if nodo is not None and (
                    hasattr(nodo, "curvas")
                    or isinstance(nodo, (CurvaBomba, EstacionBombeo, CurvaSerie, CurvaParalelo))
                    or hasattr(nodo, "H_estacion")
                    or getattr(nodo, "tipo", "") == "bomba"
                ):
                    pump_obj = nodo
                    idx_bomba = idx
                    break

        # --------------------------------------------------------------
        # CASO 1: CIRCUITO SIN BOMBA
        # --------------------------------------------------------------
        if pump_obj is None:
            salto = H_inicio - H_fin
            estado = "OK"
            mensaje = ""
            def perdidas(q, registrar=False):
                return [cls._perdida_tramo(q, t, rho, mu, registrar) for t in tramos]

            if H_j_manual is not None:
                if not H_fin <= H_j_manual <= H_inicio:
                    return ResultadoResolucion(0.0, [], [], H_inicio, salto,
                        estado="TANTEO_INVALIDO", mensaje="Hj debe estar entre las energías extremas.",
                        escala_energia=salto)
                raiz = cls._caudal_tramo(H_inicio - H_j_manual, tramos[0], rho, mu)
            elif salto == 0:
                raiz = None
            else:
                superior = max(min(float(cls.calcular_Q_karman(salto, t['L'], t['D'],
                    rho, mu, t.get('eps', 0.0), t.get('K', 0.0), t.get('LeD', 0.0)))
                    for t in tramos), 1e-30)
                for _ in range(200):
                    if sum(p[0] for p in perdidas(superior)) >= salto:
                        break
                    superior *= 2
                try:
                    raiz = biseccion(lambda q: sum(p[0] for p in perdidas(q)) - salto,
                                     0.0, superior, salto)
                except ErrorConvergencia as error:
                    raiz = error.resultado
                    estado = "SIN_CONVERGENCIA"
                    mensaje = error.resultado.mensaje

            Q = 0.0 if raiz is None else float(raiz)
            cls.limpiar_iteraciones()
            perdidas_tramos = perdidas(Q, registrar=True)
            alturas_nodos = []
            H_actual = H_inicio
            for t, p in zip(tramos[:-1], perdidas_tramos[:-1]):
                H_actual -= p[0]
                alturas_nodos.append((t.get('nodo_salida'), H_actual))
            hf_total = sum(p[0] for p in perdidas_tramos)
            error_H = salto - hf_total
            resultado = ResultadoResolucion(Q, alturas_nodos, perdidas_tramos,
                H_inicio - hf_total, error_H,
                iteraciones=0 if raiz is None else raiz.iteraciones, escala_energia=salto,
                estado=estado, mensaje=mensaje)
            if not resultado.convergio and H_j_manual is not None:
                resultado.mensaje = "El tanteo no satisface el balance de energía a 1e-8 relativo."
            return resultado

        # --------------------------------------------------------------
        # CASO 2: CIRCUITO CON BOMBA O ESTACIÓN DE BOMBEO
        # --------------------------------------------------------------
        # 1. Comprobar si la bomba carece de curvas (estado SIN_CURVA)
        curvas_bomba = getattr(pump_obj, "curvas", None)
        if hasattr(pump_obj, "curvas") and (curvas_bomba is None or len(curvas_bomba) == 0):
            return ResultadoResolucion(
                0.0, [], [], float(H_inicio), float(H_inicio - H_fin),
                estado="SIN_CURVA",
                mensaje="Falta ingresar la curva de la bomba",
                bomba_info=pump_obj,
            )
        if isinstance(pump_obj, (list, tuple)) and len(pump_obj) == 0:
            return ResultadoResolucion(
                0.0, [], [], float(H_inicio), float(H_inicio - H_fin),
                estado="SIN_CURVA",
                mensaje="Falta ingresar la curva de la bomba",
                bomba_info=pump_obj,
            )

        # 2. Construir objeto EstacionBombeo equivalente
        if isinstance(pump_obj, EstacionBombeo):
            estacion_calc = pump_obj
        elif hasattr(pump_obj, "curvas") and pump_obj.curvas:
            arr = getattr(pump_obj, "arreglo", "individual")
            if arr == "serie":
                estacion_calc = EstacionBombeo.en_serie(pump_obj.curvas)
            elif arr == "paralelo":
                estacion_calc = EstacionBombeo.en_paralelo(pump_obj.curvas)
            else:
                estacion_calc = EstacionBombeo.en_paralelo([pump_obj.curvas[0]])
        elif isinstance(pump_obj, CurvaSerie):
            estacion_calc = EstacionBombeo.en_serie(pump_obj.bombas)
        elif isinstance(pump_obj, CurvaParalelo):
            estacion_calc = EstacionBombeo.en_paralelo(pump_obj.bombas)
        elif isinstance(pump_obj, CurvaBomba):
            estacion_calc = EstacionBombeo.en_paralelo([pump_obj])
        elif isinstance(pump_obj, (list, tuple)):
            estacion_calc = EstacionBombeo.en_paralelo(pump_obj)
        else:
            estacion_calc = pump_obj

        # 3. Carga estática del circuito Y = ΔZ + ΔP/(ρ·g)
        grav = getattr(cls, "g", 9.81)
        if z_inicio is not None and z_fin is not None:
            Y = float((z_fin - z_inicio) + (P_fin - P_inicio) / (rho * grav))
        else:
            Y = float(H_fin - H_inicio)

        # Formateador de números para mensajes de error
        def _fmt(val):
            return f"{int(round(val))}" if abs(val - round(val)) < 1e-4 else f"{val:.2f}"

        # 4. Evaluar f(0) antes de buscar raíces
        X = float(estacion_calc.H_estacion(0.0))
        if X <= Y:
            return ResultadoResolucion(
                0.0, [], [], float(H_inicio), float(H_inicio - H_fin),
                estado="NO_ALCANZA_ALTURA_ESTATICA",
                mensaje=f"La bomba no alcanza a vencer la altura estática del circuito (H de cierre = {_fmt(X)} m < carga estática = {_fmt(Y)} m).",
                bomba_info=pump_obj,
            )

        # 5. Construir H_sistema(Q) con las pérdidas de carga en succión y descarga
        if "H_sistema_de_Q" in kwargs and kwargs["H_sistema_de_Q"] is not None:
            H_sistema = kwargs["H_sistema_de_Q"]
        else:
            def H_sistema(q):
                if q <= 0.0:
                    return float(Y)
                hf_total = 0.0
                for t in tramos:
                    L_t = t.get("L", 0.0)
                    D_t = t.get("D", 0.0)
                    if L_t > 0.0 and D_t > 0.0:
                        hf_tramo, _, _ = cls.calcular_hf(
                            abs(q), L_t, D_t, rho, mu, t.get("eps", 0.0),
                            sumatoria_Le_D=t.get("LeD", 0.0),
                            sumatoria_K=t.get("K", 0.0),
                            registrar=False,
                        )
                        hf_total += hf_tramo
                return float(Y + hf_total)

        # 6. Resolver punto de operación
        evaluaciones = 0

        def sistema_contado(q):
            nonlocal evaluaciones
            evaluaciones += 1
            return H_sistema(q)

        res_bombeo = punto_operacion(estacion_calc, sistema_contado, rho=rho, g=grav)

        if res_bombeo.estado == "NO_ALCANZA_ALTURA_ESTATICA":
            return ResultadoResolucion(
                0.0, [], [], float(H_inicio), float(H_inicio - H_fin),
                estado="NO_ALCANZA_ALTURA_ESTATICA",
                mensaje=f"La bomba no alcanza a vencer la altura estática del circuito (H de cierre = {_fmt(X)} m < carga estática = {_fmt(Y)} m).",
                bomba_info=pump_obj,
                resultado_bombeo=res_bombeo,
            )

        if res_bombeo.estado == "FUERA_DE_RANGO_CURVA":
            return ResultadoResolucion(
                float(res_bombeo.Q), [], [], float(H_inicio), float(H_inicio - H_fin),
                estado="FUERA_DE_RANGO_CURVA",
                mensaje="El punto de operación excede el caudal máximo de la curva de la bomba",
                bomba_info=pump_obj,
                resultado_bombeo=res_bombeo,
            )

        # 7. Cálculo del salto de energía único en el nodo de la bomba en EGL/HGL
        Q_op = float(res_bombeo.Q)
        H_total = float(res_bombeo.H_total)

        perdidas_tramos = []
        alturas_nodos = []
        H_actual = float(H_inicio)
        salto_aplicado = False

        for i, t in enumerate(tramos):
            L_t = t.get("L", 0.0)
            D_t = t.get("D", 0.0)
            if L_t > 0.0 and D_t > 0.0:
                hf_i, hf_dist_i, hf_loc_i = cls.calcular_hf(
                    Q_op, L_t, D_t, rho, mu, t.get("eps", 0.0),
                    sumatoria_Le_D=t.get("LeD", 0.0),
                    sumatoria_K=t.get("K", 0.0),
                    registrar=True,
                )
            else:
                hf_i = hf_dist_i = hf_loc_i = 0.0

            perdidas_tramos.append((hf_i, hf_dist_i, hf_loc_i))
            H_actual = H_actual - hf_i

            nodo_salida = t.get("nodo_salida")
            es_nodo_bomba = (
                (idx_bomba is not None and i == idx_bomba)
                or (nodo_salida is not None and (
                    nodo_salida is pump_obj
                    or hasattr(nodo_salida, "curvas")
                    or getattr(nodo_salida, "tipo", "") == "bomba"
                ))
            )

            # Aplicar el salto de energía UNA SOLA VEZ en el nodo de la estación
            if es_nodo_bomba and not salto_aplicado:
                H_actual = H_actual + H_total
                salto_aplicado = True

            if i < len(tramos) - 1:
                alturas_nodos.append((nodo_salida, H_actual))

        # En caso de que no haya nodo explícito de bomba, aplicar el salto en la unión intermedia
        if not salto_aplicado:
            if len(alturas_nodos) > 0:
                for k in range(len(alturas_nodos)):
                    alturas_nodos[k] = (alturas_nodos[k][0], alturas_nodos[k][1] + H_total)
            H_actual = H_actual + H_total
            salto_aplicado = True

        H_fin_calculada = H_actual
        error_H = (H_inicio - H_fin) + H_total - sum(p[0] for p in perdidas_tramos)

        resultado = ResultadoResolucion(
            Q_op,
            alturas_nodos,
            perdidas_tramos,
            H_fin_calculada,
            error_H,
            estado="OK",
            mensaje="Punto de operación encontrado con éxito.",
            bomba_info=pump_obj,
            resultado_bombeo=res_bombeo,
            iteraciones=max(0, evaluaciones - 2),
            escala_energia=max(abs(H_total), abs(Y), sum(p[0] for p in perdidas_tramos)),
        )
        if not resultado.convergio:
            resultado.mensaje = "El punto de operación no satisface el balance de energía a 1e-8 relativo."
        return resultado

    @staticmethod
    def _resolver_sistema_lineal(matriz, vector):
        """Eliminación gaussiana con pivoteo parcial para matriz cuadrada NxN."""
        n = len(vector)
        aug = [list(matriz[i]) + [float(vector[i])] for i in range(n)]
        for col in range(n):
            pivote = max(range(col, n), key=lambda r: abs(aug[r][col]))
            if abs(aug[pivote][col]) <= 0.0:
                raise ValueError(
                    "El sistema nodal es singular (verifique conectividad con reservorios)."
                )
            if pivote != col:
                aug[col], aug[pivote] = aug[pivote], aug[col]
            inv_p = 1.0 / aug[col][col]
            for j in range(col, n + 1):
                aug[col][j] *= inv_p
            for r in range(n):
                if r != col and aug[r][col] != 0.0:
                    factor = aug[r][col]
                    for j in range(col, n + 1):
                        aug[r][j] -= factor * aug[col][j]
        return [aug[i][n] for i in range(n)]

    @classmethod
    def resolver_red_ramificada_multinudo(
        cls,
        nodos_internos,
        terminales,
        tramos,
        rho,
        mu,
        H_iniciales=None,
        max_iteraciones=200,
    ):
        """Resuelve el equilibrio estacionario de una red ramificada con múltiples nudos internos.

        Args:
            nodos_internos: Secuencia ordenada de identificadores/objetos hashables de nudos internos.
            terminales: Mapeo {id_terminal: cota_piezometrica_H_m} con al menos 2 reservorios.
            tramos: Lista de dicts de macro-tramos con llaves 'origen', 'destino' y parámetros SI
                    ('L', 'D', 'eps', 'K', 'LeD') o lista 'segmentos'.
            rho: Densidad [kg/m³].
            mu: Viscosidad dinámica [Pa·s].
            H_iniciales: Opcional dict {nodo: H_semilla}.
            max_iteraciones: Máximo de iteraciones Newton / coordenada.

        Returns:
            ResultadoTupla((H_nodos, resultados_tramos), ...) con verificación de balances.
        """
        from motor.numerica import TOLERANCIA_INTERNA

        numero(rho, "densidad rho", minimo=0, estricto=True)
        numero(mu, "viscosidad mu", minimo=0, estricto=True)

        nodos = list(nodos_internos)
        if not nodos:
            raise ValueError("Se requiere al menos un nudo interno para resolver la red.")
        if len(set(nodos)) != len(nodos):
            raise ValueError("Existen nudos internos duplicados en la definición de la red.")

        if not isinstance(terminales, dict) or len(terminales) < 2:
            raise ValueError("Se requieren al menos dos reservorios terminales con energía conocida.")
        terminales_h = {
            tid: numero(val, f"energía terminal H({tid})")
            for tid, val in terminales.items()
        }
        if set(nodos) & set(terminales_h):
            raise ValueError("Un nodo no puede ser simultáneamente nudo interno y terminal.")

        tramos_lista = list(tramos)
        if not tramos_lista:
            raise ValueError("La red no contiene tramos de conducción.")

        todos_vertices = set(nodos) | set(terminales_h)
        adyacencia = {v: [] for v in todos_vertices}
        for idx_t, t in enumerate(tramos_lista):
            u = t.get("origen")
            v = t.get("destino")
            if u not in todos_vertices or v not in todos_vertices:
                raise ValueError(f"Tramo #{idx_t + 1} referencia un extremo desconocido.")
            if u is v or u == v:
                raise ValueError(f"Tramo #{idx_t + 1} une un nodo consigo mismo.")
            # Validar parámetros hidráulicos antes de iterar
            cls._perdida_tramo(0.0, t, rho, mu, registrar=False)
            adyacencia[u].append(v)
            adyacencia[v].append(u)

        # Comprobar que cada nudo interno alcanza algún terminal con energía fija
        visitados = set(terminales_h)
        cola = list(terminales_h)
        for v in cola:
            for nb in adyacencia[v]:
                if nb not in visitados:
                    visitados.add(nb)
                    cola.append(nb)
        if not set(nodos).issubset(visitados):
            raise ValueError("Hay nudos internos desconectados de los reservorios terminales.")

        K = len(nodos)
        idx_nodo = {n: i for i, n in enumerate(nodos)}
        h_vals = list(terminales_h.values())
        H_min = min(h_vals)
        H_max = max(h_vals)
        dH_escala = max(H_max - H_min, 1.0)

        def cabeza(vertice, H_vec):
            pos = idx_nodo.get(vertice)
            return H_vec[pos] if pos is not None else terminales_h[vertice]

        def flujo_dirigido(t, dH):
            if dH == 0.0:
                return 0.0
            q_mag = float(cls._caudal_tramo(abs(dH), t, rho, mu))
            return math.copysign(q_mag, dH)

        def evaluar_nodal(H_vec):
            F = [0.0] * K
            throughput = [0.0] * K
            q_edges = []
            for t in tramos_lista:
                dH = cabeza(t["origen"], H_vec) - cabeza(t["destino"], H_vec)
                q = flujo_dirigido(t, dH)
                q_edges.append(q)
                iu = idx_nodo.get(t["origen"])
                iv = idx_nodo.get(t["destino"])
                if iu is not None:
                    F[iu] += q
                    throughput[iu] += abs(q)
                if iv is not None:
                    F[iv] -= q
                    throughput[iv] += abs(q)
            return F, q_edges, throughput

        if H_max == H_min:
            H = [H_min] * K
            F, q_edges, throughput = evaluar_nodal(H)
            iter_real = 0
            estado_sol = "OK"
            mensaje_sol = "Equilibrio hidrostático (sin salto piezométrico)."
        else:
            # Inicialización mediante sistema lineal SPD de conductancias secantes características
            dH_char = max((H_max - H_min) / max(K, 1), 0.1)
            A0 = [[0.0] * K for _ in range(K)]
            b0 = [0.0] * K
            for t in tramos_lista:
                g_lin = float(cls._caudal_tramo(dH_char, t, rho, mu)) / dH_char
                g_lin = max(g_lin, 1e-18)
                u, v = t["origen"], t["destino"]
                iu, iv = idx_nodo.get(u), idx_nodo.get(v)
                if iu is not None:
                    A0[iu][iu] += g_lin
                    if iv is not None:
                        A0[iu][iv] -= g_lin
                    else:
                        b0[iu] += g_lin * terminales_h[v]
                if iv is not None:
                    A0[iv][iv] += g_lin
                    if iu is not None:
                        A0[iv][iu] -= g_lin
                    else:
                        b0[iv] += g_lin * terminales_h[u]
            H = cls._resolver_sistema_lineal(A0, b0)
            H = [min(H_max, max(H_min, val)) for val in H]
            if isinstance(H_iniciales, dict):
                for n, val in H_iniciales.items():
                    if n in idx_nodo and val is not None:
                        v_num = numero(val, f"H_inicial({n})")
                        H[idx_nodo[n]] = min(H_max, max(H_min, v_num))

            # Pre-indexar aristas incidentes para eventual barrido coordenado monótono
            incidentes = [[] for _ in range(K)]
            for t in tramos_lista:
                u, v = t["origen"], t["destino"]
                if u in idx_nodo:
                    incidentes[idx_nodo[u]].append((t, v, 1.0))
                if v in idx_nodo:
                    incidentes[idx_nodo[v]].append((t, u, -1.0))

            iter_real = 0
            estado_sol = "OK"
            mensaje_sol = ""

            for it in range(1, max_iteraciones + 1):
                F, q_edges, throughput = evaluar_nodal(H)
                activos = [0.5 * tp for tp in throughput if tp > 0.0]
                escala_local = min(activos) if activos else 0.0
                norm_inf = max((abs(x) for x in F), default=0.0)
                if (escala_local == 0.0 and norm_inf == 0.0) or (
                    escala_local > 0.0 and norm_inf <= TOLERANCIA_INTERNA * escala_local
                ):
                    break

                iter_real = it
                norm2 = math.hypot(*F) if K > 1 else abs(F[0])

                # Jacobiano tangente SPD: J_ij = dF_i/dH_j
                J = [[0.0] * K for _ in range(K)]
                for t, q in zip(tramos_lista, q_edges):
                    u, v = t["origen"], t["destino"]
                    dH_abs = abs(cabeza(u, H) - cabeza(v, H))
                    delta = max(1e-6 * dH_abs, 1e-7 * dH_escala)
                    q_plus = float(cls._caudal_tramo(dH_abs + delta, t, rho, mu))
                    g_tan = (q_plus - abs(q)) / delta
                    if not math.isfinite(g_tan) or g_tan <= 0.0:
                        g_tan = max(float(cls._caudal_tramo(delta, t, rho, mu)) / delta, 1e-18)
                    iu, iv = idx_nodo.get(u), idx_nodo.get(v)
                    if iu is not None:
                        J[iu][iu] += g_tan
                        if iv is not None:
                            J[iu][iv] -= g_tan
                    if iv is not None:
                        J[iv][iv] += g_tan
                        if iu is not None:
                            J[iv][iu] -= g_tan

                paso = cls._resolver_sistema_lineal(J, [-x for x in F])

                acepto = False
                alpha = 1.0
                for _ in range(12):
                    H_cand = [
                        min(H_max, max(H_min, H[i] + alpha * paso[i]))
                        for i in range(K)
                    ]
                    F_cand, _, _ = evaluar_nodal(H_cand)
                    norm2_cand = math.hypot(*F_cand) if K > 1 else abs(F_cand[0])
                    if norm2_cand < norm2 * (1.0 - 1e-4 * alpha) or norm2_cand < norm2 * 0.999:
                        H = H_cand
                        acepto = True
                        break
                    alpha *= 0.5

                if not acepto:
                    # Respaldo por barrido coordenado monótono (bisección por nudo)
                    mejor_cambio = False
                    for i in range(K):
                        vecinos = incidentes[i]

                        def _residuo_i(h_val, lista=vecinos):
                            total_out = 0.0
                            for tr_e, otro_v, _ in lista:
                                h_otro = cabeza(otro_v, H)
                                total_out += flujo_dirigido(tr_e, h_val - h_otro)
                            return total_out

                        fa = _residuo_i(H_min)
                        fb = _residuo_i(H_max)
                        esc_i = max(0.5 * throughput[i], abs(fa), abs(fb), 1e-12)
                        if abs(fa) <= TOLERANCIA_INTERNA * esc_i:
                            h_nuevo = H_min
                        elif abs(fb) <= TOLERANCIA_INTERNA * esc_i:
                            h_nuevo = H_max
                        else:
                            try:
                                r_bis = biseccion(
                                    _residuo_i,
                                    H_min,
                                    H_max,
                                    esc_i,
                                    tolerancia=TOLERANCIA_INTERNA,
                                )
                                h_nuevo = float(r_bis)
                            except ErrorConvergencia as err:
                                h_nuevo = float(err.resultado)
                        if abs(h_nuevo - H[i]) > 1e-15:
                            mejor_cambio = True
                        H[i] = h_nuevo
                    if not mejor_cambio:
                        break
            else:
                F, q_edges, throughput = evaluar_nodal(H)
                activos = [0.5 * tp for tp in throughput if tp > 0.0]
                escala_tmp = min(activos) if activos else 0.0
                norm_tmp = max((abs(x) for x in F), default=0.0)
                if escala_tmp > 0.0 and norm_tmp > TOLERANCIA_RELATIVA * escala_tmp:
                    estado_sol = "SIN_CONVERGENCIA"
                    mensaje_sol = (
                        "La red multi-nudo no alcanzó equilibrio dentro del límite de iteraciones."
                    )

        # Evaluación final registrada e historial de resultados por tramo
        cls.limpiar_iteraciones()
        F, q_edges, throughput = evaluar_nodal(H)
        H_nodos = {n: float(H[idx_nodo[n]]) for n in nodos}
        resultados_tramos = []
        residuo_energia = 0.0
        max_hf = 0.0

        for t, q_signed in zip(tramos_lista, q_edges):
            u, v = t["origen"], t["destino"]
            H_u = H_nodos[u] if u in H_nodos else terminales_h[u]
            H_v = H_nodos[v] if v in H_nodos else terminales_h[v]
            q_mag = abs(q_signed)

            if "segmentos" in t and t["segmentos"]:
                perdidas_segs = [
                    cls._perdida_tramo(q_mag, s, rho, mu, registrar=True)
                    for s in t["segmentos"]
                ]
                hf_t = sum(p[0] for p in perdidas_segs)
                hf_dist = sum(p[1] for p in perdidas_segs)
                hf_loc = sum(p[2] for p in perdidas_segs)
            else:
                hf_t, hf_dist, hf_loc = cls._perdida_tramo(
                    q_mag, t, rho, mu, registrar=True
                )
                perdidas_segs = [(hf_t, hf_dist, hf_loc)]

            max_hf = max(max_hf, hf_t)
            residuo_energia = max(residuo_energia, abs(abs(H_u - H_v) - hf_t))

            flujo_ori = u if H_u >= H_v else v
            flujo_des = v if H_u >= H_v else u
            res_item = {
                "origen": u,
                "destino": v,
                "flujo_origen": flujo_ori,
                "flujo_destino": flujo_des,
                "Q": float(q_mag),
                "Q_con_signo": float(q_signed),
                "hf": float(hf_t),
                "hf_dist": float(hf_dist),
                "hf_loc": float(hf_loc),
                "perdidas_segmentos": perdidas_segs,
                "H_origen": float(H_u),
                "H_destino": float(H_v),
                "direccion": f"De {getattr(flujo_ori, 'nombre', flujo_ori)} a {getattr(flujo_des, 'nombre', flujo_des)}",
            }
            if "segmentos" in t:
                res_item["segmentos"] = t["segmentos"]
            if "tuberia" in t:
                res_item["tuberia"] = t["tuberia"]
            if "meta" in t:
                res_item["meta"] = t["meta"]
            resultados_tramos.append(res_item)

        residuo_masa = max((abs(x) for x in F), default=0.0)
        activos_fin = [0.5 * tp for tp in throughput if tp > 0.0]
        escala_masa = min(activos_fin) if activos_fin else 0.0
        escala_energia = max(dH_escala, max_hf)

        return ResultadoTupla(
            (H_nodos, resultados_tramos),
            iteraciones=iter_real,
            residuo_masa=residuo_masa,
            residuo_energia=residuo_energia,
            escala_masa=escala_masa,
            escala_energia=escala_energia,
            estado=estado_sol,
            mensaje=mensaje_sol,
        )

    @classmethod
    def _sp_validar_bloque(cls, bloque, rho, mu):
        tipo = bloque.get("tipo")
        if tipo == "tramo":
            cls._perdida_tramo(0.0, bloque, rho, mu, registrar=False)
            return
        if tipo == "serie":
            hijos = bloque.get("hijos") or []
            if not hijos:
                raise ValueError("El bloque en serie no contiene sub-tramos.")
            for h in hijos:
                cls._sp_validar_bloque(h, rho, mu)
            return
        if tipo == "paralelo":
            ramas = bloque.get("ramas") or []
            if len(ramas) < 2:
                raise ValueError("El bloque en paralelo requiere al menos dos ramas.")
            for r in ramas:
                cls._sp_validar_bloque(r, rho, mu)
            return
        raise ValueError(f"Tipo de bloque serie-paralelo desconocido: {tipo!r}")

    @classmethod
    def _sp_caudal(cls, bloque, hf, rho, mu):
        """Retorna (Q_float, iteraciones) para un bloque serie-paralelo dada pérdida hf >= 0."""
        from motor.numerica import TOLERANCIA_INTERNA

        if hf <= 0.0:
            return 0.0, 0
        tipo = bloque["tipo"]
        if tipo == "tramo":
            return float(cls._caudal_tramo(hf, bloque, rho, mu)), 0
        if tipo == "paralelo":
            q_tot = 0.0
            iters = 0
            for r in bloque["ramas"]:
                q_r, it_r = cls._sp_caudal(r, hf, rho, mu)
                q_tot += q_r
                iters += it_r
            return q_tot, iters
        if tipo == "serie":
            hijos = bloque["hijos"]
            if all(h["tipo"] == "tramo" and "segmentos" not in h for h in hijos):
                return float(cls._caudal_tramo(hf, {"segmentos": hijos}, rho, mu)), 0
            upper = min(cls._sp_caudal(h, hf, rho, mu)[0] for h in hijos)
            if upper <= 0.0:
                return 0.0, 0
            raiz = biseccion(
                lambda q: cls._sp_perdida(bloque, q, rho, mu)[0] - hf,
                0.0,
                upper,
                hf,
                tolerancia=TOLERANCIA_INTERNA,
            )
            return float(raiz), int(raiz.iteraciones)
        raise ValueError(f"Tipo de bloque desconocido: {tipo!r}")

    @classmethod
    def _sp_perdida(cls, bloque, Q, rho, mu):
        """Retorna (hf_float, iteraciones) para un bloque serie-paralelo dado caudal Q >= 0."""
        from motor.numerica import TOLERANCIA_INTERNA

        if Q <= 0.0:
            return 0.0, 0
        tipo = bloque["tipo"]
        if tipo == "tramo":
            hf_t, _, _ = cls._perdida_tramo(Q, bloque, rho, mu, registrar=False)
            return float(hf_t), 0
        if tipo == "serie":
            hf_tot = 0.0
            iters = 0
            for h in bloque["hijos"]:
                hf_h, it_h = cls._sp_perdida(h, Q, rho, mu)
                hf_tot += hf_h
                iters += it_h
            return hf_tot, iters
        if tipo == "paralelo":
            ramas = bloque["ramas"]
            # Cota superior garantizada mediante duplicación desde hf inicial positivo
            hf_hi = 1.0
            hojas = [r for r in ramas if r["tipo"] == "tramo"]
            if hojas:
                hf_hi = max(min(float(cls._perdida_tramo(Q, h, rho, mu)[0]) for h in hojas), 1e-6)
            for _ in range(200):
                if cls._sp_caudal(bloque, hf_hi, rho, mu)[0] >= Q:
                    break
                hf_hi *= 2.0
            raiz = biseccion(
                lambda h: cls._sp_caudal(bloque, h, rho, mu)[0] - Q,
                0.0,
                hf_hi,
                Q,
                tolerancia=TOLERANCIA_INTERNA,
            )
            return float(raiz), int(raiz.iteraciones)
        raise ValueError(f"Tipo de bloque desconocido: {tipo!r}")

    @classmethod
    def resolver_paralelo_serie(
        cls,
        bloque_raiz,
        rho,
        mu,
        Q_total=None,
        H_disponible=None,
        H_inicio=None,
    ):
        """Resuelve una red descomponible en bloques Serie y Paralelo.

        Admitedos modos mutuamente excluyentes:
        - Caudal total impuesto ``Q_total`` (calcula pérdida total ``hf`` y reparto).
        - Salto energético disponible ``H_disponible`` (calcula ``Q_total`` y reparto).

        Returns:
            ResultadoTupla((Q_total, hf_total, resultados_tramos, H_nodos), ...).
        """
        numero(rho, "densidad rho", minimo=0, estricto=True)
        numero(mu, "viscosidad mu", minimo=0, estricto=True)
        if (Q_total is None) == (H_disponible is None):
            raise ValueError("Debe especificarse exactamente uno de Q_total o H_disponible.")

        cls._sp_validar_bloque(bloque_raiz, rho, mu)

        if Q_total is not None:
            q_val = numero(Q_total, "Q_total", minimo=0.0)
            hf_val, iters = cls._sp_perdida(bloque_raiz, q_val, rho, mu)
        else:
            h_disp = numero(H_disponible, "H_disponible")
            if h_disp < 0.0:
                return ResultadoTupla(
                    (0.0, 0.0, [], {}),
                    estado="ORIENTACION_INVERTIDA",
                    mensaje="H_inicio es menor que H_fin; el flujo no ocurre por gravedad en ese sentido.",
                    escala_energia=abs(h_disp),
                )
            hf_val = float(h_disp)
            q_val, iters = cls._sp_caudal(bloque_raiz, hf_val, rho, mu)

        cls.limpiar_iteraciones()
        resultados_tramos = []
        H_nodos = {}
        h_ref_ini = float(H_inicio) if H_inicio is not None else float(hf_val)
        residuos_masa = [0.0]
        residuos_energia = [0.0]

        def _propagar(bloque, q_b, hf_b, h_in):
            ori_b = bloque.get("origen")
            des_b = bloque.get("destino")
            if ori_b is not None and not isinstance(ori_b, type(None)):
                pass
            tipo = bloque["tipo"]
            if tipo == "tramo":
                hf_t, dist_t, loc_t = cls._perdida_tramo(q_b, bloque, rho, mu, registrar=True)
                residuos_energia.append(abs(hf_t - hf_b))
                item = {
                    "bloque": bloque,
                    "origen": ori_b,
                    "destino": des_b,
                    "Q": float(q_b),
                    "hf": float(hf_t),
                    "hf_dist": float(dist_t),
                    "hf_loc": float(loc_t),
                    "H_entrada": float(h_in),
                    "H_salida": float(h_in - hf_t),
                }
                if "tuberia" in bloque:
                    item["tuberia"] = bloque["tuberia"]
                resultados_tramos.append(item)
                return float(hf_t)
            if tipo == "serie":
                h_curr = h_in
                hf_acum = 0.0
                hijos = bloque["hijos"]
                for idx_h, hijo in enumerate(hijos):
                    if idx_h > 0 and hijo.get("origen") is not None:
                        H_nodos[hijo["origen"]] = float(h_curr)
                    hf_h, _ = cls._sp_perdida(hijo, q_b, rho, mu)
                    hf_real_h = _propagar(hijo, q_b, hf_h, h_curr)
                    h_curr -= hf_real_h
                    hf_acum += hf_real_h
                    if hijo.get("destino") is not None and idx_h < len(hijos) - 1:
                        H_nodos[hijo["destino"]] = float(h_curr)
                residuos_energia.append(abs(hf_acum - hf_b))
                return hf_acum
            if tipo == "paralelo":
                ramas = bloque["ramas"]
                q_ramas = []
                for r in ramas:
                    q_r, _ = cls._sp_caudal(r, hf_b, rho, mu)
                    q_ramas.append(q_r)
                    hf_real_r = _propagar(r, q_r, hf_b, h_in)
                    residuos_energia.append(abs(hf_real_r - hf_b))
                residuos_masa.append(abs(q_b - sum(q_ramas)))
                return float(hf_b)
            raise ValueError(f"Tipo de bloque desconocido: {tipo!r}")

        hf_final = _propagar(bloque_raiz, float(q_val), float(hf_val), h_ref_ini)
        # Filtrar para conservar únicamente nudos internos explícitos si el bloque trae extremos terminales
        ori_raiz = bloque_raiz.get("origen")
        des_raiz = bloque_raiz.get("destino")
        if ori_raiz is not None:
            H_nodos.pop(ori_raiz, None)
        if des_raiz is not None:
            H_nodos.pop(des_raiz, None)

        return ResultadoTupla(
            (float(q_val), float(hf_final), resultados_tramos, H_nodos),
            iteraciones=iters,
            residuo_masa=max(residuos_masa),
            residuo_energia=max(residuos_energia),
            escala_masa=float(q_val),
            escala_energia=max(float(hf_final), 0.0),
            estado="OK",
            mensaje="Equilibrio serie-paralelo alcanzado.",
        )


