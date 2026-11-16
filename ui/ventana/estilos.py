"""Hoja de estilos (QSS) y apariencia de la ventana principal."""

class EstilosMixin:
    """Hoja de estilos (QSS) y apariencia de la ventana principal."""

    def _apply_styles(self):
        self.setStyleSheet(
            """
            /* Base general y tipografía Stitch */
            QMainWindow, QDialog {
                background-color: #f8f9ff;
                font-family: "Inter", "Segoe UI", -apple-system, sans-serif;
            }

            /* Cabecera superior Stitch (h-12 = 48px) */
            QFrame#stitchHeaderBar {
                background-color: #ffffff;
                border-bottom: 1px solid #e2e8f0;
            }
            QLabel#stitchVersionBadge {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 600;
                color: #0c4e77;
                background-color: #eff4ff;
                border: 1px solid #cbd5e1;
                border-radius: 14px;
                padding: 0px 12px;
            }
            QPushButton#stitchUpdateBtn {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 500;
                color: #475569;
                background-color: #ffffff;
                border: 1px solid #d4e2ef;
                border-radius: 14px;
                padding: 0px 12px;
            }
            QPushButton#stitchUpdateBtn:hover {
                background-color: #e7f5ff;
                border-color: #7fc6ed;
                color: #075985;
            }
            QPushButton#stitchUpdateBtn[updateAvailable="true"] {
                background-color: #dbeafe;
                border-color: #60a5fa;
                color: #0c4e77;
                font-weight: 600;
            }

            /* Herramientas en cápsulas: aire para la elevación de 3 px. */
            QToolBar#mainToolbar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8fbff, stop:1 #edf4fc);
                border: none;
                border-bottom: 1px solid #dce7f3;
                padding: 8px 12px;
                spacing: 6px;
            }
            QToolBar#mainToolbar::separator {
                background-color: #cfdeed;
                width: 1px;
                margin: 9px 4px;
            }
            QToolBar#mainToolbar QToolButton,
            QToolBar#mainToolbar QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f7faff);
                color: #20425c;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 600;
                min-height: 20px;
                padding: 4px 10px;
                border: 1px solid #d4e2ef;
                border-radius: 15px;
            }
            QToolBar#mainToolbar QToolButton:hover,
            QToolBar#mainToolbar QPushButton:hover {
                background: #e7f5ff;
                border-color: #7fc6ed;
                color: #075985;
            }
            QToolBar#mainToolbar QToolButton:pressed,
            QToolBar#mainToolbar QPushButton:pressed {
                background: #cdeafa;
                border-color: #38a9dc;
            }
            QToolBar#mainToolbar QToolButton:checked,
            QToolBar#mainToolbar QPushButton:checked {
                background: #cceeff;
                border: 1px solid #38a9dc;
                color: #075985;
            }
            QPushButton#toolbarDropdownBtn::menu-indicator {
                image: none;
                width: 0px;
            }
            QToolBar#mainToolbar QPushButton#ghostPrimaryToolbarBtn {
                background: #e0f2fe;
                border-color: #b4dff6;
                color: #075985;
            }
            QToolBar#mainToolbar QPushButton#dangerToolbarBtn {
                background: #fff5f5;
                border-color: #f4dada;
                color: #b42332;
            }
            QToolBar#mainToolbar QPushButton#dangerToolbarBtn:hover {
                background: #ffe5e7;
                border-color: #f0a3ab;
            }
            QToolBar#mainToolbar QPushButton#neutralToolbarBtn {
                background: transparent;
                border-color: transparent;
                color: #475569;
            }
            QToolBar#mainToolbar QPushButton#neutralToolbarBtn:hover {
                background: #ffffff;
                border-color: #c6d8ea;
            }
            QToolBar#mainToolbar QToolButton:disabled,
            QToolBar#mainToolbar QPushButton:disabled {
                background: #f1f5f9;
                color: #94a3b8;
                border-color: #e2e8f0;
            }
            QToolBar#mainToolbar QToolButton#qt_toolbar_ext_button {
                background: #e0effa;
                border: none;
                border-radius: 6px;
                padding: 0;
                min-height: 0;
            }

            /* Navegación: tarjetas redondeadas y acento lateral deslizante. */
            QFrame#leftNavBar {
                background-color: #ffffff;
                border-right: 1px solid #e2e8f0;
            }
            QToolButton#navBtnActive,
            QToolButton#navBtnInactive {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.5px;
                border-radius: 16px;
                padding: 6px 4px 4px 4px;
            }
            QToolButton#navBtnActive {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #167ba8, stop:1 #123c61);
                color: #ffffff;
                border: 1px solid #176188;
            }
            QToolButton#navBtnActive:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #219aca, stop:1 #164a71);
            }
            QToolButton#navBtnInactive {
                background-color: transparent;
                color: #64748b;
                border: 1px solid transparent;
            }
            QToolButton#navBtnInactive:hover {
                background-color: #edf6ff;
                border-color: #d7e9f6;
                color: #075985;
            }

            /* Lienzo, HUDs flotantes y divisor central */
            QSplitter#mainSplitter::handle,
            QSplitter#centerSplitter::handle {
                background-color: #e2e8f0;
            }
            QSplitter#mainSplitter::handle:hover,
            QSplitter#centerSplitter::handle:hover {
                background-color: #0284c7;
            }
            QGraphicsView#canvasView {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin: 8px 4px 8px 8px;
            }
            QFrame#hudSeleccionFrame {
                background-color: rgba(255, 255, 255, 0.90);
                border: 1px solid #d8e2ee;
                border-radius: 12px;
                padding: 2px 4px;
            }
            QLabel#hudSeleccionLabel {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11px;
                color: #475569;
                background: transparent;
            }
            QFrame#hudZoomFrame {
                background-color: rgba(255, 255, 255, 0.90);
                border: 1px solid #d8e2ee;
                border-radius: 8px;
                padding: 2px 2px;
            }
            QPushButton#hudZoomBtn {
                background-color: transparent;
                color: #334155;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 13px;
                font-weight: 600;
                border: none;
                border-radius: 4px;
                padding: 2px 4px;
            }
            QPushButton#hudZoomBtn:hover {
                background-color: rgba(226, 232, 240, 0.85);
                color: #0c4e77;
            }
            QPushButton#hudZoomBtn:pressed {
                background-color: rgba(203, 213, 225, 0.9);
            }
            QLabel#hudZoomLabel {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 600;
                color: #334155;
                background: transparent;
            }
            QFrame#hudNotificacionFrame {
                background-color: rgba(255, 251, 235, 0.96);
                border: 1px solid #f59e0b;
                border-radius: 10px;
                padding: 2px 4px;
            }
            QLabel#hudNotificacionLabel {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11.5px;
                font-weight: 600;
                color: #78350f;
                background: transparent;
            }
            QPushButton#hudNotificacionClose {
                background-color: transparent;
                color: #92400e;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 700;
                border: none;
                border-radius: 4px;
                padding: 0px 4px;
            }
            QPushButton#hudNotificacionClose:hover {
                background-color: rgba(245, 158, 11, 0.22);
                color: #451a03;
            }

            /* Vista Exclusiva CURVAS (EGL / HGL estilo Google Stitch) */
            QFrame#curvasPreviewPanel {
                background-color: #eff4ff;
                border: none;
            }
            QFrame#curvasSubHeader {
                background-color: #ffffff;
                border: 1px solid #e5eeff;
                border-radius: 10px;
            }
            QPushButton#curvasBackBtn {
                background-color: #eff4ff;
                color: #0b1c30;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #dce9ff;
                border-radius: 6px;
                padding: 5px 12px;
            }
            QPushButton#curvasBackBtn:hover {
                background-color: #dce9ff;
            }
            QLabel#curvasExclusivaBadge {
                background-color: #cce5ff;
                color: #00476e;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 11.5px;
                font-weight: 600;
                border-radius: 11px;
                padding: 3px 10px;
            }
            QPushButton#curvasLineToggleEgl,
            QPushButton#curvasLineToggleHgl {
                background-color: #f8fafc;
                color: #64748b;
                border: 1px solid #e2e8f0;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 600;
                border-radius: 13px;
                padding: 4px 9px;
                min-height: 22px;
            }
            QPushButton#curvasLineToggleEgl:hover:!checked,
            QPushButton#curvasLineToggleHgl:hover:!checked {
                background-color: #f1f5f9;
                color: #334155;
            }
            QPushButton#curvasLineToggleEgl:checked {
                background-color: #fef2f2;
                color: #b91c1c;
                border: 1px solid #fecaca;
            }
            QPushButton#curvasLineToggleEgl:checked:hover {
                background-color: #fee2e2;
            }
            QPushButton#curvasLineToggleHgl:checked {
                background-color: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
            }
            QPushButton#curvasLineToggleHgl:checked:hover {
                background-color: #dbeafe;
            }
            QPushButton#curvasEscalaBtnDidactico,
            QPushButton#curvasEscalaBtnExacto {
                background-color: transparent;
                color: #64748b;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 4px 8px;
                min-height: 22px;
            }
            QPushButton#curvasEscalaBtnDidactico:hover:!checked,
            QPushButton#curvasEscalaBtnExacto:hover:!checked {
                background-color: rgba(255, 255, 255, 0.7);
                color: #0b1c30;
            }
            QPushButton#curvasEscalaBtnDidactico:checked {
                background-color: #fef3c7;
                color: #92400e;
                border: 1px solid #fde68a;
            }
            QPushButton#curvasEscalaBtnExacto:checked {
                background-color: #e0f2fe;
                color: #0c4e77;
                border: 1px solid #bae6fd;
            }
            QFrame#curvasMainArticle {
                background-color: #ffffff;
                border: 1px solid #e5eeff;
                border-radius: 12px;
            }
            QLabel#curvasHeaderIconBox {
                background-color: #e5eeff;
                border-radius: 8px;
            }
            QLabel#curvasMainTitle {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 22px;
                font-weight: 700;
                color: #0b1c30;
                letter-spacing: -0.3px;
            }
            QLabel#curvasMainSubtitle {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 13px;
                font-weight: 500;
                color: #475569;
            }
            QFrame#curvasLegendBox {
                background-color: transparent;
                border: none;
            }
            QLabel#curvasNoDataPill {
                background-color: #e5eeff;
                color: #41474e;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 11.5px;
                font-weight: 500;
                border-radius: 12px;
                padding: 5px 12px;
            }
            QLabel#curvasEmptyIconBox {
                background-color: #eff4ff;
                border: 1px solid #dce9ff;
                border-radius: 16px;
            }
            QLabel#curvasEmptyTitle {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 19px;
                font-weight: 600;
                color: #0b1c30;
            }
            QLabel#curvasEmptyDesc {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 13.5px;
                font-weight: 400;
                color: #41474e;
            }
            QPushButton#curvasIrCadBtn {
                background-color: #2f6690;
                color: #ffffff;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 13.5px;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
            }
            QPushButton#curvasIrCadBtn:hover {
                background-color: #245275;
            }
            QPushButton#curvasIrCadBtn:pressed {
                background-color: #0c4e77;
            }
            QFrame#curvasBottomKpiCard {
                background-color: #eff4ff;
                border: 1px solid #e5eeff;
                border-radius: 8px;
            }
            QLabel#curvasKpiTitle {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 10.5px;
                font-weight: 600;
                color: #41474e;
                letter-spacing: 0.6px;
            }

            /* Vista TABLA (Memoria de cálculo estilo Google Stitch) */
            QFrame#tablaPreviewPanel {
                background-color: #f1f5f9;
                border: none;
            }
            QFrame#tablaCardMain {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QFrame#tablaHeaderFrame {
                background-color: #ffffff;
                border-bottom: 1px solid #e2e8f0;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                min-height: 48px;
            }
            QLabel#tablaIconBox {
                background-color: #f0f9ff;
                border: 1px solid #e0f2fe;
                border-radius: 6px;
            }
            QLabel#tablaTitulo {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 14px;
                font-weight: 700;
                color: #0f172a;
                letter-spacing: -0.2px;
            }
            QLabel#tablaBadge {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 600;
                border-radius: 10px;
                padding: 2px 8px;
            }
            QPushButton#btnTablaExportar {
                background-color: #0284c7;
                color: #ffffff;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 600;
                border: none;
                border-radius: 8px;
                padding: 6px 14px;
            }
            QPushButton#btnTablaExportar:hover {
                background-color: #0369a1;
            }
            QPushButton#btnTablaExportar:disabled {
                background-color: #94a3b8;
                color: #ffffff;
            }
            QFrame#tablaFormulaBar {
                background-color: #f8fafc;
                border-bottom: 1px solid #e2e8f0;
                min-height: 32px;
            }
            QLabel#tablaCellRef {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 11px;
                font-weight: 700;
                color: #0f172a;
            }
            QLineEdit#tablaFormulaInput {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 4px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 11px;
                color: #0f172a;
                padding: 2px 8px;
            }
            QFrame#contenedorHojaExcel {
                background-color: #ffffff;
                border: none;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }
            QTableWidget#tablaExcelPreview {
                background-color: #ffffff;
                gridline-color: #e2e8f0;
                border: none;
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
                selection-background-color: #bae6fd;
                selection-color: #0284c7;
            }
            QTableWidget#tablaExcelPreview QHeaderView::section:horizontal {
                background-color: #f8fafc;
                color: #64748b;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #e2e8f0;
                padding: 4px 6px;
                text-align: center;
            }
            QTableWidget#tablaExcelPreview QHeaderView::section:vertical {
                background-color: #f8fafc;
                color: #64748b;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-weight: 600;
                font-size: 10px;
                border: 1px solid #e2e8f0;
                padding: 2px 4px;
                text-align: center;
            }

            /* Panel Inferior Línea de Energía (compatibilidad) */
            QFrame#eglPanel {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin: 4px 4px 8px 8px;
            }
            QLabel#eglTitle {
                font-size: 13px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#eglSubtitle {
                font-size: 11px;
                color: #64748b;
            }
            QLabel#eglLegendEgl {
                font-size: 11px;
                font-weight: 700;
                color: #0284c7;
            }
            QLabel#eglLegendHgl {
                font-size: 11px;
                font-weight: 700;
                color: #16a34a;
            }
            QLabel#eglBadgeCinetica {
                background-color: #f0f9ff;
                color: #0284c7;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 700;
            }

            /* Panel lateral derecho de propiedades y resultados (Stitch) */
            QFrame#sidePanel {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                margin: 8px 8px 8px 4px;
            }
            QScrollArea#panelScroll,
            QScrollArea#panelScroll > QWidget > QWidget,
            QWidget#panelScrollContent {
                background: transparent;
                border: none;
            }
            QScrollArea#panelScroll QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 2px 0px;
            }
            QScrollArea#panelScroll QScrollBar::handle:vertical {
                background: #cbd5e1;
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollArea#panelScroll QScrollBar::handle:vertical:hover {
                background: #94a3b8;
            }
            QScrollArea#panelScroll QScrollBar::add-line:vertical,
            QScrollArea#panelScroll QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QLabel#panelSubtitle {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 600;
                color: #006398;
                letter-spacing: 0.9px;
            }
            QLabel#panelTitle {
                font-family: "Space Grotesk", "Segoe UI", sans-serif;
                font-size: 16px;
                font-weight: 700;
                color: #0c4e77;
                letter-spacing: -0.2px;
            }
            QFrame#panelDivider {
                background-color: #eff4ff;
                max-height: 1px;
                border: none;
            }
            QLabel#panelLabel {
                font-size: 12px;
                font-weight: 600;
                color: #41474e;
                padding: 2px 0px;
            }
            QLabel#panelMicroLabel {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 10px;
                font-weight: 600;
                color: #64748b;
                letter-spacing: 0.6px;
                text-transform: uppercase;
                background: transparent;
                padding-top: 3px;
                padding-bottom: 2px;
            }

            /* Selector segmentado con dos pastillas independientes. */
            QFrame#segmentedContainer {
                background: #eef4fa;
                border: 1px solid #dce7f2;
                border-radius: 17px;
            }
            QPushButton#segTabBtnLeft,
            QPushButton#segTabBtnRight,
            QPushButton#segTabBtn {
                background: transparent;
                color: #64748b;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 500;
                border: 1px solid transparent;
                border-radius: 12px;
                padding: 5px 6px;
                min-height: 22px;
            }
            QPushButton#segTabBtnLeft:checked,
            QPushButton#segTabBtnRight:checked,
            QPushButton#segTabBtn:checked {
                background: #ffffff;
                color: #075985;
                font-weight: 600;
                border: 1px solid #c5e0f0;
            }
            QPushButton#segTabBtnLeft:hover:!checked,
            QPushButton#segTabBtnRight:hover:!checked,
            QPushButton#segTabBtn:hover:!checked {
                background: #e0effa;
                color: #075985;
            }

            /* Contenedor tonal de controles de tanque / unión */
            QFrame#modeControlCard {
                background-color: #f2f6ff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }

            /* Campos de entrada y selectores */
            QLineEdit#panelLineEdit,
            QComboBox#panelComboBox,
            QTextEdit#panelTextEdit {
                background-color: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                padding: 5px 8px;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12px;
                font-weight: 500;
                color: #0b1c30;
            }
            QLineEdit#panelLineEdit:hover,
            QComboBox#panelComboBox:hover,
            QTextEdit#panelTextEdit:hover {
                border-color: #94a3b8;
            }
            QLineEdit#panelLineEdit:focus,
            QComboBox#panelComboBox:focus,
            QTextEdit#panelTextEdit:focus {
                background-color: #ffffff;
                border: 1.5px solid #0284c7;
            }
            QPushButton#boldToggleBtn {
                background-color: #f8fafc;
                color: #334155;
                font-size: 13px;
                font-weight: 800;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
            QPushButton#boldToggleBtn:checked {
                background-color: #e0f2fe;
                color: #0284c7;
                border: 1.5px solid #0284c7;
            }
            QTextEdit#dashboardResultados {
                background-color: transparent;
                border: none;
                padding: 0px;
                font-size: 12px;
                color: #0b1c30;
            }
            QCheckBox#panelCheckBox {
                font-size: 13px;
                font-weight: 500;
                color: #334155;
                padding: 4px 0px;
            }

            /* Barra horizontal bicolor de pérdidas (Stitch) */
            QLabel#hfBarTotalLabel {
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 11px;
                font-weight: 600;
                color: #0c4e77;
            }
            QLabel#barLegendLabel {
                font-size: 11px;
                font-weight: 400;
                color: #72787f;
            }

            /* 1. Mayor peso visual: Botón de Acción Principal ("Calcular Bernoulli") */
            QPushButton#bernoulliButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0796c8, stop:0.55 #087fab, stop:1 #135579);
                color: #ffffff;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 14px;
                font-weight: 700;
                letter-spacing: 0.2px;
                border: 1px solid #087ca7;
                border-radius: 18px;
                padding: 12px 16px;
            }
            QPushButton#bernoulliButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #15afd6, stop:0.55 #078bb7, stop:1 #146789);
            }
            QPushButton#bernoulliButton:pressed {
                background: #075985;
            }
            QPushButton#bernoulliButton:disabled {
                background: #cbd5e1;
                border-color: #cbd5e1;
                color: #64748b;
            }

            /* 6. Menor peso visual: Botón Exportar a Excel (solo contorno) */
            QPushButton#excelButton {
                background-color: #ffffff;
                color: #0c4e77;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12.5px;
                font-weight: 600;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                padding: 9px 14px;
            }
            QPushButton#excelButton:hover {
                background-color: #eff4ff;
                border-color: #006398;
            }
            QPushButton#excelButton:pressed {
                background-color: #e5eeff;
            }

            /* Botón secundario (Cambiar Color) */
            QPushButton#colorButton {
                background-color: #ffffff;
                color: #1e293b;
                font-size: 12px;
                font-weight: 600;
                padding: 8px 12px;
                border: 1px solid #cbd5e1;
                border-radius: 14px;
            }
            QPushButton#colorButton:hover {
                background-color: #f8fafc;
                border-color: #94a3b8;
            }

            /* Pestañas de la vista CURVAS (Perfil EGL vs Bombas) */
            QTabWidget#curvasTabWidget::pane {
                border: none;
                background: transparent;
            }
            QTabWidget#curvasTabWidget QTabBar::tab {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11.5px;
                font-weight: 600;
                padding: 6px 16px;
                margin-right: 6px;
                border: 1px solid #dce4ee;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                background: #f2f6ff;
                color: #0c4e77;
            }
            QTabWidget#curvasTabWidget QTabBar::tab:selected {
                background: #ffffff;
                color: #006398;
                border-top: 2px solid #006398;
            }
            QTabWidget#curvasTabWidget QTabBar::tab:disabled {
                background: #f8fafc;
                color: #94a3b8;
                border-color: #e2e8f0;
            }

            /* Resultados: superficie luminosa, controles compactos y acentos CAD. */
            QWidget#resultsDashboard {
                background: transparent;
                font-family: "Segoe UI";
            }
            QWidget#resultsDashboard QLabel,
            QWidget#resultsDashboard QPushButton,
            QWidget#resultsDashboard QComboBox {
                font-family: "Segoe UI";
            }
            QLabel#resultsSectionTitle {
                color: #087fab;
                font-size: 11px;
                font-weight: 700;
                padding: 8px 0px 3px 0px;
                border-top: 1px solid #dceaf2;
            }
            QWidget#resultsDashboard QFrame#modeControlCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f0f9ff, stop:1 #effaf7);
                border: 1px solid #d1e8ef;
                border-radius: 12px;
            }
            QWidget#resultsDashboard QPushButton#bernoulliButton {
                font-size: 13px;
                padding: 6px 10px;
                border-radius: 12px;
            }
            QWidget#resultsDashboard QComboBox#panelComboBox {
                min-height: 24px;
                padding: 3px 7px;
                selection-background-color: #d8f1fb;
            }
            QWidget#resultsDashboard QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QWidget#resultsDashboard QPushButton#segTabBtnLeft:checked,
            QWidget#resultsDashboard QPushButton#segTabBtnRight:checked {
                background: #dff4fb;
                color: #075985;
                border: 1px solid #8dd2e8;
            }
            QFrame#lossesCard {
                background: #f5f9fc;
                border: 1px solid #dce8f0;
                border-radius: 12px;
            }
            QLabel#hfBarTotalLabel {
                font-family: "Segoe UI";
                font-size: 14px;
                font-weight: 700;
                color: #103e58;
            }
            QLabel#panelTitle, QLabel#panelSubtitle, QLabel#panelMicroLabel {
                font-family: "Segoe UI";
            }

            /* Barra de estado inferior fina con atajos */
            QStatusBar#mainStatusBar {
                background-color: #ffffff;
                border-top: 1px solid #e2e8f0;
                min-height: 24px;
                max-height: 24px;
                padding: 0px 8px;
            }
            QLabel#statusShortcutsLabel {
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11px;
                font-weight: 500;
                color: #64748b;
                background: transparent;
            }
            """
        )
