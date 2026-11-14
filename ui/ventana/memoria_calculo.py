"""Hojas de memoria de cálculo y tablas de iteraciones."""

from ui.curvas_presentacion import usa_puntos,puntos_tabla,puntos_total,resumen_puntos,nota_joroba

import math

from motor import MotorFluidos
from motor.hidraulica import evaluar_tramo
from motor.resultados import ResultadoTramo
from motor.friccion import RE_LIMITE_LAMINAR
from motor.numerica import TOLERANCIA_RELATIVA

try:  # Exportación a Excel (pip install xlsxwriter); la app sigue funcionando sin ella
    import xlsxwriter
    from xlsxwriter.utility import xl_rowcol_to_cell
except ImportError:  # pragma: no cover
    xlsxwriter = None
    xl_rowcol_to_cell = None


class MemoriaCalculoMixin:
    """Hojas de memoria de cálculo y tablas de iteraciones."""

    @staticmethod
    def _colebrook_cache(Re, rug_rel, n_iter=None):
        """Traza completa del motor; Excel no implementa otra iteración Python."""
        return MotorFluidos.iteraciones_colebrook(Re, rug_rel)

    @staticmethod
    def _resultado_tramo_excel(t):
        """Usa la instantánea exportada; admite diccionarios históricos de memoria."""
        resultado = t.get('resultado_tramo')
        if isinstance(resultado, ResultadoTramo):
            return resultado
        return evaluar_tramo(t['Q'], t['L'], t['D'], t.get('rugosidad', 0.0),
            t.get('K', 0.0), t.get('LeD', 0.0),
            dict(rho=t['rho'], mu=t['mu'], g=t.get('g', MotorFluidos.g)), id=t.get('id'))

    @staticmethod
    def _valores_tramo_excel(r):
        # En las fórmulas de auditoría Q=0 se representa f=0 para que Darcy dé 0;
        # el contrato físico conserva f=None. No se calcula un factor de reposo.
        return dict(L=r.L, D=r.D, Q=r.Q, K=r.K, LeD=r.LeD, V=r.v, Re=r.Re,
                    f=r.f if r.f is not None else 0.0,
                    hf=r.hf_total, hf_dist=r.hf_distribuida, hf_loc=r.hf_localizada,
                    inv_raiz_f=r.inv_raiz_f if r.inv_raiz_f is not None else 0.0,
                    karman=r.karman if r.karman is not None else 0.0)

    def _hidraulica_excel(self, libro, t):
        """Fórmulas de verificación Darcy para los Q y D resueltos por el motor.

        Hoja auxiliar oculta: no cambia la disposición del reporte. Colebrook
        admite hasta 100 iteraciones (como el motor) y se congela al converger.
        Si no converge, retorna NA(), nunca un factor aproximado aceptado.
        Las inversas Q/D siguen siendo resultados del motor, sin reescalados.
        """
        resultado = self._resultado_tramo_excel(t)
        valores = self._valores_tramo_excel(resultado)
        if not hasattr(libro, '_hidraulica_refs'):
            libro._hidraulica_refs = {}
            libro._hidraulica_hoja = libro.add_worksheet('_Hidraulica')
            libro._hidraulica_hoja.hide()
        key = tuple(float(t.get(nombre, 9.81 if nombre == 'g' else 0.0) or 0.0)
                    for nombre in ('L','D','rugosidad','rho','mu','Q','K','LeD','g','hf'))
        if key in libro._hidraulica_refs:
            return libro._hidraulica_refs[key]
        ws = libro._hidraulica_hoja
        col = len(libro._hidraulica_refs) * 5
        ref = lambda row, delta=1: xl_rowcol_to_cell(row, col + delta, True, True)
        datos = dict(valores, rugosidad=resultado.eps, rho=t['rho'], mu=t['mu'],
                     g=t.get('g', MotorFluidos.g),
                     hf=t.get('hf_resolucion', t['hf']))
        if datos['hf'] is None:
            datos['hf'] = resultado.hf_total
        entradas = ['L', 'D', 'rugosidad', 'rho', 'mu', 'Q', 'K', 'LeD', 'g', 'hf']
        for row, nombre in enumerate(entradas):
            ws.write(row, col, nombre)
            ws.write_number(row, col + 1, datos[nombre])
        L, D, eps, rho, mu, Q, K, LeD, g, hf_motor = [ref(i) for i in range(10)]
        v, re, rr = ref(11), ref(12), ref(13)
        vval, reval, rrval = resultado.v, resultado.Re, resultado.rugosidad_relativa
        ws.write_formula(11, col+1, f'=4*{Q}/(PI()*{D}^2)', None, vval)
        ws.write_formula(12, col+1, f'={rho}*{v}*{D}/{mu}', None, reval)
        ws.write_formula(13, col+1, f'={eps}/{D}', None, rrval)
        props, obtenidos = self._colebrook_cache(reval, rrval)
        for i in range(100):
            row = 22 + i
            propuesta, obtenida, fin = ref(row), ref(row, 2), ref(row, 3)
            propval = props[min(i, len(props)-1)] if i < len(props) else obtenidos[-1]
            obtval = obtenidos[min(i, len(obtenidos)-1)]
            if i == 0:
                ws.write_number(row, col+1, 1.0)
            else:
                ws.write_formula(row, col+1, f'={ref(row-1, 2)}', None, propval)
            paso = f'IF({re}<{RE_LIMITE_LAMINAR},SQRT({re}/64),-0.86*LN({rr}/3.7+2.51*{propuesta}/{re}))'
            if i:
                paso = f'IF({ref(row-1, 3)},{ref(row-1, 2)},{paso})'
            ws.write_formula(row, col+2, '=' + paso, None, obtval)
            residuo = f'ABS(({obtenida}+0.86*LN({rr}/3.7+2.51*{obtenida}/{re}))/{obtenida})'
            ws.write_formula(row, col+3,
                f'=IF({re}<{RE_LIMITE_LAMINAR},TRUE,AND(ABS({obtenida}-{propuesta})<1E-12,{residuo}<={TOLERANCIA_RELATIVA}))',
                None, i >= len(obtenidos)-1)
        x_final, fin = ref(121, 2), ref(121, 3)
        fval = valores['f']
        fref, hdist, hloc, href = ref(15), ref(16), ref(17), ref(18)
        ws.write_formula(15, col+1, f'=IF({Q}=0,0,IF({re}<{RE_LIMITE_LAMINAR},64/{re},IF({fin},1/{x_final}^2,NA())))', None, fval)
        ws.write_formula(16, col+1, f'={fref}*{L}/{D}*{v}^2/(2*{g})', None, resultado.hf_distribuida)
        ws.write_formula(17, col+1, f'=({fref}*{LeD}+{K})*{v}^2/(2*{g})', None, resultado.hf_localizada)
        ws.write_formula(18, col+1, f'=({fref}*({L}/{D}+{LeD})+{K})*{v}^2/(2*{g})', None, resultado.hf_total)
        hf_comparacion = datos['hf']
        err = (abs(resultado.hf_total - hf_comparacion) / abs(hf_comparacion)
               if hf_comparacion else abs(resultado.hf_total))
        ws.write_formula(19, col+1, f'=IF({hf_motor}=0,ABS({href}),ABS(({href}-{hf_motor})/{hf_motor}))', None, err)
        ws.write_formula(20, col+1, f'=IF(AND({fin},{ref(19)}<={TOLERANCIA_RELATIVA}),"OK","SIN_CONVERGENCIA")',
                         None, 'OK' if err <= TOLERANCIA_RELATIVA else 'SIN_CONVERGENCIA')
        ws.write_formula(14, col+1, f'=IF({re}<{RE_LIMITE_LAMINAR},0,MATCH(TRUE,{ref(22,3)}:{ref(121,3)},0))',
                         None, len(obtenidos) if reval >= RE_LIMITE_LAMINAR else 0)
        ws.write_formula(122, col+1, f'=IF({fref}=0,0,1/SQRT({fref}))', None, valores['inv_raiz_f'])
        ws.write_formula(123, col+1, f'={re}*SQRT({fref})', None, valores['karman'])
        filas = dict(L=0, D=1, Q=5, K=6, LeD=7, V=11, Re=12, f=15,
                     hf_dist=16, hf_loc=17, hf=18, inv_raiz_f=122, karman=123)
        refs = {nombre: f"'_Hidraulica'!{ref(row)}" for nombre, row in filas.items()}
        libro._hidraulica_refs[key] = refs
        return refs

    def _escribir_hidraulica_excel(self, ws, libro, t, filas, col, formato):
        refs = self._hidraulica_excel(libro, t)
        valores = self._valores_tramo_excel(self._resultado_tramo_excel(t))
        for nombre, fila in filas.items():
            ws.write_formula(fila, col, '=' + refs[nombre], formato, valores[nombre])

    def _hoja_memoria_doble_nudo(self, libro, datos):
        ws = libro.add_worksheet("Memoria Doble Nudo")
        ws.hide_gridlines(2)
        F = self._formatos_excel(libro)
        esc = self._escribir_rango
        ref = xl_rowcol_to_cell
        sup = datos["suposiciones"]
        glob = datos.get("resultados_globales", {}) or {}
        res = datos["resultados"]

        tubs = [t for rol in ("j", "central", "k") for t in datos["tuberias"] if t.get("rol") == rol]
        n = len(tubs)
        pos_j = [i for i, t in enumerate(tubs) if t["rol"] == "j"]
        pos_c = [i for i, t in enumerate(tubs) if t["rol"] == "central"]
        pos_k = [i for i, t in enumerate(tubs) if t["rol"] == "k"]
        if n != len(datos["tuberias"]) or len(pos_c) != 1 or not pos_j or not pos_k:
            raise ValueError("El Doble Nudo requiere tuberías con rol 'j', 'central' (una) y 'k'.")
        pos_c = pos_c[0]

        def v(valor):
            return "—" if valor is None else valor

        def num(valor):
            return 0 if valor is None else valor

        c_d = 0
        c_c = n + 2
        c_r = c_c + n + 2
        ancho_res = 2
        ancho_total = c_r + ancho_res
        ws.set_column(c_d, c_d, 36)
        ws.set_column(c_d + 1, c_d + n, 18)
        ws.set_column(n + 1, n + 1, 4)
        ws.set_column(c_c, c_c, 36)
        ws.set_column(c_c + 1, c_c + n, 18)
        ws.set_column(c_c + n + 1, c_c + n + 1, 4)
        ws.set_column(c_r, c_r, 30)
        ws.set_column(c_r + 1, c_r + ancho_res, 22)

        ws.merge_range(
            0, 0, 0, ancho_total,
            "Memoria de cálculo — Sistema Ramificado (Doble Nudo)",
            F["titulo"],
        )
        ws.set_row(0, 24)

        r_sec = 2
        esc(ws, r_sec, c_d, r_sec, c_d + n, "Datos", F["seccion"])
        esc(ws, r_sec, c_c, r_sec, c_c + n, "Cálculos intermedios", F["seccion"])
        esc(ws, r_sec, c_r, r_sec, c_r + ancho_res, "Resultados", F["seccion"])

        r_cab = r_sec + 2
        for c0 in (c_d, c_c):
            esc(ws, r_cab, c0, r_cab + 1, c0, "Propiedades", F["cab"])
            esc(ws, r_cab, c0 + 1, r_cab, c0 + n, "Tuberías", F["cab"])
            for i, t in enumerate(tubs):
                id_t = t["id"] if t["id"] is not None else i + 1
                ws.write(r_cab + 1, c0 + 1 + i, f"{id_t} ({t['rol']})", F["cab"])

        r = r_cab + 2
        filas_datos = [
            ("Longitud (L) [m]", "L"),
            ("Diámetro (D) [m]", "D"),
            ("Rugosidad (e) [m]", "rugosidad"),
            ("Altura (z) [m]", "Z_origen"),
            ("Rugosidad relativa (e/D)", "rugosidad_relativa"),
            ("Área de la tubería (A) [m²]", "Area"),
        ]
        fila_L, fila_D, fila_e, fila_Z, fila_relativa, fila_A = range(r, r + 6)
        fila_rho = r + len(filas_datos)
        fila_mu = fila_rho + 1
        celda_global = c_d + 1

        fila_hf, fila_karman, fila_inv, fila_f, fila_Re, fila_V, fila_Q = range(r, r + 7)
        r_iter = fila_Q + 3

        r_sup = fila_mu + 3
        fila_Hj = r_sup + 2
        fila_Hk = fila_Hj + 1

        abs_rho = ref(fila_rho, celda_global, True, True)
        abs_mu = ref(fila_mu, celda_global, True, True)
        celda_hj = ref(fila_Hj, c_d + 1, True, True)
        celda_hk = ref(fila_Hk, c_d + 1, True, True)

        for k, (etq, clave) in enumerate(filas_datos):
            ws.write(r + k, c_d, etq, F["etiqueta"])
            for i, t in enumerate(tubs):
                c = c_d + 1 + i
                if clave == "rugosidad_relativa":
                    ws.write_formula(
                        fila_relativa, c, f"={ref(fila_e, c)}/{ref(fila_D, c)}",
                        F["valor"], num(t.get("rugosidad_relativa")),
                    )
                elif clave == "Area":
                    ws.write_formula(
                        fila_A, c, f"=PI()*({ref(fila_D, c)}^2)/4", F["valor"], num(t.get("Area"))
                    )
                elif clave == "Z_origen" and t["rol"] != "central":
                    z = t.get("Z_origen")
                    ws.write(fila_Z, c, 0.0 if z is None else z, F["valor"])
                else:
                    ws.write(r + k, c, v(t.get(clave)), F["valor"])
        ws.write(fila_rho, c_d, "Densidad (ρ) [kg/m³]", F["etiqueta"])
        esc(ws, fila_rho, celda_global, fila_rho, c_d + n, tubs[0]["rho"], F["valor"])
        ws.write(fila_mu, c_d, "Viscosidad dinámica (μ) [Pa·s]", F["etiqueta"])
        esc(ws, fila_mu, celda_global, fila_mu, c_d + n, tubs[0]["mu"], F["valor"])

        suma_j = "+".join(
            f"SIGN({ref(fila_Z, c_d + 1 + i)}-{celda_hj})*{ref(fila_Q, c_c + 1 + i)}" for i in pos_j
        )
        suma_k = "+".join(
            f"SIGN({ref(fila_Z, c_d + 1 + i)}-{celda_hk})*{ref(fila_Q, c_c + 1 + i)}" for i in pos_k
        )

        # Traza convergida del motor, debajo de Cálculos intermedios, solo central.
        entradas_colebrook = []
        for i, t in enumerate(tubs):
            if t["rol"] != "central":
                continue
            resultado = self._resultado_tramo_excel(t)
            entradas_colebrook.append({
                "i": i,
                "nombre": f"Tubería {t['id'] if t['id'] is not None else i + 1} (central)",
                "celda_Re": ref(fila_Re, c_c + 1 + i),
                "celda_eD": ref(fila_relativa, c_d + 1 + i),
                "Re": resultado.Re,
                "rug_rel": resultado.rugosidad_relativa,
                "resultado_tramo": resultado,
            })
        celdas_f, celdas_inv, _ = self._tabla_iteraciones(
            ws, F, entradas_colebrook, c_c, r_iter, con_subtitulo=True
        )

        filas_calc = [
            "Pérdidas por fricción (hf) [m]",
            "Número de Kármán (Re·√f)",
            "1/√f",
            "Factor de fricción (f)",
            "Número de Reynolds (Re)",
            "Velocidad promedio (V) [m/s]",
            "Caudal (Q) [m³/s]",
        ]
        for k, etq in enumerate(filas_calc):
            ws.write(r + k, c_c, etq, F["etiqueta"])

        for i, t in enumerate(tubs):
            self._escribir_hidraulica_excel(ws, libro, t,
                dict(hf=fila_hf, karman=fila_karman, inv_raiz_f=fila_inv, f=fila_f,
                     Re=fila_Re, V=fila_V, Q=fila_Q), c_c + 1 + i, F['valor'])

        # Bloque Suposiciones (Abajo Izquierda)
        H_j_val = sup.get("H_j (Supuesta)")
        if H_j_val is None:
            H_j_val = glob.get("H_j (Calculada)", 0.0)

        esc(ws, r_sup, c_d, r_sup, c_d + n, "Suposiciones", F["seccion"])
        ws.write(fila_Hj, c_d, "Altura piezométrica 1 (hj) [m]", F["destacado_etq"])
        esc(ws, fila_Hj, c_d + 1, fila_Hj, c_d + n, H_j_val, F["destacado_val"])

        celda_hf_central = ref(fila_hf, c_c + 1 + pos_c)
        ws.write(fila_Hk, c_d, "Altura piezométrica 2 (hk = hj ∓ hf3) [m]", F["destacado_etq"])
        ws.merge_range(fila_Hk, c_d + 1, fila_Hk, c_d + n, "", F["destacado_val"])
        ws.write_formula(
            fila_Hk, c_d + 1,
            f"={celda_hj}-SIGN({suma_j})*{celda_hf_central}",
            F["destacado_val"], num(glob.get("H_k (Calculada)")),
        )

        # Bloque Resultados (Derecha Arriba)
        r_r = r_cab
        esc(ws, r_r, c_r, r_r, c_r + ancho_res, "Condición final", F["cab_neg"])
        r_r += 1
        for ecuacion in res.get("condicion_final", []):
            esc(ws, r_r, c_r, r_r, c_r + ancho_res, ecuacion, F["valor"])
            r_r += 1

        celda_Q_central = ref(fila_Q, c_c + 1 + pos_c)
        ws.write(r_r, c_r, "Variación de Q (ΔQ en k) [m³/s]", F["etiqueta"])
        ws.merge_range(r_r, c_r + 1, r_r, c_r + ancho_res, "", F["valor"])
        ws.write_formula(
            r_r, c_r + 1,
            f"=SIGN({suma_j})*{celda_Q_central}+{suma_k}",
            F["valor"], num(res.get("variacion_Q")),
        )
        celda_dq = ref(r_r, c_r + 1, True, True)
        r_r += 1

        ws.write(r_r, c_r, "Tolerancia admisible (ε_Q) [m³/s]", F["etiqueta"])
        esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, 0.0001, F["valor"])
        celda_tol = ref(r_r, c_r + 1, True, True)
        r_r += 1

        formato_diag = F["ok"] if res.get("ok") else F["error"]
        diagnostico = (
            f'=IF(ABS({celda_dq})<={celda_tol},'
            f'"EQUILIBRIO: el sistema cumple la ecuación de continuidad (ΔQ ≈ 0).",'
            f'IF({celda_dq}>0,"ERRÓNEO. AUMENTA el valor de Hj.","ERRÓNEO. DISMINUYE el valor de Hj."))'
        )
        esc(ws, r_r, c_r, r_r + 3, c_r, "Diagnóstico", F["cab"])
        ws.merge_range(r_r, c_r + 1, r_r + 3, c_r + ancho_res, "", formato_diag)
        ws.write_formula(r_r, c_r + 1, diagnostico, formato_diag, res.get("recomendacion", ""))
        for k in range(4):
            ws.set_row(r_r + k, 22)

        verde = libro.add_format({"font_color": "#1e7b34", "bold": True})
        rojo = libro.add_format({"font_color": "#c0392b", "bold": True})
        rango_diag = (r_r, c_r + 1, r_r + 3, c_r + ancho_res)
        ws.conditional_format(*rango_diag, {
            "type": "text", "criteria": "begins with", "value": "EQUILIBRIO", "format": verde,
        })
        ws.conditional_format(*rango_diag, {
            "type": "text", "criteria": "begins with", "value": "ERRÓNEO", "format": rojo,
        })

    def _hoja_memoria_bomba_ramificada(self, libro, datos):
        """
        Genera la hoja de memoria de cálculo en Excel para Bombas en Redes Ramificadas:
        - Parámetros de la red, cotas y fluido.
        - Algoritmo en 6 pasos del curso (PPTX).
        - Tabla de iteraciones paso a paso (Q_sup, H_B, hf_1, H_j, ΔQ, Acción).
        - Resumen del punto de operación y verificación de continuidad.
        """
        ws = libro.add_worksheet("Memoria Bomba Ramificada")
        ws.hide_gridlines(2)
        F = self._formatos_excel(libro)
        esc = self._escribir_rango

        b_info = datos.get("bomba", {}) or {}
        tubs = datos.get("tuberias", []) or []
        iteraciones = datos.get("iteraciones", []) or []
        H_j = datos.get("H_j", 0.0)
        error_Q = datos.get("error_Q", 0.0)
        ec_cont = datos.get("ecuacion_continuidad", "")

        ws.set_column(0, 0, 4)
        ws.set_column(1, 1, 34)
        ws.set_column(2, 6, 18)
        ws.set_column(7, 7, 38)

        # 1. Título principal
        ws.merge_range(1, 1, 1, 7, "Memoria de Cálculo — Bomba en Red Ramificada", F["titulo"])
        ws.set_row(1, 24)

        # 2. Datos Generales de la Instalación
        r = 3
        esc(ws, r, 1, r, 3, "1. Datos Generales y Parámetros del Sistema", F["seccion"])
        esc(ws, r, 4, r, 7, "2. Algoritmo de Solución (6 Fases)", F["seccion"])
        r += 1

        filas_datos = [
            ("Bomba impulsora", b_info.get("nombre", "Bomba 1")),
            ("Arreglo de bombeo", str(b_info.get("arreglo", "individual")).capitalize()),
            ("Altura de eje de bomba Z_bomba [m]", float(b_info.get("z_bomba", 0.0))),
            ("Cota piezométrica calculada en nudo J (Hj) [m]", float(H_j)),
            ("Continuidad en el nudo J", str(ec_cont)),
            ("Variación de caudal en el nudo (ΔQ) [m³/s]", float(error_Q)),
        ]

        pasos_algoritmo = [
            "Fase 1: Suponer un caudal inicial para la bomba Q_B.",
            "Fase 2: Obtener H_B(Q_B) y calcular pérdida en impulsión hf_1(Q_B).",
            "Fase 3: Calcular altura piezométrica en el nudo: H_j = Z_1 + H_B - hf_1.",
            "Fase 4: Con H_j, calcular caudales de ramales Q_i por Darcy y Kármán.",
            "Fase 5: Evaluar continuidad en nudo j: ΔQ = Q_entran - Q_salen.",
            "Fase 6: Si ΔQ > 0 disminuir Q_B; si ΔQ < 0 aumentar Q_B (hasta |ΔQ| < tol).",
        ]

        for i in range(max(len(filas_datos), len(pasos_algoritmo))):
            if i < len(filas_datos):
                etq, val = filas_datos[i]
                ws.write(r, 1, etq, F["etiqueta"])
                if isinstance(val, (int, float)):
                    ws.write_number(r, 2, val, F["valor"])
                else:
                    ws.write(r, 2, val, F["valor"])
                ws.write(r, 3, "", F["valor"])
            if i < len(pasos_algoritmo):
                esc(ws, r, 4, r, 7, pasos_algoritmo[i], F["etiqueta"])
            r += 1

        # 3. Tabla de Tuberías del Sistema
        r += 1
        esc(ws, r, 1, r, 7, "Tuberías del Sistema Ramificado", F["seccion"])
        r += 1
        cabs_tub = ["Tubería", "Longitud L [m]", "Diámetro D [m]", "Rugosidad e [m]", "Caudal Q [m³/s]", "Caudal Q [L/s]", "Pérdida hf [m]"]
        for c_idx, c_nom in enumerate(cabs_tub):
            ws.write(r, 1 + c_idx, c_nom, F["subcab"])
        r += 1

        for tub_item in tubs:
            resultado = self._resultado_tramo_excel(tub_item)
            ws.write(r, 1, tub_item.get("nombre", "Tubería"), F["etiqueta"])
            ws.write_number(r, 2, float(tub_item.get("L", 0.0)), F["valor"])
            ws.write_number(r, 3, float(tub_item.get("D", 0.0)), F["valor"])
            ws.write_number(r, 4, float(tub_item.get("rugosidad", 0.0)), F["valor"])
            q_val = float(tub_item.get("Q", 0.0))
            ws.write_number(r, 5, q_val, F["valor"])
            ws.write_number(r, 6, q_val * 1000.0, F["valor"])
            refs = self._hidraulica_excel(libro, tub_item)
            ws.write_formula(r, 7, '='+refs['hf'], F['valor'], resultado.hf_total)
            r += 1

        # 4. Tabla de Iteraciones Paso a Paso
        if iteraciones:
            r += 1
            esc(ws, r, 1, r, 7, "Tabla de Iteraciones Paso a Paso (Método de Continuidad en Nudo)", F["seccion"])
            r += 1
            cabs_iter = [
                "Iteración",
                "Q_supuesto [m³/s]",
                "H_Bomba [m]",
                "hf_impulsión [m]",
                "H_j [m]",
                "ΔQ [m³/s]",
                "Acción Recomendada",
            ]
            for c_idx, c_nom in enumerate(cabs_iter):
                ws.write(r, 1 + c_idx, c_nom, F["subcab"])
            r += 1

            for it in iteraciones:
                ws.write(r, 1, it.get("iteracion", 1), F["valor"])
                ws.write_number(r, 2, float(it.get("Q_supuesto", 0.0)), F["valor"])
                ws.write_number(r, 3, float(it.get("H_bomba", 0.0)), F["valor"])
                ws.write_number(r, 4, float(it.get("hf_bomba", 0.0)), F["valor"])
                ws.write_number(r, 5, float(it.get("H_j", 0.0)), F["valor"])
                ws.write_number(r, 6, float(it.get("error_Q", 0.0)), F["valor"])
                ws.write(r, 7, str(it.get("accion", "")), F["etiqueta"])
                r += 1

        # 5. Resumen del Punto de Operación de la Bomba
        r += 1
        esc(ws, r, 1, r, 7, "Resultados Finales del Punto de Operación", F["seccion"])
        r += 1
        resumen_final = [
            ("Caudal de operación Q_op", f"{float(b_info.get('Q_op', 0.0)):.6f} m³/s ({float(b_info.get('Q_op', 0.0))*1000.0:.2f} L/s)"),
            ("Carga manométrica de operación H_op", f"{float(b_info.get('H_op', 0.0)):.2f} m"),
            ("Cota piezométrica final en nudo J (Hj)", f"{float(H_j):.2f} m"),
            ("Rendimiento hidráulico (η)", f"{float(b_info.get('eta_op', 0.0))*100.0:.1f} %" if b_info.get("eta_op") else "—"),
            ("Potencia hidráulica", f"{float(b_info.get('potencia_hidraulica', 0.0))/1000.0:.2f} kW" if b_info.get("potencia_hidraulica") else "N/D"),
            ("Potencia al freno (BHP)", f"{float(b_info.get('potencia_freno', 0.0))/1000.0:.2f} kW" if b_info.get("potencia_freno") is not None else "—"),
            ("NPSH disponible", f"{float(b_info.get('npsh_d', 0.0)):.2f} m" if b_info.get("npsh_d") is not None else "N/D"),
            ("Veredicto de cavitación", str(b_info.get("cavitacion") or "No evaluada")),
        ]
        for etq_rf, val_rf in resumen_final:
            ws.write(r, 1, etq_rf, F["destacado_etq"])
            esc(ws, r, 2, r, 7, val_rf, F["destacado_val"])
            r += 1

    def _hoja_memoria_calculo(self, libro, datos):
        ws = libro.add_worksheet("Memoria de Calculo")
        ws.hide_gridlines(2)
        F = self._formatos_excel(libro)
        esc = self._escribir_rango
        tubs = datos["tuberias"]
        n = len(tubs)
        sup = datos["suposiciones"]
        glob = datos.get("resultados_globales", {}) or {}
        res = datos["resultados"]
        ref = xl_rowcol_to_cell
        tipo_sis = datos["tipo_sistema"]

        idx_sup = None
        if sup.get("Tub_Supuesta") is not None:
            idx_sup = next((i for i, t in enumerate(tubs) if t["nombre"] == sup["Tub_Supuesta"]), None)

        es_paralelo_clasico = (
            tipo_sis == "Sistema en Paralelo"
            and idx_sup is not None
        )
        es_mixto = tipo_sis == "Sistema Mixto (Paralelo-Serie)" and idx_sup is not None
        es_ampliacion = tipo_sis == "Sistema en Paralelo (Ampliación)"
        es_serie_energia = tipo_sis == "Sistema en Serie (por Energía)"
        es_ramificado = tipo_sis == "Sistema Ramificado"

        def v(valor):
            return "—" if valor is None else valor

        def num(valor):
            return 0 if valor is None else valor

        tiene_diseno_d = any(
            t.get("rol") in ("diseno_d", "serie_diseno_d") for t in tubs
        )
        ancho_centro = max(n, 3 if tiene_diseno_d else 1)
        c_d = 0
        c_c = n + 2
        c_r = c_c + ancho_centro + 2
        ancho_res = 2
        ancho_total = c_r + ancho_res

        ws.set_column(c_d, c_d, 36)
        ws.set_column(c_d + 1, c_d + n, 18)
        ws.set_column(n + 1, n + 1, 4)
        ws.set_column(c_c, c_c, 36)
        ws.set_column(c_c + 1, c_c + ancho_centro, 18)
        ws.set_column(c_c + ancho_centro + 1, c_c + ancho_centro + 1, 4)
        ws.set_column(c_r, c_r, 30)
        ws.set_column(c_r + 1, c_r + ancho_res, 22)

        ws.merge_range(0, 0, 0, ancho_total, f"Memoria de cálculo — {tipo_sis}", F["titulo"])
        ws.set_row(0, 24)

        r_sec = 2
        esc(ws, r_sec, c_d, r_sec, c_d + n, "Datos", F["seccion"])
        esc(ws, r_sec, c_c, r_sec, c_c + n, "Cálculos intermedios", F["seccion"])
        esc(ws, r_sec, c_r, r_sec, c_r + ancho_res, "Resultados", F["seccion"])

        r_cab = r_sec + 2
        for c0 in (c_d, c_c):
            esc(ws, r_cab, c0, r_cab + 1, c0, "Propiedades", F["cab"])
            esc(ws, r_cab, c0 + 1, r_cab, c0 + n, "Tuberías", F["cab"])
            for i, t in enumerate(tubs):
                ws.write(r_cab + 1, c0 + 1 + i, t["id"] if t["id"] is not None else i + 1, F["cab"])

        r = r_cab + 2
        filas_datos = [
            ("Longitud (L) [m]", "L"),
            ("Diámetro (D) [m]", "D"),
            ("Rugosidad (e) [m]", "rugosidad"),
            ("Altura (z) [m]", "Z_origen"),
            ("Rugosidad relativa (e/D)", "rugosidad_relativa"),
            ("Área de la tubería (A) [m²]", "Area"),
        ]
        fila_L = r
        fila_D = r + 1
        fila_e = r + 2
        fila_Z = r + 3
        fila_relativa = r + 4
        fila_A = r + 5
        fila_rho = r + len(filas_datos)
        fila_mu = fila_rho + 1
        celda_global = c_d + 1
        r_fin_datos = fila_mu
        r_sup = r_fin_datos + 3
        r_s0 = r_sup + 2

        def abs_rho():
            return ref(fila_rho, celda_global, True, True)

        def abs_mu():
            return ref(fila_mu, celda_global, True, True)

        def esc_sup_val(fila, valor, formato):
            esc(ws, fila, c_d + 1, fila, c_d + n, valor, formato)
            return ref(fila, c_d + 1, True, True)

        def esc_sup_formula(fila, formula, cache, formato):
            if n == 1:
                ws.write_formula(fila, c_d + 1, formula, formato, cache)
            else:
                ws.merge_range(fila, c_d + 1, fila, c_d + n, "", formato)
                ws.write_formula(fila, c_d + 1, formula, formato, cache)
            return ref(fila, c_d + 1, True, True)

        # Escritura preliminar de Datos (las celdas D de Rol C se conectarán a su tabla de diseño)
        for k, (etq, clave) in enumerate(filas_datos):
            ws.write(r + k, c_d, etq, F["etiqueta"])
            for i, t in enumerate(tubs):
                c = c_d + 1 + i
                if clave == "rugosidad_relativa":
                    ws.write_formula(
                        fila_relativa, c, f"=IFERROR({ref(fila_e, c)}/{ref(fila_D, c)},0)",
                        F["valor"], num(t.get("rugosidad_relativa")),
                    )
                elif clave == "Area":
                    ws.write_formula(
                        fila_A, c, f"=PI()*({ref(fila_D, c)}^2)/4", F["valor"], num(t.get("Area"))
                    )
                elif clave == "Z_origen":
                    if es_serie_energia and i == 0 and sup.get("H_A") is not None:
                        ws.write(fila_Z, c, sup["H_A"], F["valor"])
                    elif es_serie_energia and i == n - 1 and sup.get("H_B") is not None:
                        ws.write(fila_Z, c, sup["H_B"], F["valor"])
                    elif es_ramificado:
                        z = t.get("Z_origen")
                        ws.write(fila_Z, c, 0.0 if z is None else z, F["valor"])
                    else:
                        ws.write(fila_Z, c, v(t.get("Z_origen")), F["valor"])
                else:
                    ws.write(r + k, c, v(t.get(clave)), F["valor"])
        ws.write(fila_rho, c_d, "Densidad (ρ) [kg/m³]", F["etiqueta"])
        esc(ws, fila_rho, celda_global, fila_rho, c_d + n, tubs[0]["rho"], F["valor"])
        ws.write(fila_mu, c_d, "Viscosidad dinámica (μ) [Pa·s]", F["etiqueta"])
        esc(ws, fila_mu, celda_global, fila_mu, c_d + n, tubs[0]["mu"], F["valor"])

        esc(ws, r_sup, c_d, r_sup, c_d + n, "Suposiciones", F["seccion"])

        celda_dq_vivo = None
        celda_dh_vivo = None
        celdas_D_diseno = {}

        # ==================================================================
        # CASO 3 y 4B: PARALELO CLÁSICO Y MIXTO PARALELO-SERIE
        # ==================================================================
        if es_paralelo_clasico or es_mixto:
            fila_s_Qt = r_s0
            fila_s_tub = r_s0 + 1
            fila_s_q = r_s0 + 2
            fila_s_sum = r_s0 + 3
            fila_s_K = r_s0 + 4

            fila_hf = r
            fila_hfs = r + 1
            fila_karman = r + 2
            fila_inv = r + 3
            fila_Re = r + 4
            fila_Qs = r + 5
            fila_Vs = r + 6
            fila_Qr = r + 7
            fila_Vr = r + 8
            r_iter = fila_Vr + 3

            indices_par = [
                i for i, t in enumerate(tubs) if t.get("rol") in ("par_sup", "par_karman") or "Q_sup" in t
            ]
            m_par = len(indices_par)

            ws.write(fila_s_Qt, c_d, "Caudal total real (Q_total) [m³/s]", F["destacado_etq"])
            celda_Qt = esc_sup_val(fila_s_Qt, sup["Q_total"], F["destacado_val"])
            ws.write(fila_s_tub, c_d, "Tubería supuesta", F["etiqueta"])
            esc_sup_val(fila_s_tub, sup["Tub_Supuesta"], F["valor"])
            ws.write(fila_s_q, c_d, "Caudal supuesto (Q') [m³/s]", F["destacado_etq"])
            celda_q_sup = esc_sup_val(fila_s_q, sup["Q_supuesto"], F["destacado_val"])
            ws.write(fila_s_sum, c_d, "Residuo de masa relativo", F['etiqueta'])
            esc_sup_val(fila_s_sum, sup.get('Residuo_masa_relativo', 0.0), F['valor'])
            ws.write(fila_s_K, c_d, "Iteraciones de bisección", F['destacado_etq'])
            esc_sup_val(fila_s_K, sup.get('Iteraciones', 0), F['destacado_val'])
            r_s_next = fila_s_K + 1

            celda_hf_serie_disp = None
            if es_mixto and sup.get("hf_serie") is not None:
                ws.write(r_s_next, c_d, "hf disponible en tubería en serie [m]", F["destacado_etq"])
                celda_hf_serie_disp = esc_sup_val(r_s_next, sup["hf_serie"], F["destacado_val"])
                r_s_next += 1

            # Tablas de iteraciones debajo de Cálculos intermedios
            entradas_cb = [{
                'i': i, 'nombre': t['nombre'],
                'celda_Re': ref(fila_Re, c_c + 1 + i),
                'celda_eD': ref(fila_relativa, c_d + 1 + i),
                'Re': t['Re'], 'rug_rel': t['rugosidad_relativa'],
                'resultado_tramo': self._resultado_tramo_excel(t),
            } for i, t in enumerate(tubs) if t['Re'] is not None and t['Re'] >= RE_LIMITE_LAMINAR]
            celdas_f, celdas_inv, r_iter_next = self._tabla_iteraciones(
                ws, F, entradas_cb, c_c, r_iter, con_subtitulo=True
            )

            entradas_d = []
            for i, t in enumerate(tubs):
                if t.get("rol") == "serie_diseno_d":
                    entradas_d.append({
                        "i": i,
                        "nombre": f"{t['nombre']} (Diseño en serie)",
                        "celda_Q": ref(fila_Qr, c_c + 1 + i),
                        "celda_hf": ref(fila_hf, c_c + 1 + i),
                        "celda_L": ref(fila_L, c_d + 1 + i),
                        "celda_e": ref(fila_e, c_d + 1 + i),
                        "abs_rho": abs_rho(),
                        "abs_mu": abs_mu(),
                        "Q": t["Q"],
                        "hf": t["hf"],
                        "L": t["L"], "K": t.get("K", 0.0), "LeD": t.get("LeD", 0.0),
                        "eps": t["rugosidad"],
                        "rho": t["rho"],
                        "mu": t["mu"],
                        "D_final": t["D"],
                    })
            celdas_inv_D = {}
            if entradas_d:
                celdas_D_diseno, celdas_inv_D, _ = self._tabla_iteraciones_diametro(
                    ws, F, entradas_d, c_c, r_iter_next + 1, libro=libro
                )
                for i_d, celda_d_fin in celdas_D_diseno.items():
                    ws.write_formula(
                        fila_D, c_d + 1 + i_d, f"={celda_d_fin}", F["destacado_val"], tubs[i_d]["D"]
                    )


            filas_calc = [
                "Pérdidas por fricción (hf) [m]",
                "Pérdidas supuestas (hf') [m]",
                "Número de Kármán (Re'·√f')",
                "1/√f'",
                "Número de Reynolds supuesto (Re')",
                "Caudal supuesto (Q') [m³/s]",
                "Velocidad supuesta (V') [m/s]",
                "Caudal verdadero (Q) [m³/s]",
                "Velocidad verdadera (V) [m/s]",
            ]
            filas_calc[2:5] = ["Número de Kármán (Re·√f)", "1/√f", "Número de Reynolds (Re)"]
            for k, etq in enumerate(filas_calc):
                ws.write(r + k, c_c, etq, F["etiqueta"])

            for i, t in enumerate(tubs):
                c = c_c + 1 + i
                self._escribir_hidraulica_excel(ws, libro, t,
                    dict(hf=fila_hf, karman=fila_karman, inv_raiz_f=fila_inv,
                         Re=fila_Re, Q=fila_Qr, V=fila_Vr), c, F['valor'])
                for fila, clave in ((fila_hfs, 'hf_sup'), (fila_Qs, 'Q_sup'), (fila_Vs, 'V_sup')):
                    ws.write(fila, c, v(t.get(clave)), F['valor'])

        # ==================================================================
        # CASOS 1A (3 TANQUES), 2 (SERIE), 4A (AMPLIACIÓN) Y SIMPLE
        # ==================================================================
        else:
            fila_hf = r
            fila_karman = r + 1
            fila_inv = r + 2
            fila_f = r + 3
            fila_Re = r + 4
            fila_V = r + 5
            fila_Q = r + 6
            r_iter = fila_Q + 3

            # --- Construcción del bloque Suposiciones según el caso ---
            celda_hj_ram = None
            celda_hj_serie = None
            celdas_nodos_serie = []
            celda_hb_calc = None
            celda_hb_real = None
            celda_Qt_amp = None
            celda_hf_amp = None

            if es_ramificado:
                hj_val = sup.get("H_j (Supuesta)")
                if hj_val is None:
                    hj_val = glob.get("H_j (Calculada)", 0.0)
                ws.write(r_s0, c_d, "Altura piezométrica (Hj) [m]", F["destacado_etq"])
                celda_hj_ram = esc_sup_val(r_s0, hj_val, F["destacado_val"])

            elif es_serie_energia:
                hj_val = sup.get("H_J (Supuesta)")
                if hj_val is None:
                    hj_val = sup.get("H_J (Calculada)", 0.0)
                ws.write(r_s0, c_d, "Altura supuesta en nudo 1 (Hj) [m]", F["destacado_etq"])
                celda_hj_serie = esc_sup_val(r_s0, hj_val, F["destacado_val"])
                celdas_nodos_serie.append(celda_hj_serie)

                r_curr = r_s0 + 1
                letras = ("j", "k", "l", "m")
                for idx_tr in range(1, n - 1):
                    letra_ant = letras[idx_tr - 1] if idx_tr - 1 < len(letras) else f"n{idx_tr}"
                    letra_act = letras[idx_tr] if idx_tr < len(letras) else f"n{idx_tr + 1}"
                    celda_ant = celdas_nodos_serie[-1]
                    celda_hf_tr = ref(fila_hf, c_c + 1 + idx_tr)
                    h_cache = sup["H_A"] - sum(tubs[m]["hf"] for m in range(idx_tr + 1))
                    ws.write(
                        r_curr, c_d,
                        f"Altura calculada (H{letra_act} = H{letra_ant} - hf{idx_tr + 1}) [m]",
                        F["etiqueta"],
                    )
                    c_nodo = esc_sup_formula(
                        r_curr, f"={celda_ant}-{celda_hf_tr}", h_cache, F["valor"]
                    )
                    celdas_nodos_serie.append(c_nodo)
                    r_curr += 1

                celda_ult_nodo = celdas_nodos_serie[-1]
                celda_hf_ult = ref(fila_hf, c_c + n)
                hb_star_cache = glob.get(
                    "H_B* (Llegada calculada)",
                    sup["H_A"] - sum(t["hf"] for t in tubs),
                )
                ws.write(
                    r_curr, c_d,
                    f"Altura llegada (HB* = H{letras[min(n - 2, 3)]} - hf{n}) [m]",
                    F["destacado_etq"],
                )
                celda_hb_calc = esc_sup_formula(
                    r_curr, f"={celda_ult_nodo}-{celda_hf_ult}", hb_star_cache, F["destacado_val"]
                )
                r_curr += 1

                ws.write(r_curr, c_d, "Altura real destino (HB) [m]", F["etiqueta"])
                celda_hb_real = esc_sup_val(r_curr, sup.get("H_B", 0.0), F["valor"])

            elif es_ampliacion:
                ws.write(r_s0, c_d, "Caudal Total Requerido (Q_total) [m³/s]", F["destacado_etq"])
                celda_Qt_amp = esc_sup_val(r_s0, sup["Q_total"], F["destacado_val"])
                ws.write(r_s0 + 1, c_d, "Pérdida de carga disponible (hf) [m]", F["destacado_etq"])
                celda_hf_amp = esc_sup_val(r_s0 + 1, sup["hf_disponible"], F["destacado_val"])

            else:
                r_s = r_s0
                sup_limpio = {k: val for k, val in sup.items() if val is not None}
                if not sup_limpio and not glob:
                    esc(ws, r_s, c_d, r_s, c_d + n, "Datos directos sin suposiciones", F["ok"])
                else:
                    for clave_s, valor_s in sup_limpio.items():
                        ws.write(r_s, c_d, clave_s, F["destacado_etq"])
                        esc_sup_val(r_s, valor_s, F["destacado_val"])
                        r_s += 1
                    for clave_g, valor_g in glob.items():
                        ws.write(r_s, c_d, clave_g, F["etiqueta"])
                        esc_sup_val(r_s, valor_g, F["valor"])
                        r_s += 1

            # --- Tablas de iteraciones en Centro Abajo (según Rol B o Rol C) ---
            entradas_cb = []
            entradas_d = []
            for i, t in enumerate(tubs):
                rol_t = t.get("rol")
                if rol_t in ("colebrook", "serie_colebrook"):
                    if t["Re"] is not None and t["Re"] > 0 and t["Re"] >= RE_LIMITE_LAMINAR:
                        entradas_cb.append({
                            "i": i,
                            "nombre": t["nombre"],
                            "celda_Re": ref(fila_Re, c_c + 1 + i),
                            "celda_eD": ref(fila_relativa, c_d + 1 + i),
                            "Re": t["Re"],
                            "rug_rel": t["rugosidad_relativa"],
                            "resultado_tramo": self._resultado_tramo_excel(t),
                        })
                elif rol_t == "diseno_d":
                    entradas_d.append({
                        "i": i,
                        "nombre": f"{t['nombre']} (Diseño de Diámetro)",
                        "celda_Q": ref(fila_Q, c_c + 1 + i),
                        "celda_hf": ref(fila_hf, c_c + 1 + i),
                        "celda_L": ref(fila_L, c_d + 1 + i),
                        "celda_e": ref(fila_e, c_d + 1 + i),
                        "abs_rho": abs_rho(),
                        "abs_mu": abs_mu(),
                        "Q": t["Q"],
                        "hf": t["hf"],
                        "L": t["L"], "K": t.get("K", 0.0), "LeD": t.get("LeD", 0.0),
                        "eps": t["rugosidad"],
                        "rho": t["rho"],
                        "mu": t["mu"],
                        "D_final": t["D"],
                    })

            celdas_f = {}
            celdas_inv = {}
            r_iter_actual = r_iter
            if entradas_cb:
                celdas_f, celdas_inv, r_iter_actual = self._tabla_iteraciones(
                    ws, F, entradas_cb, c_c, r_iter_actual,
                    con_subtitulo=len(entradas_cb) > 1 or n > 1,
                )
                r_iter_actual += 1

            celdas_inv_D = {}
            if entradas_d:
                celdas_D_diseno, celdas_inv_D, _ = self._tabla_iteraciones_diametro(
                    ws, F, entradas_d, c_c, r_iter_actual, libro=libro
                )
                for i_d, celda_d_fin in celdas_D_diseno.items():
                    ws.write_formula(
                        fila_D, c_d + 1 + i_d, f"={celda_d_fin}", F["destacado_val"], tubs[i_d]["D"]
                    )

            # --- Cálculos intermedios en Centro Arriba ---
            filas_calc = [
                ("Pérdidas por fricción (hf) [m]", "hf"),
                ("Número de Kármán (Re·√f)", "karman"),
                ("1/√f", "inv_raiz_f"),
                ("Factor de fricción (f)", "f"),
                ("Número de Reynolds (Re)", "Re"),
                ("Velocidad promedio (V) [m/s]", "V"),
                ("Caudal (Q) [m³/s]", "Q"),
            ]
            for k, (etq, _) in enumerate(filas_calc):
                ws.write(r + k, c_c, etq, F["etiqueta"])

            for i, t in enumerate(tubs):
                self._escribir_hidraulica_excel(ws, libro, t,
                    dict(hf=fila_hf, karman=fila_karman, inv_raiz_f=fila_inv, f=fila_f,
                         Re=fila_Re, V=fila_V, Q=fila_Q), c_c + 1 + i, F['valor'])

        # ==================================================================
        # BLOQUE RESULTADOS (Columna Derecha Arriba)
        # ==================================================================
        r_r = r_cab
        celda_q_op_res = None
        if "bomba" in datos:
            b_res = datos["bomba"]
            q_op_val = float(b_res.get("Q_op", 0.0))
            h_op_val = float(b_res.get("H_op", 0.0))
            raw_eta_res = b_res.get("eta_op")
            eta_op_val = float(raw_eta_res) if raw_eta_res is not None else None
            p_hid_kw_val = float(b_res.get("potencia_hidraulica", 0.0)) / 1000.0
            raw_pf_res = b_res.get("potencia_freno")
            p_freno_kw_val = (
                float(raw_pf_res) / 1000.0
                if (raw_pf_res is not None and math.isfinite(float(raw_pf_res)))
                else None
            )
            npsh_d_val = b_res.get("npsh_d")
            npsh_r_val = b_res.get("npsh_r")
            cav_val = b_res.get("cavitacion")
            cav_txt = (
                str(cav_val)
                if (npsh_r_val is not None and cav_val is not None)
                else "No evaluada (sin NPSHr)"
            )

            fmt_num_4 = libro.add_format({
                "font_name": "Calibri", "font_size": 11, "valign": "vcenter",
                "bold": True, "align": "center", "border": 1, "bg_color": "#FFE699",
                "num_format": "0.0000",
            })
            fmt_num_2 = libro.add_format({
                "font_name": "Calibri", "font_size": 11, "valign": "vcenter",
                "bold": True, "align": "center", "border": 1, "bg_color": "#FFE699",
                "num_format": "0.00",
            })
            fmt_num_3 = libro.add_format({
                "font_name": "Calibri", "font_size": 11, "valign": "vcenter",
                "bold": True, "align": "center", "border": 1, "bg_color": "#FFE699",
                "num_format": "0.000",
            })

            def _esc_res_num(fila_idx, etq_res, val_num, fmt_celda):
                ws.write(fila_idx, c_r, etq_res, F["destacado_etq"])
                ws.merge_range(fila_idx, c_r + 1, fila_idx, c_r + ancho_res, "", fmt_celda)
                if val_num is None:
                    ws.write(fila_idx, c_r + 1, '—', fmt_celda)
                else:
                    ws.write_number(fila_idx, c_r + 1, float(val_num), fmt_celda)
                return ref(fila_idx, c_r + 1, True, True)

            def _esc_res_formula(fila_idx, etq_res, formula_str, val_cache, fmt_celda):
                ws.write(fila_idx, c_r, etq_res, F["destacado_etq"])
                ws.merge_range(fila_idx, c_r + 1, fila_idx, c_r + ancho_res, "", fmt_celda)
                ws.write_formula(fila_idx, c_r + 1, formula_str, fmt_celda, float(val_cache))
                return ref(fila_idx, c_r + 1, True, True)

            celda_q_op_res = _esc_res_num(r_r, "Q_op [m³/s]", q_op_val, fmt_num_4)
            r_r += 1
            _esc_res_formula(r_r, "Q_op [L/s]", f"={celda_q_op_res}*1000", q_op_val * 1000.0, fmt_num_2)
            r_r += 1
            celda_h_op_res = _esc_res_num(r_r, "H_op [m]", h_op_val, fmt_num_2)
            r_r += 1

            if eta_op_val is not None:
                celda_eta_res = _esc_res_num(r_r, "η_op [%]", eta_op_val * 100.0, fmt_num_2)
            else:
                ws.write(r_r, c_r, "η_op [%]", F["destacado_etq"])
                esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, "—", F["destacado_val"])
                celda_eta_res = None
            r_r += 1

            celda_phid_res = _esc_res_formula(
                r_r,
                "Potencia hidráulica [kW]",
                f"=({abs_rho()}*9.81*{celda_q_op_res}*{celda_h_op_res})/1000",
                p_hid_kw_val,
                fmt_num_3,
            )
            r_r += 1

            if p_freno_kw_val is not None and celda_eta_res is not None:
                celda_bhp_kw_res = _esc_res_formula(
                    r_r,
                    "BHP [kW]",
                    f"=IFERROR({celda_phid_res}/({celda_eta_res}/100),0)",
                    p_freno_kw_val,
                    fmt_num_3,
                )
            else:
                ws.write(r_r, c_r, "BHP [kW]", F["destacado_etq"])
                esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, "—", F["destacado_val"])
                celda_bhp_kw_res = None
            r_r += 1

            if p_freno_kw_val is not None and celda_bhp_kw_res is not None:
                _esc_res_formula(
                    r_r,
                    "BHP [HP]",
                    f"={celda_bhp_kw_res}/0.7457",
                    p_freno_kw_val / 0.7457,
                    fmt_num_2,
                )
            else:
                ws.write(r_r, c_r, "BHP [HP]", F["destacado_etq"])
                esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, "—", F["destacado_val"])
            r_r += 1

            _esc_res_num(r_r, "NPSHd [m]", npsh_d_val, fmt_num_2)
            r_r += 1

            ws.write(r_r, c_r, "Cavitación", F["destacado_etq"])
            esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, cav_txt, F["destacado_val"])
            r_r += 1

            # Enlazar las celdas de caudal (p. ej. F13 y G13) a la celda Q_op [m³/s] de Resultados
            if not (es_paralelo_clasico or es_mixto) and celda_q_op_res is not None:
                for i, t in enumerate(tubs):
                    c = c_c + 1 + i
                    ws.write_formula(
                        fila_Q, c, f"={celda_q_op_res}", F["valor"], float(num(t.get("Q")))
                    )

        esc(ws, r_r, c_r, r_r, c_r + ancho_res, "Condición final", F["cab_neg"])
        r_r += 1
        for ecuacion in res["condicion_final"]:
            esc(ws, r_r, c_r, r_r, c_r + ancho_res, ecuacion, F["valor"])
            r_r += 1

        celda_var_fija = None
        if es_ramificado:
            # La continuidad de una red segmentada se verifica por ramal en
            # el motor; sumar cada tubería aquí contaría el mismo Q varias veces.
            ws.write(r_r, c_r, "Variación de Q (ΔQ) [m³/s]", F['etiqueta'])
            esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, num(res['variacion_Q']), F['valor'])
            celda_dq_vivo = ref(r_r, c_r + 1, True, True)
            r_r += 1
            ws.write(r_r, c_r, "Tolerancia admisible (ε_Q) [m³/s]", F["etiqueta"])
            esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, 0.0001, F["valor"])
            celda_tol = ref(r_r, c_r + 1, True, True)
            r_r += 1
        elif es_serie_energia and celda_hb_calc is not None and celda_hb_real is not None:
            ws.write(r_r, c_r, "Variación de H (HB* - HB) [m]", F["etiqueta"])
            ws.merge_range(r_r, c_r + 1, r_r, c_r + ancho_res, "", F["valor"])
            ws.write_formula(
                r_r, c_r + 1, f"={celda_hb_calc}-{celda_hb_real}",
                F["valor"], num(res["variacion_Q"]),
            )
            celda_dh_vivo = ref(r_r, c_r + 1, True, True)
            r_r += 1
            ws.write(r_r, c_r, "Tolerancia admisible (ε_H) [m]", F["etiqueta"])
            esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, 0.05, F["valor"])
            celda_tol = ref(r_r, c_r + 1, True, True)
            r_r += 1
        else:
            ws.write(r_r, c_r, "Variación de Q [m³/s]", F["etiqueta"])
            esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, num(res["variacion_Q"]), F["valor"])
            celda_var_fija = ref(r_r, c_r + 1, True, True)
            r_r += 1
            ws.write(r_r, c_r, "Tolerancia admisible (ε_Q) [m³/s]", F["etiqueta"])
            esc(ws, r_r, c_r + 1, r_r, c_r + ancho_res, 0.0001, F["valor"])
            celda_tol = ref(r_r, c_r + 1, True, True)
            r_r += 1

        # Si hubo Diseño de Diámetro (Rol C), mostrar el diámetro requerido a 4 y 2 decimales
        for i_d, celda_d_fin in celdas_D_diseno.items():
            d_val = tubs[i_d]["D"]
            nom_d = tubs[i_d]["nombre"]
            ws.write(r_r, c_r, f"Diámetro {nom_d} (4 dec.) [m]", F["destacado_etq"])
            ws.merge_range(r_r, c_r + 1, r_r, c_r + ancho_res, "", F["destacado_val"])
            ws.write_formula(
                r_r, c_r + 1, f"=ROUND({celda_d_fin},4)", F["destacado_val"], round(d_val, 4)
            )
            r_r += 1
            ws.write(r_r, c_r, f"Diámetro {nom_d} (2 dec.) [m]", F["destacado_etq"])
            ws.merge_range(r_r, c_r + 1, r_r, c_r + ancho_res, "", F["destacado_val"])
            ws.write_formula(
                r_r, c_r + 1, f"=ROUND({celda_d_fin},2)", F["destacado_val"], round(d_val, 2)
            )
            r_r += 1

        formato_diag = F["ok"] if res["ok"] else F["error"]
        esc(ws, r_r, c_r, r_r + 3, c_r, "Diagnóstico", F["cab"])
        ws.merge_range(r_r, c_r + 1, r_r + 3, c_r + ancho_res, "", formato_diag)

        if celda_dq_vivo is not None:
            diag_formula = (
                f'=IF(ABS({celda_dq_vivo})<={celda_tol},'
                f'"EQUILIBRIO: el sistema cumple la ecuación de continuidad (ΔQ ≈ 0).",'
                f'IF({celda_dq_vivo}>0,"ERRÓNEO. AUMENTA el valor de Hj.","ERRÓNEO. DISMINUYE el valor de Hj."))'
            )
            ws.write_formula(r_r, c_r + 1, diag_formula, formato_diag, res["recomendacion"])
        elif celda_dh_vivo is not None:
            diag_formula = (
                f'=IF(ABS({celda_dh_vivo})<={celda_tol},'
                f'"EQUILIBRIO: La altura supuesta Hj SÍ ES ADECUADA (HB* ≈ HB).",'
                f'IF({celda_dh_vivo}>0,'
                f'"ERRÓNEO: Hj NO ES ADECUADA (sobra energía: HB* > HB). DISMINUYE Hj.",'
                f'"ERRÓNEO: Hj NO ES ADECUADA (falta energía: HB* < HB). AUMENTA Hj."))'
            )
            ws.write_formula(r_r, c_r + 1, diag_formula, formato_diag, res["recomendacion"])
        else:
            rec_segura = str(res["recomendacion"]).replace('"', '""')
            diag_formula = (
                f'=IF(ABS({celda_var_fija})<={celda_tol},'
                f'"{rec_segura}",'
                f'"ERRÓNEO: Verifica la conservación de masa y energía.")'
            )
            ws.write_formula(r_r, c_r + 1, diag_formula, formato_diag, res["recomendacion"])

        for k in range(4):
            ws.set_row(r_r + k, 22)

        verde = libro.add_format({"font_color": "#1e7b34", "bold": True})
        rojo = libro.add_format({"font_color": "#c0392b", "bold": True})
        rango_diag = (r_r, c_r + 1, r_r + 3, c_r + ancho_res)
        ws.conditional_format(*rango_diag, {
            "type": "text", "criteria": "begins with", "value": "EQUILIBRIO", "format": verde,
        })
        ws.conditional_format(*rango_diag, {
            "type": "text", "criteria": "begins with", "value": "ERRÓNEO", "format": rojo,
        })

        # Sección paso a paso de bombas si hay bomba en los datos
        if "bomba" in datos:
            r_max_actual = max(r_r + 5, r_iter_actual + 2)
            self._seccion_bombas_paso_a_paso(
                ws, F, libro, datos["bomba"], r_inicio=r_max_actual, ancho_total=ancho_total
            )

    def _seccion_bombas_paso_a_paso(self, ws, F, libro, b_info, r_inicio, ancho_total=8):
        """
        Genera la sección 'Bombas' con el procedimiento paso a paso en la Memoria de Cálculo:
        1. Curva de la bomba (ecuación analítica o interpolación).
        2. Curva del sistema (ecuación de balance energético y pérdidas).
        3. Intersección (resolución numérica del punto de operación).
        4. Potencia hidráulica y potencia al freno con fórmula P = ρ·g·Q·H / η y reemplazo numérico.
        5. NPSH disponible con fórmula y valores numéricos reemplazados.
        """
        esc = self._escribir_rango
        r = r_inicio

        # Encabezado de la sección
        esc(ws, r, 0, r, ancho_total, "MEMORIA DE CÁLCULO — MÓDULO DE BOMBAS CENTRÍFUGAS", F["seccion"])
        r += 1

        # Paso 1: Curva de la bomba
        esc(ws, r, 0, r, ancho_total, "1. Curva Característica de la Bomba", F["subcab"])
        r += 1
        arreglo = str(b_info.get("arreglo", "individual")).capitalize()
        nom_b = b_info.get("nombre", "Bomba")
        ws.write(r, 0, "Arreglo y modelo:", F["etiqueta"])
        esc(ws, r, 1, r, ancho_total, f"{nom_b} en configuración {arreglo}", F["valor"])
        r += 1

        metodo_est = str(b_info.get("metodo", "cuadratico")).lower()
        curvas = b_info.get("curvas", [])
        es_lineal = usa_puntos(curvas,metodo_est)
        for c in curvas:
            nom_c = c.get("nombre", "Curva")

            if es_lineal:
                desc_curva = f"{nom_c}: {resumen_puntos(puntos_tabla(c))}"
            else:
                eq_c = c.get("ecuacion") or {}
                a_c = eq_c.get("a")
                b_c = eq_c.get("b")
                c_c_coef = eq_c.get("c")
                txt_eq_c = eq_c.get("texto", "")
                if a_c is None and c.get("Q") and c.get("H"):
                    try:
                        from motor.bombas import CurvaBomba, ecuacion_total
                        cb_tmp = CurvaBomba(nom_c, c["Q"], c["H"], modo="ajuste")
                        eq_tmp = ecuacion_total(cb_tmp)
                        a_c, b_c, c_c_coef = eq_tmp.a, eq_tmp.b, eq_tmp.c
                        txt_eq_c = eq_tmp.texto
                    except Exception:
                        pass
                if a_c is not None and b_c is not None and c_c_coef is not None:
                    coefs_txt = f"a = {float(a_c):.4g}, b = {float(b_c):.4g}, c = {float(c_c_coef):.4g}"
                    if txt_eq_c:
                        desc_curva = f"{nom_c}: H = a + b·Q + c·Q² (mínimos cuadrados) — {txt_eq_c} ({coefs_txt})"
                    else:
                        desc_curva = f"{nom_c}: H = a + b·Q + c·Q² (mínimos cuadrados) ({coefs_txt})"
                else:
                    desc_curva = f"{nom_c}: H = a + b·Q + c·Q² (mínimos cuadrados)"
            if nota_joroba(c):
                desc_curva += '; '+nota_joroba(c)
            ws.write(r, 0, 'Curva por puntos:' if es_lineal else 'Ecuación característica:', F['etiqueta'])
            esc(ws, r, 1, r, ancho_total, desc_curva, F["valor"])
            r += 1

        if es_lineal:
            puntos = puntos_total(curvas,b_info.get('puntos_equivalente',[]))
            ws.write(r,0,'Curva total (por puntos):',F['destacado_etq'])
            esc(ws,r,1,r,ancho_total,resumen_puntos(puntos,len(curvas)>1),F['destacado_val'])
            r += 1
        else:
            eq_tot = b_info.get("ecuacion_total")
            if not eq_tot and curvas:
                try:
                    from motor.bombas import CurvaBomba, EstacionBombeo, ecuacion_total
                    modo_cb = "interpolacion" if metodo_est == "lineal" else "ajuste"
                    objs_cb = [
                        CurvaBomba(c.get("nombre", "Bomba"), c.get("Q", [0, 1]), c.get("H", [10, 5]), modo=modo_cb)
                        for c in curvas
                    ]
                    if str(b_info.get("arreglo", "")).lower() == "serie":
                        est_tmp = EstacionBombeo.en_serie(objs_cb, metodo=metodo_est)
                    else:
                        est_tmp = EstacionBombeo.en_paralelo(objs_cb, metodo=metodo_est)
                    eq_obj_t = ecuacion_total(est_tmp)
                    eq_tot = {
                        "a": eq_obj_t.a,
                        "b": eq_obj_t.b,
                        "c": eq_obj_t.c,
                        "tipo": eq_obj_t.tipo,
                        "R2": eq_obj_t.R2,
                        "texto": eq_obj_t.texto,
                    }
                except Exception:
                    eq_tot = None

            if eq_tot:
                txt_tot = eq_tot.get("texto", "")
                tipo_tot = eq_tot.get("tipo", "exacta")
                r2_tot = eq_tot.get("R2", 1.0)
                r2_str = f"{float(r2_tot):.3f}" if r2_tot is not None else "1.000"
                if metodo_est == "lineal":
                    etq_tipo_tot = f"Ajuste referencial (R² = {r2_str})"
                elif tipo_tot == "exacta":
                    etq_tipo_tot = "Exacta"
                else:
                    etq_tipo_tot = f"Ajuste (R² = {r2_str})"
                ws.write(r, 0, "Ecuación total de la estación:", F["destacado_etq"])
                esc(ws, r, 1, r, ancho_total, f"{txt_tot}  [{etq_tipo_tot}]", F["destacado_val"])
                r += 1

        r += 1
        # Paso 2: Curva del sistema
        esc(ws, r, 0, r, ancho_total, "2. Curva Resistente del Sistema (Ecuación de Bernoulli)", F["subcab"])
        r += 1
        ws.write(r, 0, "Ecuación teórica:", F["etiqueta"])
        esc(ws, r, 1, r, ancho_total, "H_sistema(Q) = (Z₂ - Z₁) + (P₂ - P₁) / (ρ·g) + Σ hf_tramos(Q)", F["valor"])
        r += 1

        t1 = b_info.get("tanque1", {})
        t2 = b_info.get("tanque2", {})
        z1 = float(t1.get("z", 0.0))
        z2 = float(t2.get("z", 0.0))
        p1 = float(t1.get("P", 0.0))
        p2 = float(t2.get("P", 0.0))
        rho = float(b_info.get("rho", 1000.0))
        g = float(b_info.get("g", 9.81))

        delta_z = z2 - z1
        delta_p = (p2 - p1) / (rho * g) if (rho * g) > 0 else 0.0
        ws.write(r, 0, "Sustitución estática:", F["etiqueta"])
        sust_estatica = (
            f"ΔZ = {z2:.2f} - {z1:.2f} = {delta_z:.2f} m  |  "
            f"ΔP/(ρ·g) = ({p2:.1f} - {p1:.1f}) / ({rho:.1f} × {g:.2f}) = {delta_p:.2f} m"
        )
        esc(ws, r, 1, r, ancho_total, sust_estatica, F["valor"])
        r += 1

        ws.write(r, 0, "Pérdidas dinámicas Σhf:", F["etiqueta"])
        esc(ws, r, 1, r, ancho_total, "Pérdidas por fricción Darcy-Weisbach (Colebrook 0.86·ln) + Accesorios ΣK·V²/(2g)", F["valor"])
        r += 1

        r += 1
        # Paso 3: Intersección (Punto de Operación)
        esc(ws, r, 0, r, ancho_total, "3. Intersección y Punto de Operación (H_bomba = H_sistema)", F["subcab"])
        r += 1
        ws.write(r, 0, "Método de resolución:", F["etiqueta"])
        esc(ws, r, 1, r, ancho_total, "Bisección numérica sobre f(Q) = H_bomba(Q) - H_sistema(Q) = 0 (Tolerancia: 1e-6 m)", F["valor"])
        r += 1

        q_op = float(b_info.get("Q_op", 0.0))
        h_op = float(b_info.get("H_op", 0.0))
        raw_eta = b_info.get("eta_op")
        eta_op = float(raw_eta) if raw_eta is not None else None

        ws.write(r, 0, "Caudal de operación Q_op:", F["destacado_etq"])
        esc(ws, r, 1, r, ancho_total, f"{q_op:.6f} m³/s  ({q_op * 1000.0:.2f} L/s)", F["destacado_val"])
        r += 1

        ws.write(r, 0, "Altura de operación H_op:", F["destacado_etq"])
        esc(ws, r, 1, r, ancho_total, f"{h_op:.4f} m", F["destacado_val"])
        r += 1

        ws.write(r, 0, "Eficiencia en punto op. η:", F["destacado_etq"])
        txt_eta = f"{eta_op * 100.0:.2f} %  (Fracción: {eta_op:.4f})" if eta_op is not None else "No especificada (curva sin datos de η)"
        esc(ws, r, 1, r, ancho_total, txt_eta, F["destacado_val"])
        r += 1

        r += 1
        # Paso 4: Potencia con fórmula P = ρ·g·Q·H / η
        esc(ws, r, 0, r, ancho_total, "4. Demanda de Potencia Hidráulica y al Freno (BHP)", F["subcab"])
        r += 1
        ws.write(r, 0, "Ecuación de potencia:", F["etiqueta"])
        esc(ws, r, 1, r, ancho_total, "P_freno = (ρ · g · Q · H) / η", F["valor"])
        r += 1

        p_hid = float(b_info.get("potencia_hidraulica", 0.0))
        raw_pf = b_info.get("potencia_freno")
        p_freno = float(raw_pf) if raw_pf is not None else None

        sust_p_hid = (
            f"P_hid = {rho:.1f} kg/m³ × {g:.2f} m/s² × {q_op:.4f} m³/s × {h_op:.2f} m = "
            f"{p_hid:.1f} W = {p_hid / 1000.0:.3f} kW"
        )
        ws.write(r, 0, "Potencia hidráulica neta:", F["etiqueta"])
        esc(ws, r, 1, r, ancho_total, sust_p_hid, F["valor"])
        r += 1

        if p_freno is not None and eta_op is not None and eta_op > 0:
            sust_p_fr = (
                f"P_freno = {p_hid / 1000.0:.3f} kW / {eta_op:.4f} = "
                f"{p_freno / 1000.0:.3f} kW  ({p_freno / 745.7:.2f} HP)"
            )
        else:
            sust_p_fr = "P_freno no calculable al no contar con curva de eficiencia η(Q)"
        ws.write(r, 0, "Potencia al freno (BHP):", F["destacado_etq"])
        esc(ws, r, 1, r, ancho_total, sust_p_fr, F["destacado_val"])
        r += 1

        r += 1
        # Paso 5: NPSH y Cavitación con fórmula y valores reemplazados
        esc(ws, r, 0, r, ancho_total, "5. Cálculo de NPSH Disponible y Veredicto de Cavitación", F["subcab"])
        r += 1
        ws.write(r, 0, "Ecuación de NPSHd:", F["etiqueta"])
        esc(ws, r, 1, r, ancho_total, "NPSH_d = P₁_abs / (ρ·g) + (Z₁ - Z_bomba) - hf_succión - Pv / (ρ·g)", F["valor"])
        r += 1

        if any(b_info.get(k) is None for k in ('P1_abs','Pv','npsh_d')):
            esc(ws,r,1,r,ancho_total,'— (faltan datos explícitos de presión para NPSH)',F['valor'])
            return
        p1_abs = float(b_info['P1_abs'])
        pv = float(b_info['Pv'])
        z_bomba = float(b_info.get("z_bomba", 0.0))
        hf_suc = float(b_info.get("hf_succion", 0.0))
        npsh_d = float(b_info.get("npsh_d", 0.0))
        npsh_r = b_info.get("npsh_r", None)
        cavitacion = b_info.get("cavitacion", "SIN RIESGO")

        term_presion = p1_abs / (rho * g) if (rho * g) > 0 else 0.0
        term_cota = z1 - z_bomba
        term_pv = pv / (rho * g) if (rho * g) > 0 else 0.0

        sust_npsh = (
            f"NPSH_d = {p1_abs:.1f}/({rho:.1f}×{g:.2f}) + ({z1:.2f} - {z_bomba:.2f}) - {hf_suc:.4f} - {pv:.1f}/({rho:.1f}×{g:.2f})\n"
            f"NPSH_d = {term_presion:.2f} m + ({term_cota:.2f} m) - {hf_suc:.4f} m - {term_pv:.2f} m = {npsh_d:.2f} m"
        )
        ws.write(r, 0, "Sustitución numérica:", F["etiqueta"])
        esc(ws, r, 1, r, ancho_total, sust_npsh, F["valor"])
        ws.set_row(r, 36)
        r += 1

        nr_txt = f"{float(npsh_r):.2f} m" if npsh_r is not None else "No definido en curva"
        ws.write(r, 0, "NPSH requerido (NPSHr):", F["etiqueta"])
        esc(ws, r, 1, r, ancho_total, nr_txt, F["valor"])
        r += 1

        if npsh_r is not None:
            margen = npsh_d - float(npsh_r)
            ws.write(r, 0, "Margen de seguridad:", F["etiqueta"])
            esc(ws, r, 1, r, ancho_total, f"ΔNPSH = {npsh_d:.2f} - {float(npsh_r):.2f} = {margen:.2f} m", F["valor"])
            r += 1

        ws.write(r, 0, "Diagnóstico final:", F["cab"])
        formato_diag = F["ok"] if cavitacion != "RIESGO DE CAVITACIÓN" else F["error"]
        txt_veredicto = (
            f"{cavitacion}: NPSHd ({npsh_d:.2f} m) "
            + (f"> NPSHr ({float(npsh_r):.2f} m). Operación segura sin riesgo de vaporización." if (npsh_r is not None and cavitacion != "RIESGO DE CAVITACIÓN") else f"≤ NPSHr ({float(npsh_r):.2f} m). Existe riesgo severo de cavitación." if npsh_r is not None else "Cálculo completado.")
        )
        esc(ws, r, 1, r, ancho_total, txt_veredicto, formato_diag)

    def _tabla_iteraciones(self, ws, F, entradas, col, fila, con_subtitulo=True):
        """Historial hasta converger, con la parada y el residuo del motor."""
        ref = xl_rowcol_to_cell
        celdas_f, celdas_inv = {}, {}
        self._escribir_rango(ws, fila, col, fila, col+1,
                            "Iteraciones con el modelo Colebrook-White", F['seccion'])
        ws.write(fila+1, col, "Propuesto 1/raiz(f)", F['cab_neg'])
        ws.write(fila+1, col+1, "Obtenido 1/raiz(f)", F['cab_neg'])
        fila += 2
        for e in entradas:
            re, rr = e['celda_Re'], e['celda_eD']
            resultado = e['resultado_tramo']
            props, obtenidos = self._colebrook_cache(resultado.Re, resultado.rugosidad_relativa)
            if con_subtitulo:
                ws.merge_range(fila, col, fila, col+1, e['nombre'], F['subcab'])
                fila += 1
            for i, (propuesto, obtenido) in enumerate(zip(props, obtenidos)):
                if i == 0:
                    ws.write(fila, col, 1.0, F['valor'])
                else:
                    ws.write_formula(fila, col, f'={ref(fila-1,col+1)}', F['valor'], propuesto)
                ws.write_formula(fila, col+1,
                    f'=IF({re}<{RE_LIMITE_LAMINAR},SQRT({re}/64),-0.86*LN({rr}/3.7+2.51*{ref(fila,col)}/{re}))',
                    F['valor'], obtenido)
                fila += 1
            x = ref(fila-1, col+1)
            propuesto = ref(fila-1, col)
            residuo = f'ABS(({x}+0.86*LN({rr}/3.7+2.51*{x}/{re}))/{x})'
            ws.write(fila, col, "Factor de fricción (f)", F['destacado_etq'])
            fval = resultado.f if resultado.f is not None else 0.0
            ws.write_formula(fila, col+1,
                f'=IF({re}=0,0,IF({re}<{RE_LIMITE_LAMINAR},64/{re},IF(AND(ABS({x}-{propuesto})<1E-12,{residuo}<={TOLERANCIA_RELATIVA}),1/{x}^2,NA())))',
                F['destacado_val'], fval)
            celdas_inv[e['i']] = x
            celdas_f[e['i']] = ref(fila, col+1)
            fila += 1
        return celdas_f, celdas_inv, fila

    def _tabla_iteraciones_diametro(self, ws, F, entradas_d, col, fila, *, libro):
        """Presenta D del solver y verifica hf(D) con K y Le/D, sin falsa inversa."""
        celdas_D, celdas_inv = {}, {}
        self._escribir_rango(ws, fila, col, fila, col+3,
                            "Diámetro del motor y verificación Darcy", F['seccion'])
        for i, texto in enumerate(('D del motor [m]', 'Reynolds (Re)', '1/raiz(f)', 'hf(D) [m]')):
            ws.write(fila+1, col+i, texto, F['cab_neg'])
        fila += 2
        for e in entradas_d:
            t = dict(L=e['L'], D=e['D_final'], rugosidad=e['eps'], rho=e['rho'], mu=e['mu'],
                     Q=e['Q'], hf=e['hf'], K=e.get('K',0.0), LeD=e.get('LeD',0.0))
            refs = self._hidraulica_excel(libro, t)
            ws.merge_range(fila, col, fila, col+3, e['nombre'], F['subcab'])
            fila += 1
            resultado = self._resultado_tramo_excel(t)
            valores = self._valores_tramo_excel(resultado)
            d = resultado.D
            for i, clave in enumerate(('D', 'Re', 'inv_raiz_f', 'hf')):
                valor = valores[clave]
                ws.write_formula(fila, col+i, '=' + refs[clave], F['valor'], valor)
            celdas_inv[e['i']] = xl_rowcol_to_cell(fila, col+2)
            fila += 1
            self._escribir_rango(ws, fila, col, fila, col+2, 'Diámetro de diseño (D) [m]', F['destacado_etq'])
            ws.write_formula(fila, col+3, '='+refs['D'], F['destacado_val'], d)
            celdas_D[e['i']] = xl_rowcol_to_cell(fila, col+3)
            fila += 1
        return celdas_D, celdas_inv, fila


