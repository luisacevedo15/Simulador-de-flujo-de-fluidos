"""Widget del perfil de la línea de energía (EGL) y de la línea hidráulica (HGL)."""

from PyQt5 import QtGui
from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.iconos import crear_icono_herramienta

PALETA_RUTAS_EGL = (
    "#0284c7",  # Azul hidráulico
    "#d97706",  # Naranja ámbar
    "#059669",  # Verde esmeralda
    "#7c3aed",  # Violeta
    "#db2777",  # Magenta
    "#0891b2",  # Cian profundo
    "#b45309",  # Terracota
    "#4f46e5",  # Índigo
)


class WidgetPerfilEGLHGL(QWidget):
    """Trazador de Línea de Energía (EGL) y Línea Piezométrica (HGL) estilo Google Stitch."""

    PALETA_RUTAS = PALETA_RUTAS_EGL

    COLORES_CAUSA = {
        "friccion": "#e74c3c",     # Rojo: Fricción en tubería (coincide con línea EGL)
        "accesorio": "#f59e0b",    # Naranja: Accesorios (válvula, codo, reducción)
        "borde": "#0d9488",        # Verde azulado: Pérdidas de entrada / salida en tanques
        "entrada": "#64748b",      # Gris: Entrada al sistema
        "salida": "#64748b",       # Gris: Salida / descarga
        "deficit": "#dc2626",      # Rojo: Energía faltante
        "bomba": "#16a34a",        # Verde: Salto de energía por bomba
        "cambio_diametro": "#7c3aed",  # Violeta: Salto cinético en cambio de diámetro
    }

    _ZOOM_MIN_SPAN = 0.002

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(340)
        self.setMouseTracking(True)
        self.series = []
        self.mostrar_valores = False
        self.mostrar_hgl = True
        self.mostrar_egl = True
        self.ocultar_textos = False
        self.ruta_seleccionada = None
        self._colores_series = []
        self.resumen = {}
        self.on_cambio_estado = None

        # Estado de viewport (zoom / paneo en coordenadas normalizadas [0, 1])
        self._vx0 = 0.0
        self._vx1 = 1.0
        self._vy0 = 0.0
        self._vy1 = 1.0
        self._zoom_step = 1.25
        self._ultimo_plot_rect = QRectF()
        self._modo_arrastre = None
        self._arrastre_inicio_pos = QPointF()
        self._arrastre_actual_pos = QPointF()
        self._pan_inicio_vp = (0.0, 1.0, 0.0, 1.0)

        # Barra superior derecha: HUD de zoom + botón Descargar imagen
        self.layout_top = QVBoxLayout(self)
        self.layout_top.setContentsMargins(14, 8, 14, 0)
        self.layout_top.setSpacing(0)

        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_row.setSpacing(8)
        hdr_row.addStretch()

        self.hud_zoom_frame = QFrame(self)
        self.hud_zoom_frame.setObjectName("hudZoomFrame")
        self.hud_zoom_frame.setStyleSheet(
            "QFrame#hudZoomFrame { background-color: rgba(255, 255, 255, 0.94); "
            "border: 1px solid #d8e2ee; border-radius: 6px; }"
            "QPushButton#hudZoomBtn { background-color: transparent; color: #334155; "
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 13px; font-weight: 600; "
            "border: none; border-radius: 4px; padding: 1px 4px; }"
            "QPushButton#hudZoomBtn:hover { background-color: #e2e8f0; color: #0c4e77; }"
            "QPushButton#hudZoomBtn:pressed { background-color: #cbd5e1; }"
            "QLabel#hudZoomLabel { font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
            "font-weight: 600; color: #334155; background: transparent; }"
        )
        hud_zoom_layout = QHBoxLayout(self.hud_zoom_frame)
        hud_zoom_layout.setContentsMargins(4, 2, 4, 2)
        hud_zoom_layout.setSpacing(2)

        self.btn_zoom_out = QPushButton("−", self.hud_zoom_frame)
        self.btn_zoom_out.setObjectName("hudZoomBtn")
        self.btn_zoom_out.setFixedSize(24, 22)
        self.btn_zoom_out.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_out.setToolTip("Alejar (rueda del mouse)")
        self.btn_zoom_out.clicked.connect(self.zoom_out)

        self.lbl_zoom_pct = QLabel("100%", self.hud_zoom_frame)
        self.lbl_zoom_pct.setObjectName("hudZoomLabel")
        self.lbl_zoom_pct.setAlignment(Qt.AlignCenter)
        self.lbl_zoom_pct.setMinimumWidth(52)

        self.btn_zoom_in = QPushButton("+", self.hud_zoom_frame)
        self.btn_zoom_in.setObjectName("hudZoomBtn")
        self.btn_zoom_in.setFixedSize(24, 22)
        self.btn_zoom_in.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_in.setToolTip("Acercar (rueda del mouse o arrastrar con botón derecho)")
        self.btn_zoom_in.clicked.connect(self.zoom_in)

        self.btn_zoom_reset = QPushButton("⛶", self.hud_zoom_frame)
        self.btn_zoom_reset.setObjectName("hudZoomBtn")
        self.btn_zoom_reset.setFixedSize(24, 22)
        self.btn_zoom_reset.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_reset.setToolTip("Restablecer vista 100% (doble clic)")
        self.btn_zoom_reset.clicked.connect(self.restablecer_zoom)

        hud_zoom_layout.addWidget(self.btn_zoom_out)
        hud_zoom_layout.addWidget(self.lbl_zoom_pct)
        hud_zoom_layout.addWidget(self.btn_zoom_in)
        hud_zoom_layout.addWidget(self.btn_zoom_reset)
        self.hud_zoom_frame.setVisible(False)
        hdr_row.addWidget(self.hud_zoom_frame)

        self.btn_ocultar_textos = QPushButton("Ocultar textos")
        self.btn_ocultar_textos.setCheckable(True)
        self.btn_ocultar_textos.setChecked(False)
        self.btn_ocultar_textos.setIcon(crear_icono_herramienta("texto", "#334155"))
        self.btn_ocultar_textos.setIconSize(QSize(12, 12))
        self.btn_ocultar_textos.setCursor(Qt.PointingHandCursor)
        self.btn_ocultar_textos.setToolTip(
            "Ocultar las etiquetas y anotaciones sobre las curvas (conserva ejes y estaciones)"
        )
        self.btn_ocultar_textos.setStyleSheet(
            "QPushButton { font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
            "font-weight: 600; color: #334155; background: #ffffff; border: 1px solid #d8e2ee; "
            "border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background: #f1f5f9; color: #0c4e77; }"
            "QPushButton:checked { color: #006398; background: #dbeafe; border-color: #93c5fd; }"
            "QPushButton:checked:hover { background: #bfdbfe; color: #0c4e77; }"
        )
        self.btn_ocultar_textos.toggled.connect(self.set_ocultar_textos)
        self.btn_ocultar_textos.setVisible(False)
        hdr_row.addWidget(self.btn_ocultar_textos)

        self.btn_exportar = QPushButton("Descargar imagen")
        self.btn_exportar.setIcon(crear_icono_herramienta("descargar", "#006398"))
        self.btn_exportar.setIconSize(QSize(13, 13))
        self.btn_exportar.setCursor(Qt.PointingHandCursor)
        self.btn_exportar.setToolTip("Exportar esta gráfica como imagen PNG de alta resolución")
        self.btn_exportar.setStyleSheet(
            "QPushButton { font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
            "font-weight: 600; color: #006398; background: #e5eeff; border: 1px solid #cce0ff; "
            "border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background: #d0e4ff; color: #0c4e77; }"
            "QPushButton:pressed { background: #b8d7ff; }"
        )
        self.btn_exportar.clicked.connect(self.exportar_imagen)
        self.btn_exportar.setVisible(False)
        hdr_row.addWidget(self.btn_exportar)

        self.layout_top.addLayout(hdr_row)
        self.layout_top.addStretch(1)

    def set_mostrar_valores(self, activo):
        self.mostrar_valores = bool(activo)
        self.update()

    def set_mostrar_hgl(self, activo):
        self.mostrar_hgl = bool(activo)
        self.update()

    def set_mostrar_egl(self, activo):
        self.mostrar_egl = bool(activo)
        self.update()

    def set_ocultar_textos(self, activo):
        nuevo = bool(activo)
        self.ocultar_textos = nuevo
        if hasattr(self, "btn_ocultar_textos"):
            self.btn_ocultar_textos.blockSignals(True)
            self.btn_ocultar_textos.setChecked(nuevo)
            self.btn_ocultar_textos.setIcon(
                crear_icono_herramienta("texto", "#006398" if nuevo else "#334155")
            )
            self.btn_ocultar_textos.blockSignals(False)
        self.update()

    def set_ruta_seleccionada(self, indice):
        """Aísla una ruta específica (índice) o muestra todas (None)."""
        if indice is None or not (0 <= int(indice) < len(self.series)):
            nueva = None
        else:
            nueva = int(indice)
        if nueva != self.ruta_seleccionada:
            self.ruta_seleccionada = nueva
            self._reiniciar_viewport()
            self.update()

    def _esta_zoomed(self):
        return (self._vx1 - self._vx0) < 0.9999 or (self._vy1 - self._vy0) < 0.9999

    def zoom_factor(self):
        sx = 1.0 / max(self._ZOOM_MIN_SPAN, self._vx1 - self._vx0)
        sy = 1.0 / max(self._ZOOM_MIN_SPAN, self._vy1 - self._vy0)
        return max(sx, sy)

    def _actualizar_hud_zoom(self):
        if hasattr(self, "lbl_zoom_pct"):
            pct = int(round(self.zoom_factor() * 100))
            self.lbl_zoom_pct.setText(f"{pct}%")

    def _reiniciar_viewport(self):
        self._vx0 = 0.0
        self._vx1 = 1.0
        self._vy0 = 0.0
        self._vy1 = 1.0
        self._modo_arrastre = None
        self._actualizar_hud_zoom()
        if self.cursor().shape() != Qt.ArrowCursor:
            self.setCursor(Qt.ArrowCursor)

    def _fijar_viewport(self, nx0, nx1, ny0, ny1):
        span_x = min(1.0, max(self._ZOOM_MIN_SPAN, float(nx1) - float(nx0)))
        span_y = min(1.0, max(self._ZOOM_MIN_SPAN, float(ny1) - float(ny0)))

        if span_x >= 0.999 and span_y >= 0.999:
            self._reiniciar_viewport()
            self.update()
            return

        if span_x >= 0.999:
            nx0, nx1 = 0.0, 1.0
        else:
            nx0 = max(0.0, min(1.0 - span_x, float(nx0)))
            nx1 = nx0 + span_x

        if span_y >= 0.999:
            ny0, ny1 = 0.0, 1.0
        else:
            ny0 = max(0.0, min(1.0 - span_y, float(ny0)))
            ny1 = ny0 + span_y

        self._vx0, self._vx1 = nx0, nx1
        self._vy0, self._vy1 = ny0, ny1
        self._actualizar_hud_zoom()
        self.update()

    def _aplicar_zoom_en(self, factor, ax=0.5, ay=0.5):
        if not self.series or factor <= 0.0:
            return
        ax = max(0.0, min(1.0, float(ax)))
        ay = max(0.0, min(1.0, float(ay)))

        span_x = self._vx1 - self._vx0
        span_y = self._vy1 - self._vy0

        wx = self._vx0 + ax * span_x
        wy = self._vy0 + ay * span_y

        new_span_x = min(1.0, max(self._ZOOM_MIN_SPAN, span_x / factor))
        new_span_y = min(1.0, max(self._ZOOM_MIN_SPAN, span_y / factor))

        nx0 = wx - ax * new_span_x
        ny0 = wy - ay * new_span_y
        self._fijar_viewport(nx0, nx0 + new_span_x, ny0, ny0 + new_span_y)

    def zoom_in(self):
        if self.series:
            self._aplicar_zoom_en(self._zoom_step, 0.5, 0.5)

    def zoom_out(self):
        if self.series:
            self._aplicar_zoom_en(1.0 / self._zoom_step, 0.5, 0.5)

    def restablecer_zoom(self):
        self._reiniciar_viewport()
        self.update()

    @staticmethod
    def _calcular_rect_plot(r, para_exportar=False):
        left_pad = 104.0
        right_pad = 58.0
        top_pad = 78.0 if para_exportar else 42.0
        bot_pad = 74.0
        return QRectF(
            r.left() + left_pad,
            r.top() + top_pad,
            max(160.0, r.width() - left_pad - right_pad),
            max(120.0, r.height() - top_pad - bot_pad),
        )

    def _plot_actual(self):
        if not self._ultimo_plot_rect.isEmpty():
            return self._ultimo_plot_rect
        return self._calcular_rect_plot(QRectF(self.rect()).adjusted(4, 4, -4, -4), False)

    def _punto_a_frac_plot(self, pos):
        plot = self._plot_actual()
        if plot.isEmpty() or plot.width() <= 0 or plot.height() <= 0:
            return 0.5, 0.5
        ax = max(0.0, min(1.0, (pos.x() - plot.left()) / plot.width()))
        ay = max(0.0, min(1.0, (plot.bottom() - pos.y()) / plot.height()))
        return ax, ay

    def _clamped_en_plot(self, pos):
        plot = self._plot_actual()
        if plot.isEmpty():
            return QPointF(pos)
        return QPointF(
            max(plot.left(), min(plot.right(), float(pos.x()))),
            max(plot.top(), min(plot.bottom(), float(pos.y()))),
        )

    def wheelEvent(self, event):
        plot = self._plot_actual()
        pos = QPointF(event.pos())
        if not self.series or plot.isEmpty() or not plot.contains(pos):
            event.ignore()
            return
        delta_y = event.angleDelta().y()
        if delta_y == 0 or (delta_y < 0 and not self._esta_zoomed()):
            event.ignore()
            return
        ax, ay = self._punto_a_frac_plot(pos)
        pasos = delta_y / 120.0
        factor = self._zoom_step ** pasos
        self._aplicar_zoom_en(factor, ax, ay)
        event.accept()

    def mousePressEvent(self, event):
        plot = self._plot_actual()
        pos = QPointF(event.pos())
        if not self.series or plot.isEmpty() or not plot.contains(pos):
            super().mousePressEvent(event)
            return

        if event.button() == Qt.RightButton or (
            event.button() == Qt.LeftButton and (event.modifiers() & Qt.ControlModifier)
        ):
            self._modo_arrastre = "box"
            p_c = self._clamped_en_plot(pos)
            self._arrastre_inicio_pos = p_c
            self._arrastre_actual_pos = p_c
            self.setCursor(Qt.CrossCursor)
            self.update()
            event.accept()
            return

        if event.button() == Qt.LeftButton and self._esta_zoomed():
            self._modo_arrastre = "pan"
            self._arrastre_inicio_pos = pos
            self._arrastre_actual_pos = pos
            self._pan_inicio_vp = (self._vx0, self._vx1, self._vy0, self._vy1)
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        plot = self._plot_actual()
        pos = QPointF(event.pos())
        if self._modo_arrastre == "box" and not plot.isEmpty():
            self._arrastre_actual_pos = self._clamped_en_plot(pos)
            self.update()
            event.accept()
            return

        if self._modo_arrastre == "pan" and not plot.isEmpty():
            dx = pos.x() - self._arrastre_inicio_pos.x()
            dy = pos.y() - self._arrastre_inicio_pos.y()
            vx0_0, vx1_0, vy0_0, vy1_0 = self._pan_inicio_vp
            span_x = vx1_0 - vx0_0
            span_y = vy1_0 - vy0_0
            du = -(dx / plot.width()) * span_x
            dv = (dy / plot.height()) * span_y
            self._fijar_viewport(vx0_0 + du, vx0_0 + du + span_x, vy0_0 + dv, vy0_0 + dv + span_y)
            event.accept()
            return

        if self.series and not plot.isEmpty() and plot.contains(pos) and self._esta_zoomed():
            if self.cursor().shape() != Qt.OpenHandCursor:
                self.setCursor(Qt.OpenHandCursor)
        else:
            if self.cursor().shape() != Qt.ArrowCursor:
                self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._modo_arrastre == "box":
            sel = QRectF(self._arrastre_inicio_pos, self._arrastre_actual_pos).normalized()
            self._modo_arrastre = None
            plot = self._plot_actual()
            if (
                not plot.isEmpty()
                and sel.width() >= 12.0
                and sel.height() >= 12.0
                and plot.width() > 0
                and plot.height() > 0
            ):
                u0 = (sel.left() - plot.left()) / plot.width()
                u1 = (sel.right() - plot.left()) / plot.width()
                v0 = (plot.bottom() - sel.bottom()) / plot.height()
                v1 = (plot.bottom() - sel.top()) / plot.height()

                span_x = self._vx1 - self._vx0
                span_y = self._vy1 - self._vy0
                nx0 = self._vx0 + u0 * span_x
                nx1 = self._vx0 + u1 * span_x
                ny0 = self._vy0 + v0 * span_y
                ny1 = self._vy0 + v1 * span_y
                if (nx1 - nx0) < self._ZOOM_MIN_SPAN:
                    cx = 0.5 * (nx0 + nx1)
                    nx0, nx1 = cx - 0.5 * self._ZOOM_MIN_SPAN, cx + 0.5 * self._ZOOM_MIN_SPAN
                if (ny1 - ny0) < self._ZOOM_MIN_SPAN:
                    cy = 0.5 * (ny0 + ny1)
                    ny0, ny1 = cy - 0.5 * self._ZOOM_MIN_SPAN, cy + 0.5 * self._ZOOM_MIN_SPAN
                self._fijar_viewport(nx0, nx1, ny0, ny1)
            else:
                self.update()
            self.setCursor(Qt.OpenHandCursor if self._esta_zoomed() else Qt.ArrowCursor)
            event.accept()
            return

        if self._modo_arrastre == "pan":
            self._modo_arrastre = None
            plot = self._plot_actual()
            if not plot.isEmpty() and plot.contains(QPointF(event.pos())) and self._esta_zoomed():
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.series and self._esta_zoomed():
            self.restablecer_zoom()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event):
        if self._modo_arrastre is None and self.cursor().shape() != Qt.ArrowCursor:
            self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    def _indices_visibles(self):
        if not self.series:
            return []
        if self.ruta_seleccionada is not None and 0 <= self.ruta_seleccionada < len(self.series):
            return [self.ruta_seleccionada]
        return list(range(len(self.series)))

    @classmethod
    def resolver_colores_series(cls, series):
        """Asigna un color distinto a cada ruta cuando hay varias ramas en pantalla."""
        if not series:
            return []
        if len(series) == 1:
            return ["#e74c3c"]
        usados = set()
        colores = []
        for idx, s in enumerate(series):
            c = str(s.get("color") or "").strip().lower()
            neutro = (not c) or c in ("#ffffff", "#f8f9ff", "#000000", "#213145")
            if neutro or c in usados:
                c = next(
                    (p for p in cls.PALETA_RUTAS if p not in usados),
                    cls.PALETA_RUTAS[idx % len(cls.PALETA_RUTAS)],
                )
            usados.add(c)
            colores.append(c)
        return colores

    def color_serie(self, idx_s):
        if 0 <= idx_s < len(self._colores_series):
            return self._colores_series[idx_s]
        if len(self.series) <= 1:
            return "#e74c3c"
        return self.PALETA_RUTAS[idx_s % len(self.PALETA_RUTAS)]

    def _series_para_dibujar(self):
        """Los modos de rótulos conservan exactamente las ordenadas del motor."""
        return [s['puntos'] for s in self.series]

    def _resumen_regimen(self):
        """Calcula cotas de referencia y régimen energético (déficit/exceso/bomba) sin alterar las ordenadas."""
        indices_vis = self._indices_visibles()
        vis_series = [self.series[i] for i in indices_vis]
        pts_base = vis_series[0]["puntos"] if vis_series else []

        z1_raw = self.resumen.get("z1")
        z2_raw = self.resumen.get("z2")
        if z1_raw is not None and z2_raw is not None:
            Z1 = float(z1_raw)
            Z2 = float(z2_raw)
        elif pts_base:
            Z1 = float(pts_base[0].get("egl", 0.0))
            Z2 = float(pts_base[-1].get("egl", 0.0))
        else:
            Z1 = 0.0
            Z2 = 0.0

        deficit = float(self.resumen.get("deficit", 0.0))
        hf_total = float(self.resumen.get("hf_total", 0.0))
        delta_z = Z1 - Z2

        # Régimen de EXCESO (hf < ΔZ): se infiere del propio resumen, sin tocar motor ni resolver.
        exc_resumen = float(self.resumen.get("excedente", 0.0) or 0.0)
        dz_energia = hf_total + exc_resumen
        tol_eq = max(0.05, 0.01 * abs(dz_energia))

        has_bomba = (
            any(
                pt.get("causa") == "bomba" or pt.get("salto_bomba")
                for s in vis_series
                for pt in s.get("puntos", [])
            )
            or ("H_op" in self.resumen)
            or ("ALTURA BOMBA" in str(self.resumen.get("tit_exc", "")))
        )

        if has_bomba:
            h_bomba_val = float(self.resumen.get("H_op", self.resumen.get("excedente", 0.0)))
            if "energia_faltante" in self.resumen:
                diff_energia = float(self.resumen["energia_faltante"])
            else:
                h_req = (Z2 - Z1) + hf_total
                diff_energia = h_req - h_bomba_val

            hay_deficit = diff_energia > 1e-3
            hay_exceso = diff_energia < -1e-3
            deficit = diff_energia if hay_deficit else 0.0
            exc_resumen = (-diff_energia) if hay_exceso else 0.0
        else:
            fines_egl = [float(s["puntos"][-1].get("egl", 0.0)) for s in vis_series if s.get("puntos")]
            destinos_etq = {s["puntos"][-1].get("etiqueta", "") for s in vis_series if s.get("puntos")}
            mismo_destino = (
                bool(fines_egl)
                and (max(fines_egl) - min(fines_egl) <= tol_eq)
                and len(destinos_etq) <= 1
            )
            hay_exceso = (
                mismo_destino
                and len(pts_base) >= 2
                and self.resumen.get("tit_exc", "ENERGÍA EXCEDENTE") == "ENERGÍA EXCEDENTE"
                and deficit <= 0.05
                and exc_resumen > tol_eq
            )
            hay_deficit = (not hay_exceso) and (deficit > 0.05 or hf_total > delta_z)

        if hay_exceso and pts_base:
            nivel_t1 = float(pts_base[0].get("egl", Z1))
            nivel_t2 = nivel_t1 - dz_energia
        else:
            nivel_t1 = Z1
            nivel_t2 = Z2

        return dict(
            z1_raw=z1_raw,
            z2_raw=z2_raw,
            Z1=Z1,
            Z2=Z2,
            deficit=deficit,
            hf_total=hf_total,
            delta_z=delta_z,
            exc_resumen=exc_resumen,
            dz_energia=dz_energia,
            has_bomba=has_bomba,
            hay_deficit=hay_deficit,
            hay_exceso=hay_exceso,
            nivel_t1=nivel_t1,
            nivel_t2=nivel_t2,
        )

    def elementos_leyenda(self):
        """Devuelve solo los elementos visuales presentes en el perfil activo."""
        if not self.series:
            return []
        reg = self._resumen_regimen()
        vis_series = [self.series[i] for i in self._indices_visibles()]
        puntos = [pt for s in vis_series for pt in s.get("puntos", [])]
        causas = {pt.get("causa") for pt in puntos if pt.get("causa")}
        tipos = {pt.get("tipo_evento") for pt in puntos if pt.get("tipo_evento")}

        items = []
        if getattr(self, "mostrar_egl", True) and getattr(self, "mostrar_hgl", True):
            items.append(("cinetica", "■", "Cinética", "#0284c7", "#e0f2fe", "#bae6fd",
                          "Carga de velocidad (área sombreada entre EGL y HGL)"))
        if "friccion" in causas:
            items.append(("friccion", "●", "Fricción", "#e74c3c", "#fef2f2", "#fecaca",
                          "Pérdidas continuas por fricción (Darcy-Weisbach)"))
        if "accesorio" in causas:
            items.append(("accesorio", "●", "Accesorios", "#b45309", "#fffbeb", "#fde68a",
                          "Pérdidas localizadas en válvulas, codos y accesorios"))
        if "cambio_diametro" in causas:
            items.append(("cambio_diametro", "◆", "Cambio Ø (Δv²/2g)", "#6d28d9", "#f5f3ff", "#ddd6fe",
                          "Redistribución entre altura piezométrica y carga de velocidad al cambiar el diámetro"))
        if "borde" in causas:
            items.append(("entrada_salida", "●", "Entrada / Salida", "#0d9488", "#f0fdfa", "#99f6e4",
                          "Pérdidas por bordes de entrada y salida en tanques"))
        if reg["has_bomba"] or "bomba" in causas:
            items.append(("bomba", "▲", "Bomba (+H)", "#15803d", "#f0fdf4", "#bbf7d0",
                          "Energía aportada por la bomba al fluido"))
        if reg["hay_deficit"]:
            items.append(("deficit", "●", "Déficit", "#b91c1c", "#fef2f2", "#fecaca",
                          "Energía faltante respecto a la cota de descarga"))
        elif reg["hay_exceso"]:
            items.append(("exceso", "●", "Excedente", "#15803d", "#f0fdf4", "#bbf7d0",
                          "Energía disponible por encima de la cota de descarga"))
        return items

    @staticmethod
    def _anotaciones_eventos(serie):
        """Índice, evento original y texto: nunca deriva hf de las ordenadas."""
        perfil = serie.get('perfil')
        if perfil is None:
            return []
        anotaciones = []
        for indice,evento in enumerate(perfil.puntos):
            if not evento.etiqueta:
                continue
            if evento.tipo in ('entrada', 'salida', 'cambio de diámetro'):
                texto = evento.etiqueta
            elif evento.tipo == 'bomba':
                texto = f'{evento.etiqueta} — H = +{evento.H_bomba:.2f} m'
            else:
                hf = evento.perdida
                cantidad = ('hf < 0.01 m' if hf<0.01 else
                            f'hf = {hf:.2e} m' if hf>=1e5 else f'hf = {hf:.2f} m')
                texto = f'{evento.etiqueta} — {cantidad}'
            anotaciones.append((indice,evento,texto))
        return anotaciones

    @classmethod
    def _anotaciones_eventos_dibujo(cls, serie, multi_ruta=False):
        """Enriquece los rótulos de dibujo con nombres reales y longitudes de tubería si están disponibles."""
        anots = cls._anotaciones_eventos(serie)
        nombres_tramos = serie.get("nombres_tramos") or {}
        if not nombres_tramos and not multi_ruta:
            return anots
        pts = serie.get("puntos") or []
        salida = []
        for idx_pt, evento, texto in anots:
            nom_t = nombres_tramos.get(str(evento.tramo_id)) if evento.tramo_id is not None else None
            if evento.tipo == "tubería" and nom_t:
                hf = evento.perdida
                cantidad = (
                    "hf < 0.01 m" if hf < 0.01 else
                    f"hf = {hf:.2e} m" if hf >= 1e5 else f"hf = {hf:.2f} m"
                )
                ds = 0.0
                if 0 < idx_pt < len(pts):
                    ds = max(0.0, float(pts[idx_pt].get("x", 0.0)) - float(pts[idx_pt - 1].get("x", 0.0)))
                if multi_ruta and ds > 0.0:
                    texto = f"{nom_t} (L={ds:.0f} m) — {cantidad}"
                else:
                    texto = f"{nom_t}: Pérdida por fricción — {cantidad}"
            elif evento.tipo == "cambio de diámetro" and 0 < idx_pt < len(pts):
                v_prev = float(pts[idx_pt - 1].get("v", 0.0))
                v_curr = float(pts[idx_pt].get("v", 0.0))
                dv2 = abs(v_curr * v_curr - v_prev * v_prev) / (2.0 * 9.81)
                if dv2 >= 0.01:
                    texto = f"{texto} · Δ(v²/2g) = {dv2:.2f} m"
            salida.append((idx_pt, evento, texto))
        return salida

    def limpiar_datos(self):
        tenia = bool(self.series)
        self.series = []
        self.ruta_seleccionada = None
        self._colores_series = []
        self.resumen = {}
        self._ultimo_plot_rect = QRectF()
        self._reiniciar_viewport()
        self.setToolTip('')
        if hasattr(self, "hud_zoom_frame"):
            self.hud_zoom_frame.setVisible(False)
        if hasattr(self, "btn_ocultar_textos"):
            self.btn_ocultar_textos.setVisible(False)
        if hasattr(self, "btn_exportar"):
            self.btn_exportar.setVisible(False)
        if tenia:
            self.update()
        if callable(self.on_cambio_estado):
            self.on_cambio_estado(False)

    def actualizar_datos(self, series, resumen=None):
        self.series = [s for s in (series or []) if s.get("puntos")]
        self.ruta_seleccionada = None
        self._colores_series = self.resolver_colores_series(self.series)
        self._reiniciar_viewport()
        self.setToolTip('\n'.join(f"{s.get('nombre','Ruta')}: {s.get('mensaje',s['estado'])}"
            for s in self.series if s.get('estado','OK')!='OK'))
        if hasattr(self, "hud_zoom_frame"):
            self.hud_zoom_frame.setVisible(bool(self.series))
        if hasattr(self, "btn_ocultar_textos"):
            self.btn_ocultar_textos.setVisible(bool(self.series))
        if hasattr(self, "btn_exportar"):
            self.btn_exportar.setVisible(bool(self.series))
        if resumen is not None:
            self.resumen = dict(resumen)
        elif self.series and self.series[0].get('perfil') is not None:
            perfil = self.series[0]['perfil']
            self.resumen = dict(z1=perfil.H_inicio,z2=perfil.H_final,
                hf_total=perfil.hf_distribuida+perfil.hf_localizada,deficit=0.0,
                excedente=perfil.H_bombas)
        self.update()
        if callable(self.on_cambio_estado):
            self.on_cambio_estado(bool(self.series))

    def actualizar_perfil(self, perfil, *args, **kwargs):
        """Acepta únicamente un perfil calculado: no estima velocidades ni pérdidas."""
        from motor.resultados import PerfilRuta
        from motor.perfiles import perfil_como_serie
        if not isinstance(perfil,PerfilRuta):
            raise ValueError('Se requiere PerfilRuta calculado; los valores agregados no definen un perfil.')
        self.actualizar_datos([perfil_como_serie(perfil)])

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        self._dibujar_perfil(p, r, para_exportar=False)
        p.end()

    def _construir_mapa_x(self, plot, indices_vis, series_dib):
        """Mapea coordenadas x por serie; alinea estaciones extremas compartidas en modo didáctico."""
        todos_x = [float(pt.get("x", 0.0)) for i in indices_vis for pt in series_dib[i]]
        x_min = min(todos_x) if todos_x else 0.0
        x_max = max(todos_x) if todos_x else 100.0
        if x_max - x_min < 1e-6:
            x_max = x_min + 100.0

        def map_lineal(idx_s, xv):
            return plot.left() + ((xv - x_min) / (x_max - x_min)) * plot.width()

        if len(indices_vis) < 2 or self.mostrar_valores:
            return map_lineal, False, x_min, x_max

        origenes = {series_dib[i][0].get("etiqueta", "") for i in indices_vis if series_dib[i]}
        destinos = {series_dib[i][-1].get("etiqueta", "") for i in indices_vis if series_dib[i]}
        mismos_extremos = len(origenes) == 1 and len(destinos) == 1 and bool(next(iter(destinos), ""))
        if not mismos_extremos:
            return map_lineal, False, x_min, x_max

        # Prefijo compartido (ej. entrada común o tramo serie aguas arriba)
        min_len = min(len(series_dib[i]) for i in indices_vis)
        split_idx = 0
        for k in range(min_len):
            firmas = set()
            for i in indices_vis:
                pt = series_dib[i][k]
                perf = self.series[i].get("perfil")
                tr_id = perf.puntos[k].tramo_id if perf is not None and k < len(perf.puntos) else None
                firmas.add((
                    pt.get("tipo_evento"),
                    tr_id,
                    round(float(pt.get("x", 0.0)), 6),
                    round(float(pt.get("egl", 0.0)), 5),
                    pt.get("etiqueta", ""),
                ))
            if len(firmas) == 1:
                split_idx = k + 1
            else:
                break

        pts_ref = series_dib[indices_vis[0]]
        x0 = float(pts_ref[0].get("x", 0.0))
        x_split = float(pts_ref[max(0, split_idx - 1)].get("x", x0))

        # Sufijo compartido (ej. tramo serie aguas abajo después de reunión paralelo)
        x_suf_len = 0.0
        tramos_lists = [self.series[i].get("tramo_ids") or [] for i in indices_vis]
        if all(len(tl) >= 2 for tl in tramos_lists):
            suf_tramos = []
            max_tl = min(len(tl) for tl in tramos_lists)
            for back in range(1, max_tl):
                candidatos = {tl[-back] for tl in tramos_lists}
                if len(candidatos) == 1 and "" not in candidatos:
                    suf_tramos.append(next(iter(candidatos)))
                else:
                    break
            if suf_tramos:
                suf_set = set(suf_tramos)
                lens_suf = []
                for i in indices_vis:
                    perf = self.series[i].get("perfil")
                    pts_i = series_dib[i]
                    if perf is None:
                        continue
                    xs_join = [
                        float(pts_i[k].get("x", 0.0))
                        for k, pe in enumerate(perf.puntos)
                        if k < len(pts_i) and str(pe.tramo_id or "") in suf_set
                    ]
                    if xs_join:
                        lens_suf.append(max(0.0, float(pts_i[-1].get("x", 0.0)) - min(xs_join)))
                if len(lens_suf) == len(indices_vis) and max(lens_suf) - min(lens_suf) < 1e-4:
                    x_suf_len = min(lens_suf)

        l_ref = max(
            max(float(series_dib[i][-1].get("x", 0.0)) - float(series_dib[i][0].get("x", 0.0)), 1.0)
            for i in indices_vis
        )
        u_split = min(0.65, max(0.0, (x_split - x0) / l_ref))
        u_suf = min(0.65, max(0.0, x_suf_len / l_ref))
        u_join = max(u_split + 0.18, 1.0 - u_suf)

        span_por_serie = {}
        for i in indices_vis:
            pts_i = series_dib[i]
            xs_i = float(pts_i[0].get("x", 0.0))
            xe_i = float(pts_i[-1].get("x", 0.0))
            xj_i = max(xs_i + (x_split - x0), xe_i - x_suf_len)
            span_por_serie[i] = (xs_i, xj_i, xe_i)

        def map_normalizado(idx_s, xv):
            if idx_s not in span_por_serie:
                return map_lineal(idx_s, xv)
            xs_i, xj_i, xe_i = span_por_serie[idx_s]
            if u_split > 1e-6 and xv <= x_split + 1e-9:
                u = ((xv - xs_i) / max(x_split - xs_i, 1e-6)) * u_split
            elif u_suf > 1e-6 and xv >= xj_i - 1e-9:
                u = u_join + ((xv - xj_i) / max(xe_i - xj_i, 1e-6)) * (1.0 - u_join)
            else:
                u = u_split + ((xv - x_split) / max(xj_i - x_split, 1e-6)) * (u_join - u_split)
            return plot.left() + max(0.0, min(1.0, u)) * plot.width()

        return map_normalizado, True, 0.0, l_ref

    @staticmethod
    def _colocar_rect_sin_solape(plot, cx, cy, w_chip, h_chip, dy_pref, ocupados):
        """Busca la posición más cercana al punto (cx, cy) sin solapar otros rótulos."""
        if (
            cx < plot.left() - 24.0
            or cx > plot.right() + 24.0
            or cy < plot.top() - 24.0
            or cy > plot.bottom() + 24.0
        ):
            return None
        lim = plot.adjusted(4.0, 4.0, -4.0, -4.0)
        dy_cands = [dy_pref, -dy_pref, dy_pref * 2.1, -dy_pref * 2.1, dy_pref * 3.3, -dy_pref * 3.3]
        dx_cands = [0.0, -56.0, 56.0, -112.0, 112.0]
        for dy in dy_cands:
            for dx in dx_cands:
                x_left = max(lim.left(), min(lim.right() - w_chip, cx + dx - w_chip / 2.0))
                y_top = max(lim.top(), min(lim.bottom() - h_chip, cy + dy - h_chip / 2.0))
                cand = QRectF(x_left, y_top, w_chip, h_chip)
                if not any(cand.intersects(prev.adjusted(-3.0, -2.0, 3.0, 2.0)) for prev in ocupados):
                    return cand
        return None

    def _dibujar_estaciones_eje_x(
        self, p, r, plot, indices_vis, series_dib, map_x_s, normalizado, rango_x=None
    ):
        """Dibuja marcas y rótulos de estaciones en X deduplicando nodos convergentes."""
        candidatas = []
        multi = len(indices_vis) > 1
        for idx_s in indices_vis:
            s = self.series[idx_s]
            nom_r = s.get("nombre", f"Ruta {idx_s + 1}")
            for pt in series_dib[idx_s]:
                if pt.get("tipo_evento") == "borde":
                    continue
                etq = pt.get("etiqueta", "")
                if not etq:
                    continue
                xv = float(pt.get("x", 0.0))
                x_px = map_x_s(idx_s, xv)
                sub_etq = pt.get("sub_etiqueta", "")
                if not sub_etq and self.mostrar_valores and not normalizado:
                    if multi and pt.get("tipo_evento") == "salida":
                        sub_etq = f"{nom_r} · {xv:.0f} m"
                    else:
                        sub_etq = f"{xv:.0f} m"
                candidatas.append((x_px, etq, sub_etq, pt.get("tipo_evento"), nom_r, xv))

        filtradas = []
        for x_px, etq, sub_etq, tipo_ev, nom_r, xv in candidatas:
            duplicada = any(
                abs(x_px - ex) < 48.0 and e0 == etq
                for ex, e0, _, _, _, _ in filtradas
            )
            if duplicada:
                continue
            muy_cerca_misma = any(
                abs(x_px - ex) < 12.0 and e0 == etq
                for ex, e0, _, _, _, _ in filtradas
            )
            if not muy_cerca_misma:
                filtradas.append((x_px, etq, sub_etq, tipo_ev, nom_r, xv))

        font_est = QFont("Inter", 8)
        font_est.setBold(True)
        font_sub_est = QFont("Inter", 7)
        fm_est = QtGui.QFontMetrics(font_est)
        fm_sub = QtGui.QFontMetrics(font_sub_est)
        pen_est_line = QPen(QColor("#cbdbf5"), 1.0, Qt.SolidLine)
        self._estaciones_rects = []
        filas_ocupadas = [[], []]
        dibujadas_r0 = []
        pendientes_sub = []
        for x_px, etq, sub_etq, tipo_ev, nom_r, xv in filtradas:
            if x_px < plot.left() - 2.0 or x_px > plot.right() + 2.0:
                continue
            p.setPen(pen_est_line)
            p.drawLine(QPointF(x_px, plot.top()), QPointF(x_px, plot.bottom()))
            w_etq = float(fm_est.horizontalAdvance(str(etq)))
            ancho_etq = max(96.0, w_etq + 18.0)
            margen_lat = 10.0
            x_caja = max(
                r.left() + margen_lat,
                min(r.right() - ancho_etq - margen_lat, x_px - ancho_etq / 2.0),
            )
            rect_r0 = QRectF(x_caja, plot.bottom() + 6.0, ancho_etq, 18.0)
            etq_dib = etq
            fila_idx = 0
            choques_r0 = [
                (e0, prev) for e0, prev in dibujadas_r0
                if rect_r0.intersects(prev.adjusted(-4, 0, 4, 0))
            ]
            if choques_r0:
                if multi and self.mostrar_valores and not normalizado and tipo_ev == "salida":
                    misma_etq = any(e0 == etq for e0, _ in choques_r0)
                    etq_dib = f"{xv:.0f} m" if misma_etq else f"{etq} · {xv:.0f} m"
                    w_alt = float(fm_est.horizontalAdvance(etq_dib)) + (12.0 if misma_etq else 14.0)
                    ancho_etq = w_alt if misma_etq else max(ancho_etq, w_alt)
                    x_caja = max(
                        r.left() + margen_lat,
                        min(r.right() - ancho_etq - margen_lat, x_px - ancho_etq / 2.0),
                    )
                rect_r1 = QRectF(x_caja, plot.bottom() + 26.0, ancho_etq, 16.0)
                if not any(rect_r1.intersects(prev.adjusted(-4, 0, 4, 0)) for prev in filas_ocupadas[1]):
                    fila_idx = 1
                    rect_etq = rect_r1
                else:
                    continue
            else:
                rect_etq = rect_r0
                dibujadas_r0.append((etq, rect_etq))

            filas_ocupadas[fila_idx].append(rect_etq)
            self._estaciones_rects.append((etq_dib, rect_etq))
            p.setFont(font_est)
            p.setPen(QColor("#41474e"))
            p.drawText(rect_etq, Qt.AlignHCenter | Qt.AlignVCenter, etq_dib)
            if sub_etq and fila_idx == 0:
                w_sub = float(fm_sub.horizontalAdvance(str(sub_etq))) + 14.0
                xs_c = max(
                    r.left() + margen_lat,
                    min(r.right() - w_sub - margen_lat, x_px - w_sub / 2.0),
                )
                pendientes_sub.append(
                    (QRectF(xs_c, plot.bottom() + 24.0, w_sub, 16.0), sub_etq, x_px, xv)
                )

        for rect_sub, sub_etq, x_sub, xv_sub in pendientes_sub:
            dibujar_sub = None
            if not any(rect_sub.intersects(prev.adjusted(-4, 0, 4, 0)) for prev in filas_ocupadas[1]):
                dibujar_sub = (rect_sub, sub_etq)
            else:
                sub_corto = f"{xv_sub:.0f} m"
                w_c = float(fm_sub.horizontalAdvance(sub_corto)) + 12.0
                xs_corto = max(
                    r.left() + margen_lat,
                    min(r.right() - w_c - margen_lat, x_sub - w_c / 2.0),
                )
                rect_corto = QRectF(xs_corto, plot.bottom() + 24.0, w_c, 16.0)
                chocando = [
                    prev for prev in filas_ocupadas[1]
                    if rect_corto.intersects(prev.adjusted(-4, 0, 4, 0))
                ]
                if not chocando:
                    dibujar_sub = (rect_corto, sub_corto)
                else:
                    # Desplazar levemente a la izquierda si una etiqueta rotulada ocupa el lado derecho
                    xs_nudge = min(xs_corto, chocando[0].left() - w_c - 6.0)
                    if xs_nudge >= r.left() + margen_lat and abs(xs_nudge - xs_corto) <= 48.0:
                        rect_nudge = QRectF(xs_nudge, plot.bottom() + 24.0, w_c, 16.0)
                        if not any(rect_nudge.intersects(prev.adjusted(-4, 0, 4, 0)) for prev in filas_ocupadas[1]):
                            dibujar_sub = (rect_nudge, sub_corto)
            if dibujar_sub is not None:
                rect_ok, txt_ok = dibujar_sub
                filas_ocupadas[1].append(rect_ok)
                p.setFont(font_sub_est)
                p.setPen(QColor("#72787f"))
                p.drawText(rect_ok, Qt.AlignHCenter | Qt.AlignVCenter, txt_ok)

        if rango_x is not None and not normalizado:
            x_v0, x_v1 = rango_x
            span_xv = max(abs(x_v1 - x_v0), 1e-6)
            dec_x = 3 if span_xv < 0.25 else (2 if span_xv < 10.0 else 1)
            font_x_tick = QFont("Consolas", 7)
            fm_xt = QtGui.QFontMetrics(font_x_tick)
            pen_x_grid = QPen(QColor("#dbeafe"), 0.9, Qt.DashLine)
            pen_x_tick = QPen(QColor("#475569"), 1.2)
            for frac_x in (0.0, 0.25, 0.5, 0.75, 1.0):
                x_px = plot.left() + frac_x * plot.width()
                val_x = x_v0 + frac_x * (x_v1 - x_v0)
                if 0.0 < frac_x < 1.0:
                    p.setPen(pen_x_grid)
                    p.drawLine(QPointF(x_px, plot.top()), QPointF(x_px, plot.bottom()))
                p.setPen(pen_x_tick)
                p.drawLine(QPointF(x_px, plot.bottom()), QPointF(x_px, plot.bottom() + 4.0))
                txt_x = f"{val_x:.{dec_x}f} m"
                w_tx = float(fm_xt.horizontalAdvance(txt_x)) + 10.0
                rx = max(
                    r.left() + 8.0,
                    min(r.right() - w_tx - 8.0, x_px - w_tx / 2.0),
                )
                rect_xt = QRectF(rx, plot.bottom() + 26.0, w_tx, 16.0)
                if not any(
                    rect_xt.intersects(prev.adjusted(-6.0, -2.0, 6.0, 2.0))
                    for prev in filas_ocupadas[1]
                ):
                    filas_ocupadas[1].append(rect_xt)
                    p.setFont(font_x_tick)
                    p.setPen(QColor("#475569"))
                    p.drawText(rect_xt, Qt.AlignCenter, txt_x)

    def _dibujar_perfil(self, p, r, para_exportar=False):
        if para_exportar:
            # Fondo blanco sólido para informes / Word / PowerPoint
            p.fillRect(r, QColor("#ffffff"))
            p.setPen(QPen(QColor("#cbd5e1"), 1.0))
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(r, 6, 6)
        else:
            # Contenedor interior estilo Stitch (surface-bright #f8f9ff con borde #e5eeff)
            p.setPen(QPen(QColor("#e5eeff"), 1.2))
            p.setBrush(QColor("#f8f9ff"))
            p.drawRoundedRect(r, 10, 10)

        if not self.series:
            font_empty = QFont("Inter", 10)
            font_empty.setWeight(QFont.DemiBold)
            p.setFont(font_empty)
            p.setPen(QColor("#72787f"))
            p.drawText(
                r,
                Qt.AlignCenter,
                "Gráfico EGL / HGL no generado",
            )
            return

        indices_vis = self._indices_visibles()
        idx_base = indices_vis[0]
        multi_ruta = len(indices_vis) > 1
        series_dib = self._series_para_dibujar()
        ocultar_textos = bool(getattr(self, "ocultar_textos", False))

        plot = self._calcular_rect_plot(r, para_exportar=para_exportar)
        left_pad = plot.left() - r.left()
        if not para_exportar:
            self._ultimo_plot_rect = QRectF(plot)

        # Fondo y cuadrícula técnica milimetrada estilo Stitch
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f8f9ff"))
        p.drawRoundedRect(plot, 4, 4)

        pen_grid_minor = QPen(QColor(220, 233, 255, 130), 0.7, Qt.SolidLine)
        p.setPen(pen_grid_minor)
        gx = plot.left() + 25.0
        while gx < plot.right():
            p.drawLine(QPointF(gx, plot.top()), QPointF(gx, plot.bottom()))
            gx += 25.0
        gy = plot.top() + 20.0
        while gy < plot.bottom():
            p.drawLine(QPointF(plot.left(), gy), QPointF(plot.right(), gy))
            gy += 20.0

        map_x_base, normalizado_paralelo, x_min_dom, x_max_dom = self._construir_mapa_x(
            plot, indices_vis, series_dib
        )
        vx0, vx1, vy0, vy1 = self._vx0, self._vx1, self._vy0, self._vy1
        span_vx = max(self._ZOOM_MIN_SPAN, vx1 - vx0)
        esta_zoomed = self._esta_zoomed()
        if esta_zoomed:
            def map_x_s(idx_s, xv):
                x_base = map_x_base(idx_s, xv)
                u_base = (x_base - plot.left()) / plot.width()
                return plot.left() + ((u_base - vx0) / span_vx) * plot.width()
        else:
            map_x_s = map_x_base

        x_vis_min = x_min_dom + vx0 * (x_max_dom - x_min_dom)
        x_vis_max = x_min_dom + vx1 * (x_max_dom - x_min_dom)

        # 4.2 Escala anclada a los tanques
        reg = self._resumen_regimen()
        z1_raw = reg["z1_raw"]
        z2_raw = reg["z2_raw"]
        Z1 = reg["Z1"]
        Z2 = reg["Z2"]
        deficit = reg["deficit"]
        hf_total = reg["hf_total"]
        delta_z = reg["delta_z"]
        exc_resumen = reg["exc_resumen"]
        dz_energia = reg["dz_energia"]
        has_bomba = reg["has_bomba"]
        hay_deficit = reg["hay_deficit"]
        hay_exceso = reg["hay_exceso"]
        nivel_t1 = reg["nivel_t1"]
        nivel_t2 = reg["nivel_t2"]

        todos_egl_vals = [float(pt.get("egl", 0.0)) for i in indices_vis for pt in series_dib[i]]
        todos_hgl_vals = [float(pt.get("hgl", 0.0)) for i in indices_vis for pt in series_dib[i]]
        todos_y_vals = [nivel_t1, nivel_t2] + todos_egl_vals + todos_hgl_vals
        val_max_y = max(todos_y_vals) if todos_y_vals else max(nivel_t1, nivel_t2)
        val_min_y = min(todos_y_vals) if todos_y_vals else min(nivel_t1, nivel_t2)
        span_y = max(val_max_y - val_min_y, 1.0)

        if has_bomba:
            y_top = val_max_y + 0.15 * span_y
            y_bot = val_min_y - 0.15 * span_y
        else:
            delta_z_ref = max(abs(nivel_t1 - nivel_t2), span_y, 1.0)
            y_top = max(nivel_t1, nivel_t2, val_max_y) + 0.15 * delta_z_ref
            if hay_deficit:
                y_bot = min(nivel_t1, nivel_t2, val_min_y) - 0.45 * max(abs(nivel_t1 - nivel_t2), 1.0)
            else:
                y_bot = min(nivel_t1, nivel_t2, val_min_y) - 0.12 * delta_z_ref

        if y_top - y_bot < 1e-6:
            y_top = y_bot + 10.0

        span_y_total = y_top - y_bot
        y_vis_bot = y_bot + vy0 * span_y_total
        y_vis_top = y_bot + vy1 * span_y_total
        span_vis_y = max(y_vis_top - y_vis_bot, 1e-6)

        def map_y(yv):
            return plot.bottom() - ((yv - y_vis_bot) / span_vis_y) * plot.height()

        x_corte_didactico = None

        # Títulos de ejes estilo Stitch
        font_axis_title = QFont("Inter", 9)
        font_axis_title.setBold(True)
        p.setFont(font_axis_title)
        p.setPen(QColor("#0c4e77"))
        if para_exportar:
            font_main_tit = QFont("Inter", 12, QFont.Bold)
            p.setFont(font_main_tit)
            p.setPen(QColor("#0c4e77"))
            p.drawText(
                QRectF(r.left() + 20, r.top() + 12, 380, 24),
                Qt.AlignLeft | Qt.AlignVCenter,
                "Líneas de Energía (EGL / HGL)",
            )
            font_sub = QFont("Inter", 8)
            p.setFont(font_sub)
            p.setPen(QColor("#64748b"))
            p.drawText(
                QRectF(r.left() + 20, r.top() + 36, 440, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                "Perfil hidráulico longitudinal de energía total y cota piezométrica",
            )
            self._dibujar_leyenda_perfil(p, r, hay_deficit, hay_exceso, indices_vis)

            p.setFont(font_axis_title)
            p.setPen(QColor("#0c4e77"))
            p.drawText(
                QRectF(r.left() + 18, plot.top() - 20, left_pad + 80, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                "Altura / Cota Hidráulica [m]",
            )
        else:
            p.drawText(
                QRectF(r.left() + 18, r.top() + 10, 260, 20),
                Qt.AlignLeft | Qt.AlignVCenter,
                "Altura / Cota Hidráulica [m]",
            )

        p.setFont(font_axis_title)
        p.setPen(QColor("#0c4e77"))
        p.drawText(
            QRectF(plot.right() - 280, plot.bottom() + 48, 280, 18),
            Qt.AlignRight | Qt.AlignVCenter,
            "Estaciones del Sistema Hidráulico",
        )

        # 1. Líneas horizontales de cota + Plano de Referencia (Datum)
        pen_grid_h = QPen(QColor("#cbdbf5"), 1.0, Qt.DashLine)
        font_axis = QFont("Consolas", 8)
        n_lineas_y = 4
        ys_dibujadas = []
        dec_y = 3 if span_vis_y < 0.25 else (2 if (esta_zoomed or span_vis_y < 5.0) else 1)
        datum_en_vista = False
        for idx_y in range(n_lineas_y + 1):
            frac = idx_y / n_lineas_y
            val_y = y_vis_top - frac * span_vis_y
            y_px = plot.top() + frac * plot.height()
            tol_datum = max(0.02, 0.02 * span_vis_y) if esta_zoomed else 0.08
            es_datum = abs(val_y) < tol_datum or (
                not esta_zoomed and idx_y == n_lineas_y and not hay_deficit
            )
            if abs(val_y) < tol_datum:
                datum_en_vista = True
            p.setPen(QPen(QColor("#72787f"), 1.4, Qt.DashLine) if es_datum else pen_grid_h)
            p.drawLine(QPointF(plot.left() - 4, y_px), QPointF(plot.right(), y_px))

            if (self.mostrar_valores or es_datum or esta_zoomed) and not (
                x_corte_didactico is not None and val_y < -0.05
            ):
                p.setFont(font_axis)
                p.setPen(QColor("#72787f") if es_datum else QColor("#41474e"))
                if es_datum and abs(val_y) < (0.04 if esta_zoomed else 0.15):
                    etiqueta_cota = "0.0 m (Datum)"
                elif es_datum:
                    etiqueta_cota = (
                        f"{val_y:.{dec_y}f} m"
                        if (self.mostrar_valores or esta_zoomed)
                        else "Datum (Ref.)"
                    )
                else:
                    etiqueta_cota = f"{val_y:.{dec_y}f} m"
                p.drawText(
                    QRectF(r.left() + 4, y_px - 8, left_pad - 12, 16),
                    Qt.AlignRight | Qt.AlignVCenter,
                    etiqueta_cota,
                )
                ys_dibujadas.append(y_px)

        if esta_zoomed and not datum_en_vista and y_vis_bot < 0.0 < y_vis_top:
            y_dat = map_y(0.0)
            p.setPen(QPen(QColor("#72787f"), 1.4, Qt.DashLine))
            p.drawLine(QPointF(plot.left() - 4, y_dat), QPointF(plot.right(), y_dat))
            if not any(abs(y_dat - yp) < 12 for yp in ys_dibujadas):
                p.setFont(font_axis)
                p.setPen(QColor("#72787f"))
                p.drawText(
                    QRectF(r.left() + 4, y_dat - 8, left_pad - 12, 16),
                    Qt.AlignRight | Qt.AlignVCenter,
                    "0.0 m (Datum)",
                )
                ys_dibujadas.append(y_dat)

        # Cotas z₁ y z₂ en el eje vertical cuando Mostrar valores está activo
        if self.mostrar_valores:
            font_z_axis = QFont("Consolas", 8)
            font_z_axis.setBold(True)
            p.setFont(font_z_axis)
            dec_z = dec_y if esta_zoomed else 1
            for z_val, suf_z, col_z in (
                (Z1, "z₁", "#0c4e77"),
                (Z2, "z₂", "#006398"),
            ):
                yz = map_y(float(z_val))
                if plot.top() - 2 <= yz <= plot.bottom() + 2:
                    p.setPen(QPen(QColor(col_z), 1.2, Qt.DashLine))
                    p.drawLine(QPointF(plot.left() - 4, yz), QPointF(plot.right(), yz))
                    y_txt = yz
                    for y_prev in ys_dibujadas:
                        if abs(y_txt - y_prev) < 12:
                            y_txt = y_prev - 12 if y_txt <= y_prev else y_prev + 12
                    ys_dibujadas.append(y_txt)
                    p.setPen(QColor(col_z))
                    p.drawText(
                        QRectF(r.left() + 2, y_txt - 8, left_pad - 10, 16),
                        Qt.AlignRight | Qt.AlignVCenter,
                        f"{float(z_val):.{dec_z}f} m ({suf_z})",
                    )

        # 4.3 Déficit de energía (cuando las pérdidas superan el desnivel disponible)
        pts_prim = series_dib[idx_base] if series_dib else []
        x_cruce_def_px = None
        x_corte_px = None

        if hay_deficit and not has_bomba:
            y_t2_px = map_y(Z2)
            # Línea horizontal punteada fina en el nivel del Tanque 2, rotulada "Nivel Tanque 2"
            if plot.top() - 1.0 <= y_t2_px <= plot.bottom() + 1.0:
                p.setPen(QPen(QColor("#94a3b8"), 1.2, Qt.DashLine))
                p.drawLine(QPointF(plot.left(), y_t2_px), QPointF(plot.right(), y_t2_px))

                if not ocultar_textos:
                    p.setFont(QFont("Inter", 8, QFont.Bold))
                    p.setPen(QColor("#64748b"))
                    p.drawText(
                        QRectF(plot.left() + 8, max(plot.top() + 2, y_t2_px - 16), 140, 14),
                        Qt.AlignLeft | Qt.AlignVCenter,
                        "Nivel Tanque 2",
                    )

            # Buscar cruce donde la EGL cae por debajo de Z2
            x_cruce = None
            for i in range(len(pts_prim) - 1):
                e1 = float(pts_prim[i].get("egl", 0.0))
                e2 = float(pts_prim[i + 1].get("egl", 0.0))
                x1 = float(pts_prim[i].get("x", 0.0))
                x2 = float(pts_prim[i + 1].get("x", 0.0))
                if e1 >= Z2 and e2 < Z2:
                    frac = (e1 - Z2) / (e1 - e2) if abs(e2 - e1) > 1e-9 else 0.0
                    x_cruce = x1 + frac * (x2 - x1)
                    break
                elif e1 < Z2 and e2 < Z2 and x_cruce is None:
                    x_cruce = x1
                    break

            if x_cruce is None and pts_prim and float(pts_prim[0].get("egl", 0.0)) < Z2:
                x_cruce = float(pts_prim[0].get("x", 0.0))

            if x_cruce is not None and getattr(self, "mostrar_egl", True):
                x_cruce_def_px = max(plot.left(), map_x_s(idx_base, x_cruce))
                h_som = plot.bottom() - y_t2_px
                w_som = plot.right() - x_cruce_def_px
                if h_som > 1.0 and w_som > 1.0:
                    rect_som = QRectF(x_cruce_def_px, y_t2_px, w_som, h_som).intersected(plot)
                    if not rect_som.isEmpty():
                        p.fillRect(rect_som, QColor(239, 68, 68, 38))

            # Buscar corte donde la EGL sale por el borde inferior (y_vis_bot)
            for i in range(len(pts_prim) - 1):
                e1 = float(pts_prim[i].get("egl", 0.0))
                e2 = float(pts_prim[i + 1].get("egl", 0.0))
                x1 = float(pts_prim[i].get("x", 0.0))
                x2 = float(pts_prim[i + 1].get("x", 0.0))
                if e1 >= y_vis_bot and e2 < y_vis_bot:
                    frac = (e1 - y_vis_bot) / (e1 - e2) if abs(e2 - e1) > 1e-9 else 0.0
                    x_corte = x1 + frac * (x2 - x1)
                    x_corte_px = map_x_s(idx_base, x_corte)
                    break
            if x_corte_didactico is not None:
                x_corte_px = map_x_s(idx_base, x_corte_didactico)

        # 4.3b Exceso de energía (hf < ΔZ): nivel del Tanque 2 + banda verde entre la EGL y ese nivel
        info_exceso = None
        if hay_exceso and not has_bomba:
            pts_e = series_dib[idx_base]
            y_t2_px = map_y(nivel_t2)
            if plot.top() - 1.0 <= y_t2_px <= plot.bottom() + 1.0:
                p.setPen(QPen(QColor("#94a3b8"), 1.2, Qt.DashLine))
                p.drawLine(QPointF(plot.left(), y_t2_px), QPointF(plot.right(), y_t2_px))

            if getattr(self, "mostrar_egl", True):
                i_ent = next((i for i, pt in enumerate(pts_e) if pt.get("etiqueta") == "Entrada"), 0)
                i_sal_e = next(
                    (i for i, pt in enumerate(pts_e) if pt.get("causa") == "salida"), len(pts_e) - 1
                )
                if i_sal_e <= i_ent:
                    i_ent, i_sal_e = 0, len(pts_e) - 1
                tramo_e = pts_e[i_ent:i_sal_e + 1]

                borde_sup = [
                    QPointF(map_x_s(idx_base, float(pt["x"])), map_y(max(float(pt["egl"]), nivel_t2)))
                    for pt in tramo_e
                ]
                x_max_vis = max(
                    map_x_s(i_v, float(series_dib[i_v][-1]["x"]))
                    for i_v in indices_vis
                    if series_dib[i_v]
                )
                if x_max_vis > borde_sup[-1].x() + 1.0:
                    borde_sup.append(QPointF(x_max_vis, borde_sup[-1].y()))
                x_a = borde_sup[0].x()
                x_b = borde_sup[-1].x()
                poligono_exc = QPolygonF(borde_sup + [QPointF(x_b, y_t2_px), QPointF(x_a, y_t2_px)])
                p.save()
                p.setClipRect(plot)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(22, 163, 74, 46))      # #16a34a con baja opacidad
                p.drawPolygon(poligono_exc)
                p.restore()

                # EGL (px) en el centro de la banda, para ubicar el rótulo dentro de ella
                x_c_exc = (x_a + x_b) / 2.0
                y_egl_c = borde_sup[-1].y()
                for k in range(len(borde_sup) - 1):
                    xa_k, xb_k = borde_sup[k].x(), borde_sup[k + 1].x()
                    if xb_k - xa_k > 1e-9 and xa_k <= x_c_exc <= xb_k:
                        y_egl_c = borde_sup[k].y() + (borde_sup[k + 1].y() - borde_sup[k].y()) * (
                            (x_c_exc - xa_k) / (xb_k - xa_k)
                        )
                        break
                info_exceso = {"x_c": x_c_exc, "y_egl_c": y_egl_c, "y_t2": y_t2_px}

        # Ejes principales (izquierdo y base) como en Stitch (#213145)
        pen_axes = QPen(QColor("#213145"), 2.0)
        p.setPen(pen_axes)
        p.drawLine(QPointF(plot.left(), plot.top()), QPointF(plot.left(), plot.bottom()))
        p.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))

        # 2. Estaciones en el eje horizontal
        self._dibujar_estaciones_eje_x(
            p,
            r,
            plot,
            indices_vis,
            series_dib,
            map_x_s,
            normalizado_paralelo,
            rango_x=(x_vis_min, x_vis_max) if (esta_zoomed and not normalizado_paralelo) else None,
        )

        # 3. Trazado por serie (recortado al área de dibujo con pendiente real y colores diferenciados)
        chips_dibujados = []
        entradas_dibujadas = []
        tramos_etiquetados = set()
        n_vis = len(indices_vis)
        es_solo_una = (len(self.series) == 1)

        info_esq = None
        if not ocultar_textos and self.series and (
            (para_exportar and not self.mostrar_valores)
            or (not para_exportar and normalizado_paralelo)
        ):
            txt_esq = (
                "Eje X alineado por estaciones"
                if normalizado_paralelo
                else "Esquemático — no a escala"
            )
            font_esq = QFont("Inter", 8)
            font_esq.setBold(True)
            fm_esq = QtGui.QFontMetrics(font_esq)
            w_esq = fm_esq.horizontalAdvance(txt_esq) + 14.0
            h_esq = 18.0
            rect_esq = QRectF(plot.right() - w_esq - 6.0, plot.top() + 6.0, w_esq, h_esq)
            chips_dibujados.append(rect_esq)
            info_esq = (rect_esq, font_esq, txt_esq)

        for pos_vis, idx_s in enumerate(indices_vis):
            s = self.series[idx_s]
            pts = series_dib[idx_s]
            if len(pts) < 2:
                continue
            pts_egl = [QPointF(map_x_s(idx_s, float(pt["x"])), map_y(float(pt["egl"]))) for pt in pts]
            pts_hgl = [QPointF(map_x_s(idx_s, float(pt["x"])), map_y(float(pt["hgl"]))) for pt in pts]

            col_egl = QColor("#e74c3c" if es_solo_una else self.color_serie(idx_s))
            if es_solo_una or not multi_ruta:
                col_hgl = QColor("#2980b9")
            else:
                col_hgl = QColor(col_egl).darker(115)
                col_hgl.setAlpha(185)

            p.save()
            p.setClipRect(plot.adjusted(-7.0, -5.0, 7.0, 5.0))

            # Área entre EGL y HGL (carga cinética v²/2g)
            if getattr(self, "mostrar_egl", True) and getattr(self, "mostrar_hgl", True):
                poly_area = QPolygonF(pts_egl + list(reversed(pts_hgl)))
                grad_area = QtGui.QLinearGradient(0, plot.top(), 0, plot.bottom())
                if multi_ruta:
                    c_sup = QColor(col_egl)
                    c_sup.setAlpha(38)
                    c_inf = QColor(col_egl)
                    c_inf.setAlpha(14)
                else:
                    c_sup = QColor(56, 189, 248, 88)
                    c_inf = QColor(56, 189, 248, 38)
                grad_area.setColorAt(0.0, c_sup)
                grad_area.setColorAt(1.0, c_inf)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(grad_area))
                p.drawPolygon(poly_area)

            # 1. Línea Piezométrica (HGL)
            if getattr(self, "mostrar_hgl", True):
                pen_hgl = QPen(col_hgl, 3.2 if multi_ruta else 3.8, Qt.DashLine)
                pen_hgl.setCapStyle(Qt.RoundCap)
                pen_hgl.setJoinStyle(Qt.RoundJoin)
                p.setPen(pen_hgl)
                p.setBrush(Qt.NoBrush)
                p.drawPolyline(QPolygonF(pts_hgl))

            # 2. Línea de Energía con velocidad (EGL)
            if getattr(self, "mostrar_egl", True):
                ancho_egl = max(3.2, 5.4 - 1.8 * pos_vis) if multi_ruta else 4.2
                pen_egl = QPen(col_egl, ancho_egl, Qt.SolidLine)
                pen_egl.setCapStyle(Qt.RoundCap)
                pen_egl.setJoinStyle(Qt.RoundJoin)
                p.setPen(pen_egl)
                p.setBrush(Qt.NoBrush)
                p.drawPolyline(QPolygonF(pts_egl))

                # Salto vertical de bomba, accesorios, bordes y cambio de diámetro
                for idx_pt in range(1, len(pts)):
                    pt_curr = pts[idx_pt]
                    causa = pt_curr.get("causa")
                    hf_tr = pt_curr.get("hf_tramo")
                    p1 = pts_egl[idx_pt - 1]
                    p2 = pts_egl[idx_pt]

                    if causa == "bomba":
                        pen_bomba = QPen(QColor("#16a34a"), 5.2, Qt.SolidLine)
                        pen_bomba.setCapStyle(Qt.RoundCap)
                        p.setPen(pen_bomba)
                        p.drawLine(p1, p2)

                        tam_flecha = 9.5
                        punta = p2
                        poly_flecha = QPolygonF([
                            punta,
                            QPointF(punta.x() - tam_flecha * 0.55, punta.y() + tam_flecha),
                            QPointF(punta.x() + tam_flecha * 0.55, punta.y() + tam_flecha),
                        ])
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor("#16a34a"))
                        p.drawPolygon(poly_flecha)
                    elif causa in ("accesorio", "borde") and hf_tr is not None and hf_tr > 1e-6:
                        alt_px = abs(p2.y() - p1.y())
                        if alt_px < 12.0:
                            cy_acc = (p1.y() + p2.y()) / 2.0
                            y1_acc = cy_acc - 6.0
                            y2_acc = cy_acc + 6.0
                        else:
                            y1_acc = min(p1.y(), p2.y())
                            y2_acc = max(p1.y(), p2.y())

                        col_caida = QColor(self.COLORES_CAUSA.get(causa, "#f59e0b"))
                        pen_acc = QPen(col_caida, 5.5, Qt.SolidLine)
                        pen_acc.setCapStyle(Qt.RoundCap)
                        p.setPen(pen_acc)
                        p.drawLine(QPointF(p2.x(), y1_acc), QPointF(p2.x(), y2_acc))

                        p.setPen(QPen(QColor("#ffffff"), 1.8))
                        p.setBrush(col_caida)
                        p.drawEllipse(QPointF(p2.x(), (y1_acc + y2_acc) / 2.0), 5.2, 5.2)
                    elif causa == "cambio_diametro" and getattr(self, "mostrar_hgl", True):
                        p_h1 = pts_hgl[idx_pt - 1]
                        p_h2 = pts_hgl[idx_pt]
                        if abs(p_h2.y() - p_h1.y()) > 1.5:
                            pen_cd = QPen(QColor("#7c3aed"), 2.0, Qt.DotLine)
                            p.setPen(pen_cd)
                            p.drawLine(p_h1, p_h2)
                            p.setPen(QPen(QColor("#ffffff"), 1.2))
                            p.setBrush(QColor("#7c3aed"))
                            p.drawRect(QRectF(p_h2.x() - 3.5, (p_h1.y() + p_h2.y()) / 2.0 - 3.5, 7.0, 7.0))

            p.restore()

            if getattr(self, "mostrar_egl", True):
                if not ocultar_textos:
                    for idx_pt, evento, texto_chip in self._anotaciones_eventos_dibujo(s, multi_ruta=multi_ruta):
                        if evento.tipo == "salida":
                            continue
                        pt_curr = pts[idx_pt]
                        p1 = pts_egl[max(0, idx_pt - 1)]
                        p2 = pts_egl[idx_pt]
                        causa = evento.tipo if evento.tipo in ("entrada", "salida") else pt_curr.get("causa")

                        if causa == "entrada":
                            duplicada_ent = any(
                                abs(p2.x() - ex) < 8.0 and abs(p2.y() - ey) < 6.0 and et == texto_chip
                                for ex, ey, et in entradas_dibujadas
                            )
                            if duplicada_ent:
                                continue
                            entradas_dibujadas.append((p2.x(), p2.y(), texto_chip))

                        clave_seg = (
                            evento.tipo,
                            str(evento.tramo_id),
                            round(p1.x(), 1),
                            round(p1.y(), 1),
                            round(p2.x(), 1),
                            round(p2.y(), 1),
                            texto_chip,
                        )
                        if multi_ruta and evento.tipo != "entrada" and clave_seg in tramos_etiquetados:
                            continue
                        tramos_etiquetados.add(clave_seg)

                        if multi_ruta and causa in ("friccion",):
                            col_seg = QColor(col_egl)
                        else:
                            col_seg = QColor(self.COLORES_CAUSA.get(causa, "#0284c7"))

                        font_chip = QFont("Inter", 7)
                        font_chip.setBold(True)
                        fm_chip = QtGui.QFontMetrics(font_chip)
                        w_chip = max(64.0, fm_chip.horizontalAdvance(texto_chip) + 14.0)
                        h_chip = 18.0

                        if multi_ruta and causa == "friccion" and abs(p2.x() - p1.x()) > 40.0:
                            frac_x = 0.30 + 0.40 * (pos_vis / max(1, n_vis - 1))
                            cx = p1.x() + frac_x * (p2.x() - p1.x())
                            cy_raw = p1.y() + frac_x * (p2.y() - p1.y())
                            offset_y = -20.0 if pos_vis % 2 == 0 else 22.0
                        elif causa == "bomba":
                            cx = min(plot.right() - w_chip / 2.0 - 6.0, p2.x() + w_chip / 2.0 + 10.0)
                            cy_raw = (p1.y() + p2.y()) / 2.0
                            offset_y = 0.0
                        else:
                            cx = (p1.x() + p2.x()) / 2.0
                            cy_raw = (p1.y() + p2.y()) / 2.0
                            offset_y = -18.0 if causa == "friccion" else (
                                14.0 if causa in ("entrada", "salida") else -24.0
                            )
                        cy = min(plot.bottom() - 10.0, max(plot.top() + 10.0, cy_raw))

                        if cy_raw < plot.top() - 24.0 or cy_raw > plot.bottom() + 24.0:
                            rect_chip = None
                        else:
                            rect_chip = self._colocar_rect_sin_solape(
                                plot, cx, cy, w_chip, h_chip, offset_y, chips_dibujados
                            )
                        if rect_chip is not None:
                            chips_dibujados.append(rect_chip)
                            p.setPen(QPen(col_seg, 0.9, Qt.DotLine))
                            y_ancla = (
                                rect_chip.bottom() if rect_chip.center().y() < cy else rect_chip.top()
                            )
                            p.drawLine(QPointF(rect_chip.center().x(), y_ancla), QPointF(cx, cy))

                            bg_chip = QColor("#ffffff")
                            bg_chip.setAlpha(245)
                            p.setPen(QPen(col_seg, 1.15))
                            p.setBrush(bg_chip)
                            p.drawRoundedRect(rect_chip, 4.0, 4.0)

                            p.setFont(font_chip)
                            p.setPen(col_seg.darker(115) if causa in ("accesorio", "borde") else col_seg)
                            p.drawText(rect_chip, Qt.AlignCenter, texto_chip)

                # Marcadores circulares
                for idx_pt, (pt_info, pt_px) in enumerate(zip(pts, pts_egl)):
                    causa_pt = pt_info.get("causa")
                    if multi_ruta and (causa_pt == "friccion" or idx_pt in (0, len(pts) - 1)):
                        col_pto = QColor(col_egl)
                    elif causa_pt:
                        col_pto = QColor(self.COLORES_CAUSA.get(causa_pt, "#0c4e77"))
                    else:
                        col_pto = QColor("#0c4e77")
                    if pt_info.get("etiqueta") or causa_pt in ("accesorio", "borde") or idx_pt in (0, len(pts) - 1):
                        if plot.top() - 4 <= pt_px.y() <= plot.bottom() + 4 and plot.left() - 6 <= pt_px.x() <= plot.right() + 6:
                            p.setPen(QPen(QColor("#ffffff"), 1.6))
                            p.setBrush(col_pto)
                            p.drawEllipse(pt_px, 4.5, 4.5)

                # Marca de corte "//" cuando la línea sale por el borde inferior (4.3); se dibuja
                # al final para que ningún rótulo la tape
                if pos_vis == 0 and x_corte_px is not None and plot.left() <= x_corte_px <= plot.right():
                    pen_corte = QPen(QColor("#dc2626"), 2.4)
                    pen_corte.setCapStyle(Qt.RoundCap)
                    p.setPen(pen_corte)
                    p.setBrush(Qt.NoBrush)
                    cy_c = plot.bottom()
                    p.drawLine(QPointF(x_corte_px - 5, cy_c - 9), QPointF(x_corte_px + 1, cy_c + 9))
                    p.drawLine(QPointF(x_corte_px + 1, cy_c - 9), QPointF(x_corte_px + 7, cy_c + 9))

        # Rótulo de Energía faltante / déficit (4.3)
        if not ocultar_textos and hay_deficit and getattr(self, "mostrar_egl", True):
            val_hw = deficit if deficit > 0 else max(0.0, hf_total - delta_z)
            if val_hw >= 1e5:
                hw_str = f"{val_hw:.2e}"
            else:
                hw_str = f"{val_hw:.2f}"
            if has_bomba:
                txt_rotulo_deficit = f"Energía faltante = {hw_str} m"
            else:
                txt_rotulo_deficit = f"Energía faltante = h_W = {hw_str} m (se requiere bomba)"

            font_hw = QFont("Inter", 8)
            font_hw.setBold(True)
            p.setFont(font_hw)
            fm_hw = QtGui.QFontMetrics(font_hw)
            w_box_hw = fm_hw.horizontalAdvance(txt_rotulo_deficit) + 16.0
            h_box_hw = 22.0

            cx_box = (x_cruce_def_px + plot.right()) / 2.0 if x_cruce_def_px is not None else (plot.left() + plot.right()) / 2.0
            y_t2_px = map_y(Z2)
            if y_t2_px <= plot.bottom() - 24.0 and (
                x_cruce_def_px is None or x_cruce_def_px <= plot.right() - 20.0
            ):
                cy_box = (y_t2_px + plot.bottom()) / 2.0
                bx = max(plot.left() + 6.0, min(plot.right() - w_box_hw - 6.0, cx_box - w_box_hw / 2.0))
                by = max(plot.top() + 4.0, max(y_t2_px + 4.0, min(plot.bottom() - h_box_hw - 4.0, cy_box - h_box_hw / 2.0)))
                rect_hw = QRectF(bx, by, w_box_hw, h_box_hw)

                p.setPen(QPen(QColor("#dc2626"), 1.2))
                p.setBrush(QColor(254, 242, 242, 240))
                p.drawRoundedRect(rect_hw, 4.0, 4.0)

                p.setPen(QColor("#b91c1c"))
                p.drawText(rect_hw, Qt.AlignCenter, txt_rotulo_deficit)

        # 4. Callouts de Nivel Inicial (z₁) y Nivel Final (z₂) cuando Mostrar valores está activo
        if not ocultar_textos and self.mostrar_valores and indices_vis:
            pts0 = series_dib[idx_base]
            if len(pts0) >= 2:
                z1_num = float(z1_raw if z1_raw is not None else pts0[0]["egl"])
                z2_num = float(z2_raw if z2_raw is not None else pts0[-1]["egl"])
                y_ini_c = map_y(nivel_t1 if z1_raw is not None else float(pts0[0]["egl"]))
                y_fin_c = map_y(nivel_t2 if z2_raw is not None else float(pts0[-1]["egl"]))
                p_ini = QPointF(map_x_s(idx_base, float(pts0[0]["x"])), y_ini_c)
                p_fin = QPointF(
                    map_x_s(idx_base, float(pts0[-1]["x"])) if esta_zoomed else (plot.right() - 8.0),
                    y_fin_c,
                )

                font_call = QFont("Consolas", 8)
                font_call.setBold(True)
                p.setFont(font_call)
                for pt_ref, txt_call, align_right in (
                    (p_ini, f"z₁ = {z1_num:.2f} m (Nivel Inicial)", False),
                    (p_fin, f"z₂ = {z2_num:.2f} m (Nivel Final)", True),
                ):
                    if not plot.adjusted(-8.0, -8.0, 8.0, 8.0).contains(pt_ref):
                        continue
                    w_box = QtGui.QFontMetrics(font_call).horizontalAdvance(txt_call) + 16.0
                    h_box = 22.0
                    bx = pt_ref.x() - w_box - 6.0 if align_right else pt_ref.x() + 6.0
                    box_r = self._colocar_rect_sin_solape(
                        plot,
                        bx + w_box / 2.0,
                        max(r.top() + 18.0, min(plot.bottom() - h_box / 2.0 - 4.0, pt_ref.y() - 20.0)),
                        w_box,
                        h_box,
                        -12.0,
                        chips_dibujados,
                    )
                    if box_r is not None:
                        chips_dibujados.append(box_r)
                        p.setPen(Qt.NoPen)
                        p.setBrush(QColor("#213145"))
                        p.drawRoundedRect(box_r, 4.0, 4.0)
                        p.setPen(QColor("#ffffff"))
                        p.drawText(box_r, Qt.AlignCenter, txt_call)

        # 5. Rótulos del régimen de exceso (al final, para que nada los tape)
        if (
            not ocultar_textos
            and hay_exceso
            and info_exceso is not None
            and getattr(self, "mostrar_egl", True)
            and info_exceso["y_t2"] >= plot.top() - 24.0
            and info_exceso["y_egl_c"] <= plot.bottom() + 24.0
        ):
            y_t2_px = info_exceso["y_t2"]
            zona_ocupada = [c.adjusted(-3, -2, 3, 2) for c in chips_dibujados]

            # 5a. Rótulo "Nivel Tanque 2 (x.xx m)" pegado al borde derecho, por encima de la línea
            txt_t2 = f"Nivel Tanque 2 ({nivel_t2:.2f} m)"
            font_t2 = QFont("Inter", 8, QFont.Bold)
            w_t2 = QtGui.QFontMetrics(font_t2).horizontalAdvance(txt_t2) + 6.0
            rect_t2 = QRectF(plot.right() - w_t2 - 8.0, y_t2_px - 16.0, w_t2, 14.0)
            for dy_t2 in (-16.0, -34.0, -52.0, -70.0):
                cand_t2 = QRectF(plot.right() - w_t2 - 8.0, y_t2_px + dy_t2, w_t2, 14.0)
                if cand_t2.top() >= plot.top() + 2.0 and not any(cand_t2.intersects(z) for z in zona_ocupada):
                    rect_t2 = cand_t2
                    break

            # 5b. Rótulo dentro de la banda verde
            exc_val = max(0.0, dz_energia - hf_total)
            txt_exc = f"Energía excedente = {exc_val:.2f} m (el caudal podría ser mayor)"
            font_exc = QFont("Inter", 8)
            font_exc.setBold(True)
            w_exc = QtGui.QFontMetrics(font_exc).horizontalAdvance(txt_exc) + 16.0
            h_exc = 22.0
            y_ega = info_exceso["y_egl_c"]
            alto_banda = y_t2_px - y_ega
            if alto_banda >= h_exc + 8.0:
                cy_exc = (y_ega + y_t2_px) / 2.0
                top_exc = cy_exc - h_exc / 2.0
            else:
                top_exc = y_t2_px + 6.0           # banda muy delgada: justo bajo el nivel de Z2
            bx_exc = max(plot.left() + 6.0, min(plot.right() - w_exc - 6.0, info_exceso["x_c"] - w_exc / 2.0))
            rect_exc = QRectF(bx_exc, top_exc, w_exc, h_exc)
            for dy_exc in (0.0, 26.0, -26.0, 52.0, -52.0):
                cand = QRectF(bx_exc, top_exc + dy_exc, w_exc, h_exc)
                dentro = plot.top() + 3.0 <= cand.top() and cand.bottom() <= plot.bottom() - 3.0
                if alto_banda >= h_exc + 8.0:
                    dentro = dentro and (cand.top() >= y_ega + 2.0) and (cand.bottom() <= y_t2_px - 2.0)
                if dentro and not any(cand.intersects(z) for z in zona_ocupada) and not cand.intersects(rect_t2):
                    rect_exc = cand
                    break
            if rect_exc.intersects(rect_t2):
                rect_exc.moveRight(rect_t2.left() - 8.0)

            p.setPen(QPen(QColor("#16a34a"), 1.2))
            p.setBrush(QColor(240, 253, 244, 240))
            p.drawRoundedRect(rect_exc, 4.0, 4.0)
            p.setFont(font_exc)
            p.setPen(QColor("#15803d"))
            p.drawText(rect_exc, Qt.AlignCenter, txt_exc)

            p.setPen(Qt.NoPen)
            p.setBrush(QColor(248, 249, 255, 235))
            p.drawRoundedRect(rect_t2.adjusted(-3, -1, 3, 1), 3.0, 3.0)
            p.setFont(font_t2)
            p.setPen(QColor("#64748b"))
            p.drawText(rect_t2, Qt.AlignRight | Qt.AlignVCenter, txt_t2)

        # 6. Etiqueta discreta al exportar PNG en modo didáctico o vista paralela normalizada
        if info_esq is not None:
            rect_esq, font_esq, txt_esq = info_esq
            p.setPen(QPen(QColor("#0284c7"), 1.0))
            p.setBrush(QColor(240, 249, 255, 235))
            p.drawRoundedRect(rect_esq, 4.0, 4.0)
            p.setFont(font_esq)
            p.setPen(QColor("#0369a1"))
            p.drawText(rect_esq, Qt.AlignCenter, txt_esq)

        if not para_exportar and self._modo_arrastre == "box":
            sel_rect = (
                QRectF(self._arrastre_inicio_pos, self._arrastre_actual_pos)
                .normalized()
                .intersected(plot)
            )
            if not sel_rect.isEmpty():
                p.setPen(QPen(QColor("#0284c7"), 1.5, Qt.DashLine))
                p.setBrush(QColor(2, 132, 199, 32))
                p.drawRect(sel_rect)

    def _dibujar_leyenda_perfil(self, p, r, hay_deficit, hay_exceso, indices_vis=None):
        indices_vis = indices_vis if indices_vis is not None else self._indices_visibles()
        items_leyenda = []
        if getattr(self, "mostrar_egl", True):
            if len(indices_vis) > 1 or len(self.series) > 1:
                for idx_s in indices_vis:
                    nom_r = self.series[idx_s].get("nombre", f"Ruta {idx_s + 1}")
                    items_leyenda.append((f"━━ {nom_r}", self.color_serie(idx_s)))
            else:
                items_leyenda.append(("━━ EGL", "#e74c3c"))
        if getattr(self, "mostrar_hgl", True):
            col_h = "#475569" if (len(indices_vis) > 1 or len(self.series) > 1) else "#2980b9"
            items_leyenda.append(("╌╌ HGL", col_h))
        for clave, simbolo, texto, col_hex, _, _, _ in self.elementos_leyenda():
            etq = "■ Cinética" if clave == "cinetica" else f"{simbolo} {texto}"
            items_leyenda.append((etq, col_hex))

        font_ley = QFont("Inter", 8, QFont.DemiBold)
        p.setFont(font_ley)
        fm = QtGui.QFontMetrics(font_ley)

        max_w = max(220.0, r.width() - 40.0)
        filas = [[]]
        cur_w = 12.0
        for txt, col_hex in items_leyenda:
            item_w = fm.horizontalAdvance(txt) + 14.0
            if filas[-1] and cur_w + item_w > max_w:
                filas.append([])
                cur_w = 12.0
            filas[-1].append((txt, col_hex, fm.horizontalAdvance(txt)))
            cur_w += item_w

        ancho_total = min(
            max_w,
            max(sum(w_t + 14.0 for _, _, w_t in fila) + 12.0 for fila in filas),
        )
        h_fila = 20.0
        h_ley = len(filas) * h_fila + 6.0
        ley_rect = QRectF(r.right() - ancho_total - 18, r.top() + 10, ancho_total, h_ley)

        p.setPen(QPen(QColor("#cbd5e1"), 0.9))
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawRoundedRect(ley_rect, 4.0, 4.0)

        for idx_f, fila in enumerate(filas):
            cur_x = ley_rect.left() + 8.0
            top_f = ley_rect.top() + 3.0 + idx_f * h_fila
            for txt, col_hex, w_txt in fila:
                p.setPen(QColor(col_hex))
                p.drawText(QRectF(cur_x, top_f, w_txt + 4, h_fila), Qt.AlignVCenter, txt)
                cur_x += w_txt + 14.0

    def exportar_imagen(self):
        """Exporta la gráfica EGL/HGL a imagen PNG en alta resolución sobre fondo blanco."""
        if not self.series:
            QMessageBox.information(
                self, "Sin datos", "No hay datos de perfil hidráulico calculados para exportar."
            )
            return

        nombre_sugerido = "linea_energia_EGL_HGL.png"
        ruta, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar gráfica como imagen",
            nombre_sugerido,
            "Imágenes PNG (*.png)",
        )
        if not ruta:
            return

        if not ruta.lower().endswith(".png"):
            ruta += ".png"

        try:
            ancho_logico = max(1100, self.width())
            alto_logico = max(600, self.height())
            escala = 2.5

            ancho_px = int(ancho_logico * escala)
            alto_px = int(alto_logico * escala)

            imagen = QImage(ancho_px, alto_px, QImage.Format_ARGB32)
            imagen.fill(QColor("#ffffff"))

            p = QPainter(imagen)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.TextAntialiasing, True)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.scale(escala, escala)

            rect_export = QRectF(0, 0, ancho_logico, alto_logico).adjusted(6, 6, -6, -6)
            self._dibujar_perfil(p, rect_export, para_exportar=True)
            p.end()

            exito = imagen.save(ruta, "PNG")
            if not exito:
                raise IOError(f"El sistema operativo no permitió guardar el archivo en:\n{ruta}")
        except Exception as error:
            QMessageBox.critical(
                self,
                "Error al exportar imagen",
                f"No se pudo guardar la imagen de la gráfica:\n\n{error}",
            )
            return


GraficoEGLWidget = WidgetPerfilEGLHGL
