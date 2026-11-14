"""Widget interactivo para graficar las curvas H-Q de bombas, curva resistente del sistema y eficiencia."""

import math

from PyQt5.QtCore import QPointF, QRectF, QRect, Qt, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap, QPolygonF
from PyQt5.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ui.iconos import crear_icono_herramienta
from ui.nombres_bombas import nombre_equipo_bomba
from ui.curvas_presentacion import usa_puntos,puntos_tabla,puntos_total,resumen_puntos,tabla_tsv


class WidgetGraficoBombas(QWidget):
    """
    Gráfico técnico estilo Google Stitch que representa:
    - Curva característica de cada bomba individual y curva equivalente (serie/paralelo).
    - Curva resistente del sistema H_sistema(Q).
    - Punto de operación (Q_op, H_op) con retícula y leyenda destacada.
    - Gráfico inferior alineado de Eficiencia vs Caudal con (Q_op, η_op).
    - Zoom con rueda del ratón, arrastre panorámico y botón de restablecimiento de vista.
    """

    visibilidad_cambiada = pyqtSignal()

    COLORES_BOMBAS = ['#009e73','#cc79a7','#4d4d4d','#7a5252']
    COLORES_NPSHR = ['#e69f00','#d55e00','#f0a35b','#a45a00']
    COLORES_EFICIENCIA = ['#7b2cbf','#a663cc','#4b1d73','#c77dff']
    COLOR_SISTEMA = "#006398"     # Azul cyan característico del sistema
    COLOR_EQUIVALENTE = "#111111" # Verde bosque para curva equivalente
    COLOR_OPERACION = "#dc2626"   # Rojo protagonista para el punto de operación
    COLOR_EFICIENCIA = "#7b2cbf"  # Azul cielo para la eficiencia

    @classmethod
    def _color_serie(cls,tipo,indice=0):
        paletas = {'bomba':cls.COLORES_BOMBAS,'npshr':cls.COLORES_NPSHR,
                   'eficiencia':cls.COLORES_EFICIENCIA}
        paleta = paletas[tipo]
        if indice<len(paleta):
            return paleta[indice]
        # Equipos adicionales conservan su gama, sin reciclar colores.
        tono = {'bomba':145,'npshr':32,'eficiencia':280}[tipo]
        return QColor.fromHsv(tono+(indice*7)%15,160+(indice*13)%80,
                              100+(indice*37)%145).name()

    def _etiqueta_serie(self,tipo,indice=0):
        nombre = self.nombres_bombas[indice]
        return {'bomba':f'{nombre} — H-Q','npshr':f'NPSHr — {nombre}',
                'eficiencia':f'Eficiencia — {nombre}'}[tipo]

    @staticmethod
    def _fuera_del_dominio(punto):
        return not punto.valido and 'FUERA_DE_RANGO_CURVA' in punto.estado

    def _muestras_invalidas(self):
        conjuntos = [(self._etiqueta_serie('bomba',i),m) for i,m in enumerate(self.muestras_bombas)]
        conjuntos += [('Curva del sistema',self.muestras_sistema)]
        if len(self.curvas)>1:
            conjuntos += [('Curva equivalente',self.muestras_equivalente)]
        return [(nombre,p) for nombre,lista in conjuntos for p in lista if not p.valido]

    def _tooltip_en_posicion(self,posicion):
        candidatos = [(math.hypot(posicion.x()-p.x(),posicion.y()-p.y()),texto)
                      for p,texto in getattr(self,'_puntos_tooltip',[])]
        return min(candidatos)[1] if candidatos and min(candidatos)[0]<=10 else ''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(380)

        # Datos de simulación
        self.curvas = []           # Lista de CurvaBomba
        self.nombres_bombas = []
        self.curva_eq = None       # Objeto CurvaBomba o CurvaEquivalente
        self.H_sistema_fn = None   # Indicador de muestras disponibles; nunca se evalúa.
        self.muestras_sistema, self.muestras_bombas, self.muestras_equivalente = [], [], []
        self.ecuacion_total, self.ecuaciones_bombas = None, []
        self.Q_op = None           # Caudal de operación [m³/s]
        self.H_op = None           # Altura de operación [m]
        self.eta_op = None         # Eficiencia en punto de operación [0-1]
        self.arreglo = "individual"
        self.metodo = "cuadratico"
        self.reparto = []
        self._ultimo_puntos_eq_data = []
        self._ultimo_trazo_bombas_modo = []
        self._puntos_tooltip = []
        self._ticks_y_hq = []
        self._rect_ultimo_q_ls = None
        self._rect_titulo_x = None

        # Interacción y navegación (zoom y pan)
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self._dragging = False
        self._last_mouse_pos = QPointF(0.0, 0.0)
        self.setMouseTracking(True)
        self._marcador_op_hq_pos = None
        self._marcador_op_eta_pos = None
        self.q_max_escala_base = 0.05
        self.h_max_escala_base = 20.0
        self.visibilidad = {
            "sistema": True,
            "bombas": {},
            "curva_eq": True,
            "punto_op": True,
            "puntos_tabla": True,
            "panel_eficiencia": True,
        }

        # Barra superior con controles
        self._setup_ui()

    def set_visibilidad(self, clave, valor, sub_idx=None):
        """Modifica la visibilidad de una curva o elemento sin reescalar los ejes."""
        if sub_idx is not None:
            if clave not in self.visibilidad or not isinstance(self.visibilidad[clave], dict):
                self.visibilidad[clave] = {}
            self.visibilidad[clave][sub_idx] = bool(valor)
        else:
            self.visibilidad[clave] = bool(valor)
        self._sincronizar_controles_eficiencia()
        self.visibilidad_cambiada.emit()
        self.update()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 8)
        layout.setSpacing(6)

        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)

        self.lbl_titulo = QLabel("CURVAS CARACTERÍSTICAS H-Q Y RESISTENCIA DEL SISTEMA")
        self.lbl_titulo.setWordWrap(True)
        self.lbl_titulo.setMinimumWidth(0)
        self.lbl_titulo.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
            "font-weight: 700; color: #0c4e77; letter-spacing: 0.5px;"
        )
        hdr_row.addWidget(self.lbl_titulo)
        hdr_row.addStretch()

        self.btn_reset = QPushButton("↺ Restablecer vista")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setStyleSheet(
            "QPushButton { font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
            "font-weight: 600; color: #006398; background: #e5eeff; border: 1px solid #cce0ff; "
            "border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background: #d0e4ff; color: #0c4e77; }"
            "QPushButton:pressed { background: #b8d7ff; }"
        )
        self.btn_reset.clicked.connect(self.restablecer_vista)
        hdr_row.addWidget(self.btn_reset)

        self.btn_eficiencia = QPushButton('Panel de eficiencia')
        self.btn_eficiencia.setCheckable(True)
        self.btn_eficiencia.setCursor(Qt.PointingHandCursor)
        self.btn_eficiencia.setStyleSheet(self.btn_reset.styleSheet()+
            'QPushButton:checked { background: #b8d7ff; border-color: #006398; }')
        self.btn_eficiencia.toggled.connect(lambda valor:self.set_visibilidad('panel_eficiencia',valor))
        hdr_row.addWidget(self.btn_eficiencia)
        self._sincronizar_controles_eficiencia()

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
        hdr_row.addWidget(self.btn_exportar)

        layout.addLayout(hdr_row)
        layout.addStretch(1)

        self.header_eficiencia = QWidget(self)
        fila_eta = QHBoxLayout(self.header_eficiencia)
        fila_eta.setContentsMargins(0,0,0,0)
        fila_eta.addStretch()
        self.btn_exportar_eficiencia = QPushButton('Descargar imagen')
        self.btn_exportar_eficiencia.setIcon(self.btn_exportar.icon())
        self.btn_exportar_eficiencia.setIconSize(self.btn_exportar.iconSize())
        self.btn_exportar_eficiencia.setCursor(Qt.PointingHandCursor)
        self.btn_exportar_eficiencia.setStyleSheet(self.btn_exportar.styleSheet())
        self.btn_exportar_eficiencia.setToolTip('Exportar solo la curva de eficiencia como PNG de alta resolución')
        self.btn_exportar_eficiencia.clicked.connect(self.exportar_imagen_eficiencia)
        fila_eta.addWidget(self.btn_exportar_eficiencia)
        self._sincronizar_controles_eficiencia()

    def _sincronizar_controles_eficiencia(self):
        if not hasattr(self,'btn_eficiencia'):
            return
        previo = self.btn_eficiencia.blockSignals(True)
        self.btn_eficiencia.setChecked(self.visibilidad.get('panel_eficiencia',True))
        self.btn_eficiencia.blockSignals(previo)
        self.btn_eficiencia.setEnabled(self.tiene_eficiencia)
        self.btn_eficiencia.setToolTip('Mostrar u ocultar el panel de eficiencia' if self.tiene_eficiencia
                                     else 'Ninguna bomba tiene datos de eficiencia.')
        if hasattr(self,'header_eficiencia'):
            visible = self.tiene_eficiencia and self.visibilidad.get('panel_eficiencia',True)
            self.header_eficiencia.setVisible(visible)
            self.btn_exportar_eficiencia.setVisible(visible)

    @property
    def tiene_eficiencia(self):
        """Verifica si alguna de las curvas cargadas posee datos de eficiencia."""
        if not self.curvas:
            return False
        return any(getattr(b, "tiene_eficiencia", False) for b in self.curvas)

    def restablecer_vista(self):
        """Restablece el nivel de zoom y el desplazamiento a los valores iniciales."""
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0.0, 0.0)
        self.update()

    def limpiar_datos(self):
        """Borra los datos del gráfico y vuelve al estado vacío."""
        self.curvas = []
        self.nombres_bombas = []
        self.curva_eq = None
        self.H_sistema_fn = None
        self.muestras_sistema, self.muestras_bombas, self.muestras_equivalente = [], [], []
        self.ecuacion_total, self.ecuaciones_bombas = None, []
        self.Q_op = None
        self.H_op = None
        self.eta_op = None
        self._ultimo_puntos_eq_data = []
        self._ultimo_trazo_bombas_modo = []
        self._puntos_tooltip = []
        if hasattr(self, "btn_exportar"):
            self.btn_exportar.setVisible(False)
        self._sincronizar_controles_eficiencia()
        self.visibilidad_cambiada.emit()
        self.restablecer_vista()

    def actualizar_datos(self, curvas, curva_eq, H_sistema, Q_op, H_op, eta_op, arreglo="individual", reparto=None, metodo=None, muestras_sistema=None, muestras_bombas=None,
                         muestras_equivalente=None, ecuacion_total=None, ecuaciones_bombas=None, nombres_bombas=None):
        """
        Carga y actualiza los datos calculados para renderizar el gráfico.
        """
        self.curvas = list(curvas) if curvas else []
        self.nombres_bombas = [nombre_equipo_bomba(
            {'nombre':nombres_bombas[i]} if nombres_bombas and i<len(nombres_bombas) else None,
            curva=b,indice=i) for i,b in enumerate(self.curvas)]
        self.curva_eq = curva_eq
        self.muestras_sistema = muestras_sistema if muestras_sistema is not None else []
        self.muestras_bombas = muestras_bombas if muestras_bombas is not None else []
        self.muestras_equivalente = muestras_equivalente if muestras_equivalente is not None else []
        self.ecuacion_total = ecuacion_total
        self.ecuaciones_bombas = ecuaciones_bombas or []
        self.H_sistema_fn = self.muestras_sistema if self.muestras_sistema else None
        self.Q_op = float(Q_op) if Q_op is not None else None
        self.H_op = float(H_op) if H_op is not None else None
        self.eta_op = float(eta_op) if eta_op is not None else None
        if hasattr(self, "btn_exportar"):
            self.btn_exportar.setVisible(bool(self.curvas) or self.Q_op is not None)
        self.arreglo = str(arreglo).lower()
        self.reparto = list(reparto) if reparto else []
        if metodo is not None:
            self.metodo = str(metodo).lower()
        elif self.curva_eq is not None and hasattr(self.curva_eq, "metodo"):
            self.metodo = str(getattr(self.curva_eq, "metodo", "cuadratico")).lower()
        elif self.curvas and hasattr(self.curvas[0], "metodo"):
            self.metodo = str(getattr(self.curvas[0], "metodo", "cuadratico")).lower()
        else:
            self.metodo = "cuadratico"

        # Las escalas y los trazos solo leen las muestras calculadas en el motor.
        conjuntos = [self.muestras_equivalente]+self.muestras_bombas
        puntos = [pt for lista in conjuntos for pt in lista if pt.valido and pt.H is not None]
        q_max_data = max([pt.Q for pt in puntos]+[float(b.Q_max) for b in self.curvas]
                         +[self.Q_op or 0.0]) or 1e-4
        self.q_max_escala_base = q_max_data*1.15
        h_max_data = max([pt.H for pt in puntos]+[self.H_op or 0.0]) or 1.0
        self.h_max_escala_base = h_max_data*1.25

        # Inicializar estado de visibilidad para nuevas bombas (persistencia de sesión)
        if "bombas" not in self.visibilidad:
            self.visibilidad["bombas"] = {}
        for idx in range(len(self.curvas)):
            if idx not in self.visibilidad["bombas"]:
                self.visibilidad["bombas"][idx] = True

        self._sincronizar_controles_eficiencia()
        self.visibilidad_cambiada.emit()
        self.restablecer_vista()

    def wheelEvent(self, event):
        if not self.curvas:
            return
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.85
        nuevo_zoom = max(0.5, min(10.0, self.zoom_factor * factor))

        # Centrar zoom en el cursor
        m_pos = event.pos()
        self.pan_offset = (self.pan_offset - m_pos) * (nuevo_zoom / self.zoom_factor) + m_pos
        self.zoom_factor = nuevo_zoom
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.curvas:
            self._dragging = True
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.pos() - self._last_mouse_pos
            self.pan_offset += QPointF(delta.x(), delta.y())
            self._last_mouse_pos = event.pos()
            self.update()
        else:
            cerca = False
            m_pos = event.pos()
            if self.visibilidad.get("punto_op", True) and self.Q_op is not None:
                for pt in (getattr(self, "_marcador_op_hq_pos", None), getattr(self, "_marcador_op_eta_pos", None)):
                    if pt is not None:
                        dist = math.hypot(m_pos.x() - pt.x(), m_pos.y() - pt.y())
                        if dist <= 14.0:
                            cerca = True
                            break

            if cerca and self.Q_op is not None:
                q_ls = self.Q_op * 1000.0
                h_val = self.H_op if self.H_op is not None else 0.0
                eta_val = self.eta_op * 100.0 if self.eta_op is not None else None
                eta_txt = f"{eta_val:.1f} %" if eta_val is not None else "N/D"
                tip_text = (
                    f"Punto de operación:\n"
                    f"Q = {q_ls:.2f} L/s ({self.Q_op:.4f} m³/s)\n"
                    f"H = {h_val:.2f} m\n"
                    f"η = {eta_txt}"
                )
                QToolTip.showText(event.globalPos(), tip_text, self)
            else:
                tip = self._tooltip_en_posicion(event.pos())
                if tip:
                    QToolTip.showText(event.globalPos(),tip,self)
                else:
                    QToolTip.hideText()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.restablecer_vista()
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        p = QPainter()
        if not p.begin(self):
            return
        try:
            p.setRenderHint(QPainter.Antialiasing)
            rect_total = QRectF(self.rect()).adjusted(6, 6, -6, -6)
            self._dibujar_grafico_completo(p, rect_total, para_exportar=False)
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            p.end()

    def _dibujar_grafico_completo(self, p, rect_total, para_exportar=False, panel_exportar=None):
        if para_exportar and panel_exportar is None:
            panel_exportar = 'hq'
        dibujar_hq = panel_exportar != 'eficiencia'
        self._capturar_tooltips = not para_exportar
        if not para_exportar:
            self._puntos_tooltip = []
        if para_exportar:
            # Fondo blanco sólido para informes / Word / PowerPoint
            p.fillRect(rect_total, QColor("#ffffff"))
            p.setPen(QPen(QColor("#cbd5e1"), 1.0))
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(rect_total, 8.0, 8.0)

            # Título principal de la gráfica
            p.setFont(QFont("Inter", 11, QFont.Bold))
            p.setPen(QColor("#0c4e77"))
            p.drawText(
                QRectF(rect_total.left() + 20, rect_total.top() + 10, rect_total.width() - 40, 24),
                Qt.AlignLeft | Qt.AlignVCenter,
                "" if panel_exportar=="eficiencia" else "CURVAS CARACTERÍSTICAS H-Q Y RESISTENCIA DEL SISTEMA",
            )
        else:
            # 1. Contenedor principal con estilo Stitch
            p.setPen(QPen(QColor("#e5eeff"), 1.2))
            p.setBrush(QColor("#f8f9ff"))
            p.drawRoundedRect(rect_total, 10.0, 10.0)

        # Si no hay datos de bombas cargados, mostrar estado vacío
        if not self.curvas:
            self._dibujar_estado_vacio(p, rect_total)
            return

        # 2. Definición de áreas de los gráficos
        tiene_eff = self.tiene_eficiencia and self.visibilidad.get("panel_eficiencia", True) and panel_exportar != "hq"
        pad_izq = 80.0
        pad_der = 35.0
        # Deja espacio al título, incluso cuando ocupa dos líneas.
        pad_arr = (70.0 if para_exportar else max(60.0,
            self.layout().itemAt(0).geometry().bottom()+26.0-rect_total.top()))
        pad_abj = 68.0

        ancho_util = max(180.0, rect_total.width() - pad_izq - pad_der)

        if panel_exportar=='eficiencia':
            plot_hq = None
            plot_eta = QRectF(rect_total.left()+pad_izq,rect_total.top()+pad_arr,ancho_util,
                              max(160.0,rect_total.height()-pad_arr-pad_abj))
        elif tiene_eff:
            gap_entre_plots = 38.0
            alto_disponible = max(160.0, rect_total.height() - pad_arr - pad_abj - gap_entre_plots)
            alto_hq = alto_disponible * 0.65
            alto_eta = alto_disponible * 0.35
            plot_hq = QRectF(rect_total.left() + pad_izq, rect_total.top() + pad_arr, ancho_util, alto_hq)
            plot_eta = QRectF(rect_total.left() + pad_izq, plot_hq.bottom() + gap_entre_plots, ancho_util, alto_eta)
        else:
            alto_disponible = max(160.0, rect_total.height() - pad_arr - pad_abj)
            alto_hq = alto_disponible
            plot_hq = QRectF(rect_total.left() + pad_izq, rect_total.top() + pad_arr, ancho_util, alto_hq)
            plot_eta = None

        if not para_exportar:
            self._ultimo_plot_hq,self._ultimo_plot_eta = plot_hq,plot_eta
            self._sincronizar_controles_eficiencia()
            if plot_eta is not None:
                self.header_eficiencia.setGeometry(QRect(int(plot_eta.left()+120),int(plot_eta.top()-36),
                    max(200,int(plot_eta.width()-120)),26))

        # 3. Determinación de escalas fijas (estables al ocultar/mostrar curvas)
        q_max_escala = getattr(self, "q_max_escala_base", 0.05)
        h_max_escala = getattr(self, "h_max_escala_base", 20.0)

        # 4. Dibujo de fondos de gráfico y cuadrículas técnicas
        if dibujar_hq:
            self._dibujar_fondo_y_cuadricula(p, plot_hq, q_max_escala, h_max_escala, tipo="hq")
        if tiene_eff and plot_eta is not None:
            self._dibujar_fondo_y_cuadricula(p, plot_eta, q_max_escala, 100.0, tipo="eta")

        if dibujar_hq:
            # 5. Trazado de curvas en el gráfico H-Q (con clipping y transformaciones de zoom/pan)
            p.save()
            p.setClipRect(plot_hq)

            # Curva resistente del sistema
            if self.H_sistema_fn is not None and self.visibilidad.get("sistema", True):
                self._trazar_curva_sistema(p, plot_hq, q_max_escala, h_max_escala)

            # Curvas de bombas individuales
            self._ultimo_trazo_bombas_modo = []
            for idx, bomba in enumerate(self.curvas):
                if not self.visibilidad.get("bombas", {}).get(idx, True):
                    continue
                color = self._color_serie('bomba',idx)
                estilo = Qt.DashLine if len(self.curvas) > 1 and self.arreglo in ("serie", "paralelo") else Qt.SolidLine
                self._trazar_curva_bomba_h(p, plot_hq, bomba, q_max_escala, h_max_escala, color, estilo)

            # NPSHr es una magnitud independiente, con sus propias muestras ya calculadas.
            for idx in range(len(self.curvas)):
                if self._tiene_npshr(idx) and self.visibilidad.get('npshr',{}).get(idx,True):
                    self._trazar_muestras(p,plot_hq,self.muestras_bombas[idx],q_max_escala,h_max_escala,
                        self._color_serie('npshr',idx),Qt.DotLine,npshr=True,etiqueta=self._etiqueta_serie('npshr',idx))

            # Curva equivalente si hay arreglo múltiple
            self._ultimo_puntos_eq_data = []
            if self.curva_eq is not None and len(self.curvas) > 1 and self.visibilidad.get("curva_eq", True):
                self._trazar_curva_bomba_h(
                    p, plot_hq, self.curva_eq, q_max_escala, h_max_escala, self.COLOR_EQUIVALENTE, Qt.SolidLine, grosor=3.0, es_equivalente=True
                )

            # Marcador del punto de operación en H-Q
            self._marcador_op_hq_pos = None
            if self.Q_op is not None and self.H_op is not None and self.visibilidad.get("punto_op", True):
                self._dibujar_marcador_op(p, plot_hq, self.Q_op, self.H_op, q_max_escala, h_max_escala, tipo="hq")

            p.restore()

        # 6. Trazado de curva en el gráfico η-Q (solo si tiene eficiencia)
        self._marcador_op_eta_pos = None
        if tiene_eff and plot_eta is not None:
            p.save()
            p.setClipRect(plot_eta)

            for idx, bomba in enumerate(self.curvas):
                if not self.visibilidad.get("bombas", {}).get(idx, True):
                    continue
                if getattr(bomba, "tiene_eficiencia", False):
                    col_eta = self._color_serie('eficiencia',idx)
                    estilo_eta = Qt.DashLine
                    self._trazar_curva_eficiencia(p, plot_eta, bomba, q_max_escala, color_hex=col_eta, estilo=estilo_eta)

            # Marcar (Q_i, eta_i) de cada bomba en la curva de eficiencia
            if self.reparto and self.visibilidad.get("punto_op", True):
                for idx_r, rep in enumerate(self.reparto):
                    if not self.visibilidad.get("bombas", {}).get(idx_r, True):
                        continue
                    q_i = rep.get("Q")
                    eta_i = rep.get("eta")
                    activa = rep.get("activa", True)
                    if activa and q_i is not None and eta_i is not None:
                        col_pto = self._color_serie('eficiencia',idx_r)
                        px_i = self._map_x(q_i, plot_eta, q_max_escala)
                        py_i = self._map_y(eta_i * 100.0, plot_eta, 100.0)
                        p.setPen(QPen(QColor("#ffffff"), 1.8))
                        p.setBrush(QBrush(QColor(col_pto)))
                        p.drawEllipse(QPointF(px_i, py_i), 4.5, 4.5)

            eta_global_op = self.eta_op
            if self.Q_op is not None and eta_global_op is not None and self.visibilidad.get("punto_op", True):
                self._dibujar_marcador_op(
                    p, plot_eta, self.Q_op, eta_global_op * 100.0, q_max_escala, 100.0, tipo="eta"
                )

            p.restore()

        # 7. Ejes, escalas numéricas y títulos (sin leyenda interna repetida)
        self._dibujar_ejes_y_textos(p, plot_hq, plot_eta, q_max_escala, h_max_escala)

        # 8. Leyenda de curvas en la imagen exportada
        if para_exportar:
            self._dibujar_leyenda(p, plot_hq if dibujar_hq else plot_eta, panel=panel_exportar)

    def _dibujar_estado_vacio(self, p, r):
        p.setFont(QFont("Inter", 11, QFont.DemiBold))
        p.setPen(QColor("#72787f"))
        p.drawText(
            r,
            Qt.AlignCenter,
            "Gráfico de Bombas no generado\n\n"
            "Selecciona los tanques en el panel lateral y haz clic en\n"
            "'▶ Calcular Punto de Operación' para visualizar la curva H-Q.",
        )

    def _map_x(self, q, plot, q_max):
        u = float(q) / float(q_max) if q_max > 0 else 0.0
        x_base = plot.left() + u * plot.width()
        cx = plot.center().x()
        return cx + (x_base - cx) * self.zoom_factor + self.pan_offset.x()

    def _map_y(self, y_val, plot, y_max):
        v = float(y_val) / float(y_max) if y_max > 0 else 0.0
        y_base = plot.bottom() - v * plot.height()
        cy = plot.center().y()
        return cy + (y_base - cy) * self.zoom_factor + self.pan_offset.y()

    def _marcas_y(self,plot,y_max):
        """Marcas 1/2/5/10 según el rango visible y el espacio en píxeles."""
        y0,y1 = self._map_y(0,plot,y_max),self._map_y(y_max,plot,y_max)
        limites = [(y-y0)/(y1-y0)*y_max for y in (plot.top(),plot.bottom())]
        minimo,maximo = sorted(limites)
        cantidad = min(10,max(2,int(plot.height()/28)+1))
        bruto = (maximo-minimo)/(cantidad-1)
        potencia = 10**math.floor(math.log10(bruto))
        paso = next(n for n in (1,2,5,10) if n*potencia>=bruto*(1-1e-12))*potencia
        primero = math.ceil(minimo/paso-1e-12)
        ultimo = math.floor(maximo/paso+1e-12)
        return [float(f'{i*paso:.12g}') for i in range(primero,ultimo+1)]

    def _dibujar_fondo_y_cuadricula(self, p, plot, q_max, y_max, tipo="hq"):
        p.save()
        p.setClipRect(plot)

        # Fondo del recuadro
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(plot, 3, 3)

        # Rejilla milimétrica suave
        p.setPen(QPen(QColor(220, 233, 255, 120), 0.7, Qt.SolidLine))

        # La rejilla usa las mismas marcas que los rótulos.
        for valor in self._marcas_y(plot,y_max):
            y_pos = self._map_y(valor,plot,y_max)
            p.drawLine(QPointF(plot.left(),y_pos),QPointF(plot.right(),y_pos))

        # Líneas verticales (Q)
        n_x = 5
        for i in range(1, n_x + 1):
            val_q = (q_max / (n_x + 1)) * i
            x_pos = self._map_x(val_q, plot, q_max)
            p.drawLine(QPointF(x_pos, plot.top()), QPointF(x_pos, plot.bottom()))

        p.restore()

        # Borde exterior del recuadro del plot
        p.setPen(QPen(QColor("#cbd5e1"), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawRect(plot)

    def _trazar_muestras(self, p, plot, muestras, q_max, y_max, color, estilo, grosor=2.2, eficiencia=False, npshr=False, etiqueta=None, solo_invalidos=False):
        """Corta la línea en fallos y marca una cruz de estado al pie del gráfico."""
        p.setPen(QPen(QColor(color),grosor,estilo))
        segmento = []
        for pt in muestras:
            if solo_invalidos and pt.valido:
                continue
            valor = pt.NPSHr if npshr else pt.eficiencia if eficiencia else pt.H
            if not pt.valido or valor is None:
                if len(segmento)>1:
                    p.drawPolyline(QPolygonF(segmento))
                segmento = []
                clave = 'fuera_rango' if self._fuera_del_dominio(pt) else 'muestras_invalidas'
                if not pt.valido and self.visibilidad.get(clave,True):
                    x,y = self._map_x(pt.Q,plot,q_max),plot.bottom()-4
                    p.drawLine(QPointF(x-2,y-2),QPointF(x+2,y+2))
                    p.drawLine(QPointF(x-2,y+2),QPointF(x+2,y-2))
                    if getattr(self,'_capturar_tooltips',False) and plot.contains(QPointF(x,y)):
                        self._puntos_tooltip.append((QPointF(x,y),f'{etiqueta or "Muestra"}\nQ = {pt.Q:.8g} m³/s\n{pt.estado}\nMuestra inválida; no representa H=0.'))
                continue
            punto = QPointF(self._map_x(pt.Q,plot,q_max),self._map_y(valor*100 if eficiencia else valor,plot,y_max))
            segmento.append(punto)
            if etiqueta and getattr(self,'_capturar_tooltips',False) and plot.contains(punto):
                unidad = '%' if eficiencia else 'm'
                mostrado = valor*100 if eficiencia else valor
                self._puntos_tooltip.append((punto,f'{etiqueta}\nQ = {pt.Q:.8g} m³/s; {mostrado:.8g} {unidad}'))
        if len(segmento)>1:
            p.drawPolyline(QPolygonF(segmento))

    def _trazar_curva_sistema(self,p,plot,q_max,h_max):
        self._trazar_muestras(p,plot,self.muestras_sistema,q_max,h_max,self.COLOR_SISTEMA,Qt.SolidLine,2.4,etiqueta="Curva del sistema")

    def _q_ultimo_valido_equivalente(self,curva_eq):
        return max((pt.Q for pt in self.muestras_equivalente if pt.valido),default=0.0)

    def _tiene_npshr(self,indice):
        return indice<len(self.muestras_bombas) and any(
            p.valido and p.NPSHr is not None for p in self.muestras_bombas[indice])

    def _muestras_individuales(self,curva):
        indice = next((i for i,b in enumerate(self.curvas) if b is curva),None)
        return self.muestras_bombas[indice] if indice is not None and indice<len(self.muestras_bombas) else []

    def _trazar_curva_bomba_h(self,p,plot,curva,q_max,h_max,color_hex,estilo_linea,grosor=2.2,es_equivalente=False):
        muestras = self.muestras_equivalente if es_equivalente else self._muestras_individuales(curva)
        originales = muestras
        lineal = not es_equivalente and usa_puntos([curva])
        if lineal:
            from motor.resultados import PuntoCurva
            muestras = [PuntoCurva(float(q),float(h),True,'OK') for q,h in puntos_tabla(curva)]
        indice = next((i for i,b in enumerate(self.curvas) if b is curva),0)
        self._trazar_muestras(p,plot,muestras,q_max,h_max,color_hex,estilo_linea,grosor,
            etiqueta='Curva equivalente' if es_equivalente else self._etiqueta_serie('bomba',indice))
        if lineal:
            self._trazar_muestras(p,plot,originales,q_max,h_max,color_hex,estilo_linea,grosor,
                etiqueta=self._etiqueta_serie('bomba',indice),solo_invalidos=True)
        datos = [(pt.Q,pt.H) for pt in muestras if pt.valido]
        if es_equivalente:
            self._ultimo_puntos_eq_data = datos
        else:
            tabla = list(zip(curva.Q,curva.H))
            self._ultimo_trazo_bombas_modo.append(dict(modo=getattr(curva,'metodo','cuadratico'),
                puntos_polilinea=datos,puntos_tabla=tabla))
            if self.visibilidad.get('puntos_tabla',True):
                p.setPen(QPen(QColor(color_hex),1.8))
                p.setBrush(QBrush(QColor('#ffffff')))
                for q,h in tabla:
                    p.drawEllipse(QPointF(self._map_x(q,plot,q_max),self._map_y(h,plot,h_max)),3.6,3.6)

    def _trazar_curva_eficiencia(self,p,plot,curva,q_max,color_hex=None,estilo=Qt.SolidLine):
        self._trazar_muestras(p,plot,self._muestras_individuales(curva),q_max,100.0,
            color_hex or self.COLOR_EFICIENCIA,estilo,eficiencia=True,
            etiqueta=self._etiqueta_serie('eficiencia',next(i for i,b in enumerate(self.curvas) if b is curva)))

    def _formato_polinomio(self, b):
        if usa_puntos([b],self.metodo):
            return resumen_puntos(puntos_tabla(b))
        a = getattr(b, "poly_a", 0.0)
        b_val = getattr(b, "poly_b", 0.0)
        c = getattr(b, "poly_c", 0.0)
        partes = []
        if abs(a) > 1e-6:
            partes.append(f"{a:+.1f}Q²")
        if abs(b_val) > 1e-6:
            partes.append(f"{b_val:+.1f}Q")
        if abs(c) > 1e-6:
            partes.append(f"{c:+.1f}")
        poly_str = " ".join(partes).strip()
        if poly_str.startswith("+"):
            poly_str = poly_str[1:].strip()
        if not poly_str:
            poly_str = f"{c:.1f}"
        return f"{b.nombre}: H = {poly_str}"

    def _dibujar_chips_polinomios(self, p, plot_hq):
        chip_x = plot_hq.left() + 8.0
        chip_y = plot_hq.top() + 8.0
        font_chip = QFont("JetBrains Mono", 7, QFont.Bold)
        p.setFont(font_chip)
        fm = p.fontMetrics()

        chips = []
        for idx, b in enumerate(self.curvas):
            col = self._color_serie('bomba',idx)
            txt = self._formato_polinomio(b)
            chips.append((txt, col))

        if self.curva_eq is not None and len(self.curvas) > 1:
            chips.append(("Curva equivalente", self.COLOR_EQUIVALENTE))

        for txt_chip, col_chip in chips:
            w_c = fm.horizontalAdvance(txt_chip) + 12.0
            h_c = 18.0
            if chip_x + w_c > plot_hq.right() - 140.0:
                break
            rect_c = QRectF(chip_x, chip_y, w_c, h_c)
            p.setPen(QPen(QColor(col_chip), 1.0))
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawRoundedRect(rect_c, 3.0, 3.0)
            p.setPen(QColor(col_chip))
            p.drawText(rect_c, Qt.AlignCenter, txt_chip)
            chip_x += w_c + 6.0

    def _dibujar_marcador_op(self, p, plot, q_op, y_op, q_max, y_max, tipo="hq"):
        px = self._map_x(q_op, plot, q_max)
        py = self._map_y(y_op, plot, y_max)

        if tipo == "hq":
            self._marcador_op_hq_pos = QPointF(px, py)
        else:
            self._marcador_op_eta_pos = QPointF(px, py)
            self._ultimo_eta_marcador_op = float(y_op)

        # Líneas guía discontinuas a los ejes
        p.setPen(QPen(QColor(self.COLOR_OPERACION), 1.2, Qt.DashLine))
        p.drawLine(QPointF(px, plot.bottom()), QPointF(px, py))
        p.drawLine(QPointF(plot.left(), py), QPointF(px, py))

        # Punto circular destacado (sin recuadro flotante de texto para no repetir números)
        p.setPen(QPen(QColor("#ffffff"), 2.0))
        p.setBrush(QBrush(QColor(self.COLOR_OPERACION)))
        p.drawEllipse(QPointF(px, py), 5.5, 5.5)

    def _dibujar_ejes_y_textos(self, p, plot_hq, plot_eta, q_max, h_max):
        font_axis = QFont("JetBrains Mono", 8)
        font_title = QFont("Inter", 8, QFont.Bold)
        p.setFont(font_axis)
        p.setPen(QColor("#475569"))

        if plot_hq is not None:
            self._ticks_y_hq = self._marcas_y(plot_hq,h_max)
            for val_h in self._ticks_y_hq:
                y_pos = self._map_y(val_h,plot_hq,h_max)
                p.drawText(QRectF(plot_hq.left()-74,y_pos-9,68,18),
                           Qt.AlignRight|Qt.AlignVCenter,f'{val_h:g}')

            # Título Eje Y H-Q
            p.setFont(font_title)
            p.setPen(QColor("#0c4e77"))
            p.drawText(
                QRectF(plot_hq.left() - 74, plot_hq.top() - 20, 160, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                "ALTURA H [m]",
            )

        # Eje Y en η-Q (solo si plot_eta existe)
        if plot_eta is not None:
            p.setFont(font_axis)
            p.setPen(QColor("#475569"))
            self._ticks_y_eta = self._marcas_y(plot_eta,100.0)
            for val_eta in self._ticks_y_eta:
                y_pos = self._map_y(val_eta, plot_eta, 100.0)
                if plot_eta.top() - 2 <= y_pos <= plot_eta.bottom() + 2:
                    p.drawText(
                        QRectF(plot_eta.left() - 74, y_pos - 9, 68, 18),
                        Qt.AlignRight | Qt.AlignVCenter,
                        f"{val_eta:g}",
                    )

            # Título Eje Y η-Q
            p.setFont(font_title)
            p.setPen(QColor("#006398"))
            p.drawText(
                QRectF(plot_eta.left() - 74, plot_eta.top() - 20, 160, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                "EFICIENCIA η [%]",
            )

        # Eje X en la base del gráfico inferior (plot_eta si existe, o plot_hq)
        plot_base_x = plot_eta if plot_eta is not None else plot_hq
        p.setFont(font_axis)
        p.setPen(QColor("#475569"))
        n_x = 5
        self._rect_ultimo_q_ls = None
        for i in range(n_x + 2):
            val_q = (q_max / (n_x + 1)) * i
            x_pos = self._map_x(val_q, plot_base_x, q_max)
            if plot_base_x.left() - 5 <= x_pos <= plot_base_x.right() + 5:
                # Mostrar en m³/s y L/s sin solaparse con el título del eje X
                r_m3 = QRectF(x_pos - 52, plot_base_x.bottom() + 4, 104, 14)
                r_ls = QRectF(x_pos - 52, plot_base_x.bottom() + 19, 104, 15)
                p.drawText(
                    r_m3,
                    Qt.AlignHCenter | Qt.AlignTop,
                    f"{val_q:.4f}",
                )
                p.drawText(
                    r_ls,
                    Qt.AlignHCenter | Qt.AlignTop,
                    f"({val_q*1000.0:.1f} L/s)",
                )
                self._rect_ultimo_q_ls = r_ls

        # Título Eje X
        p.setFont(font_title)
        p.setPen(QColor("#0c4e77"))
        self._rect_titulo_x = QRectF(plot_base_x.left(), plot_base_x.bottom() + 42, plot_base_x.width(), 18)
        p.drawText(
            self._rect_titulo_x,
            Qt.AlignCenter,
            "CAUDAL Q [m³/s]",
        )

    def _dibujar_leyenda(self, p, plot, panel=None):
        if panel=='eficiencia':
            items_leyenda = [(f'━━ {self.nombres_bombas[i]} — η(Q)',
                              self._color_serie('eficiencia',i))
                for i,b in enumerate(self.curvas) if getattr(b,'tiene_eficiencia',False)
                and self.visibilidad.get('bombas',{}).get(i,True)]
            if self.eta_op is not None and self.visibilidad.get('punto_op',True):
                items_leyenda.append(('● Punto de Operación',self.COLOR_OPERACION))
        else:
            items_leyenda = []
            if panel!="eficiencia" and self.H_sistema_fn is not None and self.visibilidad.get("sistema", True):
                items_leyenda.append(("━━ Curva del Sistema", self.COLOR_SISTEMA))

            if len(self.curvas) == 1:
                if self.visibilidad.get("bombas", {}).get(0, True):
                    items_leyenda.append((f"━━ {self.nombres_bombas[0]}", self._color_serie('bomba',0)))
            else:
                for idx, b in enumerate(self.curvas):
                    if not self.visibilidad.get("bombas", {}).get(idx, True):
                        continue
                    col = self._color_serie('bomba',idx)
                    estilo_txt = "╌╌" if self.arreglo in ("serie", "paralelo") else "━━"
                    items_leyenda.append((f"{estilo_txt} {self.nombres_bombas[idx]}", col))
                if self.curva_eq is not None and self.visibilidad.get("curva_eq", True):
                    items_leyenda.append((f"━━ Curva Eq. ({self.arreglo.capitalize()})", self.COLOR_EQUIVALENTE))

            for idx in range(len(self.curvas)):
                if panel!="eficiencia" and self._tiene_npshr(idx) and self.visibilidad.get('npshr',{}).get(idx,True):
                    items_leyenda.append((f'··· {self._etiqueta_serie("npshr",idx)}',self._color_serie('npshr',idx)))
            if self.Q_op is not None and self.visibilidad.get("punto_op", True):
                items_leyenda.append(("● Punto de Operación", self.COLOR_OPERACION))

            tiene_eff = self.tiene_eficiencia and self.visibilidad.get("panel_eficiencia", True) and panel!="hq"
            if tiene_eff:
                items_leyenda.append(("━━ Eficiencia η(Q)", self.COLOR_EFICIENCIA))

        if not items_leyenda:
            return

        # Dibujar cajita de leyenda arriba a la derecha
        p.setFont(QFont("Inter", 8, QFont.DemiBold))
        fm = p.fontMetrics()

        ancho_total = sum(fm.horizontalAdvance(txt) + 16 for txt, _ in items_leyenda) + 12
        ley_rect = QRectF(plot.right() - ancho_total - 10, plot.top() + 8, ancho_total, 24)

        p.setPen(QPen(QColor("#cbd5e1"), 0.9))
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawRoundedRect(ley_rect, 4, 4)

        cur_x = ley_rect.left() + 8
        for txt, col in items_leyenda:
            p.setPen(QColor(col))
            p.drawText(QRectF(cur_x, ley_rect.top(), fm.horizontalAdvance(txt) + 12, 24), Qt.AlignVCenter, txt)
            cur_x += fm.horizontalAdvance(txt) + 16

    def exportar_imagen(self):
        return self._exportar_panel('hq')

    def exportar_imagen_eficiencia(self):
        if self.tiene_eficiencia and self.visibilidad.get('panel_eficiencia',True):
            return self._exportar_panel('eficiencia')

    def _exportar_panel(self,panel):
        """Exporta solo el panel elegido a la misma resolución, sin modificar la vista."""
        if not self.curvas and self.Q_op is None:
            QMessageBox.information(
                self, "Sin datos", "No hay datos de curvas de bomba calculados para exportar."
            )
            return

        nombre_sugerido = "curva_HQ.png" if panel=="hq" else "curva_eficiencia.png"
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
            ancho_logico = max(1000, self.width())
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
            self._dibujar_grafico_completo(p, rect_export, para_exportar=True,panel_exportar=panel)
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


class AutoFitEquationLabel(QLabel):
    """Ecuación completa, sin elipsis, alojada en un scroll horizontal."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._raw_text = text
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setWordWrap(False)
        self.setTextFormat(Qt.PlainText)
        self.setStyleSheet(
            "font-family: 'JetBrains Mono', 'Consolas', monospace; "
            "font-weight: 800; color: #0c4e77; border: none; background: transparent;"
        )

    def setText(self, text):
        self._raw_text = text
        super().setText(text)
        self._ajustar_fuente()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ajustar_fuente()

    def _ajustar_fuente(self):
        self.setFont(QFont('JetBrains Mono',14,QFont.Bold))
        self.ensurePolished()
        fm = self.fontMetrics()
        self.setFixedSize(fm.horizontalAdvance(self._raw_text)+12,fm.height()+8)



class SwatchTrazoCurva(QLabel):
    """Muestra visual del color y tipo de trazo de la curva para la lista de selección."""

    def __init__(self, color="#000000", estilo="solido", grosor=2.2, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 16)
        self.color = color
        self.estilo = estilo
        self.grosor = grosor
        self._dibujar()

    def _dibujar(self):
        pm = QPixmap(28, 16)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen_col = QColor(self.color)
        cy = 8.0

        if self.estilo == "punto_op":
            pen = QPen(pen_col, 1.2, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(2, cy), QPointF(26, cy))
            p.setPen(QPen(QColor("#ffffff"), 1.6))
            p.setBrush(QBrush(pen_col))
            p.drawEllipse(QPointF(14, cy), 4.0, 4.0)
        elif self.estilo == "puntos_tabla":
            p.setPen(QPen(pen_col, 1.6))
            p.setBrush(QBrush(QColor("#ffffff")))
            p.drawEllipse(QPointF(7, cy), 3.2, 3.2)
            p.drawEllipse(QPointF(21, cy), 3.2, 3.2)
        elif self.estilo == "punteado":
            pen = QPen(pen_col, self.grosor, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(2, cy), QPointF(26, cy))
        elif self.estilo == "puntos":
            p.setPen(QPen(pen_col,self.grosor,Qt.DotLine))
            p.drawLine(QPointF(2,cy),QPointF(26,cy))
        else:  # solido
            pen = QPen(pen_col, self.grosor, Qt.SolidLine)
            p.setPen(pen)
            p.drawLine(QPointF(2, cy), QPointF(26, cy))

        p.end()
        self.setPixmap(pm)


class PanelLateralCurvasBomba(QFrame):
    """
    Panel lateral derecho de la vista Curvas de Bomba (H - Q).
    Organiza la información de arriba hacia abajo, cada dato UNA sola vez:
    a) Dos números grandes: Q operación (L/s) y H operación (m), con m³/s bajo Q.
    b) Tarjeta Ecuación Total (lo más destacado): 22-26px autoajustable, borde de acento,
       términos con '−' y 'Q²', unidades, botón Copiar y línea gris de R² y Δ en Q_op.
    c) Lista de curvas con interruptor, swatch de color/trazo, nombre y ecuación.
    """

    def __init__(self, grafico, parent=None):
        super().__init__(parent)
        self.grafico = grafico
        self.setObjectName("panelLateralCurvasBomba")
        self.setStyleSheet(
            "QFrame#panelLateralCurvasBomba { background: #ffffff; border: 1px solid #dce4ee; border-radius: 8px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # -------------------------------------------------------------
        # a) Dos números grandes: "Q operación (L/s)" y "H operación (m)"
        # -------------------------------------------------------------
        fila_kpis = QHBoxLayout()
        fila_kpis.setContentsMargins(0, 0, 0, 0)
        fila_kpis.setSpacing(10)

        # Tarjeta Q op
        card_q = QFrame()
        card_q.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;")
        l_q = QVBoxLayout(card_q)
        l_q.setContentsMargins(10, 8, 10, 8)
        l_q.setSpacing(2)

        lbl_q_tit = QLabel("Q operación (L/s)")
        lbl_q_tit.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 10px; "
            "font-weight: 700; color: #64748b; border: none; background: transparent;"
        )
        l_q.addWidget(lbl_q_tit)

        self.lbl_qop_main = QLabel("— L/s")
        self.lbl_qop_main.setStyleSheet(
            "font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 19px; "
            "font-weight: 800; color: #0c4e77; border: none; background: transparent;"
        )
        l_q.addWidget(self.lbl_qop_main)

        self.lbl_qop_sub = QLabel("— m³/s")
        self.lbl_qop_sub.setStyleSheet(
            "font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; "
            "font-weight: 500; color: #72787f; border: none; background: transparent;"
        )
        l_q.addWidget(self.lbl_qop_sub)

        # Tarjeta H op
        card_h = QFrame()
        card_h.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px;")
        l_h = QVBoxLayout(card_h)
        l_h.setContentsMargins(10, 8, 10, 8)
        l_h.setSpacing(2)

        lbl_h_tit = QLabel("H operación (m)")
        lbl_h_tit.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 10px; "
            "font-weight: 700; color: #64748b; border: none; background: transparent;"
        )
        l_h.addWidget(lbl_h_tit)

        self.lbl_hop_main = QLabel("— m")
        self.lbl_hop_main.setStyleSheet(
            "font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 19px; "
            "font-weight: 800; color: #0c4e77; border: none; background: transparent;"
        )
        l_h.addWidget(self.lbl_hop_main)

        self.lbl_hop_sub = QLabel(" ")
        self.lbl_hop_sub.setStyleSheet(
            "font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; "
            "color: #72787f; border: none; background: transparent;"
        )
        l_h.addWidget(self.lbl_hop_sub)

        fila_kpis.addWidget(card_q, 1)
        fila_kpis.addWidget(card_h, 1)
        layout.addLayout(fila_kpis)

        # -------------------------------------------------------------
        # b) TARJETA "Ecuación total" (lo más destacado del panel)
        # -------------------------------------------------------------
        self.card_eq_total = QFrame()
        self.card_eq_total.setObjectName("cardLateralEqTotal")
        self.card_eq_total.setStyleSheet(
            "QFrame#cardLateralEqTotal { background-color: #f0f7ff; border: 1px solid #bfdbfe; "
            "border-left: 4px solid #006398; border-radius: 6px; }"
        )
        l_eq = QVBoxLayout(self.card_eq_total)
        l_eq.setContentsMargins(12, 10, 12, 10)
        l_eq.setSpacing(4)

        fila_top_eq = QHBoxLayout()
        fila_top_eq.setContentsMargins(0, 0, 0, 0)
        lbl_eq_titulo = self.lbl_eq_titulo = QLabel("ECUACIÓN TOTAL")
        lbl_eq_titulo.setWordWrap(True)
        lbl_eq_titulo.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 10px; "
            "font-weight: 700; color: #475569; letter-spacing: 0.5px; border: none; background: transparent;"
        )
        fila_top_eq.addWidget(lbl_eq_titulo)

        lbl_eq_unid = QLabel("(Q en m³/s, H en m)")
        lbl_eq_unid.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 9.5px; "
            "font-weight: 500; color: #64748b; border: none; background: transparent;"
        )
        fila_top_eq.addWidget(lbl_eq_unid)
        fila_top_eq.addStretch()

        self.btn_copiar_eq = QPushButton("Copiar")
        self.btn_copiar_eq.setCursor(Qt.PointingHandCursor)
        self.btn_copiar_eq.setFixedHeight(22)
        self.btn_copiar_eq.setStyleSheet(
            "QPushButton { font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 10px; "
            "font-weight: 600; color: #006398; background: #e0f2fe; border: 1px solid #bae6fd; "
            "border-radius: 3px; padding: 2px 8px; }"
            "QPushButton:hover { background: #bae6fd; color: #0c4e77; }"
        )
        self.btn_copiar_eq.clicked.connect(self._copiar_ecuacion)
        fila_top_eq.addWidget(self.btn_copiar_eq)
        l_eq.addLayout(fila_top_eq)

        self.lbl_eq_total = AutoFitEquationLabel("H(Q) = —")
        self.scroll_ecuacion = QScrollArea()
        self.scroll_ecuacion.setFrameShape(QFrame.NoFrame)
        self.scroll_ecuacion.setWidgetResizable(False)
        self.scroll_ecuacion.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_ecuacion.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_ecuacion.setWidget(self.lbl_eq_total)
        self.scroll_ecuacion.setFixedHeight(62)
        self.scroll_ecuacion.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Fixed)
        self.scroll_ecuacion.setMinimumWidth(0)
        l_eq.addWidget(self.scroll_ecuacion)

        self.lbl_eq_detalle = QLabel("—")
        self.lbl_eq_detalle.setWordWrap(True)
        self.lbl_eq_detalle.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 10.5px; "
            "color: #64748b; border: none; background: transparent;"
        )
        l_eq.addWidget(self.lbl_eq_detalle)
        layout.addWidget(self.card_eq_total)

        # -------------------------------------------------------------
        # c) LISTA DE CURVAS
        # -------------------------------------------------------------
        fila_curvas_hdr = QHBoxLayout()
        fila_curvas_hdr.setContentsMargins(0, 4, 0, 0)
        lbl_curvas_hdr = QLabel("LISTA DE CURVAS")
        lbl_curvas_hdr.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 10px; "
            "font-weight: 700; color: #475569; letter-spacing: 0.5px;"
        )
        fila_curvas_hdr.addWidget(lbl_curvas_hdr)
        fila_curvas_hdr.addStretch()

        layout.addLayout(fila_curvas_hdr)

        scroll_curvas = QScrollArea()
        scroll_curvas.setWidgetResizable(True)
        scroll_curvas.setFrameShape(QFrame.NoFrame)
        scroll_curvas.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_curvas.setStyleSheet("background: transparent;")

        self.w_lista_curvas = QWidget()
        self.layout_lista_curvas = QVBoxLayout(self.w_lista_curvas)
        self.layout_lista_curvas.setContentsMargins(0, 2, 0, 2)
        self.layout_lista_curvas.setSpacing(6)
        scroll_curvas.setWidget(self.w_lista_curvas)
        layout.addWidget(scroll_curvas, 1)

        self._checks_filas = {}
        self.chips_bombas_individuales = []
        self.grafico.visibilidad_cambiada.connect(self._sincronizar_checks)

    def _sincronizar_checks(self):
        for clave,chk in self._checks_filas.items():
            valor = (self.grafico.visibilidad.get(clave[0],{}).get(clave[1],True)
                     if isinstance(clave,tuple) else self.grafico.visibilidad.get(clave,True))
            previo = chk.blockSignals(True)
            chk.setChecked(valor)
            chk.blockSignals(previo)

    def _copiar_ecuacion(self):
        txt = (tabla_tsv(self._puntos_copia) if getattr(self,'_modo_puntos',False) else self.lbl_eq_total.text())
        if txt:
            from PyQt5.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.clipboard().setText(txt)
            self.btn_copiar_eq.setText("✓ Copiado")
            if not hasattr(self,'_timer_copiar'):
                self._timer_copiar = QTimer(self.btn_copiar_eq)
                self._timer_copiar.setSingleShot(True)
                self._timer_copiar.timeout.connect(lambda:self.btn_copiar_eq.setText('Copiar'))
            self._timer_copiar.start(1500)

    def actualizar(self):
        """Actualiza todos los valores del panel lateral según el estado actual de grafico_bombas."""
        g = self.grafico
        if not g.curvas or g.Q_op is None:
            return

        q_op = float(g.Q_op)
        h_op = float(g.H_op or 0.0)
        q_ls = q_op * 1000.0

        # a) Dos números grandes
        self.lbl_qop_main.setText(f"{q_ls:.2f} L/s")
        self.lbl_qop_sub.setText(f"{q_op:.4f} m³/s")
        self.lbl_hop_main.setText(f"{h_op:.2f} m")

        # b) Tarjeta Ecuación Total
        curvas = list(g.curvas)
        obj_eq = g.curva_eq or curvas[0]
        eq_info = getattr(g,'ecuacion_total',None) or {}

        self._modo_puntos = usa_puntos(curvas,g.metodo)
        if self._modo_puntos:
            self._puntos_copia = puntos_total(curvas,g.muestras_equivalente)
            self.lbl_eq_titulo.setText('Curva total (por puntos)' if len(curvas)==1 else 'Combinación por puntos')
            self.lbl_eq_total.setText(resumen_puntos(self._puntos_copia,len(curvas)>1))
            self.lbl_eq_detalle.setText('')
        else:
            self.lbl_eq_titulo.setText('ECUACIÓN TOTAL')
            raw_txt = eq_info.get("texto", "H(Q) = —")
            txt_eq = raw_txt.replace(" - ", " − ").replace("-", "−").replace("Q^2", "Q²").replace("Q2", "Q²")
            if not txt_eq.startswith("H(Q) =") and not txt_eq.startswith("H ="):
                txt_eq = f"H(Q) = {txt_eq}"
            self.lbl_eq_total.setText(txt_eq)

            metodo_actual = str(getattr(g, "metodo", getattr(obj_eq, "metodo", "cuadratico"))).lower()
            def error_texto(valor):
                return f'{valor:.6g} m' if valor is not None and math.isfinite(valor) else '—'
            errores = [error_texto(getattr(b,'error_max_ajuste',None)) for b in curvas]
            error_equivalente = error_texto(eq_info.get('error_max'))
            if len(curvas)==1:
                detalle = f'Ajuste cuadrático — error máx. {errores[0]}'
            else:
                ajustes = '; '.join(f'{nombre}: {error}' for nombre,error in zip(g.nombres_bombas,errores))
                if eq_info.get('tipo') == 'exacta':
                    detalle = f'Combinación exacta de curvas ajustadas — error máx. de cada ajuste: {ajustes}'
                else:
                    detalle = (f'Ajuste de la curva equivalente — error máx. {error_equivalente}; '
                               f'error máx. de cada ajuste: {ajustes}')
            self.lbl_eq_detalle.setText(detalle)

        # c) Reconstruir lista de curvas preservando el estado de los interruptores
        self._reconstruir_lista_curvas()

    def _crear_fila_curva(self, clave, nombre, subtexto="", swatch=None, valor_actual=True, callback=None):
        fila = QFrame()
        fila.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 5px; padding: 3px 6px; }"
            "QFrame:hover { background: #f1f5f9; border-color: #cbd5e1; }"
        )
        h = QHBoxLayout(fila)
        h.setContentsMargins(4, 3, 4, 3)
        h.setSpacing(8)

        chk = QCheckBox()
        chk.setChecked(bool(valor_actual))
        chk.setCursor(Qt.PointingHandCursor)
        chk.setStyleSheet("QCheckBox::indicator { width: 15px; height: 15px; }")
        if callback:
            chk.toggled.connect(callback)
        h.addWidget(chk)

        if swatch:
            h.addWidget(swatch)

        col_txt = QVBoxLayout()
        col_txt.setContentsMargins(0, 0, 0, 0)
        col_txt.setSpacing(1)

        lbl_nom = QLabel(nombre)
        lbl_nom.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
            "font-weight: 600; color: #1e293b; border: none; background: transparent;"
        )
        col_txt.addWidget(lbl_nom)

        if subtexto:
            lbl_sub = QLabel(subtexto)
            lbl_sub.setStyleSheet(
                "font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 10px; "
                "color: #64748b; border: none; background: transparent;"
            )
            col_txt.addWidget(lbl_sub)

        h.addLayout(col_txt, 1)
        self.layout_lista_curvas.addWidget(fila)
        return chk

    def _reconstruir_lista_curvas(self):
        while self.layout_lista_curvas.count():
            item = self.layout_lista_curvas.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._checks_filas = {}
        self.chips_bombas_individuales = []
        g = self.grafico
        curvas = list(g.curvas)
        n_bombas = len(curvas)

        # Fila 1: Curva del sistema
        chk_sis = self._crear_fila_curva(
            "sistema",
            "Curva del sistema",
            swatch=SwatchTrazoCurva("#006398", estilo="solido", grosor=2.4),
            valor_actual=g.visibilidad.get("sistema", True),
            callback=lambda val: g.set_visibilidad("sistema", val),
        )
        self._checks_filas["sistema"] = chk_sis

        # Fila 2..N+1: Cada bomba
        for idx, b in enumerate(curvas):
            col_b = g._color_serie('bomba',idx)
            nom_b = g.nombres_bombas[idx]
            eq_b_info = g.ecuaciones_bombas[idx] if idx < len(g.ecuaciones_bombas) else {}
            if usa_puntos(curvas,g.metodo):
                prefijo = 'Interpolación lineal' if usa_puntos([b],g.metodo) else 'Curva por muestras'
                txt_eq_b = f'{prefijo} · {len(puntos_tabla(b))} puntos'
            else:
                raw_eq_b = eq_b_info.get("texto", "")
                txt_eq_b = raw_eq_b.replace(" - ", " − ").replace("-", "−").replace("Q^2", "Q²").replace("Q2", "Q²")
                if txt_eq_b.startswith("H(Q) ="):
                    txt_eq_b = "H = " + txt_eq_b[6:].strip()

            chk_b = self._crear_fila_curva(
                ("bombas", idx),
                nom_b,
                subtexto=txt_eq_b,
                swatch=SwatchTrazoCurva(col_b, estilo="punteado" if n_bombas > 1 else "solido", grosor=2.2),
                valor_actual=g.visibilidad.get("bombas", {}).get(idx, True),
                callback=(lambda i: lambda val: g.set_visibilidad("bombas", val, sub_idx=i))(idx),
            )
            self._checks_filas[("bombas", idx)] = chk_b

            chip_ref = QLabel(f"● {nom_b}: {txt_eq_b}")
            chip_ref.setProperty("color_curva", col_b)
            self.chips_bombas_individuales.append(chip_ref)

        for idx in range(n_bombas):
            if not g._tiene_npshr(idx):
                continue
            nombre = g._etiqueta_serie('npshr',idx)
            chk = self._crear_fila_curva(('npshr',idx),nombre,
                swatch=SwatchTrazoCurva(g._color_serie('npshr',idx),estilo='puntos'),
                valor_actual=g.visibilidad.get('npshr',{}).get(idx,True),
                callback=lambda valor,i=idx:g.set_visibilidad('npshr',valor,sub_idx=i))
            chk.setToolTip(nombre)
            chk.parentWidget().setToolTip(nombre)
            self._checks_filas[('npshr',idx)] = chk

        # Fila N+2: Curva equivalente/total (si hay >= 2 bombas)
        if n_bombas >= 2:
            nom_eq = f"Curva equivalente ({g.arreglo.capitalize()})"
            chk_eq = self._crear_fila_curva(
                "curva_eq",
                nom_eq,
                swatch=SwatchTrazoCurva(g.COLOR_EQUIVALENTE, estilo="solido", grosor=3.2),
                valor_actual=g.visibilidad.get("curva_eq", True),
                callback=lambda val: g.set_visibilidad("curva_eq", val),
            )
            self._checks_filas["curva_eq"] = chk_eq

        # Fila N+3: Punto de operación
        chk_op = self._crear_fila_curva(
            "punto_op",
            "Punto de operación",
            swatch=SwatchTrazoCurva("#dc2626", estilo="punto_op"),
            valor_actual=g.visibilidad.get("punto_op", True),
            callback=lambda val: g.set_visibilidad("punto_op", val),
        )
        self._checks_filas["punto_op"] = chk_op

        # Fila N+4: Puntos de la tabla
        chk_pts = self._crear_fila_curva(
            "puntos_tabla",
            "Puntos de la tabla",
            swatch=SwatchTrazoCurva("#475569", estilo="puntos_tabla"),
            valor_actual=g.visibilidad.get("puntos_tabla", True),
            callback=lambda val: g.set_visibilidad("puntos_tabla", val),
        )
        self._checks_filas["puntos_tabla"] = chk_pts

        invalidas = g._muestras_invalidas()
        for clave,nombre,fuera in [('fuera_rango','× Fuera del rango de la bomba',True),
                                   ('muestras_invalidas','× Muestra no calculada',False)]:
            motivos = sorted({f'{etiqueta}: {p.estado}' for etiqueta,p in invalidas
                              if g._fuera_del_dominio(p)==fuera})
            if motivos:
                chk = self._crear_fila_curva(clave,nombre,valor_actual=g.visibilidad.get(clave,True),
                    callback=lambda valor,k=clave:g.set_visibilidad(k,valor))
                chk.setToolTip('\n'.join(motivos)+'\nNo representa H=0.')
                chk.parentWidget().setToolTip(chk.toolTip())
                self._checks_filas[clave] = chk

        self.layout_lista_curvas.addStretch()
        self._sincronizar_checks()


class ContenedorResponsiveHQ(QWidget):
    """
    Contenedor responsive para la vista Curvas de Bomba (H - Q).
    - Ancho >= 1100 px: Dos columnas (gráfico a la izquierda, panel lateral a la derecha).
    - Ancho < 1100 px: Panel lateral arriba del gráfico.
    """

    def __init__(self, grafico, panel_lateral, parent=None):
        super().__init__(parent)
        self.grafico = grafico
        self.panel_lateral = panel_lateral
        self._es_horizontal = None

        self.layout_box = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.layout_box.setContentsMargins(0, 0, 0, 0)
        self.layout_box.setSpacing(12)

        self._ajustar_layout(self.width() >= 1100 if self.width() > 0 else True)

    def _ajustar_layout(self, horizontal):
        if self._es_horizontal == horizontal:
            return
        self._es_horizontal = horizontal

        self.layout_box.removeWidget(self.grafico)
        self.layout_box.removeWidget(self.panel_lateral)

        if horizontal:
            # Gráfico a la izquierda, panel lateral a la derecha
            self.layout_box.setDirection(QBoxLayout.LeftToRight)
            self.layout_box.addWidget(self.grafico, 1)
            self.layout_box.addWidget(self.panel_lateral, 0)
            self.panel_lateral.setFixedWidth(360)
            self.panel_lateral.setMaximumHeight(16777215)
            self.panel_lateral.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        else:
            # Panel lateral arriba del gráfico
            self.layout_box.setDirection(QBoxLayout.TopToBottom)
            self.layout_box.addWidget(self.panel_lateral, 0)
            self.layout_box.addWidget(self.grafico, 1)
            self.panel_lateral.setMaximumWidth(16777215)
            self.panel_lateral.setMinimumWidth(0)
            self.panel_lateral.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        ancho = event.size().width()
        self._ajustar_layout(ancho >= 1100)
