"""Dashboard de análisis del sistema (Bernoulli y pérdidas)."""


from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from motor import MotorFluidos
from motor.hidraulica import evaluar_tramo
from ui.graficos import NodoUnionGrafico, TanqueGrafico
from ui.widgets import _AutoHeightTextEdit, _InterruptorStitch
from ui.iconos import crear_icono_herramienta
from ui.constantes import formatear_numero


def desglosar_perdidas_tuberia(tuberia, hf_loc, resultado=None):
    """Separa hf_loc en (hf_accesorios, hf_bordes) según K/LeD sin mezclar bordes en accesorios."""
    hf_l = max(0.0, float(hf_loc or 0.0))
    if hf_l <= 0.0:
        return 0.0, 0.0
    k_bordes = float(getattr(tuberia, "sumatoria_K_bordes", 0.0) or 0.0)
    if k_bordes <= 0.0:
        return hf_l, 0.0
    k_acc = float(getattr(tuberia, "sumatoria_K_accesorios", 0.0) or 0.0)
    le_d = float(getattr(tuberia, "sumatoria_Le_D", 0.0) or 0.0)
    res_obj = resultado or getattr(tuberia, "_resultado_tramo_resuelto", None)
    f_val = float(getattr(res_obj, "f", 0.0) or 0.0) if res_obj is not None else 0.0
    denom = f_val * le_d + k_acc + k_bordes
    if denom <= 0.0:
        return hf_l, 0.0
    frac_bordes = min(1.0, max(0.0, k_bordes / denom))
    hf_bordes = hf_l * frac_bordes
    return hf_l - hf_bordes, hf_bordes


def desglosar_hf_rutas(tuberias, hf_loc_total):
    """Agrupa y separa hf_loc_total de una lista de tuberías en (hf_accesorios, hf_bordes)."""
    hf_l_tot = max(0.0, float(hf_loc_total or 0.0))
    if hf_l_tot <= 0.0:
        return 0.0, 0.0
    vistos = {}
    for t in tuberias:
        if id(t) not in vistos:
            vistos[id(t)] = t
    hf_acc_sum = 0.0
    hf_brd_sum = 0.0
    tiene_detalle = False
    for t in vistos.values():
        hl = getattr(t, "hf_loc_calculado", None)
        if hl is not None:
            tiene_detalle = True
            ha, hb = desglosar_perdidas_tuberia(t, hl)
            hf_acc_sum += ha
            hf_brd_sum += hb
    if tiene_detalle and (hf_acc_sum + hf_brd_sum) > 0.0:
        escala = hf_l_tot / (hf_acc_sum + hf_brd_sum)
        return hf_acc_sum * escala, hf_brd_sum * escala
    k_acc_tot = sum(float(getattr(t, "sumatoria_K_accesorios", 0.0) or 0.0) for t in vistos.values())
    k_brd_tot = sum(float(getattr(t, "sumatoria_K_bordes", 0.0) or 0.0) for t in vistos.values())
    if k_brd_tot > 0.0 and (k_acc_tot + k_brd_tot) > 0.0:
        hb = hf_l_tot * (k_brd_tot / (k_acc_tot + k_brd_tot))
        return hf_l_tot - hb, hb
    return hf_l_tot, 0.0


class _BarraDistribucionPerdidas(QWidget):
    """Barra proporcional tricolor (Fricción, Accesorios, Bordes) compatible con .value()."""

    COLORES = ("#e74c3c", "#f59e0b", "#0d9488")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fracs = (0.0, 0.0, 0.0)
        self._pct_dist = 0
        self.setFixedHeight(12)

    def set_proporciones(self, fric, acc, bordes):
        self._fracs = (
            max(0.0, float(fric or 0.0)),
            max(0.0, float(acc or 0.0)),
            max(0.0, float(bordes or 0.0)),
        )
        tot = sum(self._fracs)
        self._pct_dist = int(round((self._fracs[0] / tot) * 100.0)) if tot > 0 else 0
        self.update()

    def value(self):
        return self._pct_dist

    def paintEvent(self, _event):
        w = float(self.width())
        h = float(self.height())
        if w <= 0 or h <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        ruta = QPainterPath()
        ruta.addRoundedRect(QRectF(0.0, 0.0, w, h), 4.0, 4.0)
        painter.setClipPath(ruta)
        painter.fillRect(QRectF(0.0, 0.0, w, h), QColor("#dce9ff"))
        tot = sum(self._fracs)
        if tot > 0:
            activos = [(i, (val / tot) * w) for i, val in enumerate(self._fracs) if val > 0]
            min_px = 3.0 if len(activos) > 1 and w >= 12.0 else 0.0
            anchos = {i: max(min_px, sw) for i, sw in activos}
            exceso = sum(anchos.values()) - w
            if exceso > 1e-6:
                reducible = sum(max(0.0, a - min_px) for a in anchos.values())
                if reducible > 1e-6:
                    factor = max(0.0, (reducible - exceso) / reducible)
                    for i in anchos:
                        if anchos[i] > min_px:
                            anchos[i] = min_px + (anchos[i] - min_px) * factor
            x = 0.0
            for i in range(3):
                ancho = anchos.get(i, 0.0)
                if ancho > 0:
                    painter.fillRect(QRectF(x, 0.0, ancho, h), QColor(self.COLORES[i]))
                    x += ancho
        painter.end()


class DashboardMixin:
    """Dashboard de análisis del sistema (Bernoulli y pérdidas)."""

    def _cambiar_modo_dashboard(self, indice):
        from ui.transiciones import revelar_contenido
        cambio = self.stack_modo.currentIndex() != indice
        self.stack_modo.setCurrentIndex(indice)
        self.btn_tab_simple.setChecked(indice == 0)
        self.btn_tab_ramificado.setChecked(indice == 1)
        self.btn_tab_simple.setIcon(
            crear_icono_herramienta("rama_simple", "#006398" if indice == 0 else "#72787f")
        )
        self.btn_tab_ramificado.setIcon(
            crear_icono_herramienta("rama_red", "#006398" if indice == 1 else "#72787f")
        )
        if cambio:
            revelar_contenido(self.stack_modo, 16)

    def _crear_dashboard(self):
        self.dashboard_widget = QWidget()
        self.dashboard_widget.setObjectName("resultsDashboard")
        layout = QVBoxLayout(self.dashboard_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        # Selector segmentado horizontal: [ Sistema Simple | Ramificado ]
        lbl_sec_modo = QLabel("MODO DE ANÁLISIS")
        lbl_sec_modo.setObjectName("panelMicroLabel")
        layout.addWidget(lbl_sec_modo)

        seg_frame = QFrame()
        seg_frame.setObjectName("segmentedContainer")
        seg_layout = QHBoxLayout(seg_frame)
        seg_layout.setContentsMargins(4, 4, 4, 4)
        seg_layout.setSpacing(4)

        self.btn_tab_simple = QPushButton(
            crear_icono_herramienta("rama_simple", "#006398"), " Sistema Simple"
        )
        self.btn_tab_simple.setObjectName("segTabBtnLeft")
        self.btn_tab_simple.setIconSize(QSize(14, 14))
        self.btn_tab_simple.setCheckable(True)
        self.btn_tab_simple.setChecked(True)
        self.btn_tab_simple.setCursor(Qt.PointingHandCursor)
        self.btn_tab_simple.clicked.connect(lambda: self._cambiar_modo_dashboard(0))

        self.btn_tab_ramificado = QPushButton(
            crear_icono_herramienta("rama_red", "#72787f"), " Ramificado"
        )
        self.btn_tab_ramificado.setObjectName("segTabBtnRight")
        self.btn_tab_ramificado.setIconSize(QSize(14, 14))
        self.btn_tab_ramificado.setCheckable(True)
        self.btn_tab_ramificado.setChecked(False)
        self.btn_tab_ramificado.setCursor(Qt.PointingHandCursor)
        self.btn_tab_ramificado.clicked.connect(lambda: self._cambiar_modo_dashboard(1))

        seg_layout.addWidget(self.btn_tab_simple, 1)
        seg_layout.addWidget(self.btn_tab_ramificado, 1)
        layout.addWidget(seg_frame, 0)

        self.stack_modo = QStackedWidget()
        self.stack_modo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.stack_modo.setFixedHeight(124)
        self.toolbox = self.stack_modo

        # Página 0: Sistema Simple (Contenedor tonal Stitch + Combos lado a lado + botón 52px + interruptor curvas)
        widget_simple = QFrame()
        widget_simple.setObjectName("modeControlCard")
        layout_simple = QVBoxLayout(widget_simple)
        layout_simple.setContentsMargins(10, 10, 10, 10)
        layout_simple.setSpacing(8)

        fila_combos = QHBoxLayout()
        fila_combos.setContentsMargins(0, 0, 0, 0)
        fila_combos.setSpacing(8)

        col_t1 = QVBoxLayout()
        col_t1.setSpacing(3)
        lbl_t1 = QLabel("TANQUE DE INICIO (Z₁)")
        lbl_t1.setObjectName("panelMicroLabel")
        col_t1.addWidget(lbl_t1)
        self.combo_punto1 = QComboBox()
        self.combo_punto1.setObjectName("panelComboBox")
        col_t1.addWidget(self.combo_punto1)

        col_t2 = QVBoxLayout()
        col_t2.setSpacing(3)
        lbl_t2 = QLabel("TANQUE DE DESTINO (Z₂)")
        lbl_t2.setObjectName("panelMicroLabel")
        col_t2.addWidget(lbl_t2)
        self.combo_punto2 = QComboBox()
        self.combo_punto2.setObjectName("panelComboBox")
        col_t2.addWidget(self.combo_punto2)

        fila_combos.addLayout(col_t1, 1)
        fila_combos.addLayout(col_t2, 1)
        layout_simple.addLayout(fila_combos)

        self.boton_bernoulli = QPushButton(crear_icono_herramienta("play", "#ffffff"), "Calcular Bernoulli")
        self.boton_bernoulli.setIconSize(QSize(18, 18))
        self.boton_bernoulli.setObjectName("bernoulliButton")
        self.boton_bernoulli.setFixedHeight(42)
        self.boton_bernoulli.setCursor(Qt.PointingHandCursor)
        self.boton_bernoulli.clicked.connect(self._on_resolver_bernoulli)
        layout_simple.addWidget(self.boton_bernoulli)

        self.combo_punto1.currentIndexChanged.connect(self._actualizar_texto_boton)
        self.combo_punto2.currentIndexChanged.connect(self._actualizar_texto_boton)

        # Página 1: Sistema Ramificado
        widget_ramificado = QFrame()
        widget_ramificado.setObjectName("modeControlCard")
        layout_ramificado = QVBoxLayout(widget_ramificado)
        layout_ramificado.setContentsMargins(10, 10, 10, 10)
        layout_ramificado.setSpacing(8)
        lbl_u = QLabel("SELECCIONA LA UNIÓN O RED A RESOLVER")
        lbl_u.setObjectName("panelMicroLabel")
        layout_ramificado.addWidget(lbl_u)
        self.combo_uniones = QComboBox()
        self.combo_uniones.setObjectName("panelComboBox")
        self.combo_uniones.currentIndexChanged.connect(self._actualizar_texto_boton)
        layout_ramificado.addWidget(self.combo_uniones)
        self.boton_ramificado = QPushButton(crear_icono_herramienta("rama_red", "#ffffff"), "Resolver red ramificada")
        self.boton_ramificado.setObjectName("bernoulliButton")
        self.boton_ramificado.setFixedHeight(42)
        self.boton_ramificado.setCursor(Qt.PointingHandCursor)
        self.boton_ramificado.clicked.connect(self._on_resolver_bernoulli)
        layout_ramificado.addWidget(self.boton_ramificado)

        self.stack_modo.addWidget(widget_simple)
        self.stack_modo.addWidget(widget_ramificado)
        layout.addWidget(self.stack_modo, 0)

        # Encabezado de sección para resultados
        self.lbl_sec_resultados = QLabel("RESULTADOS  /  Resumen hidráulico")
        self.lbl_sec_resultados.setObjectName("resultsSectionTitle")
        layout.addWidget(self.lbl_sec_resultados)

        # Visor de resultados auto-ajustable en altura (sin scroll interno, usa el único scroll del panel)
        self.texto_resultados = _AutoHeightTextEdit(getattr(self, "panel_scroll", None))
        self.texto_resultados.setObjectName("dashboardResultados")
        self.texto_resultados.setReadOnly(True)
        self.texto_resultados.document().setDefaultFont(QFont("Segoe UI", 10))
        self.texto_resultados.document().setDefaultStyleSheet("body, p, td { font-family: 'Segoe UI'; }")
        self.texto_resultados.setPlaceholderText("Los resultados del análisis hidráulico aparecerán aquí.")
        layout.addWidget(self.texto_resultados, 0)

        # Barra única bicolor de Distribución de Pérdidas (Stitch)
        self.contenedor_barras = QFrame()
        self.contenedor_barras.setObjectName("lossesCard")
        layout_barras = QVBoxLayout(self.contenedor_barras)
        layout_barras.setContentsMargins(12, 10, 12, 10)
        layout_barras.setSpacing(6)

        cab_barras = QHBoxLayout()
        cab_barras.setContentsMargins(0, 0, 0, 0)
        lbl_tit_barras = QLabel("DISTRIBUCIÓN DE PÉRDIDAS")
        lbl_tit_barras.setObjectName("panelMicroLabel")
        self.lbl_hf_bar_total = QLabel()
        self.lbl_hf_bar_total.setObjectName("hfBarTotalLabel")
        cab_barras.addWidget(lbl_tit_barras)
        cab_barras.addStretch()
        cab_barras.addWidget(self.lbl_hf_bar_total)
        layout_barras.addLayout(cab_barras)

        self.bar_distribuida = _BarraDistribucionPerdidas()
        layout_barras.addWidget(self.bar_distribuida)

        # Mantenemos referencia de compatibilidad para bar_localizada (oculta)
        self.bar_localizada = QProgressBar()
        self.bar_localizada.hide()

        pie_barras = QVBoxLayout()
        pie_barras.setContentsMargins(0, 2, 0, 0)
        pie_barras.setSpacing(2)
        self.lbl_distribuida = QLabel()
        self.lbl_distribuida.setObjectName("barLegendLabel")
        self.lbl_distribuida.setWordWrap(True)
        self.lbl_localizada = QLabel()
        self.lbl_localizada.setObjectName("barLegendLabel")
        self.lbl_localizada.setWordWrap(True)
        self.lbl_bordes = QLabel()
        self.lbl_bordes.setObjectName("barLegendLabel")
        self.lbl_bordes.setWordWrap(True)
        pie_barras.addWidget(self.lbl_distribuida)
        pie_barras.addWidget(self.lbl_localizada)
        pie_barras.addWidget(self.lbl_bordes)
        layout_barras.addLayout(pie_barras)

        layout.addWidget(self.contenedor_barras, 0)
        self._limpiar_barra_perdidas()

        self.boton_excel = QPushButton(
            crear_icono_herramienta("excel", "#006398"), "  Exportar a Excel"
        )
        self.boton_excel.setObjectName("excelButton")
        self.boton_excel.setMinimumHeight(40)
        self.boton_excel.setCursor(Qt.PointingHandCursor)
        self.boton_excel.clicked.connect(self._exportar_excel)
        layout.addWidget(self.boton_excel, 0)
        self.boton_excel.hide()

        self._tanques_dashboard = []
        self._uniones_dashboard = []

    _desglosar_perdidas_tuberia = staticmethod(desglosar_perdidas_tuberia)
    _desglosar_hf_rutas = staticmethod(desglosar_hf_rutas)

    def _limpiar_barra_perdidas(self):
        """Oculta y reinicia el bloque de Distribución de Pérdidas cuando no hay resultados."""
        self._actualizar_barra_perdidas(0.0, 0.0, 0.0, 0.0, mostrar=False)

    def _actualizar_barra_perdidas(self, hf_total, hf_dist, hf_acc, hf_bordes=0.0, mostrar=True):
        self.lbl_hf_bar_total.setText(f"hf = {hf_total:.2f} m")
        hf_d = max(0.0, float(hf_dist or 0.0))
        hf_a = max(0.0, float(hf_acc or 0.0))
        hf_b = max(0.0, float(hf_bordes or 0.0))
        hf_barras = hf_d + hf_a + hf_b
        if hf_barras > 0:
            pct_dist = (hf_d / hf_barras) * 100.0
            pct_acc = (hf_a / hf_barras) * 100.0
            pct_brd = (hf_b / hf_barras) * 100.0
        else:
            pct_dist = pct_acc = pct_brd = 0.0
        self.bar_distribuida.set_proporciones(hf_d, hf_a, hf_b)
        fmt_val = "color:#0b1c30; font-weight:600; font-family:Consolas,monospace;"
        self.lbl_distribuida.setText(
            f"<span style='color:#e74c3c;'>●</span> "
            f"<span style='color:#72787f; font-weight:400;'>Fricción:</span> "
            f"<span style='{fmt_val}'>{pct_dist:.1f}% ({hf_d:.2f} m)</span>"
        )
        self.lbl_localizada.setText(
            f"<span style='color:#f59e0b;'>●</span> "
            f"<span style='color:#72787f; font-weight:400;'>Accesorios:</span> "
            f"<span style='{fmt_val}'>{pct_acc:.1f}% ({hf_a:.2f} m)</span>"
        )
        self.lbl_bordes.setText(
            f"<span style='color:#0d9488;'>●</span> "
            f"<span style='color:#72787f; font-weight:400;'>Bordes (Ent./Sal.):</span> "
            f"<span style='{fmt_val}'>{pct_brd:.1f}% ({hf_b:.2f} m)</span>"
        )
        if mostrar:
            self.contenedor_barras.show()
        else:
            self.contenedor_barras.hide()

    def _fila_tabla_cad_tuberia(self, tuberia, Q_si, hf_val):
        color_hex = (
            tuberia.color_personalizado.name()
            if tuberia.color_personalizado is not None
            else tuberia.pen().color().name()
        )
        nom_corto = f"Tubería {tuberia.id_tuberia}" if tuberia.id_tuberia is not None else tuberia.nombre
        try:
            L_si, D_si, eps_si = self._datos_si(tuberia)
            k_sum = tuberia.sumatoria_K
            resultado = evaluar_tramo(Q_si, L_si, D_si, eps_si, k_sum,
                tuberia.sumatoria_Le_D,
                dict(rho=self.fluido_rho, mu=self.fluido_mu, g=MotorFluidos.g),
                id=tuberia.id_tuberia)
        except (ValueError, TypeError, OverflowError) as error:
            resultado = None
            tip_tub = f'{nom_corto} | Datos inválidos: {error}'
            valores = ['—'] * 4
        else:
            tip_tub = (
                f"{nom_corto} | L = {resultado.L:.2f} m | D = {resultado.D*1000.0:.1f} mm | "
                f"ε = {resultado.eps*1000.0:.4f} mm | ΣK = {resultado.K:.2f} | "
                f"Re = {resultado.Re:,.0f} | {resultado.regimen}"
            )
            valores = [f'{resultado.Q:.4f}', f'{resultado.v:.2f}',
                       f'{resultado.f:.4f}' if resultado.f is not None else '—',
                       f'{resultado.hf_total:.2f}']
        celdas = [
            f"<span title='{tip_tub}' style='color:#0c4e77; font-weight:500;'>"
            f"<span style='color:{color_hex}; font-size:12px;'>●</span>&nbsp;{nom_corto}</span>",
            f"<span style='font-family:Consolas,monospace; color:#0b1c30; font-weight:400;'>{valores[0]}</span>",
            f"<span style='font-family:Consolas,monospace; color:#0b1c30; font-weight:400;'>{valores[1]}</span>",
            f"<span style='font-family:Consolas,monospace; color:#0b1c30; font-weight:400;'>{valores[2]}</span>",
            f"<span style='font-family:Consolas,monospace; color:#0c4e77; font-weight:600;'>{valores[3]}</span>",
        ]
        return celdas, resultado.Re if resultado is not None else None

    def _refrescar_combos_dashboard(self):
        tanques = sorted(
            (i for i in self.canvas_view.scene().items() if isinstance(i, TanqueGrafico)),
            key=lambda t: (t.id_tanque is None, t.id_tanque or 0),
        )

        previos = []
        for combo in (self.combo_punto1, self.combo_punto2):
            idx = combo.currentIndex()
            previos.append(
                self._tanques_dashboard[idx] if 0 <= idx < len(self._tanques_dashboard) else None
            )

        self._tanques_dashboard = tanques
        por_defecto = (0, 1 if len(tanques) > 1 else 0)
        for combo, previo, defecto in zip(
            (self.combo_punto1, self.combo_punto2), previos, por_defecto
        ):
            combo.clear()
            combo.addItems(
                [f"{t.nombre} ({formatear_numero(t.elevacion_z)} m)" for t in tanques]
            )
            if previo in tanques:
                combo.setCurrentIndex(tanques.index(previo))
            elif tanques:
                combo.setCurrentIndex(defecto)

        self._actualizar_texto_boton()

        union_previa = None
        idx_previo = self.combo_uniones.currentIndex()
        if 0 <= idx_previo < len(self._uniones_dashboard):
            union_previa = self._uniones_dashboard[idx_previo]

        uniones = [i for i in self.canvas_view.scene().items() if isinstance(i, NodoUnionGrafico)]
        self._uniones_dashboard = []
        self.combo_uniones.clear()

        def clave(x):
            return (x.id_union is None, x.id_union or 0)

        entradas = []

        for u in uniones:
            analisis = self._analizar_red_union(u) if hasattr(self, "_analizar_red_union") else None
            if analisis and analisis.get("valida"):
                if analisis["tipo"] == "tres_reservorios":
                    tanques_conectados = [t.nombre.replace("Tanque ", "T") for t in analisis["tanques"]]
                    entradas.append(
                        (clave(u), u, f"{u.nombre} ({', '.join(tanques_conectados)})")
                    )
                elif analisis["tipo"] == "bomba_ramificada":
                    bomba = analisis["bomba"]
                    nom_b = bomba.nombre
                    tq_b = analisis["tanque_bomba"].nombre.replace("Tanque ", "T")
                    tqs_r = ", ".join(r["tanque"].nombre.replace("Tanque ", "T") for r in analisis["ramas_tanques"])
                    entradas.append(
                        (clave(u), u, f"{nom_b} + {u.nombre} ({tq_b} → {tqs_r})")
                    )
            else:
                tanques_conectados = []
                es_valida = True
                for tub in u.tuberias:
                    extremo = tub.nodo_origen if tub.nodo_destino is u else tub.nodo_destino
                    if isinstance(extremo, TanqueGrafico):
                        tanques_conectados.append(extremo.nombre.replace("Tanque ", "T"))
                    else:
                        es_valida = False

                if es_valida and len(tanques_conectados) >= 3:
                    entradas.append(
                        (clave(u), u, f"{u.nombre} ({', '.join(tanques_conectados)})")
                    )

        pares_vistos = set()
        for u in uniones:
            for tub in u.tuberias:
                otro = tub.nodo_origen if tub.nodo_destino is u else tub.nodo_destino
                if not isinstance(otro, NodoUnionGrafico) or otro is u:
                    continue
                par = frozenset((id(u), id(otro)))
                if par in pares_vistos:
                    continue
                pares_vistos.add(par)

                j, k = sorted((u, otro), key=clave)
                if self._estructura_doble_nudo(j, k) is not None:
                    entradas.append(
                        (clave(j), (j, k), f"Doble Nudo ({j.nombre} - {k.nombre})")
                    )

        multinudos_vistos = set()
        if hasattr(self, "_analizar_componente_multinudo"):
            from ui.ventana.ramificadas import RedMultiNudo

            for u in uniones:
                comp = self._analizar_componente_multinudo(u)
                if not comp or not comp.get("valida"):
                    continue
                nodos_r = tuple(comp["nodos_ramificados"])
                clave_comp = tuple(id(n) for n in nodos_r)
                if clave_comp in multinudos_vistos:
                    continue
                multinudos_vistos.add(clave_comp)
                if comp.get("es_doble_nudo_estricto"):
                    continue
                if comp.get("es_unico_nudo"):
                    a_simple = (
                        self._analizar_red_union(nodos_r[0])
                        if hasattr(self, "_analizar_red_union")
                        else None
                    )
                    if a_simple and a_simple.get("valida"):
                        continue
                red_multi = RedMultiNudo(nodos_r)
                entradas.append((clave(nodos_r[0]), red_multi, red_multi.nombre))

        for _, red, texto in sorted(entradas, key=lambda e: e[0]):
            self._uniones_dashboard.append(red)
            self.combo_uniones.addItem(texto)

        if union_previa is not None and union_previa in self._uniones_dashboard:
            self.combo_uniones.setCurrentIndex(self._uniones_dashboard.index(union_previa))

    def _actualizar_texto_boton(self):
        try:
            i1 = self.combo_punto1.currentIndex()
            i2 = self.combo_punto2.currentIndex()
            tanques = getattr(self, "_tanques_dashboard", [])
            if 0 <= i1 < len(tanques) and 0 <= i2 < len(tanques) and i1 != i2:
                t1 = tanques[i1]
                t2 = tanques[i2]
                if hasattr(self, "_buscar_bomba_en_ruta"):
                    bomba, _ = self._buscar_bomba_en_ruta(t1, t2, diagnosticar=False)
                    if bomba is not None:
                        nom1 = t1.id_tanque if getattr(t1, "id_tanque", None) is not None else 1
                        nom2 = t2.id_tanque if getattr(t2, "id_tanque", None) is not None else 2
                        self.boton_bernoulli.setText(f"Calcular operación {nom1} → {nom2}")
                        return
        except Exception:
            pass
        self.boton_bernoulli.setText("Calcular Bernoulli")

        if hasattr(self, "combo_uniones") and hasattr(self, "boton_ramificado"):
            try:
                idx_u = self.combo_uniones.currentIndex()
                uniones_list = getattr(self, "_uniones_dashboard", [])
                if 0 <= idx_u < len(uniones_list):
                    item_u = uniones_list[idx_u]
                    if isinstance(item_u, NodoUnionGrafico) and hasattr(self, "_analizar_red_union"):
                        an = self._analizar_red_union(item_u)
                        if an and an.get("tipo") == "bomba_ramificada":
                            self.boton_ramificado.setText("Resolver bomba + ramificada")
                            return
            except Exception:
                pass
            self.boton_ramificado.setText("Resolver red ramificada")

    def _mostrar_dashboard(self):
        if hasattr(self, "lbl_panel_subtitle"):
            self.lbl_panel_subtitle.setText("CÁLCULO HIDRÁULICO")
        if hasattr(self, "lbl_panel_title"):
            self.lbl_panel_title.setText("Análisis del Sistema (Bernoulli)")
        self._limpiar_panel_content()
        self.campos_tuberia = {}
        self.campos_tanque = {}
        self.campos_accesorio = {}
        self.campos_nodo_union = {}
        self.campos_forma = {}

        self._refrescar_combos_dashboard()
        if (
            not getattr(self, "datos_exportacion", None)
            and hasattr(self, "texto_resultados")
            and not self.texto_resultados.toPlainText().strip()
        ):
            self._limpiar_barra_perdidas()
        self.panel_content_layout.addWidget(self.dashboard_widget)
        self.dashboard_widget.show()
        if hasattr(self, "panel_scroll") and self.panel_scroll is not None:
            self.panel_scroll.verticalScrollBar().setValue(0)
