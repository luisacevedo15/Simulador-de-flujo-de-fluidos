"""Cambio entre vistas CAD / TABLA / CURVAS y la vista de tabla Excel."""

import io
import math

from PyQt5 import QtGui
from PyQt5.QtCore import QPoint, QRect, QSize, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QTableWidgetItem

try:  # Vista previa de tabla Excel (pip install openpyxl)
    import openpyxl
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    openpyxl = None
    get_column_letter = None
try:  # Exportación a Excel (pip install xlsxwriter); la app sigue funcionando sin ella
    import xlsxwriter
    from xlsxwriter.utility import xl_rowcol_to_cell
except ImportError:  # pragma: no cover
    xlsxwriter = None
    xl_rowcol_to_cell = None

from ui.constantes import TEMA_STITCH
from ui.iconos import crear_icono_herramienta
from ui.transiciones import revelar_contenido


class VistasMixin:
    """Cambio entre vistas CAD / TABLA / CURVAS y la vista de tabla Excel."""

    def _cambiar_modo_vista_curvas(self, indice):
        """Alterna entre Líneas de Energía (EGL / HGL) [0] y Curvas de Bomba (H - Q) [1]."""
        if hasattr(self, "stack_modo_curvas"):
            self.stack_modo_curvas.setCurrentIndex(indice)
        if hasattr(self, "btn_curvas_egl"):
            self.btn_curvas_egl.setChecked(indice == 0)
            self.btn_curvas_egl.setIcon(
                crear_icono_herramienta("curvas", "#006398" if indice == 0 else "#72787f")
            )
        if hasattr(self, "btn_curvas_bomba"):
            self.btn_curvas_bomba.setChecked(indice == 1)
            self.btn_curvas_bomba.setIcon(
                crear_icono_herramienta("bomba", "#006398" if indice == 1 else "#72787f")
            )
        es_egl = (indice == 0)
        tiene_egl = bool(getattr(self, "egl_chart", None) and self.egl_chart.series)
        self._actualizar_controles_egl_visibles(es_egl and tiene_egl)
        self._sincronizar_estado_bomba_curvas()

    def _actualizar_controles_egl_visibles(self, visible):
        for attr in (
            "sep_curvas_controles",
            "chk_linea_piezometrica",
            "chk_linea_energia",
            "seg_escala_frame",
        ):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setVisible(bool(visible))

    def _actualizar_leyenda_curvas(self):
        layout_ley = getattr(self, "layout_leyenda_curvas", None)
        chart = getattr(self, "egl_chart", None)
        if layout_ley is None or chart is None:
            return

        while layout_ley.count():
            item = layout_ley.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        items = chart.elementos_leyenda()

        for _, simbolo, texto, col_txt, col_bg, col_borde, tip in items:
            texto_chip = (
                f"<span style='font-weight:800;'>{simbolo}</span> {texto}"
                if simbolo
                else texto
            )
            chip = QLabel(texto_chip)
            chip.setTextFormat(Qt.RichText)
            chip.setToolTip(tip)
            chip.setStyleSheet(
                f"QLabel {{ font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
                f"font-weight: 600; color: {col_txt}; background-color: {col_bg}; "
                f"border: 1px solid {col_borde}; border-radius: 10px; padding: 3px 9px; }}"
            )
            layout_ley.addWidget(chip)

        self.frame_leyenda_curvas.updateGeometry()
        if hasattr(self, "stack_hdr_curvas"):
            self.stack_hdr_curvas.updateGeometry()

    @staticmethod
    def _icono_punto_ruta(color_hex, tam=10):
        pix = QPixmap(tam, tam)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color_hex))
        painter.drawEllipse(1, 1, tam - 2, tam - 2)
        painter.end()
        return QIcon(pix)

    def _actualizar_barra_rutas_egl(self):
        barra = getattr(self, "barra_rutas_egl", None)
        layout = getattr(self, "layout_rutas_egl", None)
        chart = getattr(self, "egl_chart", None)
        if barra is None or layout is None or chart is None:
            return

        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._botones_rutas_egl = []

        series = getattr(chart, "series", None) or []
        if len(series) <= 1:
            barra.hide()
            return

        lbl_tit = QLabel("RUTAS:")
        lbl_tit.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 10px; "
            "font-weight: 700; color: #475569; background: transparent; padding-right: 4px;"
        )
        layout.addWidget(lbl_tit)

        sel = getattr(chart, "ruta_seleccionada", None)

        def crear_pill(texto, col_hex, activo, on_click):
            btn = QPushButton(texto)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setChecked(bool(activo))
            if col_hex:
                btn.setIcon(self._icono_punto_ruta("#ffffff" if activo else col_hex))
                btn.setIconSize(QSize(10, 10))
            if activo:
                col_bg = col_hex or "#006398"
                btn.setStyleSheet(
                    f"QPushButton {{ font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
                    f"font-weight: 700; color: #ffffff; background: {col_bg}; "
                    f"border: 1.2px solid {col_bg}; border-radius: 6px; padding: 4px 10px; }}"
                )
            else:
                borde_h = col_hex or "#006398"
                btn.setStyleSheet(
                    f"QPushButton {{ font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
                    f"font-weight: 600; color: #1e293b; background: #ffffff; "
                    f"border: 1.2px solid #cbd5e1; border-radius: 6px; padding: 4px 10px; }}"
                    f"QPushButton:hover {{ border-color: {borde_h}; background: #f8fafc; }}"
                )
            btn.clicked.connect(on_click)
            return btn

        btn_todas = crear_pill(
            f"Todas ({len(series)})",
            None,
            sel is None,
            lambda _checked=False: self._on_seleccionar_ruta_egl(None),
        )
        layout.addWidget(btn_todas)
        self._botones_rutas_egl.append(btn_todas)

        for idx, s in enumerate(series):
            col = chart.color_serie(idx) if hasattr(chart, "color_serie") else s.get("color", "#0284c7")
            nom = s.get("nombre", f"Ruta {idx + 1}")
            meta = s.get("meta_ruta") or {}
            partes = [nom]
            if meta.get("q_ls") is not None:
                partes.append(f"{meta['q_ls']:.2f} L/s")
            btn_ruta = crear_pill(
                " · ".join(partes),
                col,
                sel == idx,
                lambda _checked=False, i=idx: self._on_seleccionar_ruta_egl(i),
            )
            btn_ruta.setToolTip(
                f"Aislar {nom} para inspeccionar su EGL, HGL (piezométrica) y pérdidas individuales."
            )
            layout.addWidget(btn_ruta)
            self._botones_rutas_egl.append(btn_ruta)

        barra.show()
        barra.updateGeometry()

    def _on_seleccionar_ruta_egl(self, indice):
        if hasattr(self, "egl_chart") and hasattr(self.egl_chart, "set_ruta_seleccionada"):
            self.egl_chart.set_ruta_seleccionada(indice)
        self._actualizar_barra_rutas_egl()
        self._actualizar_leyenda_curvas()

    def _sincronizar_estado_bomba_curvas(self):
        """Sincroniza el estado vacío o calculado de la vista Curvas de Bomba (H - Q)."""
        if not hasattr(self, "stack_contenido_bomba_curvas"):
            return
        tiene_bomba_calc = bool(
            hasattr(self, "grafico_bombas")
            and self.grafico_bombas.curvas
            and self.grafico_bombas.Q_op is not None
        )
        if tiene_bomba_calc:
            self.stack_contenido_bomba_curvas.setCurrentIndex(1)
            if hasattr(self, "lbl_pill_bomba_vacio"):
                self.lbl_pill_bomba_vacio.setVisible(False)
            if hasattr(self, "grafico_bombas") and hasattr(self.grafico_bombas, "btn_exportar"):
                self.grafico_bombas.btn_exportar.setVisible(True)
            if hasattr(self, "panel_lateral_bombas"):
                self.panel_lateral_bombas.actualizar()
                self.chips_bombas_individuales = getattr(self.panel_lateral_bombas, "chips_bombas_individuales", [])
        else:
            self.stack_contenido_bomba_curvas.setCurrentIndex(0)
            if hasattr(self, "lbl_pill_bomba_vacio"):
                self.lbl_pill_bomba_vacio.setVisible(True)
            if hasattr(self, "grafico_bombas") and hasattr(self.grafico_bombas, "btn_exportar"):
                self.grafico_bombas.btn_exportar.setVisible(False)

    def _actualizar_pestana_bombas(self):
        """Mantiene la pestaña de Bombas siempre disponible."""
        scene = getattr(self, "canvas_view", None)
        scene = scene.scene() if scene else None

        hay_bomba = False
        if scene is not None:
            from ui.graficos import BombaGrafica
            hay_bomba = any(isinstance(i, BombaGrafica) for i in scene.items())

        if hasattr(self, "btn_curvas_bomba"):
            self.btn_curvas_bomba.setVisible(True)
            self.btn_curvas_bomba.setEnabled(True)

        if hasattr(self, "tab_curvas"):
            self.tab_curvas.setTabEnabled(1, hay_bomba)
            if hasattr(self.tab_curvas, "setTabVisible"):
                self.tab_curvas.setTabVisible(1, True)

        self._sincronizar_estado_bomba_curvas()

    def _on_toggle_mostrar_valores_curvas(self, activo):
        if hasattr(self, "egl_chart"):
            self.egl_chart.set_mostrar_valores(activo)
        if hasattr(self, "btn_modo_exacto") and hasattr(self, "btn_modo_didactico"):
            prev_ex = self.btn_modo_exacto.blockSignals(True)
            prev_di = self.btn_modo_didactico.blockSignals(True)
            self.btn_modo_exacto.setChecked(bool(activo))
            self.btn_modo_didactico.setChecked(not bool(activo))
            self.btn_modo_exacto.blockSignals(prev_ex)
            self.btn_modo_didactico.blockSignals(prev_di)

    def _on_toggle_linea_piezometrica(self, activo):
        if hasattr(self, "egl_chart"):
            self.egl_chart.set_mostrar_hgl(activo)
        if hasattr(self, "chk_linea_piezometrica"):
            self.chk_linea_piezometrica.setIcon(
                crear_icono_herramienta("trazo_discontinuo", "#2980b9" if activo else "#94a3b8")
            )
        self._actualizar_leyenda_curvas()

    def _on_toggle_linea_energia(self, activo):
        if hasattr(self, "egl_chart"):
            self.egl_chart.set_mostrar_egl(activo)
        if hasattr(self, "chk_linea_energia"):
            self.chk_linea_energia.setIcon(
                crear_icono_herramienta("trazo_solido", "#e74c3c" if activo else "#94a3b8")
            )
        self._actualizar_leyenda_curvas()

    def _sincronizar_estado_vista_curvas(self, tiene_datos):
        self._actualizar_pestana_bombas()
        self._sincronizar_estado_bomba_curvas()
        if not hasattr(self, "stack_contenido_curvas"):
            return
        es_egl = getattr(self, "stack_modo_curvas", None) is None or self.stack_modo_curvas.currentIndex() == 0
        if hasattr(self, "egl_chart") and hasattr(self.egl_chart, "btn_exportar"):
            self.egl_chart.btn_exportar.setVisible(bool(tiene_datos))
        if tiene_datos:
            self.stack_contenido_curvas.setCurrentIndex(1)
            self.stack_hdr_curvas.setCurrentIndex(1)
            self._actualizar_controles_egl_visibles(es_egl)
            self._actualizar_barra_rutas_egl()
            self._actualizar_leyenda_curvas()
            res = getattr(self.egl_chart, "resumen", {}) or {}
            z1_v = float(res.get("z1", 0.0))
            z2_v = float(res.get("z2", 0.0))
            hf_v = float(res.get("hf_total", 0.0))
            exc_v = float(res.get("H_op", res.get("excedente", max(0.0, (z1_v - z2_v) - hf_v))))
            sub_z1 = res.get("sub_z1", "Tanque 1 (Superficie)")
            sub_z2 = res.get("sub_z2", "Tanque 2 (Descarga)")
            sub_hf = res.get("sub_hf", "Fricción + Accesorios + Bordes")
            sub_exc = res.get("sub_exc", "Flujo por gravedad asegurado")
            tit_exc = res.get("tit_exc", "ENERGÍA EXCEDENTE")
            col_exc = res.get("col_exc", "#006398")

            if "z1" in self._curvas_kpi_labels:
                _, lv, _, ls = self._curvas_kpi_labels["z1"]
                lv.setText(f"{z1_v:.2f}")
                ls.setText(sub_z1)
            if "z2" in self._curvas_kpi_labels:
                _, lv, _, ls = self._curvas_kpi_labels["z2"]
                lv.setText(f"{z2_v:.2f}")
                ls.setText(sub_z2)
            if "hf" in self._curvas_kpi_labels:
                _, lv, _, ls = self._curvas_kpi_labels["hf"]
                lv.setText(f"{hf_v:.2f}")
                ls.setText(sub_hf)
            if "exc" in self._curvas_kpi_labels:
                lt, lv, _, ls = self._curvas_kpi_labels["exc"]
                lt.setText(tit_exc)
                lv.setText(f"{exc_v:.2f}")
                ls.setText(sub_exc)
                ls.setStyleSheet(
                    f"font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; "
                    f"font-weight: 600; color: {col_exc}; background: transparent;"
                )
        else:
            self.stack_contenido_curvas.setCurrentIndex(0)
            self.stack_hdr_curvas.setCurrentIndex(0)
            self._actualizar_controles_egl_visibles(False)
            self._actualizar_barra_rutas_egl()
            if hasattr(self, "lbl_egl_subtitle"):
                self.lbl_egl_subtitle.setText("Perfil de energía y cota piezométrica")

    def _cambiar_vista_central(self, modo):
        if modo == "tabla" and openpyxl is None:
            QMessageBox.information(
                self, "Próximamente", "Próximamente: Vista previa de tabla"
            )
            return

        mapa_idx = {"cad": 0, "tabla": 1, "curvas": 2}
        idx = mapa_idx.get(modo, 0)
        cambio_vista = hasattr(self, "stack_central") and self.stack_central.currentIndex() != idx
        if hasattr(self, "stack_central"):
            self.stack_central.setCurrentIndex(idx)

        if modo == "curvas":
            self._actualizar_pestana_bombas()

        # En TABLA y CURVAS se ocultan el panel derecho y la barra de herramientas superior; en CAD se muestran
        if hasattr(self, "side_panel") and self.side_panel is not None:
            if modo in ("tabla", "curvas"):
                self.side_panel.hide()
            else:
                self.side_panel.show()

        if hasattr(self, "main_toolbar") and self.main_toolbar is not None:
            if modo == "cad":
                self.main_toolbar.show()
            else:
                self.main_toolbar.hide()
            if hasattr(self, "top_bars_container") and self.top_bars_container is not None:
                self.top_bars_container.adjustSize()

        if hasattr(self, "contenedor_trazado") and self.contenedor_trazado is not None:
            if modo == "cad":
                self.contenedor_trazado.show()
            else:
                self.contenedor_trazado.hide()

        botones_nav = (
            ("cad", self.btn_nav_cad, "cad"),
            ("tabla", self.btn_nav_tabla, "tabla"),
            ("curvas", self.btn_nav_curvas, "curvas"),
        )
        for clave, btn, tipo_ico in botones_nav:
            activo = clave == modo
            btn.setObjectName("navBtnActive" if activo else "navBtnInactive")
            color_ico = (
                "#ffffff"
                if activo
                else TEMA_STITCH["on_surface_variant"]
            )
            btn.setIcon(crear_icono_herramienta(tipo_ico, color_ico))
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
            if activo and hasattr(self, "indicador_nav"):
                self.indicador_nav.ir_a(btn)

        if modo == "tabla":
            self._actualizar_vista_tabla_excel()
        elif modo == "curvas" and hasattr(self, "egl_chart"):
            self._sincronizar_estado_vista_curvas(bool(self.egl_chart.series))

        if cambio_vista:
            revelar_contenido(self.stack_central, 28)

    @staticmethod
    def _rgb_openpyxl(color_obj):
        try:
            if color_obj is not None and color_obj.type == "rgb" and color_obj.rgb:
                rgb = str(color_obj.rgb)
                if len(rgb) in (6, 8):
                    return "#" + rgb[-6:]
        except Exception:
            pass
        return None

    def _actualizar_vista_tabla_excel(self):
        if not hasattr(self, "stack_tabla"):
            return
        datos = self.datos_exportacion
        if openpyxl is None or xlsxwriter is None or not datos or not datos.get("tuberias"):
            self._tabla_cache = None
            self._mostrar_tabla_vacia()
            return

        try:
            buf = io.BytesIO()
            self._escribir_libro_excel(buf, datos)
            crudo = buf.getvalue()
            ws_val = openpyxl.load_workbook(io.BytesIO(crudo), data_only=True).active
            ws_for = openpyxl.load_workbook(io.BytesIO(crudo), data_only=False).active
        except Exception:
            self._tabla_cache = None
            self._mostrar_tabla_vacia()
            return

        max_r = ws_val.max_row or 1
        max_c = ws_val.max_column or 1
        celdas = {}
        for r_idx in range(1, max_r + 1):
            for c_idx in range(1, max_c + 1):
                celda = ws_val.cell(row=r_idx, column=c_idx)
                val = celda.value
                if val is None:
                    txt = ""
                elif isinstance(val, float):
                    txt = f"{int(val)}" if val.is_integer() and abs(val) < 1e9 else f"{val:.6g}"
                else:
                    txt = str(val)
                # Solo presentación: 1/raiz(f) se muestra como 1/√f (no altera el Excel)
                txt_vis = txt.replace("1/raiz(f)", "1/√f").replace("raiz(f)", "√f")
                formula = ws_for.cell(row=r_idx, column=c_idx).value
                formula_txt = formula if isinstance(formula, str) and formula.startswith("=") else txt
                fnt = celda.font
                alin = celda.alignment
                bg = None
                if celda.fill and celda.fill.fill_type == "solid" and celda.fill.fgColor is not None:
                    bg = self._rgb_openpyxl(celda.fill.fgColor)
                    if bg and bg.lower() == "#000000":
                        bg = None
                color_txt = self._rgb_openpyxl(fnt.color) if fnt is not None else None
                negrita = bool(fnt.bold) if fnt is not None else False
                if txt.startswith("EQUILIBRIO"):
                    color_txt, negrita = "#1e7b34", True
                elif txt.startswith("ERRÓNEO"):
                    color_txt, negrita = "#c0392b", True
                celdas[(r_idx, c_idx)] = {
                    # Número original de la caché Excel; txt solo lo formatea.
                    "valor": val,
                    "txt": txt_vis,
                    "formula": formula_txt,
                    "negrita": negrita,
                    "tam": float(fnt.size) if (fnt is not None and fnt.size) else 11.0,
                    "color": color_txt,
                    "bg": bg,
                    "alin": alin.horizontal if alin is not None else None,
                    "wrap": bool(alin.wrap_text) if alin is not None else False,
                    "numero": isinstance(val, (int, float)) and not isinstance(val, bool),
                }

        anchos = []
        for c_idx in range(1, max_c + 1):
            dim = ws_val.column_dimensions.get(get_column_letter(c_idx))
            anchos.append(dim.width if (dim and dim.width) else 14)
        altos = []
        for r_idx in range(1, max_r + 1):
            dim_r = ws_val.row_dimensions.get(r_idx)
            altos.append(dim_r.height if (dim_r and dim_r.height) else 20)

        uniones = []
        for mr in ws_val.merged_cells.ranges:
            if mr.max_row > mr.min_row or mr.max_col > mr.min_col:
                uniones.append((mr.min_row, mr.min_col, mr.max_row, mr.max_col))

        self._tabla_cache = {
            "max_r": max_r,
            "max_c": max_c,
            "celdas": celdas,
            "anchos": anchos,
            "altos": altos,
            "uniones": uniones,
            "titulo": datos.get("tipo_sistema", "Sistema"),
            "ok": bool((datos.get("resultados") or {}).get("ok", False)),
        }
        self._renderizar_tabla_excel()
        self._mostrar_tabla_con_datos()

    def _mostrar_tabla_vacia(self):
        if not hasattr(self, "stack_tabla"):
            return
        self.stack_tabla.setCurrentIndex(0)
        if hasattr(self, "lbl_tabla_titulo"):
            self.lbl_tabla_titulo.setText("Memoria de cálculo — Sin sistema calculado")
        if hasattr(self, "lbl_tabla_badge"):
            self.lbl_tabla_badge.setText("  Sin datos de simulación  ")
            self.lbl_tabla_badge.setStyleSheet(
                "background-color: #f1f5f9; color: #64748b; border-radius: 10px; "
                "font-size: 11px; font-weight: 600; padding: 2px 8px; border: 1px solid #e2e8f0;"
            )
        if hasattr(self, "btn_tabla_exportar"):
            self.btn_tabla_exportar.setEnabled(False)
        if hasattr(self, "lbl_tabla_ref"):
            self.lbl_tabla_ref.setText("—")
        if hasattr(self, "txt_tabla_formula"):
            self.txt_tabla_formula.setText("")
            self.txt_tabla_formula.setPlaceholderText("Hoja vacía. Ninguna celda seleccionada.")
        if hasattr(self, "hud_tabla_zoom"):
            self.hud_tabla_zoom.hide()

    def _mostrar_tabla_con_datos(self):
        if not hasattr(self, "stack_tabla"):
            return
        cache = self._tabla_cache or {}
        self.stack_tabla.setCurrentIndex(1)
        if hasattr(self, "lbl_tabla_titulo"):
            self.lbl_tabla_titulo.setText(f"Memoria de cálculo — {cache.get('titulo', 'Sistema')}")
        if hasattr(self, "lbl_tabla_badge"):
            if cache.get("ok"):
                self.lbl_tabla_badge.setText("  Equilibrio verificado  ")
                self.lbl_tabla_badge.setStyleSheet(
                    "background-color: #dcfce7; color: #166534; border-radius: 10px; "
                    "font-size: 11px; font-weight: 600; padding: 2px 8px; border: 1px solid #bbf7d0;"
                )
            else:
                self.lbl_tabla_badge.setText("  Revisar diagnóstico  ")
                self.lbl_tabla_badge.setStyleSheet(
                    "background-color: #fee2e2; color: #991b1b; border-radius: 10px; "
                    "font-size: 11px; font-weight: 600; padding: 2px 8px; border: 1px solid #fecaca;"
                )
        if hasattr(self, "btn_tabla_exportar"):
            self.btn_tabla_exportar.setEnabled(True)
        if hasattr(self, "txt_tabla_formula"):
            self.txt_tabla_formula.setPlaceholderText("Selecciona una celda para ver su fórmula")
        if hasattr(self, "hud_tabla_zoom"):
            self.hud_tabla_zoom.show()
            self.hud_tabla_zoom.raise_()
        if hasattr(self, "contenedor_hoja"):
            self.contenedor_hoja._reposicionar_hud()
        if hasattr(self, "tabla_excel_preview"):
            r = max(0, self.tabla_excel_preview.currentRow())
            c = max(0, self.tabla_excel_preview.currentColumn())
            self.tabla_excel_preview.setCurrentCell(r, c)
            self._on_tabla_celda_actual(r, c)

    def _renderizar_tabla_excel(self):
        cache = getattr(self, "_tabla_cache", None)
        if not cache:
            return
        z = self._tabla_zoom
        tabla = self.tabla_excel_preview
        max_r, max_c = cache["max_r"], cache["max_c"]
        celdas = cache["celdas"]

        tabla.setUpdatesEnabled(False)
        fila_sel, col_sel = tabla.currentRow(), tabla.currentColumn()
        tabla.clearSpans()
        tabla.clear()
        tabla.setRowCount(max_r)
        tabla.setColumnCount(max_c)
        tabla.setHorizontalHeaderLabels([get_column_letter(c) for c in range(1, max_c + 1)])
        tabla.setVerticalHeaderLabels([str(r) for r in range(1, max_r + 1)])

        f_hdr = QFont("Inter", 9)
        f_hdr.setPointSizeF(max(5.0, 8.5 * z))
        f_hdr.setWeight(QFont.DemiBold)
        tabla.horizontalHeader().setFont(f_hdr)
        tabla.verticalHeader().setFont(f_hdr)
        fm_hdr = QtGui.QFontMetrics(f_hdr)
        tabla.horizontalHeader().setFixedHeight(int(fm_hdr.height() + 12 * z))
        tabla.verticalHeader().setFixedWidth(int(fm_hdr.horizontalAdvance(str(max_r)) + 22 * z))

        cubiertas = set()
        inicio_union = {}
        for (r1, c1, r2, c2) in cache["uniones"]:
            inicio_union[(r1, c1)] = (r2, c2)
            for rr in range(r1, r2 + 1):
                for cc in range(c1, c2 + 1):
                    if (rr, cc) != (r1, c1):
                        cubiertas.add((rr, cc))

        pad = max(22.0, 24.0 * z)
        anchos = [max(48.0, a * 8.0) * z for a in cache["anchos"]]
        altos = [max(24.0, h * 1.25) * z for h in cache["altos"]]
        fuentes = {}

        def fuente_de(info):
            clave = (info["numero"], info["negrita"], info["tam"])
            if clave not in fuentes:
                fam = "JetBrains Mono" if info["numero"] else "Inter"
                f = QFont(fam)
                if info["numero"]:
                    f.setFamilies(["JetBrains Mono", "Consolas"]) if hasattr(f, "setFamilies") else None
                f.setPointSizeF(max(5.0, info["tam"] * 0.85 * z))
                f.setBold(info["negrita"])
                f.setStyleStrategy(QFont.PreferAntialias)
                fuentes[clave] = f
            return fuentes[clave]

        for (r_idx, c_idx), info in celdas.items():
            item = QTableWidgetItem(info["txt"])
            al = info["alin"]
            if al == "center":
                flags_al = Qt.AlignCenter
            elif al == "right":
                flags_al = Qt.AlignRight | Qt.AlignVCenter
            else:
                flags_al = Qt.AlignLeft | Qt.AlignVCenter
            item.setTextAlignment(flags_al)
            fnt = fuente_de(info)
            item.setFont(fnt)
            item.setForeground(QBrush(QColor(info["color"] or "#0b1c30")))
            if info["bg"]:
                item.setBackground(QBrush(QColor(info["bg"])))
            tabla.setItem(r_idx - 1, c_idx - 1, item)

            if (r_idx, c_idx) in cubiertas or not info["txt"]:
                continue
            fm = QtGui.QFontMetrics(fnt)
            alto_lin = fm.height() + 10.0 * z
            altos[r_idx - 1] = max(altos[r_idx - 1], alto_lin)
            if (r_idx, c_idx) in inicio_union:
                continue
            if info["wrap"] and fm.horizontalAdvance(info["txt"]) + pad > anchos[c_idx - 1] * 1.6:
                rect = fm.boundingRect(QRect(0, 0, int(anchos[c_idx - 1] - pad), 100000),
                                       Qt.TextWordWrap, info["txt"])
                altos[r_idx - 1] = max(altos[r_idx - 1], rect.height() + 10.0 * z)
            else:
                anchos[c_idx - 1] = max(anchos[c_idx - 1], fm.horizontalAdvance(info["txt"]) + pad)

        # Celdas combinadas: el texto nunca se corta (se amplía la última columna o las filas)
        for (r1, c1), (r2, c2) in inicio_union.items():
            info = celdas.get((r1, c1))
            if not info or not info["txt"]:
                continue
            fm = QtGui.QFontMetrics(fuente_de(info))
            ancho_txt = fm.horizontalAdvance(info["txt"]) + pad
            ancho_disp = sum(anchos[c1 - 1:c2])
            alto_disp = sum(altos[r1 - 1:r2])
            if r2 == r1 or not info["wrap"]:
                if ancho_txt > ancho_disp:
                    anchos[c2 - 1] += ancho_txt - ancho_disp
            else:
                rect = fm.boundingRect(QRect(0, 0, int(max(40.0, ancho_disp - pad)), 100000),
                                       Qt.TextWordWrap, info["txt"])
                necesario = rect.height() + 12.0 * z
                if necesario > alto_disp:
                    extra = (necesario - alto_disp) / float(r2 - r1 + 1)
                    for rr in range(r1, r2 + 1):
                        altos[rr - 1] += extra

        for (r1, c1), (r2, c2) in inicio_union.items():
            tabla.setSpan(r1 - 1, c1 - 1, r2 - r1 + 1, c2 - c1 + 1)
        for c_idx, w in enumerate(anchos):
            tabla.setColumnWidth(c_idx, int(math.ceil(w)))
        for r_idx, h in enumerate(altos):
            tabla.setRowHeight(r_idx, int(math.ceil(h)))

        if 0 <= fila_sel < max_r and 0 <= col_sel < max_c:
            tabla.setCurrentCell(fila_sel, col_sel)
        tabla.setUpdatesEnabled(True)
        self.lbl_tabla_zoom_pct.setText(f"{int(round(z * 100))}%")

    def _aplicar_zoom_tabla(self, nuevo):
        nuevo = max(self.TABLA_ZOOM_MIN, min(self.TABLA_ZOOM_MAX, float(nuevo)))
        if abs(nuevo - self._tabla_zoom) < 1e-4:
            self.lbl_tabla_zoom_pct.setText(f"{int(round(nuevo * 100))}%")
            return
        self._tabla_zoom = nuevo
        self._renderizar_tabla_excel()

    def _zoom_tabla_in(self):
        self._aplicar_zoom_tabla(self._tabla_zoom * self.TABLA_ZOOM_PASO)

    def _zoom_tabla_out(self):
        self._aplicar_zoom_tabla(self._tabla_zoom / self.TABLA_ZOOM_PASO)

    def _zoom_tabla_reset(self):
        self._aplicar_zoom_tabla(1.0)

    def _zoom_tabla_ajustar(self):
        tabla = self.tabla_excel_preview
        if not getattr(self, "_tabla_cache", None):
            return
        ancho_total = sum(tabla.columnWidth(c) for c in range(tabla.columnCount()))
        ancho_total += tabla.verticalHeader().width()
        disp = tabla.viewport().width() + tabla.verticalHeader().width() - 8
        if ancho_total <= 0:
            return
        self._aplicar_zoom_tabla(self._tabla_zoom * disp / float(ancho_total))

    def _on_tabla_celda_actual(self, fila, col, *_):
        cache = getattr(self, "_tabla_cache", None)
        if not cache or fila < 0 or col < 0:
            self.lbl_tabla_ref.setText("—")
            self.txt_tabla_formula.setText("")
            return
        self.lbl_tabla_ref.setText(f"{get_column_letter(col + 1)}{fila + 1}")
        info = cache["celdas"].get((fila + 1, col + 1))
        formula = info["formula"] if info else ""
        if isinstance(formula, str):
            formula = formula.replace("1/raiz(f)", "1/√f") if not formula.startswith("=") else formula
        self.txt_tabla_formula.setText(str(formula or ""))
        self.txt_tabla_formula.setCursorPosition(0)
