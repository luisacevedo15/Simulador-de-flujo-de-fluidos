"""Módulo y mixin de integración de bombas centrífugas en la ventana principal."""

from PyQt5.QtWidgets import QMessageBox

from motor import MotorFluidos
from motor.bombas import EstacionBombeo, evaluar_operacion_estacion, punto_operacion
from motor.curvas import construir_curvas_estacion
from ui.curvas_presentacion import usa_puntos
from ui.nombres_bombas import nombre_equipo_bomba
from ui.graficos import BombaGrafica, TanqueGrafico
from ui.reportes import reporte_bomba, reporte_diagnostico_bomba
from ui.ventana.dashboard import desglosar_perdidas_tuberia
from ui.ventana.invalidacion import (
    aplicar_sentido_flujo_ruta,
    limpiar_datos_bomba,
    limpiar_sentido_flujo_escena,
)


class BombasMixin:
    """Mixin para la resolución del punto de operación, NPSH y reporte de bombas."""

    def _aplicar_resultado_estacion(self, bomba, resultado):
        """Adaptación de nombres/formato; los valores físicos ya vienen resueltos."""
        textos = {'seguro':'OPERACIÓN SEGURA','riesgo':'RIESGO DE CAVITACIÓN',
                  'desconocido':'SIN DATO NPSHr'}
        bomba.Q_op, bomba.H_op = resultado.Q, resultado.H
        bomba.eta_op = resultado.eficiencia
        bomba.potencia_hidraulica_op = resultado.potencia_hidraulica
        bomba.potencia_freno_op = resultado.potencia_eje
        bomba.npsh_d = resultado.NPSHd
        bomba.npsh_r = resultado.NPSHr if resultado.cavitacion!='desconocido' else None
        bomba.cavitacion = textos[resultado.cavitacion]
        bomba.estado_operacion, bomba.mensaje_operacion = resultado.estado, resultado.mensaje
        bomba.desglose = list(resultado.bombas)
        bomba.resultado_estacion = resultado
        curvas = list(getattr(bomba,'curvas',[]))
        bomba.reparto = [dict(bomba=b.id if b.id.startswith('Bomba') else f'Bomba {b.id}',
            Q=b.Q,H=b.H,eta=b.eficiencia,potencia_hidraulica=b.potencia_hidraulica,
            potencia_freno=b.potencia_eje,activa=b.activa,etapa=b.etapa,
            npsh_d=b.NPSHd,npsh_r=b.NPSHr,cavitacion=textos[b.cavitacion],
            H_cierre=getattr(curvas[i],'H_cierre',None) if i<len(curvas) else None,
            H_op=resultado.H) for i,b in enumerate(resultado.bombas)]
        bomba.actualizar_tooltip()
        return bomba.reparto

    def _limpiar_resultados_bomba(self, bomba, estado="SIN_CALCULAR", mensaje=""):
        """Borra los resultados numéricos de una corrida previa para no dejar valores viejos."""
        limpiar_datos_bomba(bomba, estado, mensaje)
        bomba.actualizar_tooltip()
        self._ultimo_datos_grafico_bombas = None
        if hasattr(self, "grafico_bombas") and self.grafico_bombas is not None:
            self.grafico_bombas.limpiar_datos()
        if hasattr(self, "_sincronizar_estado_bomba_curvas"):
            self._sincronizar_estado_bomba_curvas()
        if hasattr(self, "texto_resultados") and self.texto_resultados is not None:
            self.texto_resultados.clear()
        # La invalidación limpia datos, sin destruir el editor cuyo textChanged
        # la ha disparado. Los cambios de selección montan su propio panel.
        if (not getattr(self, '_invalidando_resultados', False)
                and hasattr(self, "_mostrar_campos_bomba")
                and getattr(self, "bomba_seleccionada", None) is bomba):
            self._mostrar_campos_bomba(bomba)

    def _mostrar_diagnostico_bomba(self, bomba, estado, mensaje):
        """Muestra el letrero visible con el mensaje del diagnóstico y limpia resultados numéricos anteriores."""
        self._limpiar_resultados_bomba(bomba, estado=estado, mensaje=mensaje)
        html_diag = reporte_diagnostico_bomba(bomba.nombre, estado, mensaje)
        self.texto_resultados.setHtml(html_diag)

    def _buscar_bomba_en_ruta(self, tanque1, tanque2, *, diagnosticar=True):
        """
        Busca si en la trayectoria entre tanque1 y tanque2 existe una BombaGrafica instalada.
        Devuelve (bomba, ruta) o (None, None). La consulta para el texto del
        botón usa diagnosticar=False: no invalida datos ni reconstruye paneles.
        """
        nodos, tubos, pendientes = set(), set(), [tanque1]
        while pendientes:
            nodo = pendientes.pop()
            if nodo in nodos:
                continue
            nodos.add(nodo)
            for tub in nodo.tuberias:
                tubos.add(tub)
                otro = tub.nodo_destino if tub.nodo_origen is nodo else tub.nodo_origen
                pendientes.append(otro)
        bombas = [n for n in nodos if isinstance(n, BombaGrafica)]
        if not bombas:
            return None, None
        motivo = None
        if len(bombas) != 1:
            motivo = "varias estaciones de bomba en el mismo componente"
        elif tanque2 not in nodos:
            motivo = "el tanque de destino no pertenece al circuito de la bomba"
        elif len(tubos) != len(nodos) - 1:
            motivo = "bypass o ciclos con rutas alternativas alrededor de la bomba"
        elif any(isinstance(n, TanqueGrafico) and n not in (tanque1, tanque2) for n in nodos):
            motivo = "tanques intermedios o adicionales en el circuito de la bomba"
        elif any(len(n.tuberias) != (1 if n in (tanque1, tanque2) else 2) for n in nodos):
            motivo = "ramificaciones o conexiones adicionales; use el resolutor de red ramificada para las redes admitidas"
        if motivo:
            if not diagnosticar:
                return None, None
            mensaje = f"Topología no soportada: {motivo}. Solo se admite una cadena en serie entre los dos tanques."
            for bomba in bombas:
                self._limpiar_resultados_bomba(bomba, estado="TOPOLOGIA_NO_SOPORTADA", mensaje=mensaje)
            raise ValueError(mensaje)
        # Componente completo validado: no puede ocultarse un bypass eligiendo
        # únicamente la primera ruta que contiene una bomba.
        ruta, nodo, anterior = [], tanque1, None
        while nodo is not tanque2:
            tub = next(t for t in nodo.tuberias if t is not anterior)
            ruta.append(tub)
            nodo = tub.nodo_destino if tub.nodo_origen is nodo else tub.nodo_origen
            anterior = tub
        return bombas[0], ruta

    def _separar_tramos_succion_descarga(self, ruta, bomba):
        """
        Dada una ruta ordenada de tuberías desde tanque1 hasta tanque2 y la bomba intermedia,
        separa las tuberías en lista de succión y lista de descarga.
        """
        succion = []
        descarga = []
        en_descarga = False

        for tub in ruta:
            if not en_descarga:
                succion.append(tub)
                if tub.nodo_destino is bomba or tub.nodo_origen is bomba:
                    en_descarga = True
            else:
                descarga.append(tub)

        return succion, descarga

    def _on_calcular_punto_operacion(self):
        """
        Resuelve el punto de operación (H_op, Q_op) para la bomba entre los tanques seleccionados,
        calcula el NPSH disponible, verifica cavitación, genera el reporte HTML y actualiza los gráficos.
        """
        scene = self.canvas_view.scene()
        limpiar_sentido_flujo_escena(scene)
        self.contenedor_barras.hide()
        if hasattr(self, "boton_excel"):
            self.boton_excel.hide()
        self.datos_exportacion = {}
        self._perfiles_calculados = {}
        MotorFluidos.limpiar_iteraciones()

        i1 = self.combo_punto1.currentIndex()
        i2 = self.combo_punto2.currentIndex()
        tanques = getattr(self, "_tanques_dashboard", [])

        if not (0 <= i1 < len(tanques) and 0 <= i2 < len(tanques)):
            self.texto_resultados.setPlainText("Selecciona dos tanques en el lienzo CAD.")
            return

        tanque1 = tanques[i1]
        tanque2 = tanques[i2]

        if tanque1 is tanque2:
            QMessageBox.warning(
                self,
                "Tanques iguales",
                "El tanque de inicio y el de destino deben ser diferentes para resolver el sistema.",
            )
            return

        if tanque1.scene() is not scene or tanque2.scene() is not scene:
            self._refrescar_combos_dashboard()
            self.texto_resultados.setPlainText("Alguno de los tanques seleccionados ya no existe.")
            return

        try:
            bomba, ruta = self._buscar_bomba_en_ruta(tanque1, tanque2)
        except ValueError as error:
            self.texto_resultados.setPlainText(str(error))
            return
        if bomba is None:
            QMessageBox.warning(
                self,
                "Sin Bomba",
                f"No se encontró ninguna bomba en el trazado entre {tanque1.nombre} y {tanque2.nombre}.\n"
                "Inserte una bomba arrastrándola sobre la tubería.",
            )
            return

        # 1. Comprobar equipos y curvas (Estado SIN_CURVA)
        equipos = getattr(bomba, "equipos", [])
        if equipos:
            sin_curva = any(eq.get("curva") is None for eq in equipos)
            if sin_curva or not bomba.curvas:
                msg = "Falta ingresar la curva de la bomba"
                self._mostrar_diagnostico_bomba(bomba, "SIN_CURVA", msg)
                QMessageBox.warning(
                    self,
                    "Sin Curva de Bomba",
                    msg,
                )
                return
            lista_curvas = [eq["curva"] for eq in equipos]
        else:
            if not bomba.curvas:
                msg = "Falta ingresar la curva de la bomba"
                self._mostrar_diagnostico_bomba(bomba, "SIN_CURVA", msg)
                QMessageBox.warning(
                    self,
                    "Sin Curva de Bomba",
                    msg,
                )
                return
            lista_curvas = list(bomba.curvas)

        succion_tramos, descarga_tramos = self._separar_tramos_succion_descarga(ruta, bomba)

        # Validación de orientación de la bomba:
        # Si la tubería de descarga física de la bomba quedó asignada a la succión, está al revés.
        if (
            bomba.tuberia_descarga is not None
            and bomba.tuberia_descarga in succion_tramos
            and len(descarga_tramos) == 0
        ):
            QMessageBox.warning(
                self,
                "Sentido de Bombeo Invertido",
                f"La {bomba.nombre} está orientada hacia {tanque1.nombre}.\n"
                f"Invierta los tanques de inicio y destino en el panel para bombear en el sentido correcto.",
            )
            return

        # Preparar tramos para evaluar pérdidas en la ecuación de energía del sistema
        tramos_data = []
        for tub in (succion_tramos + descarga_tramos):
            try:
                L_si, D_si, eps_si = self._datos_si(tub)
            except ValueError as e:
                QMessageBox.warning(self, "Datos inválidos", str(e))
                return
            tramos_data.append({
                "L": L_si,
                "D": D_si,
                "eps": eps_si,
                "K": tub.sumatoria_K,
                "LeD": tub.sumatoria_Le_D,
            })

        rho = getattr(self, "fluido_rho", 1000.0)
        mu = getattr(self, "fluido_mu", 0.001002)

        def H_sistema(q):
            return MotorFluidos.carga_requerida_sistema(
                q,
                z1=tanque1.elevacion_z,
                z2=tanque2.elevacion_z,
                P1=tanque1.presion_P,
                P2=tanque2.presion_P,
                rho=rho,
                mu=mu,
                tramos=tramos_data,
            )

        # Convertir lista de equipos a EstacionBombeo (paralelo -> 1 etapa; serie -> N etapas)
        metodo_estacion = getattr(bomba, "metodo", "cuadratico")
        if str(bomba.arreglo).lower() == "serie":
            estacion = EstacionBombeo.en_serie(lista_curvas, metodo=metodo_estacion)
        else:
            estacion = EstacionBombeo.en_paralelo(lista_curvas, metodo=metodo_estacion)

        curva_bomba_obj = estacion

        # Resolver punto de operación con punto_operacion()
        p_atm, Pv = self.fluido_P_atm, self.fluido_P_vap
        presion_manometrica = 0.0 if tanque1.abierto_atmosfera else tanque1.presion_P
        P1_abs = p_atm + presion_manometrica
        sol = evaluar_operacion_estacion(estacion,H_sistema,rho=rho,mu=mu,g=MotorFluidos.g,
            tramos=tramos_data,indices_succion=range(len(succion_tramos)),
            P_atm=p_atm,P_vap=Pv,z1=tanque1.elevacion_z,z_bomba=bomba.z_bomba,
            P1=presion_manometrica,id=str(bomba.id_bomba))

        if sol.estado == "SIN_CURVA":
            msg = "Falta ingresar la curva de la bomba"
            self._mostrar_diagnostico_bomba(bomba, sol.estado, msg)
            QMessageBox.warning(self, "Sin Curva de Bomba", msg)
            return
        elif sol.estado == "NO_ALCANZA_ALTURA_ESTATICA":
            self._mostrar_diagnostico_bomba(bomba, sol.estado, sol.mensaje)
            QMessageBox.warning(self, "Altura Estática Excesiva", sol.mensaje)
            return
        elif sol.estado == "FUERA_DE_RANGO_CURVA":
            self._mostrar_diagnostico_bomba(bomba, sol.estado, sol.mensaje)
            QMessageBox.warning(self, "Fuera de Rango", sol.mensaje)
            return
        elif sol.estado != "OK" or not sol.convergio:
            msg = sol.mensaje or "La curva de la bomba y la del sistema no se intersectan en el rango de operación."
            self._mostrar_diagnostico_bomba(bomba, sol.estado or "ERROR", msg)
            QMessageBox.warning(self, "Punto de Operación No Encontrado", msg)
            return

        Q_op = float(sol.Q)
        H_op = sol.H
        eta_op = sol.eficiencia

        hf_succion = sol.hf_succion
        reparto = self._aplicar_resultado_estacion(bomba, sol)
        npsh_d, npsh_r = bomba.npsh_d, bomba.npsh_r
        cavitacion_veredicto = bomba.cavitacion
        advertencia_fluido = ''
        p_hid_total, p_freno_total = sol.potencia_hidraulica, sol.potencia_eje

        # Guardar resultados de caudal y pérdidas en cada tubería del trazado
        hf_tot_dist = 0.0
        hf_tot_acc = 0.0
        hf_tot_bordes = 0.0
        for tub, r in zip(succion_tramos + descarga_tramos, sol.tramos):
            hf_t, dist_t, loc_t = r.hf_total, r.hf_distribuida, r.hf_localizada
            acc_t, brd_t = desglosar_perdidas_tuberia(tub, loc_t, r)
            hf_tot_dist += dist_t
            hf_tot_acc += acc_t
            hf_tot_bordes += brd_t
            self._guardar_resultado_tuberia(tub, Q_op, hf_t, por_energia=True, hf_dist=dist_t, hf_loc=loc_t,
                                            resultado_tramo=r)

        aplicar_sentido_flujo_ruta(tanque1, ruta, signo=(1 if Q_op > 0 else 0))

        hf_tot_loc = hf_tot_acc + hf_tot_bordes
        self._actualizar_barra_perdidas(
            hf_tot_dist + hf_tot_loc, hf_tot_dist, hf_tot_acc, hf_tot_bordes
        )

        if self.bomba_seleccionada is bomba and hasattr(self, "_mostrar_campos_bomba"):
            self._mostrar_campos_bomba(bomba)

        # Aviso de velocidad en succión si supera 3 m/s
        v_succion_max = 0.0
        v_succion_max = max((r.v for r in sol.tramos[:len(succion_tramos)]),default=0.0)
        aviso_succion = ""
        if v_succion_max > 3.0:
            aviso_succion = f"La velocidad en la línea de succión es de {v_succion_max:.2f} m/s (se sugiere < 3.0 m/s para prevenir descebe y cavitación)."

        muestras = construir_curvas_estacion(estacion,H_sistema,Q_op=Q_op)

        # Generar reporte HTML en el panel de resultados
        html_reporte = reporte_bomba(
            nombre_bomba=bomba.nombre,
            arreglo=bomba.arreglo,
            Q_op=Q_op,
            H_op=H_op,
            eta_op=eta_op,
            potencia_hidraulica_total=p_hid_total,
            potencia_freno_total=p_freno_total,
            npsh_d=npsh_d,
            npsh_r=npsh_r,
            cavitacion=cavitacion_veredicto,
            reparto=reparto,
            t1_nombre=tanque1.nombre,
            t2_nombre=tanque2.nombre,
            advertencia_fluido=advertencia_fluido,
            aviso_succion=aviso_succion,
            v_succion=v_succion_max,
            estacion=estacion,
            metodo=metodo_estacion,
            ecuacion=muestras['ecuacion_total'],
            puntos_curva=muestras['muestras_equivalente'],
        )
        self.texto_resultados.setHtml(html_reporte)

        # Actualizar gráfico de curvas de bomba y sistema (según el interruptor "Ver curvas de bombas")
        self._ultimo_datos_grafico_bombas = dict(
            **muestras,
            curvas=lista_curvas,
            nombres_bombas=[nombre_equipo_bomba(equipos[i] if i<len(equipos) else None,
                curva=c,indice=i,nombre_estacion=bomba.nombre if len(lista_curvas)==1 else None)
                for i,c in enumerate(lista_curvas)],
            curva_eq=estacion,
            H_sistema=H_sistema,
            Q_op=Q_op,
            H_op=H_op,
            eta_op=eta_op,
            arreglo=bomba.arreglo,
            reparto=reparto,
            metodo=metodo_estacion,
        )
        if hasattr(self, "grafico_bombas"):
            self.grafico_bombas.actualizar_datos(**self._ultimo_datos_grafico_bombas)

        # Registrar datos para la exportación a Excel y memoria de cálculo
        tramos_todos = succion_tramos + descarga_tramos
        items_export = []
        for tub, r in zip(tramos_todos, sol.tramos):
            items_export.append((tub, Q_op, r.hf_total, None, None, "colebrook"))

        metodo_txt = (
            "Interpolación lineal"
            if str(metodo_estacion).lower() == "lineal"
            else "Ajuste cuadrático"
        )
        sup_bomba = {
            "Bomba": bomba.nombre,
            "Arreglo": str(bomba.arreglo).capitalize(),
            "Método de curva": metodo_txt,
            "z_bomba": float(bomba.z_bomba),
        }

        puntos_sis = muestras['muestras_sistema']

        cond_final = [
            "H_bomba(Q_op) = H_sistema(Q_op)",
        ]

        cav_str = cavitacion_veredicto if cavitacion_veredicto is not None else "NPSHr no especificado"
        rec_bomba = (
            f"Punto de operación: Q = {Q_op:.4f} m³/s, H = {H_op:.2f} m, "
            f"NPSHd = {npsh_d:.2f} m ({cav_str})"
        )
        ok_bomba = (cavitacion_veredicto != "RIESGO DE CAVITACIÓN")

        if hasattr(self, "_registrar_exportacion"):
            self._registrar_exportacion(
                f"Sistema con Bomba ({bomba.nombre})",
                items_export,
                sup_bomba,
                cond_final,
                0.0,
                rec_bomba,
                ok=ok_bomba,
            )

        eq_est = muestras['ecuacion_total']
        self.datos_exportacion["bomba"] = {
            "nombre": bomba.nombre,
            "arreglo": bomba.arreglo,
            "metodo": metodo_estacion,
            "z_bomba": bomba.z_bomba,
            "ecuacion_total": None if usa_puntos(lista_curvas,metodo_estacion) else {
                "a": eq_est.a,
                "b": eq_est.b,
                "c": eq_est.c,
                "tipo": eq_est.tipo,
                "R2": eq_est.R2,
                "texto": eq_est.texto,
            },
            "curvas": [
                {
                    "nombre": self._ultimo_datos_grafico_bombas["nombres_bombas"][i],
                    "metodo": c.metodo,
                    "tiene_joroba": bool(getattr(c,"tiene_joroba",False)),
                    "Q": list(c.Q),
                    "H": list(c.H),
                    "eta": list(c.eta) if c.eta else None,
                    "npsh_r": list(c.npsh_r) if c.npsh_r else None,
                    "ecuacion": None if usa_puntos(lista_curvas,metodo_estacion) else {
                        "a": float(getattr(c, "coef_a", getattr(c, "poly_c", 0.0))),
                        "b": float(getattr(c, "coef_b", getattr(c, "poly_b", 0.0))),
                        "c": float(getattr(c, "coef_c", getattr(c, "poly_a", 0.0))),
                        "texto": eq.texto,
                    },
                }
                for i,(c,eq) in enumerate(zip(lista_curvas,muestras['ecuaciones_bombas']))
            ],
            "Q_op": Q_op,
            "H_op": H_op,
            "eta_op": eta_op,
            "potencia_hidraulica": p_hid_total,
            "potencia_freno": p_freno_total,
            "npsh_d": npsh_d,
            "npsh_r": npsh_r,
            "cavitacion": cavitacion_veredicto,
            "reparto": reparto,
            "puntos_sistema": puntos_sis,
            "muestras_bombas": muestras["muestras_bombas"],
            "tanque1": {"nombre": tanque1.nombre, "z": tanque1.elevacion_z, "P": tanque1.presion_P},
            "tanque2": {"nombre": tanque2.nombre, "z": tanque2.elevacion_z, "P": tanque2.presion_P},
            "P1_abs": P1_abs,
            "P_atm": p_atm,
            "P_vap": Pv,
            "Pv": Pv,
            "rho": rho,
            "mu": mu,
            "g": MotorFluidos.g,
            "hf_succion": hf_succion,
            "hf_total": hf_tot_dist + hf_tot_loc,
        }

        if hasattr(self, "boton_excel"):
            self.boton_excel.show()

        # Actualizar gráfico de perfil EGL/HGL
        if hasattr(self, "lbl_egl_subtitle"):
            self.lbl_egl_subtitle.setText(
                f"Ruta: {tanque1.nombre} → {tanque2.nombre} · {bomba.nombre}"
            )
        series_egl = []
        if hasattr(self, "egl_chart") and hasattr(self, "_construir_serie_ruta_egl"):
            series_egl = [
                self._construir_serie_ruta_egl(
                    ruta,
                    tanque1,
                    tanque2,
                    color="#0284c7",
                    h_W=H_op,
                )
            ]
            self.egl_chart.actualizar_datos(
                series_egl,
                resumen={
                    "z1": tanque1.elevacion_z,
                    "z2": tanque2.elevacion_z,
                    "hf_total": hf_tot_dist + hf_tot_loc,
                    "deficit": 0.0,
                    "excedente": H_op,
                    "H_op": H_op,
                    "energia_faltante": 0.0,
                    "sub_z1": f"{tanque1.nombre} (Succión)",
                    "sub_z2": f"{tanque2.nombre} (Descarga)",
                    "sub_hf": "Pérdidas totales del sistema",
                    "tit_exc": "ALTURA BOMBA (H_OP)",
                    "sub_exc": f"Punto de operación: {H_op:.2f} m",
                    "col_exc": "#16a34a",
                },
            )

        self.datos_exportacion["bomba"]["puntos_equivalente"] = muestras['muestras_equivalente']
        self.datos_exportacion['perfiles'] = [s['perfil'] for s in series_egl]
        self.datos_exportacion["bomba"]["puntos_egl"] = series_egl[0]["puntos"] if series_egl else []

        # Sincronizar pestañas de la vista CURVAS
        if hasattr(self, "_actualizar_pestana_bombas"):
            self._actualizar_pestana_bombas()
        if hasattr(self, "tab_curvas"):
            self.tab_curvas.setTabEnabled(1, True)
            self.tab_curvas.setCurrentIndex(1)
        elif hasattr(self, "stack_contenido_curvas"):
            self.stack_contenido_curvas.setCurrentIndex(1)
        if hasattr(self, "_sincronizar_estado_bomba_curvas"):
            self._sincronizar_estado_bomba_curvas()

