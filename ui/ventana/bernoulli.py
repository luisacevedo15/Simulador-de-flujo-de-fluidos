"""Resolución de la ecuación de Bernoulli entre dos puntos."""

import re

from PyQt5.QtWidgets import QMessageBox

from motor import MotorFluidos
from motor.hidraulica import evaluar_tramo, clasificar_regimen
from ui.reportes import RPT_AZUL, RPT_NARANJA, RPT_ROJO, RPT_VERDE, formatear_reynolds_html, rpt_estado, rpt_grid_2x2, rpt_seccion_cad, rpt_tabla
from ui.ventana.dashboard import desglosar_hf_rutas, desglosar_perdidas_tuberia
from ui.ventana.invalidacion import aplicar_sentido_flujo_ruta, limpiar_sentido_flujo_escena


class BernoulliMixin:
    """Resolución de la ecuación de Bernoulli entre dos puntos."""

    def _on_resolver_bernoulli(self):
        scene = self.canvas_view.scene()
        limpiar_sentido_flujo_escena(scene)
        self.contenedor_barras.hide()
        self.boton_excel.hide()
        self.datos_exportacion = {}
        self._perfiles_calculados = {}
        MotorFluidos.limpiar_iteraciones()

        if self.sender() is self.boton_ramificado:
            idx_union = self.combo_uniones.currentIndex()
            if not (0 <= idx_union < len(self._uniones_dashboard)):
                self.texto_resultados.setPlainText("No hay sistemas ramificados válidos detectados.")
                return

            from ui.ventana.ramificadas import RedMultiNudo

            red = self._uniones_dashboard[idx_union]
            if isinstance(red, RedMultiNudo):
                nodos = red.nodos
            elif isinstance(red, tuple):
                nodos = red
            else:
                nodos = (red,)

            if any(nodo.scene() is not scene for nodo in nodos):
                self._refrescar_combos_dashboard()
                self.texto_resultados.setPlainText("La red elegida ya no existe. Selecciona de nuevo.")
                return

            if isinstance(red, RedMultiNudo):
                self._resolver_red_multinudo(red)
            elif isinstance(red, tuple):
                self._resolver_doble_nudo(*red)
            else:
                self._resolver_union_ramificada(red)
            return

        i1 = self.combo_punto1.currentIndex()
        i2 = self.combo_punto2.currentIndex()
        tanques = self._tanques_dashboard
        if not (0 <= i1 < len(tanques) and 0 <= i2 < len(tanques)):
            self.texto_resultados.setPlainText("Añade al menos dos tanques al lienzo.")
            return

        tanque1 = tanques[i1]
        tanque2 = tanques[i2]

        if tanque1.scene() is not scene or tanque2.scene() is not scene:
            self._refrescar_combos_dashboard()
            self.texto_resultados.setPlainText("Alguno de los puntos elegidos ya no existe.")
            return

        rutas = self._encontrar_ruta(tanque1, tanque2)
        if not rutas:
            self.texto_resultados.setPlainText("No hay una ruta de tuberías entre estos puntos")
            return

        if hasattr(self, "_buscar_bomba_en_ruta"):
            try:
                bomba_en_ruta, _ = self._buscar_bomba_en_ruta(tanque1, tanque2)
            except ValueError as error:
                self.texto_resultados.setPlainText(str(error))
                return
            if bomba_en_ruta is not None:
                self._on_calcular_punto_operacion()
                return

        ramas_paralelas = []
        tub_serie = None
        descomp_ps = None
        if len(rutas) == 1 and len(rutas[0]) == 1:
            tipo_red = "simple"
        elif len(rutas) == 1:
            tipo_red = "serie"
        elif all(len(ruta) == 1 for ruta in rutas):
            tipo_red = "paralelo"
        else:
            descomp_ps = self._descomponer_paralelo_serie(rutas, tanque1, tanque2)
            if descomp_ps is not None:
                tipo_red = "paralelo_serie"
                ramas_paralelas = descomp_ps["ramas_paralelas"]
                tub_serie = descomp_ps["tub_serie_clasica"]
            else:
                self.texto_resultados.setPlainText(
                    "La red combina tramos en serie y en paralelo no descomponibles (ej. puente cruzado), lo que aún no se puede resolver."
                )
                return

        Z1_total = tanque1.elevacion_z
        Z2_total = tanque2.elevacion_z
        P1 = tanque1.presion_P
        P2 = tanque2.presion_P
        g = 9.81

        hf_protagonista = ""
        detalle_red = ""
        es_diseno = False
        q_es_dato = False
        tipo_caso_simple = ""

        if tipo_red != "simple":
            try:
                if tipo_red == "serie":
                    resultado = self._resolver_serie(rutas[0], tanque1, tanque2)
                elif tipo_red == "paralelo":
                    resultado = self._resolver_paralelo(
                        [ruta[0] for ruta in rutas], tanque1, tanque2
                    )
                else:
                    resultado = self._resolver_paralelo_serie(
                        ramas_paralelas, tub_serie, tanque1, tanque2, descomposicion=descomp_ps
                    )
            except (ValueError, ZeroDivisionError) as error:
                self.texto_resultados.setPlainText(f"Error de cálculo.\n\nDetalle: {error}")
                return
            if resultado is None:
                return
            hf_protagonista, detalle_red, hf, hf_dist, hf_loc = resultado
            h_W = MotorFluidos.carga_requerida_sistema(
                Q=0.0, z1=Z1_total, z2=Z2_total, P1=P1, P2=P2, rho=self.fluido_rho, hf=hf, g=g
            )
        else:
            tuberia = rutas[0][0]
            q_es_dato = tuberia.caudal_Q > 0 and not getattr(tuberia, "_q_por_energia", False)
            d_es_dato = tuberia.diametro > 0 and not getattr(tuberia, "_d_por_energia", False)
            Q = tuberia.caudal_Q if q_es_dato else 0.0
            D = tuberia.diametro if d_es_dato else 0.0

            if Q == 0.0 and D == 0.0:
                QMessageBox.warning(self, "Datos insuficientes", "Ingresa al menos Q o D.")
                return
            if Q < 0 or D < 0:
                QMessageBox.warning(self, "Datos inválidos", "Q y D no pueden ser negativos.")
                return

            Q_si = self._a_si(Q, tuberia.u_Q)
            D_si = self._a_si(D, tuberia.u_D)
            L_si = self._a_si(tuberia.longitud, tuberia.u_L)
            epsilon_si = self._a_si(tuberia.rugosidad, tuberia.u_eps)
            rho = self.fluido_rho
            mu = self.fluido_mu

            hf_disponible = (Z1_total - Z2_total) + ((P1 - P2) / (rho * g))

            try:
                if Q == 0.0 or D == 0.0:
                    es_diseno = True
                    if hf_disponible <= 0:
                        QMessageBox.warning(self, "Flujo imposible", "No fluye por gravedad.")
                        return

                    if Q == 0.0:
                        Q_si = MotorFluidos.calcular_Q(
                            hf_disponible, L_si, D_si, rho, mu, epsilon_si,
                            tuberia.sumatoria_K, tuberia.sumatoria_Le_D,
                        )
                        tuberia.caudal_Q = self._desde_si(Q_si, tuberia.u_Q)
                        tuberia.actualizar_etiqueta()
                        if self.tuberia_seleccionada is tuberia and "Q" in self.campos_tuberia:
                            self.campos_tuberia["Q"].setText(str(tuberia.caudal_Q))
                        tuberia._q_por_energia = True
                        tipo_caso_simple = "Q"
                    else:
                        D_si = MotorFluidos.calcular_D(
                            hf_disponible, Q_si, L_si, rho, mu, epsilon_si,
                            tuberia.sumatoria_K, tuberia.sumatoria_Le_D,
                        )
                        tuberia.diametro = self._desde_si(D_si, tuberia.u_D)
                        tuberia.actualizar_etiqueta()
                        if self.tuberia_seleccionada is tuberia and "D" in self.campos_tuberia:
                            self.campos_tuberia["D"].setText(str(tuberia.diametro))
                        tuberia._d_por_energia = True
                        tipo_caso_simple = "D"
                else:
                    tipo_caso_simple = "hf"

                tramo = evaluar_tramo(Q_si, L_si, D_si, epsilon_si,
                    tuberia.sumatoria_K, tuberia.sumatoria_Le_D,
                    dict(rho=rho, mu=mu, g=MotorFluidos.g), id=tuberia.id_tuberia)
                hf, hf_dist, hf_loc = tramo.hf_total, tramo.hf_distribuida, tramo.hf_localizada
                tuberia._resultado_tramo_resuelto = tramo
                tuberia.hf_dist_calculado, tuberia.hf_loc_calculado = hf_dist, hf_loc

                if es_diseno:
                    hf = hf_disponible
                    h_W = 0.0
                else:
                    h_W = MotorFluidos.carga_requerida_sistema(
                        Q=Q_si, z1=Z1_total, z2=Z2_total, P1=P1, P2=P2, rho=rho, hf=hf, g=g
                    )
            except (ValueError, ZeroDivisionError) as error:
                self.texto_resultados.setPlainText(f"Error de cálculo.\n\nDetalle: {error}")
                return

            if tipo_caso_simple == "Q":
                self._guardar_resultado_tuberia(tuberia, Q_si, hf, por_energia=True)
            elif tipo_caso_simple == "D":
                tuberia.actualizar_texto_hf(hf)
                self._refrescar_label_hf(tuberia)
                tuberia._d_por_energia = True
            else:
                tuberia.actualizar_texto_hf(hf)
                self._refrescar_label_hf(tuberia)

            aplicar_sentido_flujo_ruta(tanque1, rutas[0], signo=(1 if Q_si > 0 else 0))

            v_simple, re_simple = tramo.v, tramo.Re
            sub_re_simple = clasificar_regimen(re_simple)
            q_ls_simple = Q_si * 1000.0

            if es_diseno and tipo_caso_simple == "D":
                celda_3 = ("DIÁMETRO D", "⌀", f"{D_si:.4f}", "m", f"Redondeo: {D_si:.2f} m", RPT_AZUL)
            else:
                sub_hw = "No requerida" if h_W <= 0.1 else "Bomba requerida"
                celda_3 = (
                    "ALTURA H_W",
                    "⚡",
                    f"{max(0.0, h_W):.4f}",
                    "m",
                    sub_hw,
                    RPT_NARANJA if h_W > 0.1 else RPT_VERDE,
                )

            grid_simple = rpt_grid_2x2([
                ("CAUDAL Q", "💧", f"{Q_si:.4f}", "m³/s", f"{q_ls_simple:.2f} L/s", "#64748b"),
                ("PÉRDIDA HF", "📉", f"{hf:.4f}", "m", f"ΔP = {hf * rho * g / 1000.0:.1f} kPa", RPT_AZUL),
                celda_3,
                ("REYNOLDS RE", "〰", formatear_reynolds_html(re_simple), "", sub_re_simple, RPT_ROJO if re_simple >= 4000 else RPT_AZUL),
            ])

            if es_diseno:
                tono_s, tit_s, txt_s, bdg_s = (
                    "ok",
                    "Equilibrio por gravedad",
                    f"El sistema opera sin requerir bomba externa (h_W = 0). ΔZ disponible = {hf:.4f} m.",
                    "VÁLIDO",
                )
            elif h_W > 0.1:
                if q_es_dato:
                    tit_s = f"Con el Q ingresado se requiere bomba (h_W = {h_W:.2f} m)"
                    linea_extra = ""
                    if hf_disponible > 0:
                        try:
                            q_max_si = MotorFluidos.calcular_Q(
                                hf_disponible,
                                L_si,
                                D_si,
                                rho,
                                mu,
                                epsilon_si,
                                tuberia.sumatoria_K,
                                tuberia.sumatoria_Le_D,
                            )
                            if q_max_si is not None and q_max_si > 0:
                                q_max_ls = q_max_si * 1000.0
                                linea_extra = f"<br>Por gravedad, este sistema admite como máximo ≈ {q_max_ls:.2f} L/s."
                        except Exception:
                            linea_extra = ""
                    txt_s = (
                        f"Se requiere <b>BOMBA</b> de al menos <b>{h_W:.4f} m</b> para vencer las pérdidas."
                        + linea_extra
                    )
                else:
                    tit_s = "No fluye por gravedad"
                    txt_s = f"Se requiere <b>BOMBA</b> de al menos <b>{h_W:.4f} m</b> para vencer las pérdidas."
                tono_s, bdg_s = "error", "INVÁLIDO"
            elif h_W < -0.1:
                tono_s, tit_s, txt_s, bdg_s = (
                    "ok",
                    "Fluye por gravedad",
                    f"El sistema fluye por gravedad con exceso de energía de <b>{abs(h_W):.4f} m</b>.",
                    "VÁLIDO",
                )
            else:
                tono_s, tit_s, txt_s, bdg_s = (
                    "ok",
                    "Equilibrio perfecto",
                    "El sistema se encuentra en equilibrio energético (h_W ≈ 0 m).",
                    "VÁLIDO",
                )

            fila_cad_simple, _ = self._fila_tabla_cad_tuberia(tuberia, Q_si, hf)
            hf_protagonista = (
                grid_simple
                + rpt_estado(tono_s, tit_s, txt_s, badge=bdg_s)
            )
            detalle_red = (
                rpt_seccion_cad("PÉRDIDAS POR RAMAL / TRAMO", "UNIDADES SI")
                + rpt_tabla(
                    [fila_cad_simple],
                    ["RAMAL", "Q (M³/S)", "V (M/S)", "F (C-W)", "HF FRIC. (M)"],
                    ["left", "right", "right", "right", "right"],
                )
            )

        if tipo_red == "simple":
            hf_acc, hf_bordes = desglosar_perdidas_tuberia(tuberia, hf_loc, tramo)
        else:
            hf_acc, hf_bordes = desglosar_hf_rutas(
                [t for ruta in rutas for t in ruta], hf_loc
            )
        self._actualizar_barra_perdidas(hf, hf_dist, hf_acc, hf_bordes)
        if hasattr(self, "lbl_egl_subtitle"):
            self.lbl_egl_subtitle.setText(
                f"Ruta: {tanque1.nombre} → {tanque2.nombre}"
            )
        if hasattr(self, "egl_chart"):
            if tipo_red in ("simple", "serie"):
                series_egl = [
                    self._construir_serie_ruta_egl(
                        rutas[0],
                        tanque1,
                        tanque2,
                        color="#0284c7",
                        h_W=max(0.0, h_W),
                    )
                ]
            else:
                ramas_set = set(ramas_paralelas or ())
                rutas_egl = []
                nombres_vistos = {}
                for ruta in rutas:
                    ramas_en_ruta = [t for t in ruta if t in ramas_set]
                    tub_ref = ramas_en_ruta[0] if ramas_en_ruta else (ruta[-1] if ruta else None)
                    if len(ramas_en_ruta) > 1:
                        nombre_base = " · ".join(t.nombre for t in ramas_en_ruta)
                    elif tub_ref is not None:
                        nombre_base = tub_ref.nombre
                    else:
                        nombre_base = f"{tanque1.nombre} → {tanque2.nombre}"
                    conteo = nombres_vistos.get(nombre_base, 0) + 1
                    nombres_vistos[nombre_base] = conteo
                    nombre_s = nombre_base if conteo == 1 else f"{nombre_base} (#{conteo})"
                    rutas_egl.append(
                        dict(
                            tuberias=ruta,
                            tanque_ini=tanque1,
                            tanque_fin=tanque2,
                            nombre_serie=nombre_s,
                            color=tub_ref.pen().color().name() if tub_ref is not None else "#0284c7",
                            tub_referencia=tub_ref,
                            h_W=max(0.0, h_W),
                            es_paralelo=(tipo_red == "paralelo"),
                            es_mixto=(tipo_red == "paralelo_serie"),
                        )
                    )
                series_egl = self._construir_series_rutas_egl(rutas_egl)
            if h_W > 0.1:
                tit_exc_s = "ALTURA BOMBA (H_W)"
                val_exc_s = float(h_W)
                sub_exc_s = "Bomba requerida para fluir"
                col_exc_s = "#16a34a"
            else:
                tit_exc_s = "ENERGÍA EXCEDENTE"
                val_exc_s = max(0.0, float(-h_W))
                sub_exc_s = "Flujo por gravedad asegurado"
                col_exc_s = "#006398"

            self.egl_chart.actualizar_datos(
                series_egl,
                resumen={
                    "z1": Z1_total,
                    "z2": Z2_total,
                    "hf_total": hf,
                    "deficit": max(0.0, float(h_W)),
                    "excedente": val_exc_s,
                    "sub_z1": f"{tanque1.nombre} (Superficie)",
                    "sub_z2": f"{tanque2.nombre} (Descarga)",
                    "sub_hf": "Fricción + Accesorios + Bordes",
                    "tit_exc": tit_exc_s,
                    "sub_exc": sub_exc_s,
                    "col_exc": col_exc_s,
                },
            )

        if es_diseno:
            tono, titulo_diag, texto_diag = ("ok", "Cálculo de diseño", "Sin bomba ni turbina (h_W = 0)")
        elif h_W > 0.1:
            if tipo_red == "simple" and q_es_dato:
                titulo_diag = f"Con el Q ingresado se requiere bomba (h_W = {h_W:.2f} m)"
                texto_diag = f"Se requiere <b>BOMBA</b> ({h_W:.4f} m)."
                tono = "aviso"
            else:
                tono, titulo_diag, texto_diag = ("aviso", "No fluye por gravedad", f"Se requiere <b>BOMBA</b> ({h_W:.4f} m).")
        elif h_W < -0.1:
            tono, titulo_diag, texto_diag = ("ok", "Fluye por gravedad", f"Exceso de {abs(h_W):.4f} m.")
        else:
            tono, titulo_diag, texto_diag = ("ok", "Equilibrio perfecto", "En límite de flujo.")

        html_content = f"{hf_protagonista}{detalle_red}"
        self.texto_resultados.setHtml(html_content)

        if tipo_red == "simple":
            if es_diseno and tipo_caso_simple == "Q":
                rol_simple = "karman"
                sup_simple = {"hf_disponible": hf}
            elif es_diseno and tipo_caso_simple == "D":
                rol_simple = "diseno_d"
                sup_simple = {"Q_requerido": Q_si, "hf_disponible": hf}
            else:
                rol_simple = "colebrook"
                sup_simple = {}
            self._registrar_exportacion(
                "Sistema Simple",
                [(tuberia, Q_si, hf, None, None, rol_simple)],
                sup_simple,
                ["P1/γ + Z1 + h_W = P2/γ + Z2 + hf"],
                0.0,
                re.sub(r"<[^>]+>", "", f"{titulo_diag}. {texto_diag}"),
                ok=(tono == "ok"),
            )
