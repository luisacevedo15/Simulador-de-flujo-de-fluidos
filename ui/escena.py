"""Escena y vista del lienzo CAD (cuadrícula, zoom, interacción)."""

from collections import deque

from PyQt5.QtCore import QLineF, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QToolTip,
)

from ui.constantes import ARCHIVOS_ESCUDO, ARCHIVO_LOGO_PROPIO, TEXTO_AUTOR
from ui.graficos import (
    AccesorioGrafico,
    BombaGrafica,
    CuadroTextoGrafico,
    EtiquetaFlotante,
    FormaGrafica,
    NodoUnionGrafico,
    TanqueGrafico,
    TuberiaGrafica,
)
from ui.recursos import cargar_logo


class GridScene(QGraphicsScene):
    elementos_modificados = pyqtSignal()
    MAX_PARALELAS = 3
    MARCA_ALTO_ESCUDO = 64
    MARCA_ALTO_ICONO = 48
    MARCA_MARGEN = 12
    MARCA_OPACIDAD_LOGOS = 1.0
    MARCA_OPACIDAD_TEXTO = 0.4

    def __init__(self, width=2000, height=2000, parent=None, main_window=None):
        super().__init__(0, 0, width, height, parent)
        self.main_window = main_window
        self._contador_tuberias_local = 1
        self._minor_step = 20
        self._major_step = 100
        self._minor_pen = QPen(QColor("#f1f5f9"))
        self._minor_pen.setWidth(0)
        self._major_pen = QPen(QColor("#e2e8f0"))
        self._major_pen.setWidth(0)
        self.setBackgroundBrush(QColor("#ffffff"))

        self._marca_logos = [
            cargar_logo(ARCHIVOS_ESCUDO, self.MARCA_ALTO_ESCUDO),
            cargar_logo(ARCHIVO_LOGO_PROPIO, self.MARCA_ALTO_ESCUDO),
        ]

        self.modo_conexion = False
        self.modo_texto = False
        self.tanque_origen_temporal = None
        self.linea_temporal = None
        self.vertices_conexion_temporal = []
        self.direccion_conexion_temporal = "H"
        self._pos_raton_temporal = None
        self.trazado_global = "recto"

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)

        left = int(rect.left()) - (int(rect.left()) % self._minor_step)
        top = int(rect.top()) - (int(rect.top()) % self._minor_step)

        minor_lines = []
        major_lines = []

        x = left
        while x < rect.right():
            line = QLineF(x, rect.top(), x, rect.bottom())
            major_lines.append(line) if x % self._major_step == 0 else minor_lines.append(line)
            x += self._minor_step

        y = top
        while y < rect.bottom():
            line = QLineF(rect.left(), y, rect.right(), y)
            major_lines.append(line) if y % self._major_step == 0 else minor_lines.append(line)
            y += self._minor_step

        painter.setPen(self._minor_pen)
        painter.drawLines(minor_lines)
        painter.setPen(self._major_pen)
        painter.drawLines(major_lines)

        self._dibujar_marca_de_agua(painter)

    def _dibujar_marca_de_agua(self, painter):
        vistas = self.views()
        if not vistas:
            return
        area = vistas[0].viewport().rect()

        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        fuente = QFont()
        fuente.setPointSize(8)
        painter.setFont(fuente)
        metricas = painter.fontMetrics()
        ancho_texto = metricas.horizontalAdvance(TEXTO_AUTOR) + 2
        alto_texto = metricas.height()
        derecha = area.right() - self.MARCA_MARGEN
        rect_texto = QRectF(
            derecha - ancho_texto, area.bottom() - self.MARCA_MARGEN - alto_texto,
            ancho_texto, alto_texto,
        )
        painter.setOpacity(self.MARCA_OPACIDAD_TEXTO)
        painter.setPen(QColor("#1f2d3d"))
        painter.drawText(rect_texto, Qt.AlignRight | Qt.AlignVCenter, TEXTO_AUTOR)

        logos = [(pm, opaco) for pm, opaco in self._marca_logos if pm is not None]
        if logos:
            alto_fila = max(pm.height() / 2.0 for pm, _ in logos)
            centro_y = rect_texto.top() - 6 - alto_fila / 2.0
            x_derecha = derecha
            painter.setOpacity(self.MARCA_OPACIDAD_LOGOS)
            for pixmap, es_opaco in reversed(logos):
                ancho_dest, alto_dest = pixmap.width() / 2.0, pixmap.height() / 2.0
                destino = QRectF(
                    x_derecha - ancho_dest, centro_y - alto_dest / 2.0, ancho_dest, alto_dest
                )
                if es_opaco:
                    painter.setCompositionMode(QPainter.CompositionMode_Multiply)
                painter.drawPixmap(destino, pixmap, QRectF(pixmap.rect()))
                painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
                x_derecha = destino.left() - 10

        painter.restore()

    def _nodo_en(self, pos):
        for item in self.items(pos):
            if item is self.linea_temporal:
                continue
            if isinstance(item, EtiquetaFlotante):
                item = item.parentItem()
            if isinstance(item, (TanqueGrafico, NodoUnionGrafico, BombaGrafica, AccesorioGrafico)):
                return item
        return None

    def _tomar_id_tuberia(self):
        if self.main_window is not None:
            id_tuberia = self.main_window.contador_tuberias
            self.main_window.contador_tuberias += 1
        else:
            id_tuberia = self._contador_tuberias_local
            self._contador_tuberias_local += 1
        return id_tuberia

    def cancelar_conexion(self):
        if self.linea_temporal is not None:
            if self.linea_temporal.scene() is self:
                self.removeItem(self.linea_temporal)
            self.linea_temporal = None

        origen = self.tanque_origen_temporal
        if origen is not None:
            self.tanque_origen_temporal = None
            origen.setSelected(False)
            origen.restaurar_borde()

        self.vertices_conexion_temporal = []
        self.direccion_conexion_temporal = "H"
        self._pos_raton_temporal = None

    def _actualizar_fantasma_conexion(self, pos_raton):
        """Actualiza la vista previa fantasma con la ruta ortogonal que sigue al ratón."""
        if self.linea_temporal is None or self.tanque_origen_temporal is None:
            return
        self._pos_raton_temporal = pos_raton
        origen = self.tanque_origen_temporal
        centro_origen = (
            origen.centro_escena()
            if hasattr(origen, "centro_escena")
            else origen.sceneBoundingRect().center()
        )

        from ui.enrutado_ortogonal import ruta_multivertice

        puntos_base = [centro_origen] + list(self.vertices_conexion_temporal) + [pos_raton]
        dir_salida = getattr(self, "direccion_conexion_temporal", "H")
        grid = getattr(self, "_minor_step", 20)
        if getattr(self, "trazado_global", "recto") == "recto" and not self.vertices_conexion_temporal:
            puntos = [centro_origen, pos_raton]
        else:
            puntos = ruta_multivertice(puntos_base, direccion_inicial=dir_salida, grid=grid)

        if puntos:
            path = QPainterPath(puntos[0])
            for pt in puntos[1:]:
                path.lineTo(pt)
            self.linea_temporal.setPath(path)

    def _parent_dialogo(self):
        return self.main_window or (self.views()[0] if self.views() else None)

    def _advertir_incompatible_ortogonal(self, mensaje=None):
        texto = mensaje or (
            "No es posible usar tuberías en paralelo ni circuitos cerrados "
            "con el trazado ortogonal.\n\n"
            "Cambia a \"Trazado: Recto\" para trabajar con tuberías en paralelo."
        )
        QMessageBox.warning(self._parent_dialogo(), "Trazado no compatible", texto)

    def _existe_camino_tuberias(self, origen, destino):
        if origen is None or destino is None:
            return False
        if origen is destino:
            return True
        adyacencia = {}
        for item in self.items():
            if isinstance(item, TuberiaGrafica):
                u, v = item.nodo_origen, item.nodo_destino
                if u is None or v is None:
                    continue
                adyacencia.setdefault(u, []).append(v)
                adyacencia.setdefault(v, []).append(u)
        visitados = {origen}
        cola = deque([origen])
        while cola:
            actual = cola.popleft()
            if actual is destino:
                return True
            for vecino in adyacencia.get(actual, ()):
                if vecino not in visitados:
                    visitados.add(vecino)
                    cola.append(vecino)
        return False

    def _tuberias_en_caminos(self, origen, destino):
        """Retorna las tuberías que forman caminos simples entre origen y destino."""
        if origen is None or destino is None or origen is destino:
            return []
        ady = {}
        directas = []
        par = {origen, destino}
        for item in self.items():
            if isinstance(item, TuberiaGrafica):
                u, v = item.nodo_origen, item.nodo_destino
                if u is None or v is None:
                    continue
                ady.setdefault(u, {}).setdefault(v, []).append(item)
                ady.setdefault(v, {}).setdefault(u, []).append(item)
                if {u, v} == par:
                    directas.append(item)

        en_caminos = []
        vistos = set()
        for t in directas:
            vistos.add(id(t))
            en_caminos.append(t)

        presupuesto = [5000]

        def _dfs(actual, visitados, tub_camino):
            if presupuesto[0] <= 0:
                return
            presupuesto[0] -= 1
            if actual is destino:
                for t in tub_camino:
                    if id(t) not in vistos:
                        vistos.add(id(t))
                        en_caminos.append(t)
                return
            for vecino, tubos in ady.get(actual, {}).items():
                if vecino in visitados:
                    continue
                visitados.add(vecino)
                _dfs(vecino, visitados, tub_camino + tubos)
                visitados.remove(vecino)

        _dfs(origen, {origen}, [])
        return en_caminos

    def _aplicar_modo_recto_global(self):
        """Sincroniza el selector y el estado global a 'recto' sin abrir diálogos."""
        self.trazado_global = "recto"
        if self.main_window is not None:
            if hasattr(self.main_window, "_reset_selector_trazado"):
                self.main_window._reset_selector_trazado()
            else:
                self.main_window.trazado_global = "recto"

    def _notificar_cambio_trazado_paralelo(self, texto):
        """Muestra una notificación breve en el lienzo y en la barra de estado."""
        for vista in self.views():
            if hasattr(vista, "mostrar_notificacion"):
                vista.mostrar_notificacion(texto)
        if self.main_window is not None and hasattr(self.main_window, "statusBar"):
            sb = self.main_window.statusBar()
            if sb is not None:
                sb.showMessage(texto, 5000)

    def validar_compatibilidad_ortogonal(self):
        """
        Verifica si la red actual del lienzo es compatible con trazado ortogonal.
        Retorna (True, None) o (False, motivo) si hay tuberías en paralelo o ciclos.
        """
        padre = {}

        def _encontrar(nodo):
            k = id(nodo)
            if k not in padre:
                padre[k] = k
            while padre[k] != k:
                padre[k] = padre[padre[k]]
                k = padre[k]
            return k

        for item in self.items():
            if isinstance(item, TuberiaGrafica):
                ra = _encontrar(item.nodo_origen)
                rb = _encontrar(item.nodo_destino)
                if ra == rb:
                    return (
                        False,
                        "No es posible usar trazado ortogonal con tuberías en paralelo "
                        "o circuitos cerrados.\n\n"
                        "Cambia a \"Trazado: Recto\" o elimina los ramales en paralelo.",
                    )
                padre[rb] = ra

        return (True, None)

    def mousePressEvent(self, event):
        if self.modo_texto and event.button() == Qt.LeftButton:
            if self.main_window is not None:
                self.main_window._add_cuadro_texto(event.scenePos())
            event.accept()
            return

        if self.modo_conexion and event.button() == Qt.LeftButton:
            pos_evento = event.scenePos()
            nodo = self._nodo_en(pos_evento)
            modo_global = getattr(self, "trazado_global", "recto")

            if isinstance(nodo, (TanqueGrafico, NodoUnionGrafico, BombaGrafica)):
                if self.tanque_origen_temporal is None:
                    if isinstance(nodo, BombaGrafica) and len(nodo.tuberias) >= 2:
                        QMessageBox.warning(
                            self._parent_dialogo(),
                            "Límite de conexiones en Bomba",
                            f"La {nodo.nombre} ya tiene sus dos tuberías conectadas (succión y descarga).",
                        )
                        event.accept()
                        return

                    self.tanque_origen_temporal = nodo
                    nodo.setSelected(True)
                    nodo.setPen(QPen(QColor("#0284c7"), 3, Qt.DashLine))

                    self.vertices_conexion_temporal = []
                    self.direccion_conexion_temporal = "H"
                    self._pos_raton_temporal = pos_evento

                    fantasma = QGraphicsPathItem()
                    fantasma.setPen(QPen(QColor("#0284c7"), 2.2, Qt.DashLine))
                    fantasma.setZValue(10)
                    fantasma.setAcceptedMouseButtons(Qt.NoButton)
                    self.addItem(fantasma)
                    self.linea_temporal = fantasma

                    self._actualizar_fantasma_conexion(pos_evento)
                elif nodo is not self.tanque_origen_temporal:
                    if isinstance(nodo, BombaGrafica) and len(nodo.tuberias) >= 2:
                        QMessageBox.warning(
                            self._parent_dialogo(),
                            "Límite de conexiones en Bomba",
                            f"La {nodo.nombre} ya tiene sus dos tuberías conectadas (succión y descarga).",
                        )
                        self.cancelar_conexion()
                        event.accept()
                        return

                    existentes = sum(
                        1
                        for item in self.items()
                        if isinstance(item, TuberiaGrafica)
                        and {item.nodo_origen, item.nodo_destino}
                        == {self.tanque_origen_temporal, nodo}
                    )
                    limite = 1 if (isinstance(nodo, BombaGrafica) or isinstance(self.tanque_origen_temporal, BombaGrafica)) else self.MAX_PARALELAS
                    if existentes >= limite:
                        msg = "Una bomba no admite tuberías directas en paralelo." if limite == 1 else f"Límite de paralelas alcanzado (Máximo {self.MAX_PARALELAS})."
                        QMessageBox.warning(
                            self.main_window or (self.views()[0] if self.views() else None),
                            "Límite alcanzado",
                            msg,
                        )
                        self.cancelar_conexion()
                    else:
                        origen = self.tanque_origen_temporal
                        vertices = list(self.vertices_conexion_temporal)
                        dir_init = getattr(self, "direccion_conexion_temporal", "H")

                        if self._existe_camino_tuberias(origen, nodo):
                            caminos = self._tuberias_en_caminos(origen, nodo)
                            hay_ortogonal_previo = any(
                                getattr(t, "modo_trazado", "recto") == "ortogonal"
                                or bool(getattr(t, "vertices_usuario", None))
                                for t in caminos
                            )
                            if modo_global == "ortogonal" or bool(vertices) or hay_ortogonal_previo:
                                for tub_prev in caminos:
                                    if (
                                        getattr(tub_prev, "modo_trazado", "recto") == "ortogonal"
                                        or bool(getattr(tub_prev, "vertices_usuario", None))
                                    ):
                                        tub_prev.convertir_a_recto(self)
                                modo_era_ortogonal = modo_global == "ortogonal"
                                self._aplicar_modo_recto_global()
                                modo_global = "recto"
                                vertices = []
                                msg_notif = (
                                    "Cambiado a Trazado: Recto — las tuberías en paralelo no admiten trazado ortogonal."
                                    if modo_era_ortogonal
                                    else "Convertido a Trazado: Recto — las tuberías en paralelo no admiten trazado ortogonal."
                                )
                                self._notificar_cambio_trazado_paralelo(msg_notif)

                        if self.linea_temporal is not None:
                            if self.linea_temporal.scene() is self:
                                self.removeItem(self.linea_temporal)
                            self.linea_temporal = None

                        tuberia = TuberiaGrafica(origen, nodo, id_tuberia=self._tomar_id_tuberia())
                        tuberia.modo_trazado = modo_global
                        tuberia.vertices_usuario = vertices
                        tuberia.direccion_inicial = dir_init
                        tuberia.actualizar_posicion()

                        self.addItem(tuberia)
                        self.elementos_modificados.emit()
                        origen.setSelected(False)
                        origen.restaurar_borde()
                        self.tanque_origen_temporal = None
                        self.vertices_conexion_temporal = []
                        self.direccion_conexion_temporal = "H"
                        self._pos_raton_temporal = None

            elif self.tanque_origen_temporal is not None and nodo is None:
                # Clic en espacio vacío: fija un vértice intermedio ajustado a la cuadrícula
                grid = getattr(self, "_minor_step", 20)
                v_snap = QPointF(
                    round(pos_evento.x() / grid) * grid,
                    round(pos_evento.y() / grid) * grid,
                )
                self.vertices_conexion_temporal.append(v_snap)
                self._actualizar_fantasma_conexion(pos_evento)
                QToolTip.showText(
                    QCursor.pos(),
                    "Quiebre ortogonal fijado: estético (no genera pérdida K automática).",
                )

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.linea_temporal is not None:
            self._actualizar_fantasma_conexion(event.scenePos())
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        foco = self.focusItem()
        if isinstance(foco, CuadroTextoGrafico) and foco.en_edicion():
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key_Escape:
            if self.modo_conexion:
                self.cancelar_conexion()
                event.accept()
                return

        if event.key() == Qt.Key_R:
            if self.modo_conexion and self.tanque_origen_temporal is not None:
                self.direccion_conexion_temporal = (
                    "V" if getattr(self, "direccion_conexion_temporal", "H") == "H" else "H"
                )
                if self._pos_raton_temporal is not None:
                    self._actualizar_fantasma_conexion(self._pos_raton_temporal)
                event.accept()
                return

        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if any(
                isinstance(i, CuadroTextoGrafico) and i.en_edicion()
                for i in self.selectedItems()
            ):
                super().keyPressEvent(event)
                return
            self.borrar_seleccion()
            event.accept()
            return

        super().keyPressEvent(event)

    def borrar_seleccion(self):
        seleccionados = self.selectedItems()
        tuberias = [i for i in seleccionados if isinstance(i, TuberiaGrafica)]
        tanques = [i for i in seleccionados if isinstance(i, TanqueGrafico)]
        uniones = [i for i in seleccionados if isinstance(i, NodoUnionGrafico)]
        bombas = [i for i in seleccionados if isinstance(i, BombaGrafica)]
        accesorios = [i for i in seleccionados if isinstance(i, AccesorioGrafico) and not isinstance(i, BombaGrafica)]
        formas = [i for i in seleccionados if isinstance(i, FormaGrafica)]
        textos = [
            i
            for i in seleccionados
            if isinstance(i, CuadroTextoGrafico) and not i.en_edicion()
        ]

        if not (tuberias or tanques or uniones or bombas or accesorios or formas or textos):
            return

        for item in tuberias + tanques + uniones + bombas + accesorios + formas + textos:
            item.setSelected(False)

        for tuberia in tuberias:
            self._eliminar_tuberia(tuberia)
        for tanque in tanques:
            self._eliminar_tanque(tanque)
        for union in uniones:
            self._eliminar_union(union)
        for bomba in bombas:
            self._eliminar_bomba(bomba)
        for accesorio in accesorios:
            self._eliminar_accesorio(accesorio)
        for forma in formas:
            if forma.scene() is self:
                self.removeItem(forma)
        for texto in textos:
            if texto.scene() is self:
                self.removeItem(texto)

        self.elementos_modificados.emit()

    def _eliminar_tuberia(self, tuberia):
        tuberia.desconectar()
        if tuberia.scene() is self:
            self.removeItem(tuberia)

    def _eliminar_tanque(self, tanque):
        for tuberia in list(tanque.tuberias):
            self._eliminar_tuberia(tuberia)
        tanque.tuberias.clear()

        if self.tanque_origen_temporal is tanque:
            self.cancelar_conexion()

        if tanque.scene() is self:
            self.removeItem(tanque)

    def _eliminar_union(self, union):
        for tuberia in list(union.tuberias):
            self._eliminar_tuberia(tuberia)
        union.tuberias.clear()

        if self.tanque_origen_temporal is union:
            self.cancelar_conexion()

        if union.scene() is self:
            self.removeItem(union)

    def _eliminar_bomba(self, bomba):
        for tuberia in list(bomba.tuberias):
            self._eliminar_tuberia(tuberia)
        bomba.tuberias.clear()

        if self.tanque_origen_temporal is bomba:
            self.cancelar_conexion()

        if bomba.scene() is self:
            self.removeItem(bomba)

    def _eliminar_accesorio(self, accesorio):
        if self.tanque_origen_temporal is accesorio:
            self.cancelar_conexion()

        accesorio.desanclar()

        for tuberia in list(accesorio.tuberias):
            self._eliminar_tuberia(tuberia)
        accesorio.tuberias.clear()

        if accesorio.scene() is self:
            self.removeItem(accesorio)


class CanvasView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("canvasView")
        self.setRenderHint(QPainter.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.IntersectsItemShape)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.viewport().setMouseTracking(True)

        self._zoom_step = 1.15
        self._min_scale = 0.2
        self._max_scale = 5.0
        self._current_scale = 1.0

        self._panning = False
        self._pan_movido = False
        self._pan_origen = QPointF()
        self._pan_ultima = QPointF()

        # HUD Flotante Izquierdo: Píldora de Selección
        self.hud_seleccion_frame = QFrame(self)
        self.hud_seleccion_frame.setObjectName("hudSeleccionFrame")
        self.hud_seleccion_frame.setMinimumHeight(28)
        hud_sel_layout = QHBoxLayout(self.hud_seleccion_frame)
        hud_sel_layout.setContentsMargins(12, 5, 12, 5)
        hud_sel_layout.setSpacing(6)
        self.lbl_hud_seleccion = QLabel(self.hud_seleccion_frame)
        self.lbl_hud_seleccion.setObjectName("hudSeleccionLabel")
        self.lbl_hud_seleccion.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.lbl_hud_seleccion.setMinimumHeight(18)
        self.lbl_seleccion_hud = self.lbl_hud_seleccion
        hud_sel_layout.addWidget(self.lbl_hud_seleccion)

        # HUD Flotante Derecho: Barra de Zoom ([ - ] 100% [ + ] [ ⛶ ])
        self.hud_zoom_frame = QFrame(self)
        self.hud_zoom_frame.setObjectName("hudZoomFrame")
        hud_zoom_layout = QHBoxLayout(self.hud_zoom_frame)
        hud_zoom_layout.setContentsMargins(4, 3, 4, 3)
        hud_zoom_layout.setSpacing(2)

        self.btn_zoom_out = QPushButton("−", self.hud_zoom_frame)
        self.btn_zoom_out.setObjectName("hudZoomBtn")
        self.btn_zoom_out.setFixedSize(26, 24)
        self.btn_zoom_out.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_out.setToolTip("Alejar")
        self.btn_zoom_out.clicked.connect(self.zoom_out)

        self.lbl_zoom_pct = QLabel("100%", self.hud_zoom_frame)
        self.lbl_zoom_pct.setObjectName("hudZoomLabel")
        self.lbl_zoom_pct.setAlignment(Qt.AlignCenter)
        self.lbl_zoom_pct.setFixedWidth(44)

        self.btn_zoom_in = QPushButton("+", self.hud_zoom_frame)
        self.btn_zoom_in.setObjectName("hudZoomBtn")
        self.btn_zoom_in.setFixedSize(26, 24)
        self.btn_zoom_in.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_in.setToolTip("Acercar")
        self.btn_zoom_in.clicked.connect(self.zoom_in)

        self.btn_zoom_reset = QPushButton("⛶", self.hud_zoom_frame)
        self.btn_zoom_reset.setObjectName("hudZoomBtn")
        self.btn_zoom_reset.setFixedSize(26, 24)
        self.btn_zoom_reset.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_reset.setToolTip("Ajustar a pantalla (encuadrar elementos)")
        self.btn_zoom_reset.clicked.connect(self.zoom_reset)

        hud_zoom_layout.addWidget(self.btn_zoom_out)
        hud_zoom_layout.addWidget(self.lbl_zoom_pct)
        hud_zoom_layout.addWidget(self.btn_zoom_in)
        hud_zoom_layout.addWidget(self.btn_zoom_reset)
        self.hud_zoom_frame.adjustSize()

        # Notificación flotante corta para avisos automáticos del lienzo
        self.hud_notificacion_frame = QFrame(self)
        self.hud_notificacion_frame.setObjectName("hudNotificacionFrame")
        hud_notif_layout = QHBoxLayout(self.hud_notificacion_frame)
        hud_notif_layout.setContentsMargins(12, 5, 8, 5)
        hud_notif_layout.setSpacing(8)
        self.lbl_hud_notificacion = QLabel(self.hud_notificacion_frame)
        self.lbl_hud_notificacion.setObjectName("hudNotificacionLabel")
        self.lbl_hud_notificacion.setWordWrap(False)
        hud_notif_layout.addWidget(self.lbl_hud_notificacion)

        self.btn_cerrar_notificacion = QPushButton("×", self.hud_notificacion_frame)
        self.btn_cerrar_notificacion.setObjectName("hudNotificacionClose")
        self.btn_cerrar_notificacion.setFixedSize(18, 18)
        self.btn_cerrar_notificacion.setCursor(Qt.PointingHandCursor)
        self.btn_cerrar_notificacion.setToolTip("Cerrar aviso")
        self.btn_cerrar_notificacion.clicked.connect(self.hud_notificacion_frame.hide)
        hud_notif_layout.addWidget(self.btn_cerrar_notificacion)
        self.hud_notificacion_frame.hide()

        self._timer_notificacion = QTimer(self)
        self._timer_notificacion.setSingleShot(True)
        self._timer_notificacion.timeout.connect(self.hud_notificacion_frame.hide)

        self.set_seleccion_hud("Ninguna")

    def mostrar_notificacion(self, texto, duracion_ms=5000):
        """Muestra un aviso breve no bloqueante en la parte superior del lienzo."""
        self.lbl_hud_notificacion.setText(str(texto))
        self.hud_notificacion_frame.adjustSize()
        self._reposicionar_huds()
        self.hud_notificacion_frame.show()
        self.hud_notificacion_frame.raise_()
        if duracion_ms and duracion_ms > 0:
            self._timer_notificacion.start(int(duracion_ms))
        else:
            self._timer_notificacion.stop()

    def set_seleccion_hud(self, texto):
        val = texto if texto else "Ninguna"
        self.lbl_hud_seleccion.setText(
            f"<span style='color:#64748b; font-size:11px; font-weight:600;'>Selección:</span>&nbsp;"
            f"<span style='color:#0c4e77; font-size:11.5px; font-weight:700;'>{val}&nbsp;</span>"
        )
        self.lbl_hud_seleccion.ensurePolished()
        self.hud_seleccion_frame.ensurePolished()
        self.lbl_hud_seleccion.adjustSize()
        self.hud_seleccion_frame.adjustSize()
        self._reposicionar_huds()

    def showEvent(self, event):
        super().showEvent(event)
        self.lbl_hud_seleccion.adjustSize()
        self.hud_seleccion_frame.adjustSize()
        self._reposicionar_huds()

    def _actualizar_label_zoom(self):
        pct = int(round(self._current_scale * 100))
        self.lbl_zoom_pct.setText(f"{pct}%")

    def _reposicionar_huds(self):
        w_view = self.viewport().width() if self.viewport() else self.width()
        if hasattr(self, "hud_seleccion_frame"):
            self.hud_seleccion_frame.move(14, 14)
        x_zoom = 160
        if hasattr(self, "hud_zoom_frame"):
            x_zoom = max(160, w_view - self.hud_zoom_frame.width() - 14)
            self.hud_zoom_frame.move(x_zoom, 14)
        if hasattr(self, "hud_notificacion_frame"):
            w_notif = self.hud_notificacion_frame.width()
            x_centrado = max(14, (w_view - w_notif) // 2)
            limite_izq = (
                self.hud_seleccion_frame.geometry().right() + 12
                if hasattr(self, "hud_seleccion_frame")
                else 14
            )
            limite_der = x_zoom - 12 if hasattr(self, "hud_zoom_frame") else w_view - 14
            cabe_en_fila = (x_centrado >= limite_izq) and ((x_centrado + w_notif) <= limite_der)
            y_notif = 14 if cabe_en_fila else 50
            self.hud_notificacion_frame.move(x_centrado, y_notif)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposicionar_huds()

    def zoom_in(self):
        new_scale = self._current_scale * self._zoom_step
        if new_scale <= self._max_scale:
            self._current_scale = new_scale
            self.scale(self._zoom_step, self._zoom_step)
            self._actualizar_label_zoom()

    def zoom_out(self):
        factor = 1.0 / self._zoom_step
        new_scale = self._current_scale * factor
        if new_scale >= self._min_scale:
            self._current_scale = new_scale
            self.scale(factor, factor)
            self._actualizar_label_zoom()

    def zoom_reset(self):
        self.resetTransform()
        self._current_scale = 1.0
        escena = self.scene()
        if escena is not None:
            principales = [
                i
                for i in escena.items()
                if isinstance(
                    i,
                    (
                        TanqueGrafico,
                        NodoUnionGrafico,
                        BombaGrafica,
                        TuberiaGrafica,
                        AccesorioGrafico,
                        FormaGrafica,
                        CuadroTextoGrafico,
                    ),
                )
            ]
            if principales:
                rect = principales[0].sceneBoundingRect()
                for it in principales[1:]:
                    rect = rect.united(it.sceneBoundingRect())
                rect = rect.adjusted(-60, -60, 60, 60)
                vp = self.viewport().rect()
                if vp.width() > 80 and vp.height() > 80 and rect.width() > 0 and rect.height() > 0:
                    sx = vp.width() / rect.width()
                    sy = vp.height() / rect.height()
                    escala = max(self._min_scale, min(1.0, min(sx, sy)))
                    self.scale(escala, escala)
                    self._current_scale = escala
                    self.centerOn(rect.center())
        self._actualizar_label_zoom()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._panning = True
            self._pan_movido = False
            self._pan_origen = event.pos()
            self._pan_ultima = event.pos()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_ultima
            self._pan_ultima = event.pos()
            if (event.pos() - self._pan_origen).manhattanLength() > 4:
                self._pan_movido = True
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton and self._panning:
            self._panning = False
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self._pan_movido:
            self._pan_movido = False
            event.accept()
            return
        super().contextMenuEvent(event)

    def wheelEvent(self, event):
        factor = self._zoom_step if event.angleDelta().y() > 0 else 1 / self._zoom_step
        new_scale = self._current_scale * factor

        if new_scale < self._min_scale or new_scale > self._max_scale:
            return

        self._current_scale = new_scale
        self.scale(factor, factor)
        self._actualizar_label_zoom()

    def keyPressEvent(self, event):
        escena = self.scene()
        if escena is not None and getattr(escena, "modo_conexion", False):
            if event.key() in (Qt.Key_Escape, Qt.Key_R):
                escena.keyPressEvent(event)
                if event.isAccepted():
                    return
        super().keyPressEvent(event)

