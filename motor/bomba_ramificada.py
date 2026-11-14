"""Resolución de redes ramificadas alimentadas por bombas centrífugas (Bomba + Red Ramificada).

Basado en la formulación de continuidad e iteración de alturas piezométricas:
1. Suponer un caudal de bomba Q_B.
2. Determinar la carga manométrica H_B(Q_B) y la pérdida hf_1 en la conducción de impulsión/succión.
3. Calcular la altura piezométrica en el nudo j: H_j = H_tanque1 + H_B - hf_1.
4. Con H_j, calcular los caudales de cada ramal conectado al nudo j mediante Darcy-Weisbach y Kármán.
5. Evaluar la ecuación de continuidad en el nudo: error_Q = Q_entran - Q_salen.
6. Si error_Q > 0, reducir Q_B; si error_Q < 0, aumentar Q_B, hasta |error_Q| < tol.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from motor.bombas import (CurvaBomba, CurvaSerie, CurvaParalelo, EstacionBombeo,
                          BombaDesglose, evaluar_operacion_estacion,
                          _calcular_desglose, _potencias_desglose, npsh_disponible)
from motor.hidraulica import evaluar_tramo
from motor.ejecucion import ejecucion
from motor.validacion import numero, caudal, fluido as validar_fluido, tramo as validar_tramo
from motor.numerica import Metadatos, TOLERANCIA_RELATIVA


class CurvaSistemaRamificada(list, Metadatos):
    """Lista compatible de (Q≥0,H), con residuos y estado de su propia resolución."""
    def __init__(self):
        super().__init__()
        self.balances()
        self.diagnosticos = []


class ResultadoBombaRamificada(Metadatos):
    """
    Contenedor de resultados del cálculo de una red ramificada con bomba.
    Ofrece acceso por atributos y como diccionario (compatible con el resto del simulador).
    """

    def __init__(
        self,
        Q_bomba: float,
        H_bomba: float,
        H_j: float,
        error_Q: float,
        resultados_ramales: List[Dict[str, Any]],
        tramo_bomba_resultado: Dict[str, Any],
        iteraciones: List[Dict[str, Any]],
        convergio: bool,
        estado: str = "OK",
        mensaje: str = "Cálculo completado con éxito.",
        curva_sistema: Optional[List[Tuple[float, float]]] = None,
        ecuacion_continuidad: str = "",
        potencia_hidraulica: Optional[float] = None,
        potencia_freno: Optional[float] = None,
        eta: Optional[float] = None,
        npsh_r: Optional[float] = None,
        npsh_d: Optional[float] = None,
        cavitacion: Optional[bool] = None,
        desglose=None,
        hf_succion=None,
        estacion_resultado=None,
        resultados_tramos_principal=(),
        Q_ref=0.0,
        tol=TOLERANCIA_RELATIVA,
    ):
        self.Q_bomba = float(Q_bomba)
        self.direccion = 'Desde la aspiración de la bomba hacia la unión'
        self.H_bomba = float(H_bomba)
        self.H_j = float(H_j)
        self.error_Q = float(error_Q)
        self.resultados_ramales = list(resultados_ramales)
        self.tramo_bomba_resultado = dict(tramo_bomba_resultado)
        self.historial = list(iteraciones)
        self.iteraciones = len(self.historial)
        self.estado = str(estado)
        self.mensaje = str(mensaje)
        self.curva_sistema = curva_sistema or []
        self.ecuacion_continuidad = str(ecuacion_continuidad)
        self.potencia_hidraulica = potencia_hidraulica
        self.potencia_freno = potencia_freno
        self.eta = eta
        self.npsh_r = npsh_r
        self.npsh_d = npsh_d
        self.cavitacion = cavitacion
        self.desglose = list(desglose or [])
        self.hf_succion = hf_succion
        self.estacion_resultado = estacion_resultado
        self.resultados_tramos_principal = tuple(resultados_tramos_principal)
        self.Q_ref = float(Q_ref)
        self.tolerancia_relativa = tol
        self.tolerancia_absoluta = max(1e-15, tol*max(abs(self.Q_bomba),self.Q_ref))
        errores = [abs(sum(p[0] for p in r.get('perdidas_segmentos', []))-r['hf'])
                   for r in resultados_ramales if 'perdidas_segmentos' in r]
        energia = max(errores,default=0.0)
        escala_h = max([abs(H_bomba)] + [abs(r.get('hf',0)) for r in resultados_ramales])
        self.balances(iteraciones=len(self.historial),residuo_masa=error_Q,
            escala_masa=max(abs(Q_bomba),Q_ref),residuo_energia=energia,escala_energia=escala_h,
            estado=estado if convergio or estado!='OK' else 'SIN_CONVERGENCIA',mensaje=mensaje)
        # Un piso absoluto y una tolerancia configurable son parte del contrato.
        if convergio and estado=='OK' and abs(error_Q)<=self.tolerancia_absoluta and self.residuo_energia_relativo<=1e-8:
            self.estado = 'OK'

        # Alias convencionales
        self.Q_op = self.Q_bomba
        self.H_op = self.H_bomba
        self.H = self.H_bomba
        self.Q = self.Q_bomba

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except (KeyError, AttributeError):
            return default

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "Q_bomba": self.Q_bomba,
            "H_bomba": self.H_bomba,
            "H_j": self.H_j,
            "error_Q": self.error_Q,
            "convergio": self.convergio,
            "estado": self.estado,
            "mensaje": self.mensaje,
            "ecuacion_continuidad": self.ecuacion_continuidad,
            "num_iteraciones": self.iteraciones,
            "iteraciones": self.iteraciones,
            "historial": self.historial,
            "residuo_masa": self.residuo_masa,
            "residuo_energia": self.residuo_energia,
            "residuo_masa_relativo": self.residuo_masa_relativo,
            "residuo_energia_relativo": self.residuo_energia_relativo,
            "residuo_ecuacion": self.residuo_ecuacion,
            "eta": self.eta,
            "npsh_r": self.npsh_r,
            "npsh_d": self.npsh_d,
            "cavitacion": self.cavitacion,
        }


def _extraer_H_bomba(curva_bomba: Any, Q: float) -> float:
    """Obtiene la carga manométrica H entregada por la bomba o estación a caudal Q."""
    caudal(Q)
    if hasattr(curva_bomba, "H_de_Q"):
        return numero(curva_bomba.H_de_Q(Q),'H de la bomba')
    if hasattr(curva_bomba, "H"):
        val = curva_bomba.H
        if callable(val):
            return numero(val(Q),'H de la bomba')
        return numero(val,'H de la bomba')
    if callable(curva_bomba):
        return numero(curva_bomba(Q),'H de la bomba')
    raise TypeError(f"No se puede evaluar la carga de la bomba para el tipo {type(curva_bomba)}")


def _extraer_Q_max_bomba(curva_bomba: Any) -> float:
    """Estima el caudal máximo válido de la bomba."""
    for attr in ("Q_max_estacion", "Q_max", "q_max"):
        if hasattr(curva_bomba, attr):
            val = getattr(curva_bomba, attr)
            if callable(val):
                val = val()
            if val is not None and float(val) > 0:
                return float(val)

    # Si es un objeto CurvaBomba con lista de caudales Q
    if hasattr(curva_bomba, "Q") and getattr(curva_bomba, "Q"):
        return numero(max(curva_bomba.Q),'Q máximo de la tabla',minimo=0,estricto=True)

    # Si no tiene metadatos, búsqueda tentativa hasta donde H sea positiva
    q_test = 0.5
    for _ in range(10):
        try:
            h = _extraer_H_bomba(curva_bomba, q_test)
            if h <= 0:
                return q_test
            q_test *= 1.5
        except Exception:
            break
    return 1.0


class BombaRamificadaMixin:
    """Mixin que añade la resolución de redes ramificadas con bomba al motor de fluidos."""

    @classmethod
    def _metricas_ramificada(cls, estacion, curva, tramo, Q, H, rho, mu, P_atm, P_vap):
        g = cls.g
        sub = tramo.get('sub_tramos') or [tramo]
        resultados = tuple(evaluar_tramo(Q,s['L'],s['D'],s.get('eps',0),s.get('K',0),
            s.get('LeD',0),dict(rho=rho,mu=mu,g=g),id=str(i)) for i,s in enumerate(sub))
        indices, en_succion = [], True
        bomba_obj = tramo.get('bomba_obj')
        for i,s in enumerate(sub):
            if s.get('es_succion', en_succion) and not tramo.get('sin_succion'):
                indices.append(i)
            tub = s.get('tuberia')
            if bomba_obj is not None and tub is not None and bomba_obj in (tub.nodo_origen,tub.nodo_destino):
                en_succion = False
        hf_suc = sum(resultados[i].hf_total for i in indices)
        if estacion is not None:
            r = evaluar_operacion_estacion(estacion,Q=Q,rho=rho,mu=mu,g=g,
                P_atm=P_atm,P_vap=P_vap,z1=tramo.get('H',0),z_bomba=tramo.get('z_bomba',0),
                hf_succion=hf_suc,perdidas_entre_etapas=tramo.get('perdidas_entre_etapas'),
                cotas_etapas=tramo.get('cotas_etapas'), id=str(tramo.get('estacion_id','estacion')))
            desglose = [BombaDesglose(b.id,b.etapa,b.Q,b.H,b.eficiencia,b.potencia_eje,b.activa,
                b.potencia_hidraulica,b.NPSHd,b.NPSHr,
                'SIN RIESGO' if b.cavitacion=='seguro' else 'RIESGO DE CAVITACIÓN'
                if b.cavitacion=='riesgo' else 'SIN DATO NPSHr') for b in r.bombas]
            return dict(potencia_hidraulica=r.potencia_hidraulica,potencia_freno=r.potencia_eje,
                eta=r.eficiencia,npsh_d=r.NPSHd,npsh_r=r.NPSHr,
                cavitacion=(r.cavitacion=='riesgo') if r.cavitacion!='desconocido' else None,
                desglose=desglose,hf_succion=hf_suc if P_atm is not None else None,
                estacion_resultado=r,resultados_tramos_principal=resultados)
        # Compatibilidad hidráulica con H(Q) invocable sin tabla/dominio de bombas.
        desglose = _calcular_desglose(estacion,Q,rho,g,H=H,curva=curva)
        ph = sum(d.P_hidraulica for d in desglose)
        pf, eta = _potencias_desglose(desglose)
        nd = nr = cav = hf_suc = None
        if P_atm is not None and P_vap is not None:
            sub = tramo.get('sub_tramos', [])
            if sub:
                hf_suc, en_succion = 0.0, True
                bomba_obj = tramo.get('bomba_obj')
                for s in sub:
                    if s.get('es_succion',en_succion):
                        hf_suc += cls._perdida_tramo(Q,s,rho,mu)[0]
                    tub = s.get('tuberia')
                    if bomba_obj is not None and tub is not None and bomba_obj in (
                            tub.nodo_origen,tub.nodo_destino):
                        en_succion = False
            else:
                hf_suc = 0.0 if tramo.get('sin_succion') else cls._perdida_tramo(Q,tramo,rho,mu)[0]
            nd = npsh_disponible(P_atm=P_atm,P_vap=P_vap,rho=rho,g=g,
                z1=tramo.get('H',0.0),z_bomba=tramo.get('z_bomba',0.0),hf_succion=hf_suc)
            if estacion is not None:
                estacion.evaluar_npsh(Q,P_atm=P_atm,P_vap=P_vap,rho=rho,g=g,
                    z1=tramo.get('H',0.0),z_bomba=tramo.get('z_bomba',0.0),hf_succion=hf_suc,
                    desglose=desglose, perdidas_entre_etapas=tramo.get('perdidas_entre_etapas'),
                    cotas_etapas=tramo.get('cotas_etapas'))
                requeridos = [d.npsh_r for d in desglose if d.etapa==1 and d.npsh_r is not None]
                nr = max(requeridos) if requeridos else None
                verificados = [d for d in desglose if d.npsh_r is not None]
                cav = any(d.cavitacion=='RIESGO DE CAVITACIÓN' for d in verificados) if verificados else None
        return dict(potencia_hidraulica=ph,potencia_freno=pf,eta=eta,npsh_d=nd,npsh_r=nr,
                    cavitacion=cav,desglose=desglose,hf_succion=hf_suc)

    @classmethod
    @ejecucion
    def resolver_bomba_ramificada(
        cls,
        curva_bomba: Any,
        tramo_bomba: Dict[str, Any],
        tramos_ramales: List[Dict[str, Any]],
        rho: float = 1000.0,
        mu: float = 1.004e-3,
        tol: float = TOLERANCIA_RELATIVA,
        max_iter: int = 100,
        Q_manual: Optional[float] = None,
        P_atm: Optional[float] = None,
        P_vap: Optional[float] = None,
        generar_curva: bool = True,
    ) -> ResultadoBombaRamificada:
        """
        Resuelve el punto de operación de una bomba conectada a un nudo que alimenta múltiples ramales.

        Parámetros:
            curva_bomba: Instancia de CurvaBomba, EstacionBombeo o invocable H(Q).
            tramo_bomba (dict):
                {'tuberia': obj, 'H': float (cota piezométrica tanque succión z1 + P1/gamma),
                 'L': float, 'D': float, 'eps': float, 'K': float, 'LeD': float,
                 'z_bomba': float (opcional), 'bomba_obj': obj (opcional)}
            tramos_ramales (list[dict]): lista de tramos ramificados:
                [{'tuberia': obj, 'H': float (cota tanque zi + Pi/gamma),
                  'L': float, 'D': float, 'eps': float, 'K': float, 'LeD': float,
                  'id_ramal': str/int (opcional)}]
                Un ramal compuesto conserva 'segmentos': [{'L','D','eps','K','LeD'}, ...];
                no se sustituye por la tubería directa ni por un diámetro equivalente.
            rho (float): Densidad del fluido en kg/m³.
            mu (float): Viscosidad dinámica en Pa·s.
            tol (float): Tolerancia relativa en Q; piso absoluto 1e-15 m³/s.
            max_iter (int): Máximo de iteraciones.
            Q_manual (float | None): Caudal supuesto fijado por el usuario (Modo Tanteo).
            P_atm, P_vap (float | None): Datos explícitos en Pa absolutos.
                Si se omiten ambos, se conserva el cálculo hidráulico histórico
                y NPSH queda desconocido; no se supone un fluido ni temperatura.

        Retorna:
            ResultadoBombaRamificada con todos los detalles de operación, balance e historial.
        """
        if not tramos_ramales:
            raise ValueError("Se requiere al menos un ramal conectado al nudo j.")
        validar_fluido(rho,mu,cls.g)
        validar_tramo(tramo_bomba,rho,mu,cls.g)
        for tramo in tramos_ramales:
            validar_tramo(tramo,rho,mu,cls.g)
        numero(tol,'tolerancia de caudal',minimo=0,estricto=True)
        Q_ref = _extraer_Q_max_bomba(curva_bomba)
        def en_tolerancia(error, q):
            return abs(error) <= max(1e-15, tol*max(abs(q), Q_ref))
        def conservar_tramos(resultados):
            for entrada,salida in zip(tramos_ramales,resultados):
                salida['resultados_tramos'] = tuple(evaluar_tramo(salida['Q'],s['L'],s['D'],
                    s.get('eps',0),s.get('K',0),s.get('LeD',0),dict(rho=rho,mu=mu,g=cls.g),
                    id=str(i)) for i,s in enumerate(entrada.get('segmentos',[entrada])))
        if not isinstance(max_iter,int) or max_iter <= 0:
            raise ValueError('max_iter debe ser un entero positivo.')
        if Q_manual is not None:
            caudal(Q_manual,'Q supuesto')
        for clave in ('z_bomba','H'):
            if clave in tramo_bomba:
                numero(tramo_bomba[clave],clave)
        # Compatibilidad hidráulica: sin presiones no se fabrica un NPSH.
        # La UI siempre suministra ambos datos absolutos explícitamente.
        if (P_atm is None) != (P_vap is None):
            raise ValueError("Suministre P_atm y P_vap conjuntamente.")
        if P_atm is not None:
            npsh_disponible(P_atm=P_atm,P_vap=P_vap,rho=rho)
        if isinstance(curva_bomba, EstacionBombeo):
            estacion = curva_bomba
        elif isinstance(curva_bomba, CurvaSerie):
            estacion = EstacionBombeo.en_serie(curva_bomba.bombas)
        elif isinstance(curva_bomba, CurvaParalelo):
            estacion = EstacionBombeo.en_paralelo(curva_bomba.bombas)
        elif isinstance(curva_bomba, CurvaBomba):
            estacion = EstacionBombeo.en_paralelo([curva_bomba])
        else:
            estacion = None  # H(Q) sin tabla: no se inventa un dominio ni η.
        invalidas = ([b for e in estacion.etapas for b in e if not getattr(b,'valida',True)]
                     if estacion is not None else [])
        if invalidas:
            return ResultadoBombaRamificada(0,0,0,0,[],{},[],False,
                estado='CURVA_INVALIDA',mensaje='; '.join(b.mensaje for b in invalidas))

        H_tq1 = float(tramo_bomba.get("H", 0.0))
        L_1 = float(tramo_bomba.get("L", 0.0))
        D_1 = float(tramo_bomba.get("D", 0.0))
        eps_1 = float(tramo_bomba.get("eps", 1e-5))
        K_1 = float(tramo_bomba.get("K", 0.0))
        LeD_1 = float(tramo_bomba.get("LeD", 0.0))

        sub_tramos = tramo_bomba.get("sub_tramos", [])

        def evaluar_paso(
            Q_sup: float,
        ) -> Tuple[float, float, float, float, List[Dict[str, Any]], str, str]:
            """
            Evalúa un caudal de bomba supuesto Q_sup.
            Retorna:
                (error_Q, H_b, hf_1, H_j, ramales_res, accion, ec_cont)
            """
            Q_sup = caudal(Q_sup,'Q supuesto')
            H_b = _extraer_H_bomba(curva_bomba, Q_sup)

            if sub_tramos and Q_sup > 0:
                hf_1 = 0.0
                for st in sub_tramos:
                    st_L = float(st.get("L", 0.0))
                    st_D = float(st.get("D", 0.0))
                    st_eps = float(st.get("eps", 1e-5))
                    st_K = float(st.get("K", 0.0))
                    st_LeD = float(st.get("LeD", 0.0))
                    if st_L > 0 and st_D > 0:
                        hf_st = cls.calcular_hf(
                            Q_sup, st_L, st_D, rho, mu, st_eps,
                            sumatoria_Le_D=st_LeD, sumatoria_K=st_K,
                        )
                        hf_1 += float(hf_st[0] if isinstance(hf_st, tuple) else hf_st)
            elif L_1 > 0 and D_1 > 0 and Q_sup > 0:
                hf_1_tuple = cls.calcular_hf(
                    Q_sup, L_1, D_1, rho, mu, eps_1,
                    sumatoria_Le_D=LeD_1, sumatoria_K=K_1,
                )
                hf_1 = float(hf_1_tuple[0] if isinstance(hf_1_tuple, tuple) else hf_1_tuple)
            else:
                hf_1 = 0.0

            H_j = H_tq1 + H_b - hf_1

            q_entran = Q_sup
            q_salen = 0.0
            ramales_res = []
            entradas_txt = ["Q_b"] if Q_sup > 0 else []
            salidas_txt = []

            for idx, r in enumerate(tramos_ramales, 1):
                H_tq_r = float(r.get("H", 0.0))
                L_r = float(r.get("L", 0.0))
                D_r = float(r.get("D", 0.0))
                eps_r = float(r.get("eps", 1e-5))
                K_r = float(r.get("K", 0.0))
                LeD_r = float(r.get("LeD", 0.0))
                nom_r = r.get("id_ramal", f"Q{idx+1}")

                hf_r = abs(H_j - H_tq_r)
                if hf_r > 0 and (r.get("segmentos") or (L_r > 0 and D_r > 0)):
                    Q_r = float(cls._caudal_tramo(hf_r, r, rho, mu))
                else:
                    Q_r = 0.0

                if H_j >= H_tq_r:
                    direccion = "Sale de la unión"
                    sentido = "sale"
                    q_salen += Q_r
                    salidas_txt.append(str(nom_r))
                else:
                    direccion = "Entra a la unión"
                    sentido = "entra"
                    q_entran += Q_r
                    entradas_txt.append(str(nom_r))

                ramales_res.append(
                    {
                        "tuberia": r.get("tuberia"),
                        "Q": Q_r,
                        "hf": hf_r,
                        "direccion": direccion,
                        "sentido": sentido,
                        "H_tanque": H_tq_r,
                        "id_ramal": nom_r,
                        "perdidas_segmentos": [cls._perdida_tramo(Q_r, s, rho, mu)
                            for s in r.get("segmentos", [r])],
                    }
                )

            error_Q = q_entran - q_salen

            if en_tolerancia(error_Q, Q_sup):
                accion = "Equilibrio alcanzado"
            elif error_Q > 0:
                accion = "Entra demasiado caudal a j. Disminuir Q de la bomba."
            else:
                accion = "Falta caudal en j. Aumentar Q de la bomba."

            txt_in = " + ".join(entradas_txt) if entradas_txt else "0"
            txt_out = " + ".join(salidas_txt) if salidas_txt else "0"
            ec_cont = f"{txt_in} = {txt_out}"

            return error_Q, H_b, hf_1, H_j, ramales_res, accion, ec_cont

        historial: List[Dict[str, Any]] = []

        # ==================== MODO TANTEO (1 sola pasada) ====================
        if Q_manual is not None:
            Q_manual = float(Q_manual)
            error_Q, H_b, hf_1, H_j, ramales_res, accion, ec_cont = evaluar_paso(Q_manual)
            historial.append(
                {
                    "iteracion": 1,
                    "Q_supuesto": Q_manual,
                    "H_bomba": H_b,
                    "hf_bomba": hf_1,
                    "H_j": H_j,
                    "error_Q": error_Q,
                    "accion": accion,
                    "caudales_ramales": [r["Q"] for r in ramales_res],
                    "sentidos": [r["sentido"] for r in ramales_res],
                }
            )

            convergio = en_tolerancia(error_Q, Q_manual)
            estado = "OK" if convergio else "TANTEO_DESEQUILIBRADO"
            mensaje = (
                "Punto de equilibrio alcanzado en tanteo manual."
                if convergio
                else f"Desequilibrio en el nudo: ΔQ = {error_Q:+.6f} m³/s. {accion}"
            )
            metricas = cls._metricas_ramificada(estacion,curva_bomba,tramo_bomba,Q_manual,H_b,
                                                rho,mu,P_atm,P_vap)
            if estacion is not None and not metricas['estacion_resultado'].convergio:
                estado, convergio = metricas['estacion_resultado'].estado, False
                mensaje = metricas['estacion_resultado'].mensaje
            conservar_tramos(ramales_res)

            # Empaquetar resultado tramo bomba
            tramo_b_res = {
                "tuberia": tramo_bomba.get("tuberia"),
                "Q": Q_manual,
                "H_bomba": H_b,
                "hf": hf_1,
                "direccion": "Sale de la bomba e ingresa a j",
            }

            return ResultadoBombaRamificada(
                Q_bomba=Q_manual,
                H_bomba=H_b,
                H_j=H_j,
                error_Q=error_Q,
                resultados_ramales=ramales_res,
                tramo_bomba_resultado=tramo_b_res,
                iteraciones=historial,
                convergio=convergio,
                estado=estado,
                mensaje=mensaje,
                ecuacion_continuidad=ec_cont,
                Q_ref=Q_ref, tol=tol,
                **metricas,
            )

        # ==================== MODO AUTOMÁTICO (Bisección) ====================
        # Determinar cota de cierre de la bomba a Q=0
        H_cierre = _extraer_H_bomba(curva_bomba, 0.0)
        min_H_ramales = min(float(r.get("H", 0.0)) for r in tramos_ramales)
        max_H_ramales = max(float(r.get("H", 0.0)) for r in tramos_ramales)

        # Si a caudal cero, la carga de la bomba más la cota de succión ni siquiera supera la menor cota de los ramales:
        if (H_tq1 + H_cierre) < min_H_ramales:
            return ResultadoBombaRamificada(
                Q_bomba=0.0,
                H_bomba=H_cierre,
                H_j=H_tq1 + H_cierre,
                error_Q=0.0,
                resultados_ramales=[],
                tramo_bomba_resultado={"tuberia": tramo_bomba.get("tuberia"), "Q": 0.0, "H_bomba": H_cierre, "hf": 0.0},
                iteraciones=[],
                convergio=False,
                estado="BOMBA_INSUFICIENTE",
                mensaje=(
                    f"La altura de cierre de la bomba (Hc = {H_cierre:.2f} m) es insuficiente para superar "
                    f"la cota del depósito más bajo ({min_H_ramales:.2f} m)."
                ),
            )

        # Límite superior de búsqueda de Q
        q_max_curva = _extraer_Q_max_bomba(curva_bomba)
        q_low = 0.0
        q_high = q_max_curva

        # Asegurar que en q_high la carga de la bomba no sea negativa absurda
        for _ in range(20):
            try:
                hb_hi = _extraer_H_bomba(curva_bomba, q_high)
                if hb_hi > -50.0:
                    break
                q_high *= 0.75
            except Exception:
                q_high *= 0.75

        # Bisección iterativa guiada por el balance de masa
        q_sol = q_low
        convergio = False

        for it in range(1, max_iter + 1):
            q_mid = 0.5 * (q_low + q_high)
            err, hb, hf1, hj, r_res, acc, ec = evaluar_paso(q_mid)

            historial.append(
                {
                    "iteracion": it,
                    "Q_supuesto": q_mid,
                    "H_bomba": hb,
                    "hf_bomba": hf1,
                    "H_j": hj,
                    "error_Q": err,
                    "accion": acc,
                    "caudales_ramales": [r["Q"] for r in r_res],
                    "sentidos": [r["sentido"] for r in r_res],
                }
            )

            q_sol = q_mid
            if en_tolerancia(err, q_mid):
                convergio = True
                break

            # Determinar dirección de paso:
            # Evaluamos la derivada numérica del error respecto a Q para asegurar convergencia estricta
            delta_test = max(1e-7, q_mid * 1e-4)
            err_plus, _, _, _, _, _, _ = evaluar_paso(q_mid + delta_test)
            derr_dq = (err_plus - err) / delta_test

            if derr_dq * err > 0:
                # El error tiene la misma polaridad que el crecimiento de Q -> reducir q_high
                q_high = q_mid
            else:
                q_low = q_mid

        # Evaluación final con la solución encontrada
        error_Q, H_b, hf_1, H_j, ramales_res, accion, ec_cont = evaluar_paso(q_sol)

        metricas = cls._metricas_ramificada(estacion, curva_bomba, tramo_bomba, q_sol, H_b,
                                            rho, mu, P_atm, P_vap)
        dominio_valido = estacion is None or metricas['estacion_resultado'].convergio
        if not dominio_valido:
            convergio = False
        conservar_tramos(ramales_res)
        tramo_b_res = {
            "tuberia": tramo_bomba.get("tuberia"),
            "Q": q_sol,
            "H_bomba": H_b,
            "hf": hf_1,
            "direccion": "Sale de la bomba hacia la unión",
        }

        # Generar puntos de la curva del sistema para graficación (Q vs H_sistema)
        curva_sist = cls.calcular_curva_sistema_ramificada(
            curva_bomba, tramo_bomba, tramos_ramales, rho, mu, q_sol
        ) if generar_curva else CurvaSistemaRamificada()
        estado_curva = None
        if not curva_sist.convergio:
            convergio = False
            estado_curva = curva_sist.estado

        return ResultadoBombaRamificada(
            Q_bomba=q_sol,
            H_bomba=H_b,
            H_j=H_j,
            error_Q=error_Q,
            resultados_ramales=ramales_res,
            tramo_bomba_resultado=tramo_b_res,
            iteraciones=historial,
            convergio=convergio,
            estado=estado_curva or ("FUERA_DE_RANGO_CURVA" if not dominio_valido else ("OK" if convergio else "MAX_ITER_ALCANZADO")),
            mensaje=(
                f"Equilibrio alcanzado con éxito en {len(historial)} iteraciones."
                if convergio
                else (curva_sist.mensaje if estado_curva else 'El punto requiere extrapolar alguna bomba fuera de su tabla.' if not dominio_valido
                      else f"No convergió dentro de la tolerancia en {max_iter} iteraciones (ΔQ = {error_Q:.6e}).")
            ),
            curva_sistema=curva_sist,
            ecuacion_continuidad=ec_cont,
            Q_ref=Q_ref, tol=tol,
            **metricas,
        )

    @classmethod
    @ejecucion
    def calcular_curva_sistema_ramificada(cls, curva_bomba, tramo_bomba, tramos_ramales,
                                         rho, mu, Q_op, num_puntos=40):
        """H_sistema(Q) con cotas adaptativas y balances relativos por punto.

        Q es magnitud positiva; cada ramal devuelve Entra/Sale explícitamente.
        Solo la suma neta de continuidad usa signo. Se acota H duplicando el
        intervalo hasta 80 veces y se resuelve hasta 200 iteraciones. Nunca se
        acepta la última cota como solución al agotar una búsqueda.
        """
        validar_fluido(rho,mu,cls.g)
        validar_tramo(tramo_bomba,rho,mu,cls.g)
        if not tramos_ramales:
            raise ValueError('Se requiere al menos un ramal para la curva del sistema.')
        for r in tramos_ramales:
            validar_tramo(r,rho,mu,cls.g)
            numero(r.get('H',0.0),'H del tanque')
        Q_op = caudal(Q_op,'Q de operación')
        if not isinstance(num_puntos,int) or num_puntos < 2:
            raise ValueError('num_puntos debe ser un entero mayor o igual a 2.')
        q_max = numero(_extraer_Q_max_bomba(curva_bomba),'Q máximo de referencia',minimo=0,estricto=True)
        q_lim = Q_op if Q_op > 0 else q_max
        objetivo = max(q_max,1.4*Q_op)
        for _ in range(80):
            if q_lim >= objetivo:
                break
            q_lim = numero(q_lim*2,'límite de Q expandido',minimo=0,estricto=True)
        else:
            raise ValueError('No se pudo acotar Q para la curva del sistema.')
        from motor.curvas import evaluar_carga_sistema_ramificada
        resultado = CurvaSistemaRamificada()
        for q in (q_lim*i/(num_puntos-1) for i in range(num_puntos)):
            try:
                altura, diagnostico = evaluar_carga_sistema_ramificada(
                    q,tramo_bomba,tramos_ramales,rho,mu,motor=cls)
            except ValueError as error:
                resultado.estado = 'SIN_CONVERGENCIA'
                resultado.mensaje = str(error)
                return resultado
            resultado.append((float(q),altura))
            resultado.diagnosticos.append(diagnostico)
        resultado.iteraciones = sum(d['iteraciones'] for d in resultado.diagnosticos)
        resultado.residuo_masa = max(abs(d['residuo_masa']) for d in resultado.diagnosticos)
        resultado.residuo_masa_relativo = max(d['residuo_masa_relativo'] for d in resultado.diagnosticos)
        resultado.residuo_energia = max(d['residuo_energia'] for d in resultado.diagnosticos)
        resultado.residuo_energia_relativo = max(d['residuo_energia_relativo'] for d in resultado.diagnosticos)
        return resultado

