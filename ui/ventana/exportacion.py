"""Exportación de resultados a Excel."""

from ui.curvas_presentacion import usa_puntos,puntos_total,resumen_puntos
from motor.resultados import PuntoCurva
from motor.perfiles import perfil_como_serie

import math
import re

from PyQt5.QtWidgets import QFileDialog, QMessageBox

try:  # Exportación a Excel (pip install xlsxwriter); la app sigue funcionando sin ella
    import xlsxwriter
    from xlsxwriter.utility import xl_rowcol_to_cell
except ImportError:  # pragma: no cover
    xlsxwriter = None
    xl_rowcol_to_cell = None

from motor import MotorFluidos
from motor.hidraulica import evaluar_tramo


class ExportacionMixin:
    """Exportación de resultados a Excel."""

    def _fila_exportacion(self, tuberia, Q_si, hf, Q_sup=None, hf_sup=None, rol=None):
        L, D, eps = self._datos_si(tuberia)
        rho, mu = self.fluido_rho, self.fluido_mu
        fluido = dict(rho=rho, mu=mu, g=MotorFluidos.g)
        r = evaluar_tramo(Q_si, L, D, eps, tuberia.sumatoria_K, tuberia.sumatoria_Le_D,
                          fluido, id=tuberia.id_tuberia)
        traza = MotorFluidos.iteraciones_colebrook(r.Re, r.rugosidad_relativa)

        fila = {
            "id": tuberia.id_tuberia,
            "nombre": tuberia.nombre,
            "rol": rol,
            "L": r.L, "D": r.D, "rugosidad": r.eps,
            "Z_origen": self._z_tuberia(tuberia),
            "rugosidad_relativa": r.rugosidad_relativa,
            "Area": r.area, "rho": rho, "mu": mu,
            "hf": r.hf_total, "hf_dist": r.hf_distribuida, "hf_loc": r.hf_localizada,
            "hf_resolucion": None if hf is None else float(hf),
            "karman": r.karman, "inv_raiz_f": r.inv_raiz_f,
            "Re": r.Re, "V": r.v, "Q": r.Q, "f": r.f,
            "regimen": r.regimen, "ley": r.ley,
            "K": r.K, "LeD": r.LeD, "g": fluido['g'],
            "resultado_tramo": r,
            "historial_iteraciones": list(traza.historial_iteraciones),
        }
        if Q_sup is not None:
            supuesto = evaluar_tramo(Q_sup, L, D, eps, r.K, r.LeD, fluido, id=r.id)
            fila.update({
                "Q_sup": supuesto.Q, "V_sup": supuesto.v, "Re_sup": supuesto.Re,
                "hf_sup": supuesto.hf_total, "karman_sup": supuesto.karman,
                "inv_raiz_f_sup": supuesto.inv_raiz_f,
                "resultado_tramo_sup": supuesto,
            })
        return fila

    def _registrar_exportacion(self, tipo_sistema, items, suposiciones, condicion_final,
                               error_Q, recomendacion, ordenar=True, ok=None, calculos_globales=None):
        if calculos_globales is None:
            calculos_globales = {}
        if ordenar:
            items = sorted(items, key=lambda it: (it[0].id_tuberia is None, it[0].id_tuberia or 0))
        self.datos_exportacion = {
            "tipo_sistema": tipo_sistema,
            "perfiles": list(getattr(self,"_perfiles_calculados",{}).values()),
            "tuberias": [self._fila_exportacion(t, q, hf, *extra) for t, q, hf, *extra in items],
            "suposiciones": dict(suposiciones),
            "resultados_globales": dict(calculos_globales),
            "resultados": {
                "condicion_final": list(condicion_final),
                "variacion_Q": error_Q,
                "recomendacion": recomendacion,
                "ok": recomendacion.startswith("EQUILIBRIO") if ok is None else bool(ok),
            },
            "iteraciones": [],
        }
        self.datos_exportacion['iteraciones'] = [dict(it)
            for tramo in self.datos_exportacion['tuberias'] for it in tramo['historial_iteraciones']]
        self.boton_excel.show()
        if hasattr(self, "stack_central") and self.stack_central.currentIndex() == 1:
            self._actualizar_vista_tabla_excel()

    def _escribir_libro_excel(self, destino, datos=None):
        if datos is None:
            datos = self.datos_exportacion
        tipo = datos.get("tipo_sistema", "Sistema")
        libro = xlsxwriter.Workbook(destino, {"in_memory": not isinstance(destino, str)})
        if tipo == "Sistema Ramificado (Doble Nudo)":
            self._hoja_memoria_doble_nudo(libro, datos)
        elif tipo == "Bomba en Red Ramificada":
            self._hoja_memoria_bomba_ramificada(libro, datos)
        else:
            self._hoja_memoria_calculo(libro, datos)

        if "bomba" in datos:
            self._hoja_bombas(libro, datos)
            self._hoja_desglose_bomba(libro, datos)
            self._hoja_curvas_individuales(libro, datos)
            self._hoja_curva_equivalente(libro, datos)
        if datos.get("perfiles") or datos.get("bomba",{}).get("puntos_egl"):
            self._hoja_perfil_egl_hgl(libro, datos)

        libro.close()

    def _hoja_bombas(self, libro, datos):
        """
        Genera la hoja 'Bombas' en el libro Excel:
        - Datos generales de la instalación y del fluido.
        - Tabla de la curva de la bomba (H, Q, η, NPSHr) como datos brutos.
        - Tabla de la curva resistente del sistema calculada.
        - Punto de operación y potencias por bomba (valores calculados).
        - Análisis de NPSH disponible/requerido y veredicto de cavitación.
        - Reparto por bomba si es serie o paralelo.
        """
        b_info = datos.get("bomba")
        if not b_info:
            return

        ws = libro.add_worksheet("Bombas")
        ws.hide_gridlines(2)
        F = self._formatos_excel(libro)
        esc = self._escribir_rango

        # Configurar anchos de columna
        ws.set_column(0, 0, 4)
        ws.set_column(1, 1, 32)
        ws.set_column(2, 2, 18)
        ws.set_column(3, 3, 18)
        ws.set_column(4, 4, 18)
        ws.set_column(5, 5, 18)
        ws.set_column(6, 6, 20)

        # 1. Título
        ws.merge_range(1, 1, 1, 6, "Memoria de Cálculo — Módulo de Bombas Centrífugas", F["titulo"])
        ws.set_row(1, 24)

        # 2. Datos Generales de la Instalación
        r = 3
        esc(ws, r, 1, r, 2, "Datos de la Bomba y Fluido", F["seccion"])
        esc(ws, r, 4, r, 6, "Condiciones de Contorno (Tanques)", F["seccion"])
        r += 1

        t1 = b_info.get("tanque1", {})
        t2 = b_info.get("tanque2", {})

        datos_generales_izq = [
            ("Nombre de la bomba", b_info.get("nombre", "Bomba")),
            ("Arreglo hidráulico", str(b_info.get("arreglo", "individual")).capitalize()),
            ("Cota de eje Z_bomba [m]", b_info.get("z_bomba", 0.0)),
            ("Densidad del fluido ρ [kg/m³]", b_info.get("rho", 1000.0)),
            ("Viscosidad dinámica μ [Pa·s]", b_info.get("mu", 0.001002)),
        ]
        datos_generales_der = [
            ("Tanque de inicio (Succión)", t1.get("nombre", "Tanque 1")),
            ("Cota superficie Z1 [m]", t1.get("z", 0.0)),
            ("Presión manométrica P1 [Pa]", t1.get("P", 0.0)),
            ("Tanque de destino (Descarga)", t2.get("nombre", "Tanque 2")),
            ("Cota descarga Z2 [m]", t2.get("z", 0.0)),
        ]

        for idx_g in range(max(len(datos_generales_izq), len(datos_generales_der))):
            if idx_g < len(datos_generales_izq):
                etq_i, val_i = datos_generales_izq[idx_g]
                ws.write(r, 1, etq_i, F["etiqueta"])
                ws.write(r, 2, val_i, F["valor"])
            if idx_g < len(datos_generales_der):
                etq_d, val_d = datos_generales_der[idx_g]
                ws.write(r, 4, etq_d, F["etiqueta"])
                esc(ws, r, 5, r, 6, val_d, F["valor"])
            r += 1

        if usa_puntos(b_info.get('curvas',[]),b_info.get('metodo')):
            puntos = puntos_total(b_info.get('curvas',[]),b_info.get('puntos_equivalente',[]))
            esc(ws,r,1,r,6,resumen_puntos(puntos,len(b_info.get('curvas',[]))>1),F['valor'])
            r += 1
        r += 1
        # 3. Resumen del Punto de Operación y Potencias (Valores calculados)
        esc(ws, r, 1, r, 6, "Punto de Operación y Potencias Calculadas", F["seccion"])
        r += 1

        q_op = b_info.get("Q_op", 0.0)
        h_op = b_info.get("H_op", 0.0)
        eta_op = b_info.get("eta_op")
        p_hid = b_info.get("potencia_hidraulica", 0.0)
        p_freno = b_info.get("potencia_freno")
        npsh_d = b_info.get("npsh_d", 0.0)
        npsh_r = b_info.get("npsh_r", None)
        cavitacion = b_info.get("cavitacion") or "SIN DATO"

        filas_op = [
            ("Caudal de operación Q_op [m³/s]", q_op, "Caudal de operación Q_op [L/s]", q_op * 1000.0),
            ("Altura de operación H_op [m]", h_op, "Eficiencia en punto de op. η [%]", (eta_op * 100.0) if eta_op is not None else "—"),
            ("Potencia hidráulica neta [kW]", p_hid / 1000.0, "Potencia al freno (BHP) [kW]", (p_freno / 1000.0) if p_freno is not None else "—"),
            ("Potencia al freno (BHP) [HP]", (p_freno / 745.7) if p_freno is not None else "—", "NPSH disponible (NPSHd) [m]", npsh_d),
            (
                "NPSH requerido (NPSHr) [m]",
                "—" if npsh_r is None else npsh_r,
                "Margen de seguridad [m]",
                "—" if npsh_r is None or npsh_d is None else (npsh_d - npsh_r),
            ),
            (
                "Veredicto de cavitación",
                cavitacion,
                "Estado de cavitación",
                ('SEGURO' if cavitacion in ('OPERACIÓN SEGURA','SIN RIESGO') else
                 'CAVITACIÓN' if cavitacion=='RIESGO DE CAVITACIÓN' else 'SIN EVALUAR'),
            ),
        ]

        for etq1, val1, etq2, val2 in filas_op:
            ws.write(r, 1, etq1, F["destacado_etq"])
            ws.write(r, 2, val1, F["destacado_val"])
            ws.write(r, 4, etq2, F["destacado_etq"])
            es_seguro = str(val2).startswith("SEGURO")
            es_cav = str(val2) == "CAVITACIÓN"
            fmt_res = F["ok"] if es_seguro else (F["error"] if es_cav else F["destacado_val"])
            esc(ws, r, 5, r, 6, val2, fmt_res)
            r += 1

        r += 1
        # 4. Tabla de la Curva de la Bomba (Datos de entrada del usuario / catálogo)
        esc(ws, r, 1, r, 6, "Curva Característica de la Bomba (Datos de Fábrica)", F["seccion"])
        r += 1

        cabs_bomba = ["Bomba", "Punto", "Q [m³/s]", "Q [L/s]", "H [m]", "η [%]", "NPSHr [m]"]
        for c_idx, cab_tit in enumerate(cabs_bomba):
            ws.write(r, 1 + c_idx, cab_tit, F["subcab"])
        r += 1

        curvas_lista = b_info.get("curvas", [])
        for c_item in curvas_lista:
            if isinstance(c_item, dict):
                nom_c = c_item.get("nombre", "Bomba")
                q_lista = c_item.get("Q", [])
                h_lista = c_item.get("H", [])
                eta_lista = c_item.get("eta") or [None] * len(q_lista)
                npsh_lista = c_item.get("npsh_r") or [None] * len(q_lista)
            else:
                nom_c = getattr(c_item, "nombre", "Bomba")
                q_lista = list(getattr(c_item, "Q", []))
                h_lista = list(getattr(c_item, "H", []))
                eta_lista = list(c_item.eta) if getattr(c_item, "eta", None) else [None] * len(q_lista)
                npsh_lista = list(c_item.npsh_r) if getattr(c_item, "npsh_r", None) else [None] * len(q_lista)

            for p_idx in range(len(q_lista)):
                q_v = float(q_lista[p_idx])
                h_v = float(h_lista[p_idx])
                eta_v = "—" if p_idx >= len(eta_lista) or eta_lista[p_idx] is None else float(eta_lista[p_idx])
                nr_v = "—" if p_idx >= len(npsh_lista) or npsh_lista[p_idx] is None else float(npsh_lista[p_idx])

                ws.write(r, 1, nom_c, F["etiqueta"])
                ws.write(r, 2, p_idx + 1, F["valor"])
                ws.write_number(r, 3, q_v, F["valor"])
                ws.write_number(r, 4, q_v * 1000.0, F["valor"])
                ws.write_number(r, 5, h_v, F["valor"])
                if isinstance(eta_v, float):
                    ws.write_number(r, 6, eta_v, F["valor"])
                else:
                    ws.write(r, 6, eta_v, F["valor"])
                if isinstance(nr_v, float):
                    ws.write_number(r, 7, nr_v, F["valor"])
                else:
                    ws.write(r, 7, nr_v, F["valor"])
                r += 1

        r += 1
        # 5. Curva Resistente del Sistema Calculada
        esc(ws, r, 1, r, 4, "Curva Resistente del Sistema Calculada H_sistema(Q)", F["seccion"])
        r += 1
        cabs_sis = ["Punto", "Q [m³/s]", "Q [L/s]", "H_sistema [m]"]
        for c_idx, cab_tit in enumerate(cabs_sis):
            ws.write(r, 1 + c_idx, cab_tit, F["subcab"])
        r += 1

        pts_sistema = b_info.get("puntos_sistema", [])
        for p_idx, punto in enumerate(pts_sistema):
            if isinstance(punto,PuntoCurva):
                q_s,h_s,estado_punto = punto.Q,punto.H,punto.estado
            elif isinstance(punto, dict):
                q_s, h_s = punto['Q'], punto['H']
                estado_punto = punto['estado']
            else:
                q_s, h_s = punto
                estado_punto = 'OK' if h_s is not None else 'NO_CALCULADO'
            ws.write(r, 1, p_idx + 1, F["valor"])
            ws.write_number(r, 2, float(q_s), F["valor"])
            ws.write_number(r, 3, float(q_s) * 1000.0, F["valor"])
            if h_s is None:
                ws.write(r, 4, f'No calculado ({estado_punto})', F['valor'])
            else:
                ws.write_number(r, 4, float(h_s), F["valor"])
            r += 1

        # 6. Tabla de Reparto por Bomba (en caso de arreglo Serie o Paralelo)
        reparto_lista = b_info.get("reparto", [])
        if len(reparto_lista) > 1:
            r += 1
            esc(ws, r, 1, r, 7, f"Reparto de Carga en Arreglo {str(b_info.get('arreglo')).upper()}", F["seccion"])
            r += 1
            cabs_rep = ["Bomba", "Q_i [m³/s]", "Q_i [L/s]", "H_i [m]", "η_i [%]", "P. Hidráulica [kW]", "P. Freno [kW]"]
            for c_idx, cab_tit in enumerate(cabs_rep):
                ws.write(r, 1 + c_idx, cab_tit, F["subcab"])
            r += 1
            for rep in reparto_lista:
                ws.write(r, 1, rep.get("bomba", "Bomba"), F["etiqueta"])
                ws.write_number(r, 2, float(rep.get("Q", 0.0)), F["valor"])
                ws.write_number(r, 3, float(rep.get("Q", 0.0)) * 1000.0, F["valor"])
                ws.write_number(r, 4, float(rep.get("H", 0.0)), F["valor"])
                r_eta = rep.get("eta")
                if r_eta is not None:
                    ws.write_number(r, 5, float(r_eta) * 100.0, F["valor"])
                else:
                    ws.write(r, 5, "—", F["valor"])
                ws.write_number(r, 6, float(rep.get("potencia_hidraulica", 0.0)) / 1000.0, F["valor"])
                r_pf = rep.get("potencia_freno")
                if r_pf is not None:
                    ws.write_number(r, 7, float(r_pf) / 1000.0, F["valor"])
                else:
                    ws.write(r, 7, "—", F["valor"])
                r += 1

    def _hoja_desglose_bomba(self, libro, datos):
        b_info = datos.get("bomba")
        if not b_info:
            return
        ws = libro.add_worksheet("Desglose Bomba")
        ws.hide_gridlines(2)
        F = self._formatos_excel(libro)
        esc = self._escribir_rango

        ws.set_column(0, 0, 4)
        ws.set_column(1, 1, 24)
        ws.set_column(2, 7, 16)
        ws.set_column(8, 8, 20)

        ws.merge_range(1, 1, 1, 8, f"Desglose por Bomba — Arreglo {str(b_info.get('arreglo')).upper()}", F["titulo"])
        ws.set_row(1, 24)

        r = 3
        esc(ws, r, 1, r, 8, f"Equipos de Bombeo y Reparto de Caudal (Arreglo: {str(b_info.get('arreglo')).capitalize()})", F["seccion"])
        r += 1

        cabs = ["Equipo", "Q_i [m³/s]", "Q_i [L/s]", "H_i [m]", "η_i [%]", "P. Hidráulica [kW]", "BHP [kW]", "Estado", "Etapa", "NPSHd [m]", "NPSHr [m]", "Cavitación"]
        for c_idx, c_tit in enumerate(cabs):
            ws.write(r, 1 + c_idx, c_tit, F["subcab"])
        r += 1

        reparto_lista = b_info.get("reparto", [])
        for rep in reparto_lista:
            ws.write(r, 1, rep.get("bomba", "Bomba"), F["etiqueta"])
            ws.write_number(r, 2, float(rep.get("Q", 0.0)), F["valor"])
            ws.write_number(r, 3, float(rep.get("Q", 0.0)) * 1000.0, F["valor"])
            ws.write_number(r, 4, float(rep.get("H", 0.0)), F["valor"])
            r_eta = rep.get("eta")
            if r_eta is not None:
                ws.write_number(r, 5, float(r_eta) * 100.0, F["valor"])
            else:
                ws.write(r, 5, "—", F["valor"])
            ws.write_number(r, 6, float(rep.get("potencia_hidraulica", 0.0)) / 1000.0, F["valor"])
            r_pf = rep.get("potencia_freno")
            if r_pf is not None and math.isfinite(r_pf):
                ws.write_number(r, 7, float(r_pf) / 1000.0, F["valor"])
            else:
                ws.write(r, 7, "—", F["valor"])
            act = rep.get("activa", True)
            ws.write(r, 8, "Activa" if act else "Cerrada por check", F["ok"] if act else F["error"])
            ws.write(r,9,rep.get('etapa',1),F['valor'])
            for col,clave in ((10,'npsh_d'),(11,'npsh_r'),(12,'cavitacion')):
                ws.write(r,col,rep.get(clave) if rep.get(clave) is not None else '—',F['valor'])
            r += 1
            if not act:
                from ui.reportes import _formatear_distinguir_hc_hop
                hc = rep.get("H_cierre")
                hop = rep.get("H_op", b_info.get("H_op"))
                hc_txt, hop_txt = _formatear_distinguir_hc_hop(hc, hop)
                msg_chk = f"H de cierre = {hc_txt} ≤ H de operación = {hop_txt} m. No aporta caudal."
                esc(ws, r, 1, r, 8, msg_chk, F["texto"])
                r += 1

    def _hoja_curvas_individuales(self, libro, datos):
        b_info = datos.get("bomba")
        if not b_info:
            return
        ws = libro.add_worksheet("Curvas Individuales")
        ws.hide_gridlines(2)
        F = self._formatos_excel(libro)
        esc = self._escribir_rango

        ws.set_column(0, 0, 4)
        ws.set_column(1, 1, 24)
        ws.set_column(2, 6, 16)

        ws.merge_range(1, 1, 1, 6, "Curvas Características de Cada Bomba (Q, H, η, NPSHr)", F["titulo"])
        ws.set_row(1, 24)

        r = 3
        curvas = b_info.get("curvas", [])
        for indice,c in enumerate(curvas):
            nom_c = c.get("nombre", "Bomba")
            q_lista = c.get("Q", [])
            h_lista = c.get("H", [])
            eta_lista = c.get("eta") or []
            npsh_lista = c.get("npsh_r") or []

            esc(ws, r, 1, r, 6, f"Curva de Bomba: {nom_c}", F["seccion"])
            r += 1
            cabs = ["Punto", "Q [m³/s]", "Q [L/s]", "H [m]", "η [%]", "NPSHr [m]"]
            for c_idx, cab_tit in enumerate(cabs):
                ws.write(r, 1 + c_idx, cab_tit, F["subcab"])
            r += 1

            muestras = b_info.get('muestras_bombas',[])
            muestra = muestras[indice] if indice<len(muestras) else None
            for p_idx in range(len(muestra) if muestra is not None else len(q_lista)):
                if muestra is not None:
                    pt = muestra[p_idx]
                    ws.write(r,1,p_idx+1,F['valor'])
                    ws.write_number(r,2,pt.Q,F['valor'])
                    ws.write_number(r,3,pt.Q*1000,F['valor'])
                    ws.write(r,4,pt.H if pt.valido else f'No calculado ({pt.estado})',F['valor'])
                    ws.write(r,5,pt.eficiencia*100 if pt.eficiencia is not None else '—',F['valor'])
                    ws.write(r,6,pt.NPSHr if pt.NPSHr is not None else '—',F['valor'])
                    r += 1
                    continue
                q_v = float(q_lista[p_idx])
                h_v = float(h_lista[p_idx])
                eta_v = "—" if (p_idx >= len(eta_lista) or eta_lista[p_idx] is None) else float(eta_lista[p_idx]) * 100.0
                nr_v = "—" if (p_idx >= len(npsh_lista) or npsh_lista[p_idx] is None) else float(npsh_lista[p_idx])

                ws.write(r, 1, p_idx + 1, F["valor"])
                ws.write_number(r, 2, q_v, F["valor"])
                ws.write_number(r, 3, q_v * 1000.0, F["valor"])
                ws.write_number(r, 4, h_v, F["valor"])
                if isinstance(eta_v, float):
                    ws.write_number(r, 5, eta_v, F["valor"])
                else:
                    ws.write(r, 5, eta_v, F["valor"])
                if isinstance(nr_v, float):
                    ws.write_number(r, 6, nr_v, F["valor"])
                else:
                    ws.write(r, 6, nr_v, F["valor"])
                r += 1
            r += 1

    def _hoja_curva_equivalente(self, libro, datos):
        b_info = datos.get("bomba")
        if not b_info:
            return
        ws = libro.add_worksheet("Curva Equivalente")
        ws.hide_gridlines(2)
        F = self._formatos_excel(libro)
        esc = self._escribir_rango

        ws.set_column(0, 0, 4)
        ws.set_column(1, 4, 18)

        ws.merge_range(1, 1, 1, 4, f"Curva Equivalente de la Estación (Arreglo: {str(b_info.get('arreglo')).upper()})", F["titulo"])
        ws.set_row(1, 24)

        r = 3
        esc(ws, r, 1, r, 4, "Curva Equivalente H_estacion(Q)", F["seccion"])
        r += 1
        cabs = ["Punto", "Q [m³/s]", "Q [L/s]", "H_equivalente [m]"]
        for c_idx, cab_tit in enumerate(cabs):
            ws.write(r, 1 + c_idx, cab_tit, F["subcab"])
        r += 1

        puntos_eq = b_info.get("puntos_equivalente", [])
        for p_idx, punto in enumerate(puntos_eq):
            q_eq,h_eq = (punto.Q,punto.H) if isinstance(punto,PuntoCurva) else punto

            ws.write(r, 1, p_idx + 1, F["valor"])
            ws.write_number(r, 2, float(q_eq), F["valor"])
            ws.write_number(r, 3, float(q_eq) * 1000.0, F["valor"])
            ws.write(r,4,h_eq if h_eq is not None else f'No calculado ({getattr(punto,"estado","NO_CALCULADO")})',F['valor'])
            r += 1

    def _hoja_perfil_egl_hgl(self, libro, datos):
        b_info = datos.get("bomba",{})
        ws = libro.add_worksheet("Perfil EGL-HGL")
        ws.hide_gridlines(2)
        F = self._formatos_excel(libro)
        esc = self._escribir_rango

        ws.set_column(0, 0, 4)
        ws.set_column(1, 1, 24)
        ws.set_column(2, 6, 18)

        ws.merge_range(1, 1, 1, 6, "Perfil de Energía EGL y Piezométrico HGL por Estación", F["titulo"])
        ws.set_row(1, 24)

        r = 3
        esc(ws, r, 1, r, 6, "Puntos del Perfil Hidráulico Longitudinal", F["seccion"])
        r += 1
        cabs = ["Estación / Nodo", "x [m]", "EGL [m]", "HGL [m]", "Causa / Singularidad", "Salto / Pérdida [m]"]
        for c_idx, cab_tit in enumerate(cabs):
            ws.write(r, 1 + c_idx, cab_tit, F["subcab"])
        r += 1

        perfiles = datos.get('perfiles') or b_info.get('perfiles') or []
        rutas = [(p.id,p.estado,perfil_como_serie(p)['puntos']) for p in perfiles]
        if not rutas:
            rutas = [('Ruta','',b_info.get('puntos_egl',[]))]
        for nombre,estado,puntos_egl in rutas:
            esc(ws,r,1,r,6,f'{nombre} · {estado}',F['seccion'])
            r += 1
            for pt in puntos_egl:
                etq = pt.get("etiqueta") or pt.get("sub_etiqueta") or "Tramo"
                x_v = float(pt.get("x", 0.0))
                egl_v = float(pt.get("egl", 0.0))
                hgl_v = float(pt.get("hgl", 0.0))
                causa_v = pt.get("rotulo_causa") or pt.get("causa") or "—"
                salto_v = pt.get("salto_bomba") or pt.get("hf_tramo")

                ws.write(r, 1, str(etq), F["etiqueta"])
                ws.write_number(r, 2, x_v, F["valor"])
                ws.write_number(r, 3, egl_v, F["valor"])
                ws.write_number(r, 4, hgl_v, F["valor"])
                ws.write(r, 5, str(causa_v), F["texto"])
                if salto_v is not None and isinstance(salto_v, (int, float)):
                    ws.write_number(r, 6, float(salto_v), F["valor"])
                else:
                    ws.write(r, 6, "—", F["valor"])
                r += 1


    def _exportar_excel(self):
        datos = self.datos_exportacion
        if not datos or not datos.get("tuberias"):
            QMessageBox.warning(self, "Nada que exportar", "Primero realiza un cálculo.")
            return
        if xlsxwriter is None:
            QMessageBox.critical(self, "Falta la librería xlsxwriter", "Instala xlsxwriter.")
            return

        tipo = self.datos_exportacion.get('tipo_sistema', 'Sistema')
        nombres_tub = "-".join([str(t.get('nombre', 'Tub')) for t in self.datos_exportacion.get('tuberias', [])])
        nombre_defecto = f"Calculo {tipo} ({nombres_tub}).xlsx"
        nombre_defecto = re.sub(r'[<>:"/\\|?*]', "", nombre_defecto)

        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar memoria de cálculo", nombre_defecto, "Libro de Excel (*.xlsx)")
        if not ruta:
            return
        if not ruta.lower().endswith(".xlsx"):
            ruta += ".xlsx"

        try:
            self._escribir_libro_excel(ruta, datos)
        except Exception as error:
            QMessageBox.critical(self, "No se pudo exportar", f"Error:\n{error}")
            return
        QMessageBox.information(self, "Exportación exitosa", f"Guardado en:\n{ruta}")

    @staticmethod
    def _formatos_excel(libro):
        base = {"font_name": "Calibri", "font_size": 11, "valign": "vcenter"}
        def fmt(**extra): return libro.add_format({**base, **extra})
        return {
            "titulo": fmt(bold=True, font_size=14, align="left"),
            "seccion": fmt(bold=True, align="center", bg_color="#F4B183", border=1),
            "cab": fmt(align="center", border=1),
            "cab_neg": fmt(bold=True, align="center", border=1),
            "subcab": fmt(bold=True, align="center", border=1, bg_color="#FBE5D6"),
            "etiqueta": fmt(align="left", border=1),
            "valor": fmt(align="center", border=1),
            "texto": fmt(align="center", border=1, text_wrap=True),
            "ok": fmt(bold=True, align="center", border=1, text_wrap=True, font_color="#1e7b34"),
            "error": fmt(bold=True, align="center", border=1, text_wrap=True, font_color="#c0392b"),
            "destacado_etq": fmt(bold=True, align="left", border=1, bg_color="#FFE699"),
            "destacado_val": fmt(bold=True, align="center", border=1, bg_color="#FFE699"),
        }

    @staticmethod
    def _escribir_rango(ws, f1, c1, f2, c2, valor, formato):
        if f1 == f2 and c1 == c2:
            ws.write(f1, c1, valor, formato)
        else:
            ws.merge_range(f1, c1, f2, c2, valor, formato)
