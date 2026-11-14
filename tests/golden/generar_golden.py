"""Captura la lógica hidráulica ACTUAL sin importar ui ni arrancar PyQt.

Uso desde cualquier carpeta:
    python -B tests/golden/generar_golden.py
    python -B tests/golden/generar_golden.py --output-dir <carpeta_temporal>

Por defecto escribe siete JSON junto a este script. No modifica código existente.
Los archivos son instantáneas para revisión, no una demostración independiente de
corrección física. No reconstruye el perfil gráfico EGL/HGL: hoy depende de ui.
No redondea los números; conserva None, estados, residuos e historiales propios.
"""

from __future__ import annotations

import argparse
from dataclasses import fields, is_dataclass
import hashlib
import json
import math
from pathlib import Path
import sys

# También al importarse el generador se evita crear __pycache__ en el proyecto.
sys.dont_write_bytecode = True
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from motor import CurvaBomba, EstacionBombeo, MotorFluidos, punto_operacion
from motor.bombas import ResultadoBombeo
from motor.bomba_ramificada import ResultadoBombaRamificada
from motor.friccion import RE_LIMITE_LAMINAR
from motor.numerica import TOLERANCIA_INTERNA, TOLERANCIA_RELATIVA


FLUIDO = dict(rho=1000.0, mu=0.001, g=9.81, P_atm=101325.0, P_vap=2339.0)
NO_DISPONIBLE = {
    "perfil_grafico_egl_hgl": (
        "No generado: ResolucionMixin._construir_serie_ruta_egl y "
        "_construir_puntos_tramo_egl requieren elementos y posiciones de PyQt. "
        "Las alturas nodales del motor se conservan por separado."
    ),
    "presion_nodos_internos": (
        "El motor no entrega un campo general de presiones nodales; Hj y EGL "
        "no se convierten en presión sin cota, velocidad y referencia explícitas."
    ),
}


def serializar(valor):
    """No perder __dict__ al serializar subclases de float, tuple o list.

    No usar ResultadoBombaRamificada.to_dict(): omite pérdidas e historial.
    Los valores no finitos detienen la captura; no se convierten a cero/null.
    """
    if valor is None or isinstance(valor, (str, bool)):
        return valor
    atributos = vars(valor) if hasattr(valor, "__dict__") else {}
    # Esquema v1 congelado: conservar TODOS sus valores, sin sustituir las
    # capturas ni relajar test_golden. Los metadatos v2 se prueban por separado.
    if isinstance(valor, ResultadoBombeo):
        claves = ('estado','mensaje','Q','H_total','P_hidraulica','BHP_total',
                  'eta_global','desglose','direccion','historial_iteraciones')
        return {k:serializar(getattr(valor,k)) for k in claves}
    if isinstance(valor, ResultadoBombaRamificada):
        claves = ('Q_bomba','direccion','H_bomba','H_j','error_Q','resultados_ramales',
            'tramo_bomba_resultado','convergio','estado','mensaje','curva_sistema',
            'ecuacion_continuidad','potencia_hidraulica','potencia_freno','eta',
            'npsh_r','npsh_d','cavitacion','desglose','hf_succion',
            'Q_op','H_op','H','Q','historial_iteraciones')
        datos = {k:getattr(valor,k) for k in claves}
        datos['iteraciones'] = valor.historial
        datos['resultados_ramales'] = [
            {k:v for k,v in r.items() if k!='resultados_tramos'} for r in valor.resultados_ramales]
        return serializar(datos)
    if is_dataclass(valor):
        datos = {campo.name: getattr(valor, campo.name) for campo in fields(valor)}
        datos.update(atributos)
        return {k: serializar(v) for k, v in datos.items()}
    if isinstance(valor, (int, float)):
        if not math.isfinite(valor):
            raise ValueError(f"Valor no finito en la captura: {valor!r}")
        numero = float(valor) if isinstance(valor, float) else int(valor)
        if atributos:
            return {"valor": numero, "metadatos": serializar(atributos)}
        return numero
    if isinstance(valor, dict):
        if not all(isinstance(k, str) for k in valor):
            raise TypeError("Las claves de la captura deben ser identificadores de texto.")
        return {k: serializar(v) for k, v in valor.items()}
    if isinstance(valor, (tuple, list)):
        elementos = [serializar(v) for v in valor]
        if atributos:
            return {"valores": elementos, "metadatos": serializar(atributos)}
        return elementos
    if atributos:
        return {k: serializar(v) for k, v in atributos.items()}
    raise TypeError(f"Objeto no serializable en golden: {type(valor).__name__}")


def tramo(nombre, L, D, eps=0.0, K=0.0, LeD=0.0, **otros):
    return dict(tuberia=nombre, L=L, D=D, eps=eps, K=K, LeD=LeD, **otros)


def hidraulica(q, segmento):
    """Mismas derivaciones explícitas que hoy hace _fila_exportacion en la UI.

    Esta función del generador NO se presenta como una API nueva del motor.
    En Q=0 no existe un f físico definido: se conserva None.
    """
    area = math.pi * segmento["D"] ** 2 / 4.0
    v = q / area
    re = FLUIDO["rho"] * v * segmento["D"] / FLUIDO["mu"]
    f = (MotorFluidos._factor_friccion_sustitucion(re, segmento["eps"] / segmento["D"],
                                                registrar=True) if re else None)
    perdida = MotorFluidos._perdida_tramo(q, segmento, FLUIDO["rho"], FLUIDO["mu"],
                                        registrar=True)
    return dict(id=segmento["tuberia"], Q=float(q), area=area, v=v, Re=re, f=f,
                ley_motor=("sin_flujo" if not re else
                           "laminar" if re < RE_LIMITE_LAMINAR else "colebrook"),
                regimen_ui=("Laminar" if re < 2000 else
                            "Transición" if re < 4000 else "Turbulento"),
                hf_total=float(perdida[0]), hf_distribuida=float(perdida[1]),
                hf_localizada=float(perdida[2]), resultado_perdida=perdida)


def exigir_ok(resultado):
    if getattr(resultado, "estado", None) != "OK":
        raise RuntimeError(f"{getattr(resultado, 'estado', '?')}: "
                           f"{getattr(resultado, 'mensaje', '')}")


def curva(nombre="B1", qmax=0.04, hmax=40.0):
    return CurvaBomba(nombre, [0.0, qmax / 2, qmax],
                     [hmax, hmax / 2, 0.0],
                     eta=[0.8, 0.8, 0.8], npsh_r=[2.0, 2.5, 3.0], metodo="lineal")


def datos_curva(b):
    return dict(nombre=b.nombre, Q=list(b.Q), H=list(b.H),
                eta=list(b.eta) if b.eta is not None else None,
                npsh_r=b.npsh_r, metodo=b.metodo,
                coef_a=b.coef_a, coef_b=b.coef_b, coef_c=b.coef_c,
                Q_min=b.Q_min, Q_max=b.Q_max, estado=b.estado)


def caso_serie(dos_tramos=False):
    tramos = ([tramo("T1", 30.0, 0.1, K=2.0, LeD=15.0, nodo_salida="J1"),
               tramo("T2", 70.0, 0.08, eps=1e-5, K=3.0, LeD=20.0,
                     nodo_salida="B")]
              if dos_tramos else [tramo("T1", 100.0, 0.1, nodo_salida="B")])
    inicio, fin = 20.0, 5.0
    resultado = MotorFluidos.resolver_serie_por_energia(inicio, fin, tramos,
                                                      FLUIDO["rho"], FLUIDO["mu"])
    exigir_ok(resultado)
    return dict(entrada=dict(tramos=tramos, H_inicio=inicio, H_fin=fin,
                             tanques=dict(A=dict(z=inicio, P_manometrica=0.0),
                                          B=dict(z=fin, P_manometrica=0.0))),
                solver="motor.redes.RedesMixin.resolver_serie_por_energia",
                resultado=resultado,
                tramos=[hidraulica(float(resultado.Q), t) for t in tramos],
                balances=dict(residuo_energia=inicio-fin-sum(p[0] for p in resultado.perdidas_tramos),
                              residuo_masa=0.0))


def caso_paralelo():
    ramas = [tramo("R1", 100.0, 0.1), tramo("R2", 100.0, 0.05, K=1.5, LeD=8.0)]
    q_total = 0.001
    resultado = MotorFluidos.resolver_paralelo(ramas, q_total, FLUIDO["rho"], FLUIDO["mu"])
    exigir_ok(resultado)
    return dict(entrada=dict(ramas=ramas, Q_total=q_total),
                solver="motor.redes.RedesMixin.resolver_paralelo", resultado=resultado,
                ramas=[hidraulica(float(q), t) for q, t in zip(resultado.caudales, ramas)],
                balances=dict(residuo_masa=sum(resultado.caudales)-q_total,
                              residuo_energia=max(abs(p[0]-resultado.hf)
                                                  for p in resultado.perdidas_tramos)))


def caso_bombas(arreglo):
    bombas = [curva("B1")] if arreglo == "individual" else [curva("B1"), curva("B2")]
    estacion = (EstacionBombeo.en_serie(bombas) if arreglo == "serie" else
                EstacionBombeo.en_paralelo(bombas))
    tramos = [tramo("Aspiracion", 10.0, 0.15, K=1.0),
              tramo("Impulsion", 100.0, 0.1, eps=1e-5, K=2.0, LeD=15.0)]
    def sistema(q):
        return MotorFluidos.carga_requerida_sistema(q, z1=0.0, z2=10.0,
            rho=FLUIDO["rho"], mu=FLUIDO["mu"], tramos=tramos)
    resultado = punto_operacion(estacion, sistema, rho=FLUIDO["rho"], g=FLUIDO["g"])
    exigir_ok(resultado)
    hf_succion = MotorFluidos._perdida_tramo(resultado.Q, tramos[0],
                                           FLUIDO["rho"], FLUIDO["mu"])
    npsh_entrada = dict(P_atm=FLUIDO["P_atm"], P_vap=FLUIDO["P_vap"],
                        rho=FLUIDO["rho"], g=FLUIDO["g"], z1=0.0, z_bomba=0.0,
                        P1=0.0, hf_succion=float(hf_succion[0]))
    estacion.evaluar_npsh(resultado.Q, desglose=resultado.desglose, **npsh_entrada)
    qs = [estacion.Q_max * i / 20 for i in range(21)]
    hs = MotorFluidos.curva_sistema(qs, H_func=sistema)
    return dict(entrada=dict(arreglo=arreglo, curvas=[datos_curva(b) for b in bombas],
                             tramos=tramos, z_inicio=0.0, z_fin=10.0, npsh=npsh_entrada,
                             perdidas_entre_etapas=[0.0]*(len(estacion.etapas)-1)),
                solver="motor.bombas.punto_operacion + EstacionBombeo.evaluar_npsh",
                resultado=resultado, curva_sistema=list(zip(qs, hs)),
                ecuacion_total_aproximada=estacion.ecuacion_total(resultado.Q, resultado.H_total),
                tramos=[hidraulica(resultado.Q, t) for t in tramos],
                balances=dict(residuo_energia=resultado.H_total-sistema(resultado.Q),
                              residuo_masa_por_etapa=[sum(d.Q_i for d in resultado.desglose
                                                         if d.etapa==k+1)-resultado.Q
                                                     for k in range(len(estacion.etapas))]))


def caso_ramificada():
    # Flujo laminar en todo el muestreo: evita que un punto de curva caiga en el
    # hueco de pérdidas del salto de Re=2000, que el motor rechaza legítimamente.
    b = curva(qmax=1e-5, hmax=0.01)
    estacion = EstacionBombeo.en_paralelo([b])
    segmentos = [tramo("Succion", 10.0, 0.02, K=0.5, es_succion=True),
                 tramo("Hasta_J", 10.0, 0.02, LeD=5.0, es_succion=False)]
    principal = tramo("Principal", 20.0, 0.02, H=0.0, z_bomba=0.0,
                      z_tanque=0.0, P_tanque=0.0, sub_tramos=segmentos)
    ramas = [dict(tuberia="R1", id_ramal="R1", H=0.0,
                  segmentos=[tramo("R1a", 10.0, 0.02, K=1.0),
                             tramo("R1b", 10.0, 0.02, LeD=4.0)]),
             tramo("R2", 30.0, 0.02, K=2.0, H=0.0, id_ramal="R2")]
    tolerancia_q = 1e-15
    resultado = MotorFluidos.resolver_bomba_ramificada(estacion, principal, ramas,
        rho=FLUIDO["rho"], mu=FLUIDO["mu"], tol=tolerancia_q, max_iter=100,
        P_atm=FLUIDO["P_atm"], P_vap=FLUIDO["P_vap"])
    exigir_ok(resultado)
    detalles = [hidraulica(resultado.Q_bomba, s) for s in segmentos]
    for rama, res in zip(ramas, resultado.resultados_ramales):
        detalles.extend(hidraulica(res["Q"], s) for s in rama.get("segmentos", [rama]))
    return dict(entrada=dict(curvas=[datos_curva(b)], principal=principal, ramas=ramas,
                             tol_Q_absoluta=tolerancia_q, max_iter=100),
                solver="motor.bomba_ramificada.BombaRamificadaMixin.resolver_bomba_ramificada",
                resultado=resultado, tramos=detalles,
                balances=dict(residuo_masa=resultado.error_Q,
                              residuo_masa_relativo=abs(resultado.error_Q)/resultado.Q_bomba,
                              residuo_energia_principal=(principal["H"]+resultado.H_bomba
                                                        -sum(t["hf_total"] for t in detalles[:2])
                                                        -resultado.H_j),
                              residuos_energia_ramales=[
                                  abs(resultado.H_j-r["H_tanque"])
                                  -sum(float(p[0]) for p in r["perdidas_segmentos"])
                                  for r in resultado.resultados_ramales]))


CASOS = {
    "a_tanque_tanque": lambda: caso_serie(False),
    "b_serie_accesorios": lambda: caso_serie(True),
    "c_paralelo_distinto": caso_paralelo,
    "d_una_bomba": lambda: caso_bombas("individual"),
    "e_dos_bombas_serie": lambda: caso_bombas("serie"),
    "e_dos_bombas_paralelo": lambda: caso_bombas("paralelo"),
    "f_ramificada_bomba": caso_ramificada,
}


def capturar_caso(nombre):
    """Regenera un caso completo en memoria; no escribe ni lee su JSON dorado."""
    huellas = {str(p.relative_to(RAIZ)).replace("\\", "/"):
               hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted((RAIZ / "motor").glob("*.py"))}
    captura = dict(caso=nombre, version_captura=1, fluido=FLUIDO,
                   unidades=dict(Q="m3/s", v="m/s", L_D_eps="m", hf_H_EGL_HGL_NPSH="m",
                                 presion="Pa", potencia="W", eficiencia="fraccion",
                                 Re_f_K_LeD="adimensional"),
                   tolerancias=dict(relativa_motor=TOLERANCIA_RELATIVA,
                                    interna_motor=TOLERANCIA_INTERNA,
                                    Re_limite_laminar=RE_LIMITE_LAMINAR),
                   fuentes_sha256=huellas, no_disponible=NO_DISPONIBLE, **CASOS[nombre]())
    return serializar(captura)


def generar(destino):
    destino = Path(destino)
    capturas = {}
    for nombre in CASOS:
        # Preparar todas las capturas antes de escribir; un fallo nunca produce
        # una nueva tanda que solo contenga las primeras redes.
        capturas[nombre] = json.dumps(capturar_caso(nombre), ensure_ascii=False,
                                     indent=2, allow_nan=False) + "\n"
    if any(nombre.startswith(("PyQt5", "ui.")) for nombre in sys.modules):
        raise RuntimeError("La captura ha importado una dependencia de interfaz.")
    destino.mkdir(parents=True, exist_ok=True)
    rutas = []
    for nombre, contenido in capturas.items():
        ruta = destino / f"{nombre}.json"
        ruta.write_text(contenido, encoding="utf-8")
        rutas.append(ruta)
        print(f"OK {nombre}: {ruta}")
    return rutas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    generar(args.output_dir)


if __name__ == "__main__":
    main()
