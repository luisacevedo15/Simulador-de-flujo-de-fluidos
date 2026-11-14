"""Construcción de los widgets: cabecera, paneles, lienzo y barra."""

from PyQt5.QtCore import QPointF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap, QPolygonF
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.escena import CanvasView, GridScene
from ui.constantes import TEMA_STITCH
from ui.perfil_egl import WidgetPerfilEGLHGL
from ui.grafico_bombas import (
    WidgetGraficoBombas,
    PanelLateralCurvasBomba,
    ContenedorResponsiveHQ,
)
from ui.layouts import FlowLayout, PilaPaginaActual
from ui.widgets import _ContenedorHojaExcel, _HojaExcelWidget
from ui.iconos import crear_icono_herramienta
from ui.controles_modernos import SelectorTrazado
from ui.transiciones import IndicadorNavegacion


class InterfazMixin:
    """Construcción de los widgets: cabecera, paneles, lienzo y barra."""

    def _build_header(self):
        header = QFrame()
        header.setObjectName("stitchHeaderBar")
        header.setFixedHeight(48)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 0, 14, 0)
        h_layout.setSpacing(8)

        lbl_ico = QLabel()
        lbl_ico.setPixmap(
            crear_icono_herramienta("simulador_header", TEMA_STITCH["primary"]).pixmap(20, 20)
        )
        lbl_ico.setFixedSize(22, 22)
        lbl_ico.setAlignment(Qt.AlignCenter)
        h_layout.addWidget(lbl_ico)

        lbl_title = QLabel("Simulador de Fluidos")
        lbl_title.setObjectName("stitchHeaderTitle")
        lbl_title.setWordWrap(False)
        h_layout.addWidget(lbl_title)

        lbl_slash = QLabel("/")
        lbl_slash.setObjectName("stitchHeaderSlash")
        lbl_slash.setWordWrap(False)
        h_layout.addWidget(lbl_slash)

        lbl_sub = QLabel("Ingeniería Química CAD")
        lbl_sub.setObjectName("stitchHeaderSub")
        lbl_sub.setWordWrap(False)
        h_layout.addWidget(lbl_sub)

        sep_v = QFrame()
        sep_v.setObjectName("stitchHeaderSep")
        sep_v.setFixedSize(1, 14)
        h_layout.addSpacing(4)
        h_layout.addWidget(sep_v)
        h_layout.addStretch()

        # Selector global de trazado en la parte superior (arriba de Guardar y Cargar)
        self.contenedor_trazado = QWidget()
        self.contenedor_trazado.setObjectName("contenedorTrazadoGlobal")
        layout_trazado = QHBoxLayout(self.contenedor_trazado)
        layout_trazado.setContentsMargins(0, 0, 0, 0)
        layout_trazado.setSpacing(6)

        self.combo_trazado_global = SelectorTrazado()
        self.combo_trazado_global.setObjectName("comboTrazadoHeader")
        self.combo_trazado_global.addItems(["Trazado: Recto", "Trazado: Ortogonal"])
        self.combo_trazado_global.setCurrentText("Trazado: Recto")
        self.combo_trazado_global.setFixedHeight(34)
        self.combo_trazado_global.setMinimumWidth(190)
        self.combo_trazado_global.currentTextChanged.connect(self._on_trazado_global_cambiado)
        layout_trazado.addWidget(self.combo_trazado_global)

        # Acceso a la guía visual con los videos Recto y Ortogonal.
        self.btn_ayuda_trazado = QPushButton("?")
        self.btn_ayuda_trazado.setObjectName("btnAyudaTrazado")
        self.btn_ayuda_trazado.setFixedSize(22, 22)
        self.btn_ayuda_trazado.setCursor(Qt.PointingHandCursor)
        self.btn_ayuda_trazado.setToolTip('Ver demostraciones de los trazados Recto y Ortogonal')
        self.btn_ayuda_trazado.setAccessibleName('Abrir guía visual de trazadores')
        self.btn_ayuda_trazado.setStyleSheet(
            "QPushButton#btnAyudaTrazado { "
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; font-weight: 700; "
            "color: #64748b; background-color: #f1f5f9; border: 1px solid #cbd5e1; "
            "border-radius: 11px; padding: 0px; text-align: center; }"
            "QPushButton#btnAyudaTrazado:hover { background-color: #e2e8f0; color: #334155; border-color: #94a3b8; }"
            "QPushButton#btnAyudaTrazado:pressed { background-color: #cbd5e1; }"
        )
        self.btn_ayuda_trazado.clicked.connect(self.mostrar_ayuda_trazado)
        layout_trazado.addWidget(self.btn_ayuda_trazado)

        h_layout.addWidget(self.contenedor_trazado)
        return header

    def mostrar_ayuda_trazado(self):
        """Abre una única guía, iniciada en el trazado actual del usuario."""
        guia = getattr(self, '_guia_trazado', None)
        if guia is None:
            from ui.guia_trazado import DialogoGuiaTrazado
            guia = DialogoGuiaTrazado(self, getattr(self, 'trazado_global', 'recto'))
            self._guia_trazado = guia
            guia.finished.connect(lambda resultado: setattr(self, '_guia_trazado', None))
        guia.show()
        guia.raise_()
        guia.activateWindow()

    def _on_trazado_global_cambiado(self, texto):
        modo = "ortogonal" if "ortogonal" in str(texto).lower() else "recto"
        scene = getattr(self, "canvas_view", None)
        scene = scene.scene() if scene else None
        if modo == "ortogonal" and scene is not None and hasattr(scene, "validar_compatibilidad_ortogonal"):
            compatible, motivo = scene.validar_compatibilidad_ortogonal()
            if not compatible:
                QMessageBox.warning(self, "Trazado no compatible", motivo)
                if hasattr(self, "_reset_selector_trazado"):
                    self._reset_selector_trazado()
                elif hasattr(self, "combo_trazado_global") and self.combo_trazado_global is not None:
                    self.combo_trazado_global.blockSignals(True)
                    idx = self.combo_trazado_global.findText("Trazado: Recto")
                    self.combo_trazado_global.setCurrentIndex(idx if idx >= 0 else 0)
                    self.combo_trazado_global.blockSignals(False)
                return
        self.trazado_global = modo
        if scene is not None:
            scene.trazado_global = modo

    @staticmethod
    def _aplicar_sombra_stitch(widget, blur=10, dx=0, dy=2, alpha=18):
        efecto = QGraphicsDropShadowEffect(widget)
        efecto.setBlurRadius(blur)
        efecto.setOffset(dx, dy)
        efecto.setColor(QColor(11, 28, 48, alpha))
        widget.setGraphicsEffect(efecto)

    def _build_ui(self):
        root = QWidget()
        root_vbox = QVBoxLayout(root)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        # Cabecera superior Stitch (48px) + contenedor para la barra de herramientas (44px)
        self.top_bars_container = QFrame()
        self.top_bars_container.setObjectName("stitchTopContainer")
        self.top_bars_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.top_bars_layout = QVBoxLayout(self.top_bars_container)
        self.top_bars_layout.setContentsMargins(0, 0, 0, 0)
        self.top_bars_layout.setSpacing(0)
        self.header_bar = self._build_header()
        self.top_bars_layout.addWidget(self.header_bar)
        root_vbox.addWidget(self.top_bars_container)

        body_widget = QWidget()
        root_layout = QHBoxLayout(body_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Barra lateral izquierda de navegación (~70px, 3 ítems: CAD, TABLA, CURVAS)
        nav_bar = QFrame()
        nav_bar.setObjectName("leftNavBar")
        nav_bar.setFixedWidth(TEMA_STITCH.get("nav_bar_width", 70))
        nav_layout = QVBoxLayout(nav_bar)
        nav_layout.setContentsMargins(6, 12, 6, 12)
        nav_layout.setSpacing(6)

        self.btn_nav_cad = QToolButton()
        self.btn_nav_cad.setObjectName("navBtnActive")
        self.btn_nav_cad.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_nav_cad.setIcon(
            crear_icono_herramienta("cad", TEMA_STITCH.get("nav_active_text", TEMA_STITCH["primary"]))
        )
        self.btn_nav_cad.setIconSize(QSize(22, 22))
        self.btn_nav_cad.setText("CAD")
        self.btn_nav_cad.setFixedSize(58, 52)
        self.btn_nav_cad.setCursor(Qt.PointingHandCursor)
        self.btn_nav_cad.clicked.connect(lambda: self._cambiar_vista_central("cad"))
        nav_layout.addWidget(self.btn_nav_cad, 0, Qt.AlignHCenter)

        self.btn_nav_tabla = QToolButton()
        self.btn_nav_tabla.setObjectName("navBtnInactive")
        self.btn_nav_tabla.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_nav_tabla.setIcon(
            crear_icono_herramienta("tabla", TEMA_STITCH["on_surface_variant"])
        )
        self.btn_nav_tabla.setIconSize(QSize(22, 22))
        self.btn_nav_tabla.setText("TABLA")
        self.btn_nav_tabla.setFixedSize(58, 52)
        self.btn_nav_tabla.setCursor(Qt.PointingHandCursor)
        self.btn_nav_tabla.clicked.connect(lambda: self._cambiar_vista_central("tabla"))
        nav_layout.addWidget(self.btn_nav_tabla, 0, Qt.AlignHCenter)

        self.btn_nav_curvas = QToolButton()
        self.btn_nav_curvas.setObjectName("navBtnInactive")
        self.btn_nav_curvas.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.btn_nav_curvas.setIcon(
            crear_icono_herramienta("curvas", TEMA_STITCH["on_surface_variant"])
        )
        self.btn_nav_curvas.setIconSize(QSize(22, 22))
        self.btn_nav_curvas.setText("CURVAS")
        self.btn_nav_curvas.setFixedSize(58, 52)
        self.btn_nav_curvas.setCursor(Qt.PointingHandCursor)
        self.btn_nav_curvas.clicked.connect(lambda: self._cambiar_vista_central("curvas"))
        nav_layout.addWidget(self.btn_nav_curvas, 0, Qt.AlignHCenter)
        nav_layout.addStretch()

        self.indicador_nav = IndicadorNavegacion(nav_bar)

        root_layout.addWidget(nav_bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("mainSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(2)
        self.main_splitter = splitter

        splitter.addWidget(self._build_canvas())
        self.side_panel = self._build_side_panel()
        splitter.addWidget(self.side_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([830, 390])

        root_layout.addWidget(splitter, 1)
        root_vbox.addWidget(body_widget, 1)
        self.setCentralWidget(root)

        # Barra de estado inferior fina con atajos de uso
        self.status_bar = self.statusBar()
        self.status_bar.setObjectName("mainStatusBar")
        self.status_bar.setSizeGripEnabled(False)
        self.lbl_shortcuts_status = QLabel("  Rueda: zoom  ·  Arrastre derecho: desplazar  ·  Supr: eliminar  ·  Ctrl+Z: deshacer")
        self.lbl_shortcuts_status.setObjectName("statusShortcutsLabel")
        self.status_bar.addWidget(self.lbl_shortcuts_status)

        self.canvas_view.scene().selectionChanged.connect(self._on_seleccion_cambiada)
        self.canvas_view.scene().elementos_modificados.connect(self._on_elementos_modificados)

    def _build_canvas(self):
        scene = GridScene(width=2000, height=2000, main_window=self)
        self.canvas_view = CanvasView(scene)

        # Página 1: Vista TABLA (Memoria de cálculo estilo Google Stitch)
        self.panel_vista_tabla = QFrame()
        self.panel_vista_tabla.setObjectName("tablaPreviewPanel")
        tabla_root_layout = QVBoxLayout(self.panel_vista_tabla)
        tabla_root_layout.setContentsMargins(16, 14, 16, 14)
        tabla_root_layout.setSpacing(0)

        # Tarjeta principal que aloja la cabecera, barra de fórmula y hoja
        card_tabla = QFrame()
        card_tabla.setObjectName("tablaCardMain")
        card_tabla_layout = QVBoxLayout(card_tabla)
        card_tabla_layout.setContentsMargins(0, 0, 0, 0)
        card_tabla_layout.setSpacing(0)

        # Cabecera de la hoja (48px alto, Stitch slim toolbar)
        self.cab_tabla_frame = QFrame()
        self.cab_tabla_frame.setObjectName("tablaHeaderFrame")
        cab_tabla_layout = QHBoxLayout(self.cab_tabla_frame)
        cab_tabla_layout.setContentsMargins(14, 8, 14, 8)
        cab_tabla_layout.setSpacing(10)

        icono_hoja_box = QLabel()
        icono_hoja_box.setObjectName("tablaIconBox")
        icono_hoja_box.setFixedSize(28, 28)
        icono_hoja_box.setAlignment(Qt.AlignCenter)
        icono_hoja_box.setPixmap(crear_icono_herramienta("tabla", "#0284c7").pixmap(18, 18))
        cab_tabla_layout.addWidget(icono_hoja_box)

        self.lbl_tabla_titulo = QLabel("Memoria de cálculo — Sistema en Paralelo")
        self.lbl_tabla_titulo.setObjectName("tablaTitulo")
        cab_tabla_layout.addWidget(self.lbl_tabla_titulo)

        self.lbl_tabla_badge = QLabel("  Sin datos de simulación  ")
        self.lbl_tabla_badge.setObjectName("tablaBadge")
        cab_tabla_layout.addWidget(self.lbl_tabla_badge)

        cab_tabla_layout.addStretch()

        # Botón Exportar Memoria (.xlsx) (Sólido Primario Stitch)
        self.btn_tabla_exportar = QPushButton(" Exportar Memoria (.xlsx)")
        self.btn_tabla_exportar.setObjectName("btnTablaExportar")
        self.btn_tabla_exportar.setIcon(crear_icono_herramienta("descargar", "#ffffff"))
        self.btn_tabla_exportar.setIconSize(QSize(14, 14))
        self.btn_tabla_exportar.setCursor(Qt.PointingHandCursor)
        self.btn_tabla_exportar.clicked.connect(self._exportar_excel)
        cab_tabla_layout.addWidget(self.btn_tabla_exportar)

        card_tabla_layout.addWidget(self.cab_tabla_frame)

        # Barra de fórmula bajo la cabecera (Stitch formula bar)
        self.barra_formula_frame = QFrame()
        self.barra_formula_frame.setObjectName("tablaFormulaBar")
        bar_form_layout = QHBoxLayout(self.barra_formula_frame)
        bar_form_layout.setContentsMargins(12, 4, 12, 4)
        bar_form_layout.setSpacing(8)

        self.lbl_tabla_ref = QLabel("—")
        self.lbl_tabla_ref.setObjectName("tablaCellRef")
        self.lbl_tabla_ref.setFixedSize(56, 24)
        self.lbl_tabla_ref.setAlignment(Qt.AlignCenter)
        bar_form_layout.addWidget(self.lbl_tabla_ref)

        sep_form = QFrame()
        sep_form.setFrameShape(QFrame.VLine)
        sep_form.setFrameShadow(QFrame.Plain)
        sep_form.setStyleSheet("color: #cbd5e1; background-color: #cbd5e1; max-width: 1px; max-height: 16px;")
        bar_form_layout.addWidget(sep_form)

        lbl_fx = QLabel("fx")
        lbl_fx.setStyleSheet(
            "font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 12px; "
            "font-weight: 700; color: #94a3b8; background: transparent;"
        )
        bar_form_layout.addWidget(lbl_fx)

        self.txt_tabla_formula = QLineEdit()
        self.txt_tabla_formula.setObjectName("tablaFormulaInput")
        self.txt_tabla_formula.setReadOnly(True)
        self.txt_tabla_formula.setPlaceholderText("Hoja vacía. Ninguna celda seleccionada.")
        bar_form_layout.addWidget(self.txt_tabla_formula, 1)

        lbl_modo_lectura = QLabel("Modo Lectura / Solo Consulta")
        lbl_modo_lectura.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
            "font-weight: 500; color: #94a3b8; background: transparent; padding-right: 4px;"
        )
        bar_form_layout.addWidget(lbl_modo_lectura)

        card_tabla_layout.addWidget(self.barra_formula_frame)

        # Stack de contenido: Página 0 = Estado Vacío, Página 1 = Hoja con datos y HUD
        self.stack_tabla = QStackedWidget()
        self.stack_tabla.setObjectName("stackTablaContenido")

        # Página 0: Estado Vacío de Stitch
        self.widget_tabla_vacia = QWidget()
        vacia_layout = QVBoxLayout(self.widget_tabla_vacia)
        vacia_layout.setAlignment(Qt.AlignCenter)
        vacia_layout.setContentsMargins(32, 40, 32, 40)
        vacia_layout.setSpacing(12)

        ico_box = QFrame()
        ico_box.setFixedSize(80, 80)
        ico_box.setStyleSheet(
            "background-color: #eff6ff; border: 1px solid #dbeafe; border-radius: 20px;"
        )
        ico_box_lay = QVBoxLayout(ico_box)
        ico_box_lay.setContentsMargins(0, 0, 0, 0)
        ico_box_lay.setAlignment(Qt.AlignCenter)
        lbl_ico_vacio = QLabel()
        pm_vacio = QPixmap(42, 42)
        pm_vacio.fill(Qt.transparent)
        p_v = QPainter(pm_vacio)
        p_v.setRenderHint(QPainter.Antialiasing)
        p_v.setPen(QPen(QColor("#0284c7"), 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p_v.setBrush(Qt.NoBrush)
        poly = QPolygonF([QPointF(9, 5), QPointF(24, 5), QPointF(33, 13), QPointF(33, 37), QPointF(9, 37)])
        p_v.drawPolygon(poly)
        p_v.drawLine(24, 5, 24, 13)
        p_v.drawLine(24, 13, 33, 13)
        p_v.drawLine(15, 21, 27, 21)
        p_v.drawLine(15, 26, 27, 26)
        p_v.drawLine(15, 31, 23, 31)
        p_v.end()
        lbl_ico_vacio.setPixmap(pm_vacio)
        ico_box_lay.addWidget(lbl_ico_vacio)
        vacia_layout.addWidget(ico_box, 0, Qt.AlignCenter)

        lbl_tit_vacio = QLabel("Memoria de Cálculo no generada")
        lbl_tit_vacio.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 16px; "
            "font-weight: 700; color: #1e293b; margin-top: 6px;"
        )
        lbl_tit_vacio.setAlignment(Qt.AlignCenter)
        vacia_layout.addWidget(lbl_tit_vacio)

        lbl_sub_vacio = QLabel("Primero calcula un sistema para ver la memoria de cálculo")
        lbl_sub_vacio.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 13px; "
            "color: #64748b; margin-bottom: 8px;"
        )
        lbl_sub_vacio.setAlignment(Qt.AlignCenter)
        vacia_layout.addWidget(lbl_sub_vacio)

        self.btn_ir_cad_tabla = QPushButton("  Ir a CAD")
        self.btn_ir_cad_tabla.setIcon(crear_icono_herramienta("flecha_atras", "#ffffff"))
        self.btn_ir_cad_tabla.setIconSize(QSize(15, 15))
        self.btn_ir_cad_tabla.setCursor(Qt.PointingHandCursor)
        self.btn_ir_cad_tabla.setFixedHeight(38)
        self.btn_ir_cad_tabla.setStyleSheet(
            "QPushButton { background-color: #0284c7; color: #ffffff; border: none; "
            "border-radius: 8px; font-family: 'Inter', 'Segoe UI'; font-size: 13px; "
            "font-weight: 600; padding: 0 20px; }"
            "QPushButton:hover { background-color: #0369a1; }"
            "QPushButton:pressed { background-color: #0c4e77; }"
        )
        self.btn_ir_cad_tabla.clicked.connect(lambda: self._cambiar_vista_central("cad"))
        vacia_layout.addWidget(self.btn_ir_cad_tabla, 0, Qt.AlignCenter)

        self.stack_tabla.addWidget(self.widget_tabla_vacia)

        # Página 1: Hoja con datos y HUD flotante
        self.contenedor_hoja = _ContenedorHojaExcel()
        self.contenedor_hoja.setObjectName("contenedorHojaExcel")
        c_layout = QVBoxLayout(self.contenedor_hoja)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        self.tabla_excel_preview = _HojaExcelWidget(self, self.contenedor_hoja)
        self.tabla_excel_preview.setObjectName("tablaExcelPreview")
        self.tabla_excel_preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_excel_preview.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.tabla_excel_preview.setAlternatingRowColors(False)
        self.tabla_excel_preview.setShowGrid(True)
        self.tabla_excel_preview.setWordWrap(True)
        self.tabla_excel_preview.currentCellChanged.connect(self._on_tabla_celda_actual)
        c_layout.addWidget(self.tabla_excel_preview)

        # Pastilla flotante HUD Zoom: [ - ] 100% [ + ] [ ⛶ ]
        self.hud_tabla_zoom = QFrame(self.contenedor_hoja)
        self.hud_tabla_zoom.setObjectName("hudZoomFrame")
        hud_z_layout = QHBoxLayout(self.hud_tabla_zoom)
        hud_z_layout.setContentsMargins(4, 3, 4, 3)
        hud_z_layout.setSpacing(2)

        btn_t_out = QPushButton("-", self.hud_tabla_zoom)
        btn_t_out.setObjectName("hudZoomBtn")
        btn_t_out.setFixedSize(26, 24)
        btn_t_out.setCursor(Qt.PointingHandCursor)
        btn_t_out.setToolTip("Alejar hoja (Ctrl + −)")
        btn_t_out.clicked.connect(self._zoom_tabla_out)

        self.lbl_tabla_zoom_pct = QLabel("100%", self.hud_tabla_zoom)
        self.lbl_tabla_zoom_pct.setObjectName("hudZoomLabel")
        self.lbl_tabla_zoom_pct.setAlignment(Qt.AlignCenter)
        self.lbl_tabla_zoom_pct.setFixedWidth(44)

        btn_t_in = QPushButton("+", self.hud_tabla_zoom)
        btn_t_in.setObjectName("hudZoomBtn")
        btn_t_in.setFixedSize(26, 24)
        btn_t_in.setCursor(Qt.PointingHandCursor)
        btn_t_in.setToolTip("Acercar hoja (Ctrl + +)")
        btn_t_in.clicked.connect(self._zoom_tabla_in)

        btn_t_reset = QPushButton("⛶", self.hud_tabla_zoom)
        btn_t_reset.setObjectName("hudZoomBtn")
        btn_t_reset.setFixedSize(26, 24)
        btn_t_reset.setCursor(Qt.PointingHandCursor)
        btn_t_reset.setToolTip("Restablecer zoom 100% (Ctrl + 0)")
        btn_t_reset.clicked.connect(self._zoom_tabla_reset)

        hud_z_layout.addWidget(btn_t_out)
        hud_z_layout.addWidget(self.lbl_tabla_zoom_pct)
        hud_z_layout.addWidget(btn_t_in)
        hud_z_layout.addWidget(btn_t_reset)
        self.hud_tabla_zoom.adjustSize()
        self.contenedor_hoja.set_hud(self.hud_tabla_zoom)

        self.stack_tabla.addWidget(self.contenedor_hoja)
        card_tabla_layout.addWidget(self.stack_tabla, 1)
        tabla_root_layout.addWidget(card_tabla, 1)

        self._mostrar_tabla_vacia()

        # Página 2: Vista CURVAS (Página completa Stitch: vista con gráfico + estado vacío)
        self.panel_vista_curvas = QFrame()
        self.panel_vista_curvas.setObjectName("curvasPreviewPanel")
        curvas_outer = QVBoxLayout(self.panel_vista_curvas)
        curvas_outer.setContentsMargins(16, 14, 16, 14)
        curvas_outer.setSpacing(10)

        # Barra superior contextual de CURVAS (Volver a CAD + badge Vista Exclusiva EGL / HGL)
        sub_bar = QFrame()
        sub_bar.setObjectName("curvasSubHeader")
        sub_bar_layout = FlowLayout(sub_bar)
        sub_bar_layout.setContentsMargins(10, 6, 10, 6)
        sub_bar_layout.setSpacing(6)

        def _fm_css_bold(px):
            f = QFont("Segoe UI")
            if hasattr(f, "setFamilies"):
                f.setFamilies(["Inter", "Segoe UI"])
            f.setPixelSize(px)
            f.setWeight(QFont.Bold)
            return QFontMetrics(f)

        self.btn_volver_cad_curvas = QPushButton(
            crear_icono_herramienta("flecha_atras", "#0b1c30"), " Volver a CAD"
        )
        self.btn_volver_cad_curvas.setObjectName("curvasBackBtn")
        self.btn_volver_cad_curvas.setIconSize(QSize(16, 16))
        self.btn_volver_cad_curvas.setCursor(Qt.PointingHandCursor)
        self.btn_volver_cad_curvas.clicked.connect(lambda: self._cambiar_vista_central("cad"))
        sub_bar_layout.addWidget(self.btn_volver_cad_curvas)

        sep_curvas = QFrame()
        sep_curvas.setFixedSize(1, 18)
        sep_curvas.setStyleSheet("background-color: #c1c7cf; border: none;")
        sub_bar_layout.addWidget(sep_curvas)

        # Selector segmentado en barra superior de CURVAS: [ Líneas de Energía (EGL / HGL) | Curvas de Bomba (H - Q) ]
        self.seg_curvas_frame = QFrame()
        self.seg_curvas_frame.setObjectName("segmentedContainer")
        seg_curvas_layout = QHBoxLayout(self.seg_curvas_frame)
        seg_curvas_layout.setContentsMargins(2, 2, 2, 2)
        seg_curvas_layout.setSpacing(2)

        self.btn_curvas_egl = QPushButton(
            crear_icono_herramienta("curvas", "#006398"), " Líneas de Energía (EGL / HGL)"
        )
        self.btn_curvas_egl.setObjectName("segTabBtn")
        self.btn_curvas_egl.setIconSize(QSize(14, 14))
        self.btn_curvas_egl.setCheckable(True)
        self.btn_curvas_egl.setChecked(True)
        self.btn_curvas_egl.clicked.connect(lambda: self._cambiar_modo_vista_curvas(0))

        self.btn_curvas_bomba = QPushButton(
            crear_icono_herramienta("bomba", "#72787f"), " Curvas de Bomba (H - Q)"
        )
        self.btn_curvas_bomba.setObjectName("segTabBtn")
        self.btn_curvas_bomba.setIconSize(QSize(14, 14))
        self.btn_curvas_bomba.setCheckable(True)
        self.btn_curvas_bomba.setChecked(False)
        self.btn_curvas_bomba.clicked.connect(lambda: self._cambiar_modo_vista_curvas(1))

        fm_tabs = _fm_css_bold(12)
        for btn_tab in (self.btn_curvas_egl, self.btn_curvas_bomba):
            btn_tab.setCursor(Qt.PointingHandCursor)
            btn_tab.setMinimumWidth(fm_tabs.horizontalAdvance(btn_tab.text()) + 14 + 28)

        seg_curvas_layout.addWidget(self.btn_curvas_egl)
        seg_curvas_layout.addWidget(self.btn_curvas_bomba)
        sub_bar_layout.addWidget(self.seg_curvas_frame)

        self.sep_curvas_controles = QFrame()
        self.sep_curvas_controles.setFixedSize(1, 18)
        self.sep_curvas_controles.setStyleSheet("background-color: #c1c7cf; border: none;")
        self.sep_curvas_controles.hide()
        sub_bar_layout.addWidget(self.sep_curvas_controles)

        self.chk_linea_piezometrica = QPushButton(
            crear_icono_herramienta("trazo_discontinuo", "#2980b9"), " Piezométrica (HGL)"
        )
        self.chk_linea_piezometrica.setObjectName("curvasLineToggleHgl")
        self.chk_linea_piezometrica.setIconSize(QSize(16, 14))
        self.chk_linea_piezometrica.setCheckable(True)
        self.chk_linea_piezometrica.setChecked(True)
        self.chk_linea_piezometrica.setCursor(Qt.PointingHandCursor)
        self.chk_linea_piezometrica.setToolTip("Mostrar u ocultar Línea Piezométrica (HGL = z + P/γ)")
        self.chk_linea_piezometrica.toggled.connect(self._on_toggle_linea_piezometrica)
        self.chk_linea_piezometrica.hide()
        sub_bar_layout.addWidget(self.chk_linea_piezometrica)

        self.chk_linea_energia = QPushButton(
            crear_icono_herramienta("trazo_solido", "#e74c3c"), " Energía (EGL)"
        )
        self.chk_linea_energia.setObjectName("curvasLineToggleEgl")
        self.chk_linea_energia.setIconSize(QSize(16, 14))
        self.chk_linea_energia.setCheckable(True)
        self.chk_linea_energia.setChecked(True)
        self.chk_linea_energia.setCursor(Qt.PointingHandCursor)
        self.chk_linea_energia.setToolTip("Mostrar u ocultar Línea de Energía Total (EGL = HGL + v²/2g)")
        self.chk_linea_energia.toggled.connect(self._on_toggle_linea_energia)
        self.chk_linea_energia.hide()
        sub_bar_layout.addWidget(self.chk_linea_energia)

        self.seg_escala_frame = QFrame()
        self.seg_escala_frame.setObjectName("segmentedContainer")
        seg_escala_layout = QHBoxLayout(self.seg_escala_frame)
        seg_escala_layout.setContentsMargins(2, 2, 2, 2)
        seg_escala_layout.setSpacing(2)

        self.btn_modo_didactico = QPushButton("Esquema didáctico")
        self.btn_modo_didactico.setObjectName("curvasEscalaBtnDidactico")
        self.btn_modo_didactico.setCheckable(True)
        self.btn_modo_didactico.setChecked(True)
        self.btn_modo_didactico.setToolTip(
            "Oculta los números del eje vertical para destacar dónde se pierde la energía.\n"
            "Las cifras reales están en las tarjetas inferiores."
        )

        self.btn_modo_exacto = QPushButton("Valores exactos")
        self.btn_modo_exacto.setObjectName("curvasEscalaBtnExacto")
        self.btn_modo_exacto.setCheckable(True)
        self.btn_modo_exacto.setChecked(False)
        self.btn_modo_exacto.setToolTip(
            "Muestra las cotas exactas en el eje Y y los niveles z₁ y z₂ sobre la gráfica."
        )
        self.btn_modo_exacto.toggled.connect(self._on_toggle_mostrar_valores_curvas)

        fm_escala = _fm_css_bold(11)
        for btn_escala in (self.btn_modo_didactico, self.btn_modo_exacto):
            btn_escala.setIconSize(QSize(0, 0))
            btn_escala.setCursor(Qt.PointingHandCursor)
            btn_escala.setMinimumWidth(fm_escala.horizontalAdvance(btn_escala.text()) + 24)

        self.grupo_modo_escala = QButtonGroup(self.seg_escala_frame)
        self.grupo_modo_escala.setExclusive(True)
        self.grupo_modo_escala.addButton(self.btn_modo_didactico, 0)
        self.grupo_modo_escala.addButton(self.btn_modo_exacto, 1)

        seg_escala_layout.addWidget(self.btn_modo_didactico)
        seg_escala_layout.addWidget(self.btn_modo_exacto)
        self.seg_escala_frame.hide()
        sub_bar_layout.addWidget(self.seg_escala_frame)
        curvas_outer.addWidget(sub_bar)

        # Tarjeta blanca principal (article de Stitch)
        card_curvas = QFrame()
        card_curvas.setObjectName("curvasMainArticle")
        card_layout = QVBoxLayout(card_curvas)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(14)

        # Cabecera interna de la tarjeta (Icono + Título + Subtítulo a la izq, Leyenda / Estado a la der)
        hdr_card_widget = QWidget()
        hdr_card = FlowLayout(hdr_card_widget)
        hdr_card.setContentsMargins(0, 0, 0, 8)
        hdr_card.setSpacing(14)

        left_hdr_widget = QWidget()
        left_hdr = QVBoxLayout(left_hdr_widget)
        left_hdr.setContentsMargins(0,0,0,0)
        left_hdr.setSpacing(4)
        tit_row = QHBoxLayout()
        tit_row.setSpacing(10)
        self.lbl_ico_curvas_hdr = QLabel()
        self.lbl_ico_curvas_hdr.setFixedSize(36, 36)
        self.lbl_ico_curvas_hdr.setAlignment(Qt.AlignCenter)
        self.lbl_ico_curvas_hdr.setObjectName("curvasHeaderIconBox")
        self.lbl_ico_curvas_hdr.setPixmap(
            crear_icono_herramienta("curvas", "#0c4e77").pixmap(22, 22)
        )
        tit_row.addWidget(self.lbl_ico_curvas_hdr)

        self.lbl_egl_title = QLabel("Líneas de Energía (EGL / HGL)")
        self.lbl_egl_title.setObjectName("curvasMainTitle")
        self.lbl_egl_title.setWordWrap(True)
        tit_row.addWidget(self.lbl_egl_title, 1)
        left_hdr.addLayout(tit_row)

        self.lbl_egl_subtitle = QLabel("Perfil de energía y cota piezométrica")
        self.lbl_egl_subtitle.setObjectName("curvasMainSubtitle")
        self.lbl_egl_subtitle.setWordWrap(True)
        left_hdr.addWidget(self.lbl_egl_subtitle)

        font_tit_egl = QFont("Inter")
        font_tit_egl.setPixelSize(22)
        font_tit_egl.setWeight(QFont.Bold)
        hdr_card.addWidget(
            left_hdr_widget,
            minimum_width=lambda: QFontMetrics(font_tit_egl).horizontalAdvance(self.lbl_egl_title.text()) + 54,
        )

        # Contenedor derecho del header: Leyenda dinámica (cuando hay datos) o pill "Sin datos de simulación"
        self.stack_hdr_curvas = PilaPaginaActual()
        self.stack_hdr_curvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Página 0 del header derecho: pill "Sin datos de simulación"
        w_sin_datos = QWidget()
        l_sin_datos = QHBoxLayout(w_sin_datos)
        l_sin_datos.setContentsMargins(0, 0, 0, 0)
        lbl_pill_vacio = QLabel("  ●  Sin datos de simulación  ")
        lbl_pill_vacio.setObjectName("curvasNoDataPill")
        l_sin_datos.addWidget(lbl_pill_vacio, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.stack_hdr_curvas.addWidget(w_sin_datos)

        # Página 1 del header derecho: Leyenda dinámica con chips contextuales
        self.frame_leyenda_curvas = QFrame()
        self.frame_leyenda_curvas.setObjectName("curvasLegendBox")
        self.layout_leyenda_curvas = FlowLayout(self.frame_leyenda_curvas)
        self.layout_leyenda_curvas.setContentsMargins(0, 4, 0, 0)
        self.layout_leyenda_curvas.setSpacing(6)
        self.stack_hdr_curvas.addWidget(self.frame_leyenda_curvas)

        hdr_card.addWidget(self.stack_hdr_curvas, expand=True)
        card_layout.addWidget(hdr_card_widget)

        div_curvas = QFrame()
        div_curvas.setFrameShape(QFrame.HLine)
        div_curvas.setStyleSheet("background-color: #e5eeff; max-height: 1px; border: none;")
        card_layout.addWidget(div_curvas)

        # Stack interno de CURVAS: Página 0 = Estado Vacío Stitch | Página 1 = Gráfico + 4 Tarjetas inferiores
        self.stack_contenido_curvas = QStackedWidget()

        # --- Página 0: Estado vacío Stitch ---
        pagina_vacia = QWidget()
        vacia_layout = QVBoxLayout(pagina_vacia)
        vacia_layout.setContentsMargins(24, 40, 24, 40)
        vacia_layout.setSpacing(12)
        vacia_layout.addStretch(1)

        ico_vacio_box = QLabel()
        ico_vacio_box.setFixedSize(80, 80)
        ico_vacio_box.setAlignment(Qt.AlignCenter)
        ico_vacio_box.setObjectName("curvasEmptyIconBox")
        ico_vacio_box.setPixmap(
            crear_icono_herramienta("curvas_vacio", "#0c4e77").pixmap(40, 40)
        )
        vacia_layout.addWidget(ico_vacio_box, 0, Qt.AlignHCenter)
        vacia_layout.addSpacing(6)

        self.lbl_curvas_vacio_titulo = QLabel("Gráfico EGL / HGL no generado")
        self.lbl_curvas_vacio_titulo.setObjectName("curvasEmptyTitle")
        self.lbl_curvas_vacio_titulo.setAlignment(Qt.AlignCenter)
        vacia_layout.addWidget(self.lbl_curvas_vacio_titulo, 0, Qt.AlignHCenter)

        self.lbl_curvas_vacio_desc = QLabel(
            "Primero calcula un sistema en el lienzo CAD para ver el perfil de energía."
        )
        self.lbl_curvas_vacio_desc.setObjectName("curvasEmptyDesc")
        self.lbl_curvas_vacio_desc.setAlignment(Qt.AlignCenter)
        self.lbl_curvas_vacio_desc.setWordWrap(True)
        self.lbl_curvas_vacio_desc.setMaximumWidth(460)
        vacia_layout.addWidget(self.lbl_curvas_vacio_desc, 0, Qt.AlignHCenter)
        vacia_layout.addSpacing(10)

        self.btn_ir_a_cad_curvas = QPushButton(
            crear_icono_herramienta("flecha_atras", "#ffffff"), "  Ir a CAD"
        )
        self.btn_ir_a_cad_curvas.setObjectName("curvasIrCadBtn")
        self.btn_ir_a_cad_curvas.setIconSize(QSize(16, 16))
        self.btn_ir_a_cad_curvas.setFixedHeight(40)
        self.btn_ir_a_cad_curvas.setMinimumWidth(142)
        self.btn_ir_a_cad_curvas.setEnabled(True)
        self.btn_ir_a_cad_curvas.setCursor(Qt.PointingHandCursor)
        self.btn_ir_a_cad_curvas.clicked.connect(lambda: self._cambiar_vista_central("cad"))
        vacia_layout.addWidget(self.btn_ir_a_cad_curvas, 0, Qt.AlignHCenter)
        vacia_layout.addStretch(1)
        self.stack_contenido_curvas.addWidget(pagina_vacia)

        # --- Página 1: Vista con gráfico EGL/HGL + 4 tarjetas inferiores de Stitch ---
        pagina_grafico = QWidget()
        graf_layout = QVBoxLayout(pagina_grafico)
        graf_layout.setContentsMargins(0, 4, 0, 0)
        graf_layout.setSpacing(12)

        # QTabWidget oculto de compatibilidad para tests unitarios existentes
        self.tab_curvas = QTabWidget(pagina_grafico)
        self.tab_curvas.setObjectName("curvasTabWidget")
        self.tab_curvas.addTab(QWidget(), "Perfil EGL / HGL")
        self.tab_curvas.addTab(QWidget(), "Curvas Bomba y Sistema")
        self.tab_curvas.setTabEnabled(1, False)
        self.tab_curvas.hide()

        self.barra_rutas_egl = QFrame(pagina_grafico)
        self.barra_rutas_egl.setObjectName("curvasRutasBar")
        self.barra_rutas_egl.setStyleSheet(
            "#curvasRutasBar { background: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )
        self.layout_rutas_egl = FlowLayout(self.barra_rutas_egl)
        self.layout_rutas_egl.setContentsMargins(10, 6, 10, 6)
        self.layout_rutas_egl.setSpacing(6)
        self.barra_rutas_egl.hide()
        self._botones_rutas_egl = []
        graf_layout.addWidget(self.barra_rutas_egl)

        self.egl_chart = WidgetPerfilEGLHGL(pagina_grafico)
        self.egl_chart_curvas = self.egl_chart
        self.egl_chart.on_cambio_estado = self._sincronizar_estado_vista_curvas
        graf_layout.addWidget(self.egl_chart, 1)

        div_bottom = QFrame()
        div_bottom.setFrameShape(QFrame.HLine)
        div_bottom.setStyleSheet("background-color: #e5eeff; max-height: 1px; border: none;")
        graf_layout.addWidget(div_bottom)

        # 4 tarjetas inferiores de Stitch: Cota inicial, Cota final, Pérdida total, Energía excedente
        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 2, 0, 0)
        cards_row.setSpacing(14)

        self._curvas_kpi_labels = {}
        defs_kpis_curvas = (
            ("z1", "COTA INICIAL (Z₁)", "0.00", "m", "Tanque 1 (Superficie)", "#0c4e77", "#3a4c5e"),
            ("z2", "COTA FINAL (Z₂)", "0.00", "m", "Tanque 2 (Descarga)", "#0c4e77", "#3a4c5e"),
            ("hf", "PÉRDIDA TOTAL (HF)", "0.00", "m", "Fricción + Accesorios + Bordes", "#006398", "#3a4c5e"),
            ("exc", "ENERGÍA EXCEDENTE", "0.00", "m", "Flujo por gravedad asegurado", "#0c4e77", "#006398"),
        )
        for clave_k, tit_k, val_k, uni_k, sub_k, col_v, col_s in defs_kpis_curvas:
            f_card = QFrame()
            f_card.setObjectName("curvasBottomKpiCard")
            fl = QVBoxLayout(f_card)
            fl.setContentsMargins(16, 12, 16, 12)
            fl.setSpacing(4)

            l_tit = QLabel(tit_k)
            l_tit.setObjectName("curvasKpiTitle")
            l_tit.setWordWrap(True)
            fl.addWidget(l_tit)

            val_row = QHBoxLayout()
            val_row.setContentsMargins(0, 0, 0, 0)
            val_row.setSpacing(5)
            l_val = QLabel(val_k)
            l_val.setStyleSheet(
                f"font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 20px; "
                f"font-weight: 700; color: {col_v}; background: transparent;"
            )
            l_uni = QLabel(uni_k)
            l_uni.setStyleSheet(
                "font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 12px; "
                "font-weight: 400; color: #41474e; background: transparent;"
            )
            val_row.addWidget(l_val, 0, Qt.AlignBaseline)
            val_row.addWidget(l_uni, 0, Qt.AlignBaseline)
            val_row.addStretch()
            fl.addLayout(val_row)

            l_sub = QLabel(sub_k)
            l_sub.setWordWrap(True)
            l_sub.setStyleSheet(
                f"font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 11px; "
                f"font-weight: {'600' if clave_k == 'exc' else '400'}; color: {col_s}; background: transparent;"
            )
            fl.addWidget(l_sub)
            self._curvas_kpi_labels[clave_k] = (l_tit, l_val, l_uni, l_sub)
            cards_row.addWidget(f_card, 1)

        graf_layout.addLayout(cards_row)
        self.stack_contenido_curvas.addWidget(pagina_grafico)

        card_layout.addWidget(self.stack_contenido_curvas, 1)

        # =====================================================================
        # Tarjeta principal de CURVAS DE BOMBA (H - Q)
        # =====================================================================
        card_curvas_bomba = QFrame()
        card_curvas_bomba.setObjectName("curvasMainArticle")
        card_bomba_layout = QVBoxLayout(card_curvas_bomba)
        card_bomba_layout.setContentsMargins(24, 20, 24, 20)
        card_bomba_layout.setSpacing(14)

        hdr_bomba = QHBoxLayout()
        hdr_bomba.setContentsMargins(0, 0, 0, 8)
        hdr_bomba.setSpacing(14)

        left_hdr_b = QVBoxLayout()
        left_hdr_b.setSpacing(4)
        tit_row_b = QHBoxLayout()
        tit_row_b.setSpacing(10)
        lbl_ico_bomba_hdr = QLabel()
        lbl_ico_bomba_hdr.setFixedSize(36, 36)
        lbl_ico_bomba_hdr.setAlignment(Qt.AlignCenter)
        lbl_ico_bomba_hdr.setObjectName("curvasHeaderIconBox")
        lbl_ico_bomba_hdr.setPixmap(
            crear_icono_herramienta("bomba", "#0c4e77").pixmap(22, 22)
        )
        tit_row_b.addWidget(lbl_ico_bomba_hdr)

        self.lbl_bomba_curvas_title = QLabel("Curvas de Bomba (H - Q)")
        self.lbl_bomba_curvas_title.setObjectName("curvasMainTitle")
        tit_row_b.addWidget(self.lbl_bomba_curvas_title)
        tit_row_b.addStretch()
        left_hdr_b.addLayout(tit_row_b)

        self.lbl_bomba_curvas_subtitle = QLabel(
            "Intersección entre la curva característica de la bomba H_b(Q) y la curva resistente del sistema H_sis(Q)"
        )
        self.lbl_bomba_curvas_subtitle.setObjectName("curvasMainSubtitle")
        left_hdr_b.addWidget(self.lbl_bomba_curvas_subtitle)
        hdr_bomba.addLayout(left_hdr_b, 1)

        self.lbl_pill_bomba_vacio = QLabel("  ●  Sin datos de simulación  ")
        self.lbl_pill_bomba_vacio.setObjectName("curvasNoDataPill")
        hdr_bomba.addWidget(self.lbl_pill_bomba_vacio, 0, Qt.AlignRight | Qt.AlignTop)
        card_bomba_layout.addLayout(hdr_bomba)

        # Contenedor retrocompatible para llamadas existentes
        self.stack_hdr_bomba_curvas = QStackedWidget()
        self.stack_hdr_bomba_curvas.setVisible(False)

        # Stack de contenido de Curvas de Bomba: Página 0 = Estado vacío | Página 1 = Gráfico H-Q
        self.stack_contenido_bomba_curvas = QStackedWidget()

        pagina_bomba_vacia = QWidget()
        vacia_b_layout = QVBoxLayout(pagina_bomba_vacia)
        vacia_b_layout.setContentsMargins(24, 40, 24, 40)
        vacia_b_layout.setSpacing(12)
        vacia_b_layout.addStretch(1)

        ico_bomba_vacio = QLabel()
        ico_bomba_vacio.setFixedSize(80, 80)
        ico_bomba_vacio.setAlignment(Qt.AlignCenter)
        ico_bomba_vacio.setObjectName("curvasEmptyIconBox")
        ico_bomba_vacio.setPixmap(
            crear_icono_herramienta("bomba", "#0c4e77").pixmap(40, 40)
        )
        vacia_b_layout.addWidget(ico_bomba_vacio, 0, Qt.AlignHCenter)
        vacia_b_layout.addSpacing(6)

        self.lbl_bomba_vacio_titulo = QLabel("Curvas H-Q no generadas")
        self.lbl_bomba_vacio_titulo.setObjectName("curvasEmptyTitle")
        self.lbl_bomba_vacio_titulo.setAlignment(Qt.AlignCenter)
        vacia_b_layout.addWidget(self.lbl_bomba_vacio_titulo, 0, Qt.AlignHCenter)

        self.lbl_bomba_vacio_desc = QLabel(
            "Curvas H-Q no generadas — Calcula un sistema con bomba en el lienzo"
        )
        self.lbl_bomba_vacio_desc.setObjectName("curvasEmptyDesc")
        self.lbl_bomba_vacio_desc.setAlignment(Qt.AlignCenter)
        self.lbl_bomba_vacio_desc.setWordWrap(True)
        self.lbl_bomba_vacio_desc.setMaximumWidth(480)
        vacia_b_layout.addWidget(self.lbl_bomba_vacio_desc, 0, Qt.AlignHCenter)
        vacia_b_layout.addSpacing(10)

        self.btn_ir_a_cad_bomba_curvas = QPushButton(
            crear_icono_herramienta("flecha_atras", "#ffffff"), "  Ir a CAD"
        )
        self.btn_ir_a_cad_bomba_curvas.setObjectName("curvasIrCadBtn")
        self.btn_ir_a_cad_bomba_curvas.setIconSize(QSize(16, 16))
        self.btn_ir_a_cad_bomba_curvas.setFixedHeight(40)
        self.btn_ir_a_cad_bomba_curvas.setMinimumWidth(142)
        self.btn_ir_a_cad_bomba_curvas.setEnabled(True)
        self.btn_ir_a_cad_bomba_curvas.setCursor(Qt.PointingHandCursor)
        self.btn_ir_a_cad_bomba_curvas.clicked.connect(lambda: self._cambiar_vista_central("cad"))
        vacia_b_layout.addWidget(self.btn_ir_a_cad_bomba_curvas, 0, Qt.AlignHCenter)
        vacia_b_layout.addStretch(1)
        self.stack_contenido_bomba_curvas.addWidget(pagina_bomba_vacia)

        pagina_bomba_grafico = QWidget()
        graf_b_layout = QVBoxLayout(pagina_bomba_grafico)
        graf_b_layout.setContentsMargins(0, 0, 0, 0)
        graf_b_layout.setSpacing(0)

        self.grafico_bombas = WidgetGraficoBombas()
        self.panel_lateral_bombas = PanelLateralCurvasBomba(self.grafico_bombas, self)
        self.contenedor_responsive_hq = ContenedorResponsiveHQ(self.grafico_bombas, self.panel_lateral_bombas)
        graf_b_layout.addWidget(self.contenedor_responsive_hq, 1)

        # Referencias de conveniencia y compatibilidad con pruebas
        self.card_bomba_eq_total = self.panel_lateral_bombas.card_eq_total
        self.lbl_bomba_eq_total = self.panel_lateral_bombas.lbl_eq_total
        self.badge_bomba_eq_tipo = self.panel_lateral_bombas.lbl_eq_detalle
        self.pill_bomba_qop = self.panel_lateral_bombas.lbl_qop_main
        self.pill_bomba_hop = self.panel_lateral_bombas.lbl_hop_main
        self.chips_bombas_individuales = self.panel_lateral_bombas.chips_bombas_individuales

        self.stack_contenido_bomba_curvas.addWidget(pagina_bomba_grafico)

        card_bomba_layout.addWidget(self.stack_contenido_bomba_curvas, 1)

        # Stack que alterna entre la vista EGL/HGL (0) y la vista Curvas de Bomba (1)
        self.stack_modo_curvas = PilaPaginaActual()
        self.stack_modo_curvas.addWidget(card_curvas)
        self.stack_modo_curvas.addWidget(card_curvas_bomba)
        curvas_outer.addWidget(self.stack_modo_curvas, 1)

        self.stack_central = QStackedWidget()
        self.stack_central.addWidget(self.canvas_view)
        self.stack_central.addWidget(self.panel_vista_tabla)
        self.scroll_vista_curvas = QScrollArea()
        self.scroll_vista_curvas.setFrameShape(QFrame.NoFrame)
        self.scroll_vista_curvas.setWidgetResizable(True)
        self.scroll_vista_curvas.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_vista_curvas.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_vista_curvas.setWidget(self.panel_vista_curvas)
        self.stack_central.addWidget(self.scroll_vista_curvas)
        self._sincronizar_estado_vista_curvas(False)
        return self.stack_central

    def _build_side_panel(self):
        panel = QFrame()
        panel.setObjectName("sidePanel")
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(430)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Único scroll vertical que empieza desde arriba (sin recortes ni scroll anidado)
        self.panel_scroll = QScrollArea()
        self.panel_scroll.setObjectName("panelScroll")
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setFrameShape(QFrame.NoFrame)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        contenedor = QWidget()
        contenedor.setObjectName("panelScrollContent")
        contenedor_layout = QVBoxLayout(contenedor)
        contenedor_layout.setContentsMargins(16, 16, 14, 16)
        contenedor_layout.setSpacing(8)

        self.lbl_panel_subtitle = QLabel("CÁLCULO HIDRÁULICO")
        self.lbl_panel_subtitle.setObjectName("panelSubtitle")
        contenedor_layout.addWidget(self.lbl_panel_subtitle)

        self.lbl_panel_title = QLabel("Análisis del Sistema (Bernoulli)")
        self.lbl_panel_title.setObjectName("panelTitle")
        self.lbl_panel_title.setWordWrap(True)
        contenedor_layout.addWidget(self.lbl_panel_title)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("panelDivider")
        contenedor_layout.addWidget(divider)

        self.panel_content = QWidget()
        self.panel_content_layout = QVBoxLayout(self.panel_content)
        self.panel_content_layout.setContentsMargins(0, 4, 0, 0)
        self.panel_content_layout.setSpacing(10)

        contenedor_layout.addWidget(self.panel_content)
        contenedor_layout.addStretch(1)

        self.panel_scroll.setWidget(contenedor)
        layout.addWidget(self.panel_scroll, 1)

        self._crear_dashboard()
        self._mostrar_dashboard()

        return panel
