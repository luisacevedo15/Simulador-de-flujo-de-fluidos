"""Elementos gráficos del lienzo: tanques, tuberías, accesorios, nodos y textos."""

import math

from PyQt5 import QtGui
from PyQt5.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
)
from PyQt5.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QMenu,
    QMessageBox,
    QStyle,
)

from ui.curvas_presentacion import usa_puntos,puntos_tabla,resumen_puntos,nota_joroba
from ui.animaciones import RealceGraficoMixin
from ui.constantes import COLORES_TEXTO, FACTORES_SI, TAMANOS_TEXTO, formatear_numero


MODOS_CONEXION_TANQUE = ("ninguno", "salida", "entrada")
K_ENTRADA_TANQUE = 1.0


def normalizar_conexion_tanque(config=None):
    """Normaliza una conexión tanque-tubería a {modo, tipo_borde, K}."""
    if not isinstance(config, dict):
        return {"modo": "ninguno", "tipo_borde": "", "K": 0.0}
    modo = str(config.get("modo", "ninguno") or "ninguno").strip().lower()
    if modo not in MODOS_CONEXION_TANQUE:
        modo = "ninguno"
    if modo == "ninguno":
        return {"modo": "ninguno", "tipo_borde": "", "K": 0.0}
    if modo == "entrada":
        return {"modo": "entrada", "tipo_borde": "", "K": float(K_ENTRADA_TANQUE)}
    try:
        k_val = float(config.get("K", 0.0) or 0.0)
    except (TypeError, ValueError):
        k_val = 0.0
    if not math.isfinite(k_val) or k_val < 0.0:
        k_val = 0.0
    return {"modo": "salida", "tipo_borde": "", "K": k_val}


def _acompanar_anclados_en_bloque(item, nueva_pos):
    escena = item.scene()
    if (
        escena is None
        or not item.isSelected()
        or not (item.flags() & QGraphicsItem.ItemIsMovable)
        or escena.mouseGrabberItem() is None
    ):
        return
    desplazamiento = nueva_pos - item.pos()
    if desplazamiento.isNull():
        return

    movibles = 0
    anclados = []
    for otro in escena.selectedItems():
        if otro.flags() & QGraphicsItem.ItemIsMovable:
            if isinstance(
                otro,
                (
                    TanqueGrafico,
                    NodoUnionGrafico,
                    BombaGrafica,
                    AccesorioGrafico,
                    FormaGrafica,
                    CuadroTextoGrafico,
                ),
            ):
                movibles += 1
        elif isinstance(otro, AccesorioGrafico) and otro.tuberia_padre is not None:
            anclados.append(otro)
    if not anclados or movibles == 0:
        return

    parte = desplazamiento / movibles
    for accesorio in anclados:
        accesorio.setPos(accesorio.pos() + parte)


class EtiquetaFlotante(QGraphicsTextItem):
    def __init__(self, parent=None, tamano_fuente=8.5):
        super().__init__(parent)

        fuente = QFont("Segoe UI", int(tamano_fuente))
        fuente.setWeight(QFont.DemiBold)
        self.setFont(fuente)
        self.setDefaultTextColor(QColor("#0c4e77"))

        self.document().setDocumentMargin(2.0)
        opcion = self.document().defaultTextOption()
        opcion.setAlignment(Qt.AlignCenter)
        self.document().setDefaultTextOption(opcion)

        self._fondo = QBrush(QColor(255, 255, 255, 245))
        self._borde = QPen(QColor("#cbd5e1"), 1.0)

        self.setAcceptedMouseButtons(Qt.NoButton)

    def establecer_texto(self, texto):
        if texto:
            self.setPlainText(texto)
            self.setTextWidth(-1)
            self.setTextWidth(self.document().idealWidth())
            self.show()
        else:
            self.setPlainText("")
            self.hide()

    def paint(self, painter, option, widget=None):
        if not self.toPlainText():
            return
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.boundingRect()
        radio = min(rect.height() / 2.0, 8.0)
        # Sombra suave tenue
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 23, 42, 12))
        painter.drawRoundedRect(rect.translated(0.5, 1.0), radio, radio)
        # Fondo claro y borde redondeado estilo píldora
        painter.setPen(self._borde)
        painter.setBrush(self._fondo)
        painter.drawRoundedRect(rect, radio, radio)
        super().paint(painter, option, widget)


class FormaGrafica(QGraphicsItem):
    """Línea, flecha o flecha doble que se puede estirar interactuando con sus extremos."""
    TIPO_LINEA = "Línea"
    TIPO_FLECHA = "Flecha"
    TIPO_DOBLE_FLECHA = "Flecha Doble"
    
    ESTILO_CONTINUA = "Continua"
    ESTILO_PUNTEADA = "Punteada"
    ESTILO_GUIONES = "Guiones"

    def __init__(self, x1=0, y1=0, x2=100, y2=0, tipo=TIPO_LINEA, parent=None):
        super().__init__(parent)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)

        self.p1 = QPointF(x1, y1)
        self.p2 = QPointF(x2, y2)
        
        self.tipo_forma = tipo
        self.estilo_linea = self.ESTILO_CONTINUA
        self.color = QColor("#0284c7")
        self.grosor = 3
        self.texto = "Texto..."
        
        self.arrastrando_punto = 0  # 1: p1, 2: p2, 0: ninguno
        
        # Etiqueta
        self.etiqueta = EtiquetaFlotante(self, tamano_fuente=9)
        self.actualizar_etiqueta()

    def boundingRect(self):
        extra = self.grosor / 2.0 + 15  # espacio para las cabezas de flecha y manejadores
        return QRectF(self.p1, self.p2).normalized().adjusted(-extra, -extra, extra, extra)

    def shape(self):
        path = QPainterPath(self.p1)
        path.lineTo(self.p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(self.grosor + 15)
        return stroker.createStroke(path)
        
    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self.color, self.grosor)
        
        if self.estilo_linea == self.ESTILO_PUNTEADA:
            pen.setStyle(Qt.DotLine)
        elif self.estilo_linea == self.ESTILO_GUIONES:
            pen.setStyle(Qt.DashLine)
        else:
            pen.setStyle(Qt.SolidLine)
            
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(self.color)
        
        line = QLineF(self.p1, self.p2)
        painter.drawLine(line)
        
        # Flechas
        if self.tipo_forma in (self.TIPO_FLECHA, self.TIPO_DOBLE_FLECHA) and line.length() > 0:
            angle = math.atan2(-line.dy(), line.dx())
            arrow_size = self.grosor * 4 + 4
            
            # Flecha en p2
            p2_p1 = QPointF(
                self.p2.x() - arrow_size * math.cos(angle + math.pi / 6),
                self.p2.y() + arrow_size * math.sin(angle + math.pi / 6)
            )
            p2_p2 = QPointF(
                self.p2.x() - arrow_size * math.cos(angle - math.pi / 6),
                self.p2.y() + arrow_size * math.sin(angle - math.pi / 6)
            )
            arrow_head = QPolygonF([self.p2, p2_p1, p2_p2])
            painter.drawPolygon(arrow_head)
            
            # Flecha en p1 (doble)
            if self.tipo_forma == self.TIPO_DOBLE_FLECHA:
                p1_p1 = QPointF(
                    self.p1.x() + arrow_size * math.cos(angle + math.pi / 6),
                    self.p1.y() - arrow_size * math.sin(angle + math.pi / 6)
                )
                p1_p2 = QPointF(
                    self.p1.x() + arrow_size * math.cos(angle - math.pi / 6),
                    self.p1.y() - arrow_size * math.sin(angle - math.pi / 6)
                )
                arrow_head_2 = QPolygonF([self.p1, p1_p1, p1_p2])
                painter.drawPolygon(arrow_head_2)

        # Dibujar manejadores si está seleccionado
        if self.isSelected():
            painter.setBrush(QColor("#38bdf8"))
            painter.setPen(QPen(QColor("#0284c7"), 1))
            tam = 8
            painter.drawRect(QRectF(self.p1.x() - tam/2, self.p1.y() - tam/2, tam, tam))
            painter.drawRect(QRectF(self.p2.x() - tam/2, self.p2.y() - tam/2, tam, tam))

    def mousePressEvent(self, event):
        dist1 = QLineF(event.pos(), self.p1).length()
        dist2 = QLineF(event.pos(), self.p2).length()
        tol = 10 + self.grosor
        if dist1 < tol:
            self.arrastrando_punto = 1
            event.accept()
        elif dist2 < tol:
            self.arrastrando_punto = 2
            event.accept()
        else:
            self.arrastrando_punto = 0
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.arrastrando_punto == 1:
            self.prepareGeometryChange()
            self.p1 = event.pos()
            self.actualizar_etiqueta()
            self.update()
        elif self.arrastrando_punto == 2:
            self.prepareGeometryChange()
            self.p2 = event.pos()
            self.actualizar_etiqueta()
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.arrastrando_punto != 0:
            self.arrastrando_punto = 0
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        dist1 = QLineF(event.pos(), self.p1).length()
        dist2 = QLineF(event.pos(), self.p2).length()
        tol = 10 + self.grosor
        if dist1 < tol or dist2 < tol:
            self.setCursor(Qt.CrossCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def actualizar_etiqueta(self):
        self.etiqueta.establecer_texto(self.texto)
        line = QLineF(self.p1, self.p2)
        centro = line.pointAt(0.5)
        rect = self.etiqueta.boundingRect()
        self.etiqueta.setPos(
            centro.x() - rect.width() / 2,
            centro.y() - rect.height() - self.grosor / 2 - 2,
        )

    def set_color(self, color):
        self.color = color
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            _acompanar_anclados_en_bloque(self, value)
        return super().itemChange(change, value)


class CuadroTextoGrafico(QGraphicsTextItem):
    """Cuadro de texto libre estilo PowerPoint sobre el lienzo."""

    def __init__(self, x=0, y=0, texto="Escribe aquí", parent=None):
        super().__init__(parent)
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(3)

        self.tamano_clave = "Mediano"
        self.color_texto = QColor(COLORES_TEXTO[0])
        self.negrita = False
        self._callback_cambio = None

        self.setPlainText(texto)
        self._aplicar_fuente()
        self.setDefaultTextColor(self.color_texto)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        self.document().contentsChanged.connect(self._on_contenido_cambiado)

    def _aplicar_fuente(self):
        pt = TAMANOS_TEXTO.get(self.tamano_clave, TAMANOS_TEXTO["Mediano"])
        fuente = QFont("Segoe UI", pt)
        fuente.setBold(bool(self.negrita))
        self.setFont(fuente)
        self.prepareGeometryChange()
        self.update()

    def set_tamano(self, clave):
        if clave in TAMANOS_TEXTO:
            self.tamano_clave = clave
            self._aplicar_fuente()

    def set_color(self, color):
        self.color_texto = QColor(color)
        self.setDefaultTextColor(self.color_texto)
        self.update()

    def set_negrita(self, activo):
        self.negrita = bool(activo)
        self._aplicar_fuente()

    def en_edicion(self):
        return bool(self.textInteractionFlags() & Qt.TextEditorInteraction)

    def activar_edicion(self, seleccionar_todo=False):
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)
        cursor = self.textCursor()
        if seleccionar_todo:
            cursor.select(QtGui.QTextCursor.Document)
        else:
            cursor.clearSelection()
        self.setTextCursor(cursor)
        self.update()

    def desactivar_edicion(self):
        if self.en_edicion():
            self.setTextInteractionFlags(Qt.NoTextInteraction)
            cursor = self.textCursor()
            cursor.clearSelection()
            self.setTextCursor(cursor)
            self.clearFocus()
        if not self.toPlainText().strip():
            escena = self.scene()
            if escena is not None:
                self.setSelected(False)
                escena.removeItem(self)
                escena.elementos_modificados.emit()
                return
        self.update()

    def _on_contenido_cambiado(self):
        self.prepareGeometryChange()
        self.update()
        if self._callback_cambio is not None:
            self._callback_cambio(self.toPlainText())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activar_edicion(seleccionar_todo=False)
            super().mouseDoubleClickEvent(event)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.desactivar_edicion()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.desactivar_edicion()
            event.accept()
            return
        super().keyPressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            _acompanar_anclados_en_bloque(self, value)
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        mostrar_marco = self.isSelected() or self.en_edicion()
        if mostrar_marco:
            rect = self.boundingRect().adjusted(-2, -1, 2, 1)
            pen = QPen(QColor("#0284c7"), 1.4, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QColor(2, 132, 199, 20))
            painter.drawRoundedRect(rect, 5, 5)
        painter.restore()

        opt = QtGui.QStyleOptionGraphicsItem(option) if hasattr(QtGui, "QStyleOptionGraphicsItem") else option
        try:
            from PyQt5.QtWidgets import QStyleOptionGraphicsItem
            opt = QStyleOptionGraphicsItem(option)
            opt.state &= ~(QStyle.State_Selected | QStyle.State_HasFocus)
        except Exception:
            opt = option
        super().paint(painter, opt, widget)


class NodoUnionGrafico(RealceGraficoMixin, QGraphicsEllipseItem):
    DIAMETRO = 16

    def __init__(self, x=0, y=0, parent=None, id_union=None):
        super().__init__(0, 0, 16, 16, parent)
        self.setPos(x, y)
        self.id_union = id_union
        self.setBrush(QBrush(QColor("#334155")))
        self.setPen(QPen(QColor("#0f172a"), 2))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setTransformOriginPoint(8, 8)
        self.setZValue(1)
        self.tuberias = []
        self.energia_supuesta = 0.0
        self.hj_calculada = None
        self.etiqueta = EtiquetaFlotante(self, tamano_fuente=8)
        self.etiqueta._fondo = QBrush(QColor("#0f172a"))
        self.etiqueta._borde = QPen(QColor("#0f172a"), 1.0)
        self.etiqueta.setDefaultTextColor(QColor("#ffffff"))
        self.actualizar_etiqueta()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        # Halo de selección
        if self.isSelected():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(2, 132, 199, 75))
            painter.drawEllipse(r.adjusted(-4, -4, 4, 4))

        # Brida exterior
        borde = QColor("#0284c7") if self.isSelected() else self.color_interactivo("#0f172a")
        painter.setPen(QPen(borde, 2))
        painter.setBrush(self.color_interactivo("#334155"))
        painter.drawEllipse(r)

        # Centro metálico
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#38bdf8") if self.isSelected() else QColor("#94a3b8"))
        painter.drawEllipse(r.adjusted(4.5, 4.5, -4.5, -4.5))

    def restaurar_borde(self):
        self.setPen(QPen(QColor("#0f172a"), 2, Qt.SolidLine))

    @property
    def nombre(self):
        return f"Unión {self.id_union}" if self.id_union else "Unión"

    def actualizar_etiqueta(self):
        codigo = f"J-{self.id_union}" if self.id_union else "J"
        texto = codigo
        if self.hj_calculada is not None:
            texto += f"\nHj: {self.hj_calculada:.2f} m"
        self.etiqueta.establecer_texto(texto)
        rect_etiq = self.etiqueta.boundingRect()
        self.etiqueta.setPos(8 - rect_etiq.width() / 2, -rect_etiq.height() - 4)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            _acompanar_anclados_en_bloque(self, value)
        elif change == QGraphicsItem.ItemPositionHasChanged:
            for tuberia in self.tuberias:
                tuberia.actualizar_posicion()
        return super().itemChange(change, value)


class TanqueGrafico(RealceGraficoMixin, QGraphicsRectItem):
    ANCHO = 60
    ALTO = 80

    def __init__(self, x=0, y=0, parent=None, id_tanque=None):
        super().__init__(0, 0, self.ANCHO, self.ALTO, parent)
        self.setPos(x, y)
        self.id_tanque = id_tanque
        self.color_fondo = QColor("#7dd3fc")
        self.setPen(QPen(QColor("#1a1a1a"), 2))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.elevacion_z = 0.0
        self.presion_P = 0.0
        self.abierto_atmosfera = True
        self.tuberias = []
        self.etiqueta = EtiquetaFlotante(self, tamano_fuente=8)
        self.actualizar_etiqueta()

    def boundingRect(self):
        return self.rect().adjusted(-20, -34, 20, 6)

    @property
    def color_fondo(self):
        return self._color_fondo

    @color_fondo.setter
    def color_fondo(self, color):
        self._color_fondo = QColor(color)
        self.setBrush(QBrush(self._color_fondo))

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        cx = r.center().x()

        # 1. Sombra exterior suave
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 23, 42, 22))
        painter.drawRoundedRect(r.translated(3, 4), 4, 4)

        # 2. Fondo interior del reservorio (vacío arriba)
        painter.setBrush(QColor("#f8fafc"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(r, 3, 3)

        # 3. Fluido con degradado vertical (ocupa el 78% inferior del tanque)
        nivel_y = r.top() + r.height() * 0.22
        rect_agua = QRectF(r.left() + 2, nivel_y, r.width() - 4, r.height() * 0.78 - 2)
        grad = QtGui.QLinearGradient(rect_agua.topLeft(), rect_agua.bottomLeft())
        c_base = self.color_interactivo(self._color_fondo)
        grad.setColorAt(0.0, c_base.lighter(115))
        grad.setColorAt(1.0, c_base.darker(120))
        painter.setBrush(QBrush(grad))
        # Una pequeña onda se amortigua al señalar o seleccionar el tanque.
        # Es decorativa: ni el nivel medio dibujado ni la cota hidráulica cambian.
        amplitud = 3.5 * math.sin(math.pi * self._gesto) * (1.0 - 0.5 * self._gesto)
        superficie = QPainterPath()
        for i in range(33):
            u = i / 32.0
            punto = QPointF(rect_agua.left() + u * rect_agua.width(),
                            nivel_y + amplitud * math.sin(2 * math.pi * u + 6 * math.pi * self._gesto))
            if i == 0:
                superficie.moveTo(punto)
            else:
                superficie.lineTo(punto)
        agua = QPainterPath(superficie)
        agua.lineTo(rect_agua.bottomRight())
        agua.lineTo(rect_agua.bottomLeft())
        agua.closeSubpath()
        painter.drawPath(agua)

        # Línea de superficie libre del agua
        painter.setPen(QPen(c_base.darker(150), 1.8, Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(superficie)

        # 4. Paredes estructurales del tanque
        color_borde = QColor("#0284c7") if self.isSelected() else QColor("#334155")
        grosor_borde = 2.8 if self.isSelected() else 2.2
        pen_pared = QPen(color_borde, grosor_borde, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
        painter.setPen(pen_pared)
        painter.setBrush(Qt.NoBrush)

        if self.abierto_atmosfera:
            poly = QPolygonF([
                QPointF(r.left(), r.top() + 4),
                QPointF(r.left(), r.bottom()),
                QPointF(r.right(), r.bottom()),
                QPointF(r.right(), r.top() + 4),
            ])
            painter.drawPolyline(poly)

            # Soporte en T y símbolo azul "ATM" arriba del tanque
            painter.setPen(QPen(QColor("#64748b"), 1.6, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(cx, r.top() + 3), QPointF(cx, r.top() - 9))
            painter.drawLine(QPointF(cx - 7, r.top() - 9), QPointF(cx + 7, r.top() - 9))
            painter.drawLine(QPointF(cx - 7, r.top() - 9), QPointF(cx - 7, r.top() - 5))
            painter.drawLine(QPointF(cx + 7, r.top() - 9), QPointF(cx + 7, r.top() - 5))

            font_atm = QFont("Consolas", 7)
            font_atm.setBold(True)
            painter.setFont(font_atm)
            painter.setPen(QColor("#0284c7"))
            painter.drawText(
                QRectF(cx - 22, r.top() - 24, 44, 13),
                Qt.AlignCenter,
                "ATM",
            )
        else:
            painter.drawRoundedRect(r, 4, 4)

            # Pequeño manómetro y texto rojo "P = ... kPa" arriba del tanque presurizado
            painter.setPen(QPen(QColor("#334155"), 1.6))
            painter.drawLine(QPointF(cx, r.top()), QPointF(cx, r.top() - 6))
            centro_man = QPointF(cx, r.top() - 13)
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(centro_man, 6.5, 6.5)
            painter.setPen(QPen(QColor("#dc2626"), 1.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(centro_man, QPointF(cx + 3.5, r.top() - 16.5))

            p_val = self.presion_P
            if abs(p_val) >= 100.0:
                txt_p_sup = f"P={formatear_numero(p_val / 1000.0)} kPa"
            else:
                txt_p_sup = f"P={formatear_numero(p_val)} Pa"
            font_man = QFont("Consolas", 7)
            font_man.setBold(True)
            painter.setFont(font_man)
            painter.setPen(QColor("#dc2626"))
            painter.drawText(
                QRectF(cx - 38, r.top() - 32, 76, 12),
                Qt.AlignCenter,
                txt_p_sup,
            )

    def restaurar_borde(self):
        self.setPen(QPen(QColor("#334155"), 2, Qt.SolidLine))

    @property
    def nombre(self):
        return f"Tanque {self.id_tanque}" if self.id_tanque is not None else "Tanque"

    def actualizar_etiqueta(self):
        if self.abierto_atmosfera:
            texto_presion = "P = 0.0 kPa (manom)"
        else:
            if abs(self.presion_P) >= 100.0:
                texto_presion = f"P = {formatear_numero(self.presion_P / 1000.0)} kPa"
            else:
                texto_presion = f"P = {formatear_numero(self.presion_P)} Pa"
        self.etiqueta.establecer_texto(
            f"{self.nombre}\nz = {formatear_numero(self.elevacion_z)} m\n{texto_presion}"
        )
        rect_etiqueta = self.etiqueta.boundingRect()
        self.etiqueta.setPos(
            (self.rect().width() - rect_etiqueta.width()) / 2,
            self.rect().bottom() + 6,
        )

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            _acompanar_anclados_en_bloque(self, value)
        elif change == QGraphicsItem.ItemPositionHasChanged:
            for tuberia in self.tuberias:
                tuberia.actualizar_posicion()
        return super().itemChange(change, value)


class TuberiaGrafica(RealceGraficoMixin, QGraphicsPathItem):
    DESPLAZAMIENTOS = (0, 60, -60)
    DISTANCIA_PUENTE = 85
    COLORES = (QColor("#334155"), QColor("#d97706"), QColor("#16a34a"))

    def __init__(self, nodo_origen, nodo_destino, id_tuberia=None, parent=None):
        super().__init__(parent)
        self.nodo_origen = nodo_origen
        self.nodo_destino = nodo_destino
        self.id_tuberia = id_tuberia
        self.nombre = f"Tubería {id_tuberia}" if id_tuberia is not None else "Tubería"
        self._color_personalizado = None
        self.accesorios_conectados = []
        self._puntos_trazado = []
        self._botones_esquina = []
        self.etiqueta = EtiquetaFlotante(self, tamano_fuente=8)
        self.etiqueta._fondo = QBrush(QColor(255, 255, 255, 248))
        self.etiqueta._borde = QPen(QColor("#b9d5f5"), 1.0)
        self.etiqueta.setDefaultTextColor(QColor("#0c4e77"))
        self.etiqueta_q = EtiquetaFlotante(self, tamano_fuente=8)
        self.etiqueta_q._fondo = QBrush(QColor("#eff6ff"))
        self.etiqueta_q._borde = QPen(QColor("#bfdbfe"), 1.0)
        self.etiqueta_q.setDefaultTextColor(QColor("#0369a1"))
        self.etiqueta_q.hide()
        self.hf_calculado = None
        self.sentido_flujo_calculado = None
        self.longitud = 0.0
        self.diametro = 0.0
        self.rugosidad = 0.0
        self.caudal_Q = 0.0
        self.u_Q = "m³/s"
        self.u_L = "m"
        self.u_D = "m"
        self.u_eps = "m"
        self.modo_trazado = "recto"
        self.vertices_usuario = []
        self.direccion_inicial = "H"
        self.conexion_origen = normalizar_conexion_tanque()
        self.conexion_destino = normalizar_conexion_tanque()

        indice_color = min(len(self._hermanas()) - 1, len(self.COLORES) - 1)
        pen = QPen(self.COLORES[indice_color], 4)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.NoBrush))
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

        nodo_origen.tuberias.append(self)
        nodo_destino.tuberias.append(self)
        nodo_origen.update()
        nodo_destino.update()

        self.actualizar_posicion()
        self.actualizar_etiqueta()

    def boundingRect(self):
        base = super().boundingRect()
        if self._tiene_conexiones_tanque():
            return base.adjusted(-42, -42, 42, 42)
        if getattr(self, "sentido_flujo_calculado", None) in (1, -1):
            return base.adjusted(-16, -16, 16, 16)
        return base

    def establecer_sentido_flujo(self, sentido):
        """Define la dirección visual resuelta respecto a origen->destino (1, -1, 0 o None)."""
        valor = int(sentido) if sentido in (1, -1, 0) else None
        if getattr(self, "sentido_flujo_calculado", None) == valor:
            return
        self.prepareGeometryChange()
        self.sentido_flujo_calculado = valor
        self.update()

    @staticmethod
    def _distancia_a_rect(punto, rect):
        dx = max(rect.left() - punto.x(), 0.0, punto.x() - rect.right())
        dy = max(rect.top() - punto.y(), 0.0, punto.y() - rect.bottom())
        if dx > 0.0 or dy > 0.0:
            return math.hypot(dx, dy)
        return -min(
            punto.x() - rect.left(),
            rect.right() - punto.x(),
            punto.y() - rect.top(),
            rect.bottom() - punto.y(),
        )

    def _ubicaciones_flechas_flujo(self):
        """Calcula [(punto, angulo_grados)] sobre tramos despejados de etiquetas y nodos."""
        sentido = getattr(self, "sentido_flujo_calculado", None)
        if sentido not in (1, -1) or self.path().isEmpty():
            return []

        pts = getattr(self, "_puntos_trazado", None) or []
        if len(pts) < 2:
            return []

        segmentos = []
        long_total = 0.0
        for p_a, p_b in zip(pts, pts[1:]):
            dx = p_b.x() - p_a.x()
            dy = p_b.y() - p_a.y()
            l_seg = math.hypot(dx, dy)
            if l_seg > 1e-3:
                ang = math.degrees(math.atan2(dy, dx))
                segmentos.append((p_a, p_b, l_seg, long_total, ang))
                long_total += l_seg

        if long_total < 16.0 or not segmentos:
            return []

        rects_obstaculo = []
        circs_obstaculo = []

        for etq in (getattr(self, "etiqueta", None), getattr(self, "etiqueta_q", None)):
            if etq is not None and etq.isVisible() and etq.toPlainText():
                r_etq = etq.boundingRect()
                rects_obstaculo.append(
                    QRectF(
                        etq.pos().x(), etq.pos().y(), r_etq.width(), r_etq.height()
                    ).adjusted(-6.0, -5.0, 6.0, 5.0)
                )

        extremos = (
            (self.nodo_origen, getattr(self, "conexion_origen", None), pts[0], pts[1]),
            (self.nodo_destino, getattr(self, "conexion_destino", None), pts[-1], pts[-2]),
        )
        for nodo, cfg, p_node, p_adj in extremos:
            if isinstance(nodo, TanqueGrafico) and hasattr(nodo, "rect"):
                r_tq = QRectF(
                    nodo.pos().x(),
                    nodo.pos().y(),
                    nodo.rect().width(),
                    nodo.rect().height(),
                )
                rects_obstaculo.append(r_tq.adjusted(-14.0, -14.0, 14.0, 14.0))
                if isinstance(cfg, dict) and cfg.get("modo") in ("salida", "entrada"):
                    seg_t = QLineF(p_node, p_adj)
                    if seg_t.length() > 1e-3:
                        ux = seg_t.dx() / seg_t.length()
                        uy = seg_t.dy() / seg_t.length()
                        p_borde = self._punto_borde_tanque(nodo, p_node, p_adj)
                        circs_obstaculo.append(
                            (QPointF(p_borde.x() + ux * 24.0, p_borde.y() + uy * 24.0), 34.0)
                        )
            elif isinstance(nodo, BombaGrafica):
                circs_obstaculo.append((self._centro(nodo), 34.0))
            elif isinstance(nodo, NodoUnionGrafico):
                circs_obstaculo.append((self._centro(nodo), 15.0))
            elif isinstance(nodo, AccesorioGrafico):
                circs_obstaculo.append((self._centro(nodo), 22.0))

        for acc in getattr(self, "accesorios_conectados", []):
            c_acc = self._centro(acc)
            radio_acc = 18.0 if getattr(acc, "esquina_indice", None) is not None else 22.0
            circs_obstaculo.append((c_acc, radio_acc))

        for esquina in pts[1:-1]:
            circs_obstaculo.append((esquina, 14.0))

        candidatos = []
        for p_a, p_b, l_seg, s_ini, ang in segmentos:
            if l_seg < 12.0:
                continue
            dx = p_b.x() - p_a.x()
            dy = p_b.y() - p_a.y()
            n_pasos = max(3, int(l_seg // 12))
            for k in range(n_pasos):
                u = (k + 0.5) / n_pasos
                pt = QPointF(p_a.x() + u * dx, p_a.y() + u * dy)
                s_rel = (s_ini + u * l_seg) / long_total

                distancias = [self._distancia_a_rect(pt, r) for r in rects_obstaculo]
                distancias.extend(
                    math.hypot(pt.x() - c.x(), pt.y() - c.y()) - rad
                    for c, rad in circs_obstaculo
                )
                margen = min(distancias) if distancias else 100.0
                candidatos.append((pt, ang, s_rel, margen, margen >= 0.0))

        if not candidatos:
            centro = self.path().pointAtPercent(0.5)
            ang = -self.path().angleAtPercent(0.5)
            candidatos.append((centro, ang, 0.5, 0.0, False))

        offset_ang = 0.0 if sentido == 1 else 180.0
        izq = [c for c in candidatos if c[2] < 0.5 and c[4]]
        der = [c for c in candidatos if c[2] >= 0.5 and c[4]]
        if izq and der and long_total >= 260.0:
            mejor_izq = max(izq, key=lambda c: (min(c[3], 35.0) - 8.0 * abs(c[2] - 0.25)))
            mejor_der = max(der, key=lambda c: (min(c[3], 35.0) - 8.0 * abs(c[2] - 0.75)))
            sep = math.hypot(
                mejor_der[0].x() - mejor_izq[0].x(),
                mejor_der[0].y() - mejor_izq[0].y(),
            )
            if sep >= 90.0:
                return [
                    (mejor_izq[0], mejor_izq[1] + offset_ang),
                    (mejor_der[0], mejor_der[1] + offset_ang),
                ]

        mejor = max(
            candidatos,
            key=lambda c: (c[4], min(c[3], 35.0) - 6.0 * abs(c[2] - 0.5)),
        )
        return [(mejor[0], mejor[1] + offset_ang)]

    def _dibujar_flechas_flujo(self, painter):
        ubicaciones = self._ubicaciones_flechas_flujo()
        if not ubicaciones:
            return
        grosor = self.pen().widthF()
        largo = max(13.0, min(18.0, 11.0 + grosor * 0.45))
        ancho = max(6.5, min(9.5, 5.5 + grosor * 0.25))
        flecha = QPolygonF([
            QPointF(largo * 0.55, 0.0),
            QPointF(-largo * 0.45, -ancho),
            QPointF(-largo * 0.18, 0.0),
            QPointF(-largo * 0.45, ancho),
        ])
        pen_halo = QPen(QColor("#ffffff"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        brush_flecha = QBrush(QColor("#0284c7"))

        for pt, ang in ubicaciones:
            painter.save()
            painter.translate(pt)
            painter.rotate(ang)
            painter.setPen(pen_halo)
            painter.setBrush(brush_flecha)
            painter.drawPolygon(flecha)
            painter.restore()

    def _tiene_conexiones_tanque(self):
        return any(
            isinstance(nodo, TanqueGrafico)
            and isinstance(cfg, dict)
            and cfg.get("modo") in ("salida", "entrada")
            for nodo, cfg in (
                (self.nodo_origen, getattr(self, "conexion_origen", None)),
                (self.nodo_destino, getattr(self, "conexion_destino", None)),
            )
        )

    @staticmethod
    def _punto_borde_tanque(tanque, p_dentro, p_fuera):
        dx = p_fuera.x() - p_dentro.x()
        dy = p_fuera.y() - p_dentro.y()
        rect_t = QRectF(
            tanque.pos().x(),
            tanque.pos().y(),
            tanque.rect().width(),
            tanque.rect().height(),
        )
        ts = []
        if abs(dx) > 1e-9:
            for bx in (rect_t.left(), rect_t.right()):
                t = (bx - p_dentro.x()) / dx
                if t > 0:
                    yh = p_dentro.y() + t * dy
                    if rect_t.top() - 1e-6 <= yh <= rect_t.bottom() + 1e-6:
                        ts.append(t)
        if abs(dy) > 1e-9:
            for by in (rect_t.top(), rect_t.bottom()):
                t = (by - p_dentro.y()) / dy
                if t > 0:
                    xh = p_dentro.x() + t * dx
                    if rect_t.left() - 1e-6 <= xh <= rect_t.right() + 1e-6:
                        ts.append(t)
        t_hit = min(ts) if ts else 0.0
        return QPointF(p_dentro.x() + dx * t_hit, p_dentro.y() + dy * t_hit)

    def _dibujar_conexiones_tanque(self, painter):
        pts = getattr(self, "_puntos_trazado", None) or []
        if len(pts) < 2:
            return
        extremos = (
            ("origen", self.nodo_origen, getattr(self, "conexion_origen", None), pts[0], pts[1]),
            ("destino", self.nodo_destino, getattr(self, "conexion_destino", None), pts[-1], pts[-2]),
        )
        idx_p = self._indice_paralela()
        hermanas = self._hermanas()
        for _ext, nodo, cfg, p_tank, p_next in extremos:
            if not isinstance(nodo, TanqueGrafico) or not isinstance(cfg, dict):
                continue
            modo = cfg.get("modo", "ninguno")
            if modo not in ("salida", "entrada"):
                continue
            seg = QLineF(p_tank, p_next)
            largo = seg.length()
            if largo < 1e-3:
                continue
            ux, uy = seg.dx() / largo, seg.dy() / largo
            nx, ny = -uy, ux
            p_borde = self._punto_borde_tanque(nodo, p_tank, p_next)
            # Desplazar justo fuera de la pared del tanque (TanqueGrafico tiene zValue=0)
            p_muro = QPointF(p_borde.x() + ux * 2.5, p_borde.y() + uy * 2.5)

            color = QColor("#d97706") if modo == "salida" else QColor("#0284c7")
            painter.save()
            painter.setPen(QPen(color, 2.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.setBrush(QBrush(color))

            # Brida / cuello en la interfaz tanque-tubería
            wing = 6.5
            p_a = QPointF(p_muro.x() + nx * wing, p_muro.y() + ny * wing)
            p_b = QPointF(p_muro.x() - nx * wing, p_muro.y() - ny * wing)
            painter.drawLine(p_a, p_b)

            # Flecha indicadora de sentido (Salida: hacia la tubería; Entrada: hacia el tanque)
            signo = 1.0 if modo == "salida" else -1.0
            p_punta = QPointF(p_muro.x() + ux * (11.5 if modo == "salida" else 6.0),
                              p_muro.y() + uy * (11.5 if modo == "salida" else 6.0))
            base_c = QPointF(p_punta.x() - signo * ux * 5.5, p_punta.y() - signo * uy * 5.5)
            tri = QPolygonF([
                p_punta,
                QPointF(base_c.x() + nx * 4.0, base_c.y() + ny * 4.0),
                QPointF(base_c.x() - nx * 4.0, base_c.y() - ny * 4.0),
            ])
            painter.drawPolygon(tri)

            # Pastilla compacta con modo y K fuera de la pared del tanque
            dist_desde_borde = QLineF(p_borde, p_next).length()
            if dist_desde_borde >= 24.0:
                k_val = float(cfg.get("K", 0.0) or 0.0)
                pref = "Sal." if modo == "salida" else "Ent."
                txt_k = f"{pref} K={formatear_numero(k_val)}"
                font_k = QFont("Consolas", 7)
                font_k.setBold(True)
                painter.setFont(font_k)
                fm = QtGui.QFontMetrics(font_k)
                w_p = float(fm.horizontalAdvance(txt_k)) + 10.0
                h_p = 15.0
                lado = 1.0 if (len(hermanas) > 1 and idx_p % 2 == 1) else -1.0
                sep = 16.0 + (idx_p // 2) * 16.0
                centro_pill = QPointF(
                    p_muro.x() + ux * (20.0 + w_p * 0.35) + nx * (lado * sep),
                    p_muro.y() + uy * (20.0 + w_p * 0.35) + ny * (lado * sep),
                )
                rect_pill = QRectF(
                    centro_pill.x() - w_p / 2.0,
                    centro_pill.y() - h_p / 2.0,
                    w_p,
                    h_p,
                )
                bg_pill = QColor("#fffbeb") if modo == "salida" else QColor("#eff6ff")
                borde_pill = QColor("#f59e0b") if modo == "salida" else QColor("#60a5fa")
                painter.setPen(QPen(borde_pill, 1.0))
                painter.setBrush(QBrush(bg_pill))
                painter.drawRoundedRect(rect_pill, 4, 4)
                painter.setPen(QColor("#92400e") if modo == "salida" else QColor("#075985"))
                painter.drawText(rect_pill, Qt.AlignCenter, txt_k)
            painter.restore()

    def paint(self, painter, option, widget=None):
        if self.path().isEmpty():
            return
        painter.setRenderHint(QPainter.Antialiasing)
        grosor = self.pen().widthF()
        color_base = self.color_interactivo(self.pen().color())

        # Halo de selección si está activa
        if self.isSelected():
            pen_sel = QPen(QColor(2, 132, 199, 90), grosor + 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen_sel)
            painter.drawPath(self.path())

        # Trazo principal (pared de la tubería)
        pen_ext = QPen(color_base, grosor, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen_ext)
        painter.drawPath(self.path())

        # Brillo cilíndrico central (efecto tubería 3D sutil)
        pen_int = QPen(color_base.lighter(145), max(1.2, grosor * 0.35), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen_int)
        painter.drawPath(self.path())

        # Indicadores de Entrada / Salida en paredes de tanques
        self._dibujar_conexiones_tanque(painter)

        # Flechas de sentido de flujo calculado (solo tras resolver el ejercicio)
        self._dibujar_flechas_flujo(painter)

    def _centro(self, nodo):
        if hasattr(nodo, "centro_escena"):
            return nodo.centro_escena()
        return nodo.sceneBoundingRect().center()

    def _hermanas(self):
        nodos = {self.nodo_origen, self.nodo_destino}
        hermanas = [t for t in self.nodo_origen.tuberias if {t.nodo_origen, t.nodo_destino} == nodos]
        if all(t is not self for t in hermanas):
            hermanas.append(self)
        hermanas.sort(key=lambda t: (t.id_tuberia is None, t.id_tuberia or 0))
        return hermanas

    def _indice_paralela(self, hermanas=None):
        if hermanas is None:
            hermanas = self._hermanas()
        return next(i for i, t in enumerate(hermanas) if t is self)

    def _desplazamiento(self):
        if isinstance(self.nodo_origen, AccesorioGrafico) or isinstance(
            self.nodo_destino, AccesorioGrafico
        ):
            return 0
        hermanas = self._hermanas()
        indice = self._indice_paralela(hermanas)
        if indice < len(self.DESPLAZAMIENTOS):
            desplazamiento = self.DESPLAZAMIENTOS[indice]
        else:
            desplazamiento = 60 * ((indice + 1) // 2) * (1 if indice % 2 else -1)
        if desplazamiento != 0 and hermanas[0].nodo_origen is not self.nodo_origen:
            desplazamiento = -desplazamiento
        return desplazamiento

    @property
    def color_personalizado(self):
        return self._color_personalizado

    @color_personalizado.setter
    def color_personalizado(self, color):
        self._color_personalizado = QColor(color) if color is not None else None
        self._aplicar_color()
        self.update()

    def _aplicar_color(self):
        if self._color_personalizado is not None:
            color = self._color_personalizado
        else:
            indice = min(self._indice_paralela(), len(self.COLORES) - 1)
            color = self.COLORES[indice]
        if self.pen().color() != color:
            pen = self.pen()
            pen.setColor(color)
            self.setPen(pen)

    def actualizar_posicion(self):
        origen = self._centro(self.nodo_origen)
        destino = self._centro(self.nodo_destino)
        desplazamiento = self._desplazamiento()

        if desplazamiento == 0:
            if getattr(self, "modo_trazado", "recto") == "ortogonal":
                from ui.enrutado_ortogonal import (
                    proyectar_punto_a_polilinea,
                    punto_en_longitud_arco,
                    ruta_multivertice,
                )

                pts_base = [origen] + list(getattr(self, "vertices_usuario", [])) + [destino]
                dir_init = getattr(self, "direccion_inicial", "H")
                puntos = ruta_multivertice(pts_base, direccion_inicial=dir_init)

                path = QPainterPath(puntos[0])
                for pt in puntos[1:]:
                    path.lineTo(pt)

                self.setPath(path)
                self._puntos_trazado = puntos

                # Anclaje continuo de accesorios a lo largo del camino ortogonal (sin mover vértices)
                vertices_intermedios = puntos[1:-1]
                esc = self.scene()
                for accesorio in getattr(self, "accesorios_conectados", []):
                    c_act = (
                        accesorio.centro_escena()
                        if hasattr(accesorio, "centro_escena")
                        else accesorio.sceneBoundingRect().center()
                    )
                    esta_arrastrando = (esc is not None and esc.mouseGrabberItem() is accesorio
                                         and not getattr(accesorio, '_finalizando_arrastre', False))
                    t_val = getattr(accesorio, "t_anclaje", None)
                    if t_val is None or esta_arrastrando:
                        _, t_val, _ = proyectar_punto_a_polilinea(c_act, puntos)
                        if not esta_arrastrando:
                            accesorio.t_anclaje = t_val

                    pt_arco, ang_tangente = punto_en_longitud_arco(t_val, puntos)

                    # Si es Codo, verificar si hay un vértice ortogonal cercano (umbral 35 px)
                    ajustado_a_vertice = False
                    if getattr(accesorio, "forma_visual", "") == "Codo" and vertices_intermedios:
                        c_ref = c_act
                        v_cercano = None
                        d_min = float("inf")
                        idx_v = -1
                        for idx_cand, v in enumerate(vertices_intermedios):
                            d_cand = math.hypot(c_ref.x() - v.x(), c_ref.y() - v.y())
                            if d_cand < d_min:
                                d_min = d_cand
                                v_cercano = v
                                idx_v = idx_cand + 1

                        esquina = getattr(accesorio, 'esquina_indice', None)
                        if esquina is not None:
                            idx_v = min(max(1, esquina), len(puntos) - 2)
                            accesorio.esquina_indice = idx_v
                            v_cercano, d_min = puntos[idx_v], 0.0
                        if v_cercano is not None and d_min <= 35.0:
                            ajustado_a_vertice = True
                            pt_final = v_cercano
                            p_prev = puntos[idx_v - 1]
                            p_next = puntos[idx_v + 1]
                            ang_in = math.degrees(
                                math.atan2(v_cercano.y() - p_prev.y(), v_cercano.x() - p_prev.x())
                            )
                            ang_out = math.degrees(
                                math.atan2(p_next.y() - v_cercano.y(), p_next.x() - v_cercano.x())
                            )
                            accesorio.angulo_in = ang_in
                            accesorio.angulo_out = ang_out
                            accesorio.setRotation(-ang_in)

                    if not ajustado_a_vertice:
                        pt_final = pt_arco
                        accesorio.angulo_in = ang_tangente
                        accesorio.angulo_out = ang_tangente
                        accesorio.setRotation(-ang_tangente)

                    if not esta_arrastrando:
                        w_acc = getattr(accesorio, "ANCHO", 30)
                        h_acc = getattr(accesorio, "ALTO", 30)
                        accesorio._actualizando_anclaje = True
                        try:
                            accesorio.setPos(pt_final.x() - w_acc / 2.0, pt_final.y() - h_acc / 2.0)
                        finally:
                            accesorio._actualizando_anclaje = False
                    accesorio.update()
            else:
                ordenados = sorted(
                    self.accesorios_conectados,
                    key=lambda a: QLineF(origen, a.centro_escena() if hasattr(a, "centro_escena") else a.sceneBoundingRect().center()).length(),
                )

                path = QPainterPath(origen)
                puntos = [origen]
                for accesorio in ordenados:
                    centro = accesorio.centro_escena() if hasattr(accesorio, "centro_escena") else accesorio.sceneBoundingRect().center()
                    path.lineTo(centro)
                    puntos.append(centro)
                path.lineTo(destino)
                puntos.append(destino)

                self.setPath(path)
                self._puntos_trazado = puntos

                anterior = origen
                for accesorio, centro, siguiente in zip(ordenados, puntos[1:-1], puntos[2:]):
                    ang_in = QLineF(anterior, centro).angle()
                    ang_out = QLineF(centro, siguiente).angle()
                    accesorio.angulo_in = ang_in
                    accesorio.angulo_out = ang_out
                    accesorio.setRotation(-ang_in)
                    accesorio.update()
                    anterior = centro
        else:
            L = QLineF(origen, destino)
            if L.length() == 0:
                path = QPainterPath(origen)
                path.lineTo(destino)
                self.setPath(path)
                self._puntos_trazado = [origen, destino]
            else:
                ux, uy = L.dx() / L.length(), L.dy() / L.length()
                normal = L.normalVector()
                normal.setLength(desplazamiento)
                nx, ny = normal.p2().x() - normal.p1().x(), normal.p2().y() - normal.p1().y()

                arranque = min(self.DISTANCIA_PUENTE, L.length() / 2)
                p1 = origen + QPointF(ux * arranque, uy * arranque)
                p4 = destino - QPointF(ux * arranque, uy * arranque)
                p2 = p1 + QPointF(nx, ny)
                p3 = p4 + QPointF(nx, ny)

                path = QPainterPath(origen)
                path.lineTo(p1)
                path.lineTo(p2)
                path.lineTo(p3)
                path.lineTo(p4)
                path.lineTo(destino)
                self.setPath(path)
                self._puntos_trazado = [origen, p1, p2, p3, p4, destino]

        self._sincronizar_botones_esquina()
        self._aplicar_color()
        self._centrar_etiqueta()

        for nodo in (self.nodo_origen, self.nodo_destino):
            if isinstance(nodo, AccesorioGrafico) and nodo.tuberia_padre is None:
                nodo.orientar_desde_nodos()

    def _sincronizar_botones_esquina(self):
        puntos = (
            self._puntos_trazado[1:-1]
            if (self.modo_trazado == 'ortogonal' and self._desplazamiento() == 0)
            else []
        )
        while len(self._botones_esquina) > len(puntos):
            boton = self._botones_esquina.pop()
            boton.setParentItem(None)
            if boton.scene() is not None:
                boton.scene().removeItem(boton)
        while len(self._botones_esquina) < len(puntos):
            self._botones_esquina.append(BotonPerdidaEsquina(self, len(self._botones_esquina) + 1))
        for boton, punto in zip(self._botones_esquina, puntos):
            boton.setPos(punto)
            boton.configurar_geometria(self._puntos_trazado[boton.indice - 1], punto,
                                       self._puntos_trazado[boton.indice + 1])
            perdida = next((a for a in self.accesorios_conectados
                            if getattr(a, 'esquina_indice', None) == boton.indice), None)
            configurada = perdida is not None and perdida.valor > 0
            boton.configurada = configurada
            boton.update()
            boton.setToolTip(
                f'Pérdida en esquina · {perdida.tipo_perdida} = {perdida.valor:g}' if perdida is not None
                else 'Agregar pérdida en esquina · K o Le/D')

    def _centrar_etiqueta(self):
        centro = self.path().pointAtPercent(0.5) if not self.path().isEmpty() else QPointF()
        rect = self.etiqueta.boundingRect()
        offset_y = -rect.height() - 5 if self.etiqueta_q.isVisible() else -rect.height() / 2
        self.etiqueta.setPos(
            centro.x() - rect.width() / 2,
            centro.y() + offset_y,
        )
        if self.etiqueta_q.isVisible():
            rect_q = self.etiqueta_q.boundingRect()
            self.etiqueta_q.setPos(
                centro.x() - rect_q.width() / 2,
                centro.y() + 4,
            )

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(self.pen().widthF() + 6)
        stroker.setJoinStyle(Qt.RoundJoin)
        return stroker.createStroke(self.path())

    def distancia_a(self, punto):
        puntos = self._puntos_trazado
        if len(puntos) < 2:
            return float("inf")
        return min(
            self._distancia_a_segmento(punto, p1, p2) for p1, p2 in zip(puntos, puntos[1:])
        )

    @staticmethod
    def _distancia_a_segmento(punto, p1, p2):
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        largo2 = dx * dx + dy * dy
        if largo2 == 0:
            return math.hypot(punto.x() - p1.x(), punto.y() - p1.y())
        t = ((punto.x() - p1.x()) * dx + (punto.y() - p1.y()) * dy) / largo2
        t = max(0.0, min(1.0, t))
        return math.hypot(punto.x() - (p1.x() + t * dx), punto.y() - (p1.y() + t * dy))

    def actualizar_etiqueta(self):
        encabezado = self.nombre.upper()
        partes_dim = []
        if self.longitud > 0:
            partes_dim.append(f"L = {formatear_numero(self.longitud)} {self.u_L}")
        if self.diametro > 0:
            partes_dim.append(f"D = {formatear_numero(self.diametro)} {self.u_D}")
        texto_etq = encabezado if not partes_dim else f"{encabezado}\n{' | '.join(partes_dim)}"
        self.etiqueta.establecer_texto(texto_etq)

        if self.caudal_Q > 0:
            q_si = self.caudal_Q * FACTORES_SI.get(self.u_Q, 1.0)
            q_ls = q_si * 1000.0
            if self.u_Q == "L/s":
                txt_q = f"Q = {self.caudal_Q:.2f} L/s ({q_si:.4f} m³/s)"
            else:
                txt_q = f"Q = {self.caudal_Q:.4f} {self.u_Q} ({q_ls:.2f} L/s)"
            self.etiqueta_q.establecer_texto(txt_q)
        else:
            self.etiqueta_q.establecer_texto("")

        diametro_m = self.diametro * FACTORES_SI.get(self.u_D, 1.0)
        grosor = max(4.0, min(16.0, 4.0 + (diametro_m * 15.0)))
        pen = self.pen()
        pen.setWidthF(grosor)
        self.setPen(pen)
        self._centrar_etiqueta()

    def actualizar_texto_hf(self, hf):
        self.hf_calculado = hf
        self.actualizar_etiqueta()

    def desconectar(self):
        hermanas = [t for t in self._hermanas() if t is not self]

        for nodo in (self.nodo_origen, self.nodo_destino):
            if self in nodo.tuberias:
                nodo.tuberias.remove(self)
            nodo.update()

        for hermana in hermanas:
            hermana.actualizar_posicion()

        for accesorio in list(self.accesorios_conectados):
            accesorio.tuberia_padre = None
            accesorio.setFlag(QGraphicsItem.ItemIsMovable, True)
            accesorio.orientar_desde_nodos()
        self.accesorios_conectados.clear()

        for nodo in (self.nodo_origen, self.nodo_destino):
            if isinstance(nodo, AccesorioGrafico) and nodo.tuberia_padre is None:
                if not nodo.tuberias:
                    nodo.setFlag(QGraphicsItem.ItemIsMovable, True)
                nodo.orientar_desde_nodos()

    def _diametro_si(self):
        return self.diametro * FACTORES_SI.get(self.u_D, 1.0)

    def _accesorios_asignados(self):
        """Propietario único: padre anclado o menor D; empate por ID estable.

        La orientación origen/destino no interviene. En un divisor la velocidad
        de referencia sigue siendo la de menor diámetro, como antes.
        """
        candidatos = list(self.accesorios_conectados) + [n for n in
            (self.nodo_origen, self.nodo_destino) if isinstance(n, AccesorioGrafico)]
        asignados, vistos = [], set()
        for acc in candidatos:
            if id(acc) in vistos:
                continue
            vistos.add(id(acc))
            padre = getattr(acc, 'tuberia_padre', None)
            if padre is not None:
                propietario = padre
            else:
                tubos = list(dict.fromkeys(getattr(acc, 'tuberias', [])))
                if not tubos:
                    # Un accesorio anclado antiguo puede no guardar tuberia_padre.
                    tubos = [self] if acc in self.accesorios_conectados else []
                if not tubos:
                    continue
                menor = min(t._diametro_si() for t in tubos)
                tubos = [t for t in tubos if math.isclose(t._diametro_si(), menor,
                                                         rel_tol=1e-9, abs_tol=1e-12)]
                propietario = min(tubos, key=lambda t: (
                    getattr(t, 'id_tuberia', None) is None,
                    getattr(t, 'id_tuberia', None) or 0, getattr(t, 'nombre', ''), id(t)))
            if propietario is self:
                asignados.append(acc)
        return asignados

    @staticmethod
    def _k_conexiones_tanque(tuberia):
        total = 0.0
        for attr_cfg, attr_nodo in (
            ("conexion_origen", "nodo_origen"),
            ("conexion_destino", "nodo_destino"),
        ):
            nodo = getattr(tuberia, attr_nodo, None)
            cfg = getattr(tuberia, attr_cfg, None)
            if (
                isinstance(nodo, TanqueGrafico)
                and isinstance(cfg, dict)
                and cfg.get("modo") in ("salida", "entrada")
            ):
                norm = normalizar_conexion_tanque(cfg)
                total += float(norm["K"])
        return total

    def establecer_conexion_tanque(self, extremo, modo, tipo_borde="", K=None):
        """Configura la condición Entrada/Salida en un extremo conectado a Tanque."""
        attr = "conexion_origen" if extremo == "origen" else "conexion_destino"
        self.prepareGeometryChange()
        cfg = normalizar_conexion_tanque({"modo": modo, "tipo_borde": tipo_borde, "K": K})
        setattr(self, attr, cfg)
        self.actualizar_etiqueta()
        self.update()
        return cfg

    def _datos_perdidas_tanques(self, origen, destino, largo):
        """Retorna tuplas (etiqueta, x, K, 0.0) ordenadas respecto a origen->destino."""
        datos = []
        pares = (
            ("origen", self.nodo_origen, getattr(self, "conexion_origen", None)),
            ("destino", self.nodo_destino, getattr(self, "conexion_destino", None)),
        )
        for extremo, nodo, cfg in pares:
            if not isinstance(nodo, TanqueGrafico) or not isinstance(cfg, dict):
                continue
            norm = normalizar_conexion_tanque(cfg)
            modo = norm["modo"]
            k_val = float(norm["K"])
            if modo not in ("salida", "entrada") or k_val <= 0.0:
                continue
            if nodo is origen:
                x_pos = 0.0
            elif nodo is destino:
                x_pos = float(largo)
            else:
                x_pos = 0.0 if extremo == "origen" else float(largo)
            nom_tq = getattr(nodo, "nombre", "Tanque")
            if modo == "entrada":
                etiqueta = f"Pérdida de entrada a {nom_tq}"
            else:
                etiqueta = f"Pérdida de salida de {nom_tq}"
            datos.append((etiqueta, x_pos, k_val, 0.0))
        return datos

    def _sumar_accesorios(self, tipo):
        total = sum(a.valor for a in self._accesorios_asignados() if a.tipo_perdida == tipo)
        if tipo == "K":
            total += TuberiaGrafica._k_conexiones_tanque(self)
        return total

    @property
    def sumatoria_K(self):
        return self._sumar_accesorios("K")

    @property
    def sumatoria_K_accesorios(self):
        """Suma de coeficientes K únicamente de accesorios propios del tramo (sin bordes de tanque)."""
        return sum(a.valor for a in self._accesorios_asignados() if a.tipo_perdida == "K")

    @property
    def sumatoria_K_bordes(self):
        """Suma de coeficientes K correspondientes a pérdidas de entrada/salida en tanques."""
        return TuberiaGrafica._k_conexiones_tanque(self)

    @property
    def sumatoria_Le_D(self):
        return self._sumar_accesorios("Le/D")

    def re_autorutear(self):
        """Limpia los vértices fijados por el usuario y recalcula la ruta automáticamente."""
        self.vertices_usuario = []
        self.actualizar_posicion()
        if self.scene() is not None:
            self.scene().elementos_modificados.emit()
        self.update()

    def convertir_a_recto(self, escena=None):
        """Convierte la tubería a trazado recto reubicando accesorios anclados al tramo lineal."""
        escena = escena or self.scene()
        p0 = self._centro(self.nodo_origen)
        p1 = self._centro(self.nodo_destino)

        for acc in list(getattr(self, "accesorios_conectados", [])):
            if getattr(acc, "esquina_indice", None) is not None:
                # Las esquinas sin pérdida configurada no deben quedar como artefactos en modo recto.
                if float(getattr(acc, "valor", 0.0) or 0.0) <= 0.0:
                    acc.setSelected(False)
                    acc.desanclar()
                    if escena is not None and acc.scene() is escena:
                        escena.removeItem(acc)
                    continue
                delattr(acc, "esquina_indice")
                acc.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)

            t_val = getattr(acc, "t_anclaje", None)
            t_val = 0.5 if t_val is None else max(0.0, min(1.0, float(t_val)))
            centro = QPointF(p0.x() + t_val * (p1.x() - p0.x()), p0.y() + t_val * (p1.y() - p0.y()))
            w_acc = getattr(acc, "ANCHO", 30)
            h_acc = getattr(acc, "ALTO", 30)
            acc._actualizando_anclaje = True
            try:
                acc.setPos(centro.x() - w_acc / 2.0, centro.y() - h_acc / 2.0)
                acc.setFlag(QGraphicsItem.ItemIsMovable, getattr(acc, "forma_visual", "") == "Codo")
            finally:
                acc._actualizando_anclaje = False
            acc.t_anclaje = None

        self.modo_trazado = "recto"
        self.vertices_usuario = []
        self.actualizar_posicion()
        self.actualizar_etiqueta()
        self.update()

    def contextMenuEvent(self, event):
        menu = QMenu()
        accion_reautorutear = menu.addAction("Re-autorutear")

        sel = menu.exec_(event.screenPos())
        if sel is accion_reautorutear:
            self.re_autorutear()
        event.accept()

    def to_dict(self):
        """Serializa la configuración de la tubería, incluyendo trazado ortogonal."""
        return {
            "id_tuberia": self.id_tuberia,
            "nombre": self.nombre,
            "modo_trazado": getattr(self, "modo_trazado", "recto"),
            "direccion_inicial": getattr(self, "direccion_inicial", "H"),
            "vertices_usuario": [
                [float(p.x()), float(p.y())] for p in getattr(self, "vertices_usuario", [])
            ],
            "longitud": self.longitud,
            "diametro": self.diametro,
            "rugosidad": self.rugosidad,
            "caudal_Q": self.caudal_Q,
            "_q_por_energia": bool(getattr(self,'_q_por_energia',False)),
            "_d_por_energia": bool(getattr(self,'_d_por_energia',False)),
            "u_Q": self.u_Q,
            "u_L": self.u_L,
            "u_D": self.u_D,
            "u_eps": self.u_eps,
            "conexion_origen": normalizar_conexion_tanque(
                getattr(self, "conexion_origen", None)
            ),
            "conexion_destino": normalizar_conexion_tanque(
                getattr(self, "conexion_destino", None)
            ),
        }

    def from_dict(self, data):
        """Carga la configuración de la tubería; archivos antiguos cargan en 'recto'."""
        self.modo_trazado = data.get("modo_trazado", "recto")
        self.direccion_inicial = data.get(
            "direccion_inicial", getattr(self, "direccion_inicial", "H")
        )
        verts = data.get("vertices_usuario", [])
        self.vertices_usuario = [QPointF(float(v[0]), float(v[1])) for v in verts if len(v) >= 2]
        self.longitud = float(data.get("longitud", self.longitud))
        self.diametro = float(data.get("diametro", self.diametro))
        self.rugosidad = float(data.get("rugosidad", self.rugosidad))
        self.caudal_Q = float(data.get('caudal_Q',self.caudal_Q))
        for unidad in ('u_Q','u_L','u_D','u_eps'):
            if unidad in data:
                setattr(self,unidad,data[unidad])
        self._q_por_energia = data.get('_q_por_energia',False)
        self._d_por_energia = data.get('_d_por_energia',False)
        self.conexion_origen = normalizar_conexion_tanque(data.get("conexion_origen"))
        self.conexion_destino = normalizar_conexion_tanque(data.get("conexion_destino"))
        self.actualizar_posicion()
        self.actualizar_etiqueta()

    @staticmethod
    def _eliminar_de_escena(tuberia, escena):
        if hasattr(escena, "_eliminar_tuberia"):
            escena._eliminar_tuberia(tuberia)
        else:
            tuberia.desconectar()
            if tuberia.scene() is escena:
                escena.removeItem(tuberia)

    @staticmethod
    def _liberar_anclados(tuberias):
        anclados = []
        for t in tuberias:
            for acc in list(getattr(t, "accesorios_conectados", [])):
                acc.tuberia_padre = None
                acc.t_anclaje = None
                if acc not in anclados:
                    anclados.append(acc)
            t.accesorios_conectados.clear()
        return anclados

    def dividir_por_nodo(self, nodo, escena):
        """
        Divide esta tubería en dos tramos conectados mediante `nodo`,
        conservando propiedades hidráulicas, accesorios anclados y trazado ortogonal.
        """
        o = self.nodo_origen
        d = self.nodo_destino
        conn_orig = normalizar_conexion_tanque(getattr(self, "conexion_origen", None))
        conn_dest = normalizar_conexion_tanque(getattr(self, "conexion_destino", None))
        anclados = self._liberar_anclados([self])

        atributos = ("diametro", "rugosidad", "caudal_Q", "u_Q", "u_L", "u_D", "u_eps")
        datos = {attr: getattr(self, attr) for attr in atributos}
        modo = getattr(self, "modo_trazado", "recto")
        dir_orig = getattr(self, "direccion_inicial", "H")
        c_nodo = nodo.centro_escena() if hasattr(nodo, "centro_escena") else nodo.sceneBoundingRect().center()

        pts1 = pts2 = None
        dir1 = dir2 = dir_orig
        if modo == "ortogonal":
            from ui.enrutado_ortogonal import (
                direccion_inicial_polilinea,
                dividir_polilinea_ortogonal,
                ruta_multivertice,
            )

            puntos = list(getattr(self, "_puntos_trazado", []))
            if len(puntos) < 2:
                puntos = ruta_multivertice(
                    [self._centro(o)] + list(getattr(self, "vertices_usuario", [])) + [self._centro(d)],
                    direccion_inicial=dir_orig,
                )
            pt_corte, t_corte, _, pts1, pts2 = dividir_polilinea_ortogonal(puntos, c_nodo)
            nodo.setPos(nodo.pos() + (pt_corte - c_nodo))
            fraccion = max(0.01, min(0.99, float(t_corte)))
            dir1 = direccion_inicial_polilinea(pts1) or dir_orig
            dir2 = direccion_inicial_polilinea(pts2) or dir_orig
        else:
            d1 = QLineF(self._centro(o), c_nodo).length()
            d2 = QLineF(c_nodo, self._centro(d)).length()
            fraccion = d1 / (d1 + d2) if (d1 + d2) > 0 else 0.5
            fraccion = max(0.01, min(0.99, float(fraccion)))

        longitud1 = round(self.longitud * fraccion, 4)
        longitud2 = round(self.longitud - longitud1, 4)
        self._eliminar_de_escena(self, escena)

        tomar_id = getattr(escena, "_tomar_id_tuberia", None)
        id1 = tomar_id() if callable(tomar_id) else None
        id2 = tomar_id() if callable(tomar_id) else None
        t1 = TuberiaGrafica(o, nodo, id_tuberia=id1)
        t2 = TuberiaGrafica(nodo, d, id_tuberia=id2)
        t1.conexion_origen = conn_orig
        t2.conexion_destino = conn_dest

        configs = (
            (t1, longitud1, pts1[1:-1] if pts1 is not None else [], dir1),
            (t2, longitud2, pts2[1:-1] if pts2 is not None else [], dir2),
        )
        for nueva, longitud, vertices, dir_i in configs:
            for attr, val in datos.items():
                setattr(nueva, attr, val)
            nueva.longitud = longitud
            nueva.modo_trazado = modo
            nueva.vertices_usuario = list(vertices)
            nueva.direccion_inicial = dir_i
            escena.addItem(nueva)
            nueva.actualizar_posicion()
            nueva.actualizar_etiqueta()

        AccesorioGrafico._reanclar(anclados, [t1, t2])
        return t1, t2

    @staticmethod
    def recombinar_desde_nodo(nodo, escena):
        """
        Recombina las dos tuberías incidentes a `nodo` en una única tubería
        conservando propiedades hidráulicas, accesorios anclados y trazado ortogonal.
        """
        t1, t2 = nodo.tuberias[0], nodo.tuberias[1]
        origen = t1.nodo_origen if t1.nodo_destino is nodo else t1.nodo_destino
        destino = t2.nodo_destino if t2.nodo_origen is nodo else t2.nodo_origen
        conn_orig = normalizar_conexion_tanque(
            getattr(t1, "conexion_origen", None)
            if t1.nodo_origen is origen
            else getattr(t1, "conexion_destino", None)
        )
        conn_dest = normalizar_conexion_tanque(
            getattr(t2, "conexion_destino", None)
            if t2.nodo_destino is destino
            else getattr(t2, "conexion_origen", None)
        )
        anclados = TuberiaGrafica._liberar_anclados([t1, t2])

        atributos = ("diametro", "rugosidad", "caudal_Q", "u_Q", "u_L", "u_D", "u_eps")
        datos = {attr: getattr(t1, attr) for attr in atributos}
        longitud_total = round(t1.longitud + t2.longitud, 4)

        es_ortogonal = (
            getattr(t1, "modo_trazado", "recto") == "ortogonal"
            or getattr(t2, "modo_trazado", "recto") == "ortogonal"
        )
        vertices = []
        dir_init = getattr(t1, "direccion_inicial", "H")
        if es_ortogonal:
            from ui.enrutado_ortogonal import (
                direccion_inicial_polilinea,
                recombinar_polilineas_ortogonales,
            )

            p1 = list(
                getattr(t1, "_puntos_trazado", [])
                or [t1._centro(t1.nodo_origen), t1._centro(t1.nodo_destino)]
            )
            if t1.nodo_origen is nodo:
                p1.reverse()
            p2 = list(
                getattr(t2, "_puntos_trazado", [])
                or [t2._centro(t2.nodo_origen), t2._centro(t2.nodo_destino)]
            )
            if t2.nodo_destino is nodo:
                p2.reverse()

            combinada = recombinar_polilineas_ortogonales(p1, p2)
            vertices = list(combinada[1:-1])
            dir_init = direccion_inicial_polilinea(combinada) or dir_init

        TuberiaGrafica._eliminar_de_escena(t1, escena)
        TuberiaGrafica._eliminar_de_escena(t2, escena)
        nodo.tuberias.clear()

        tomar_id = getattr(escena, "_tomar_id_tuberia", None)
        nueva = TuberiaGrafica(origen, destino, id_tuberia=tomar_id() if callable(tomar_id) else None)
        for attr, val in datos.items():
            setattr(nueva, attr, val)
        nueva.longitud = longitud_total
        nueva.modo_trazado = "ortogonal" if es_ortogonal else "recto"
        nueva.vertices_usuario = vertices
        nueva.direccion_inicial = dir_init
        nueva.conexion_origen = conn_orig
        nueva.conexion_destino = conn_dest
        escena.addItem(nueva)
        nueva.actualizar_posicion()
        nueva.actualizar_etiqueta()
        AccesorioGrafico._reanclar(anclados, [nueva])
        return nueva


class BotonPerdidaEsquina(QGraphicsItem):
    """Zona discreta de hover con un + flotante y un codo verde si tiene pérdida."""

    def __init__(self, tuberia, indice):
        super().__init__(tuberia)
        self.tuberia = tuberia
        self.indice = indice
        self.configurada = False
        self._hover = False
        self.centro_boton = QPointF(22, -22)
        self.brazo_entrada = QPointF(-16, 0)
        self.brazo_salida = QPointF(0, 16)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(8)
        self.setToolTip('Configurar pérdida de la esquina · K o Le/D')

    def configurar_geometria(self, anterior, punto, siguiente):
        def direccion(destino):
            vector = destino - punto
            largo = math.hypot(vector.x(), vector.y())
            return vector / largo if largo > 1e-6 else QPointF()
        entrada, salida = direccion(anterior), direccion(siguiente)
        self.prepareGeometryChange()
        # El cuadrante opuesto a los dos brazos mantiene el botón fuera del trazo.
        self.centro_boton = (entrada + salida) * -22
        self.brazo_entrada = entrada * min(16, QLineF(anterior, punto).length() / 3)
        self.brazo_salida = salida * min(16, QLineF(punto, siguiente).length() / 3)

    def boundingRect(self):
        return self.shape().boundingRect().united(QRectF(-21, -21, 42, 42)).adjusted(-2, -2, 2, 2)

    def shape(self):
        zona = QPainterPath()
        zona.addEllipse(QPointF(), 13, 13)
        zona.addEllipse(self.centro_boton, 11, 11)
        puente = QPainterPath(QPointF())
        puente.lineTo(self.centro_boton)
        contorno = QPainterPathStroker()
        contorno.setWidth(18)
        return zona.united(contorno.createStroke(puente))

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        self.setCursor(Qt.PointingHandCursor if QLineF(event.pos(), self.centro_boton).length() <= 11
                       else Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.unsetCursor()
        self.update()
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        if self.configurada:
            codo = QPainterPath(self.brazo_entrada)
            codo.lineTo(QPointF())
            codo.lineTo(self.brazo_salida)
            painter.setPen(QPen(QColor('#15803d'), 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(codo)
            painter.setPen(QPen(QColor('#4ade80'), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(codo)
        if self._hover:
            centro = self.centro_boton
            painter.setPen(QPen(QColor('#bbdceb'), 1, Qt.DotLine))
            painter.drawLine(QPointF(), centro)
            painter.setPen(QPen(QColor('#0284c7'), 1.3))
            painter.setBrush(QBrush(QColor('#ffffff')))
            painter.drawEllipse(centro, 9, 9)
            painter.setPen(QPen(QColor('#0284c7'), 1.8, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(centro + QPointF(-3.5, 0), centro + QPointF(3.5, 0))
            painter.drawLine(centro + QPointF(0, -3.5), centro + QPointF(0, 3.5))

    def abrir(self):
        escena = self.scene()
        accesorio = next((a for a in self.tuberia.accesorios_conectados
                          if getattr(a, 'esquina_indice', None) == self.indice), None)
        if accesorio is None:
            punto = self.tuberia._puntos_trazado[self.indice]
            accesorio = AccesorioGrafico(punto.x() - 15, punto.y() - 15, forma_visual='Codo')
            accesorio.esquina_indice = self.indice
            escena.addItem(accesorio)
            accesorio.anclar_a(self.tuberia)
            escena.elementos_modificados.emit()
        escena.clearSelection()
        accesorio.setSelected(True)
        ventana = getattr(escena, 'main_window', None)
        if ventana is not None:
            ventana.campos_accesorio['valor'].setFocus()
        return accesorio

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._hover and QLineF(event.pos(), self.centro_boton).length() <= 11:
            self.abrir()
            event.accept()
        else:
            event.ignore()


class AccesorioGrafico(RealceGraficoMixin, QGraphicsItem):
    ANCHO = 30
    ALTO = 30
    FORMAS = ("Válvula", "Reducción", "Expansión")
    TIPOS_PERDIDA = ("K", "Le/D")
    FORMAS_DIVISORAS = ("Reducción", "Expansión")
    COLOR_LIBRE = QColor("#f59e0b")
    COLOR_CONECTADO = QColor("#16a34a")

    def __init__(
        self,
        x=0,
        y=0,
        forma_visual="Válvula",
        tipo_perdida="K",
        valor=0.0,
        tuberia_padre=None,
        parent=None,
    ):
        super().__init__(parent)
        self.forma_visual = forma_visual
        self.tipo_perdida = tipo_perdida
        self.valor = valor
        self.tuberia_padre = tuberia_padre
        self.tuberias = []
        self.angulo_in = 0.0
        self.angulo_out = 90.0

        self.setPos(x, y)
        self.setTransformOriginPoint(self.ANCHO / 2, self.ALTO / 2)
        self.setFlag(QGraphicsItem.ItemIsMovable, tuberia_padre is None)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(1)

    def centro_escena(self):
        """Retorna el centro geométrico del elemento en coordenadas de la escena."""
        return self.mapToScene(QPointF(self.ANCHO / 2.0, self.ALTO / 2.0))

    def boundingRect(self):
        return QRectF(0, 0, self.ANCHO, self.ALTO)

    def paint(self, painter, option, widget=None):
        if getattr(self, 'esquina_indice', None) is not None:
            return  # La esquina usa su botón +; no superponer otro símbolo.
        painter.setRenderHint(QPainter.Antialiasing)
        conectado = self.tuberia_padre is not None or bool(self.tuberias)
        color = self.color_interactivo(self.COLOR_CONECTADO if conectado else self.COLOR_LIBRE)
        borde = color.darker(150)

        if self.forma_visual == "Válvula":
            painter.setPen(QPen(borde, 1.5))
            painter.setBrush(QBrush(color))
            painter.drawPolygon(QPolygonF([QPointF(3, 6), QPointF(15, 15), QPointF(3, 24)]))
            painter.drawPolygon(QPolygonF([QPointF(27, 6), QPointF(15, 15), QPointF(27, 24)]))
        elif self.forma_visual == "Codo":
            pen = QPen(color, 5)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            brazo_in, brazo_out = self._brazos_codo()
            painter.save()
            painter.translate(self.ANCHO / 2, self.ALTO / 2)
            painter.drawLine(QPointF(0, 0), brazo_in)
            painter.drawLine(QPointF(0, 0), brazo_out)
            painter.restore()
        elif self.forma_visual == "Reducción":
            painter.setPen(QPen(borde, 1.5))
            painter.setBrush(QBrush(color))
            painter.drawPolygon(QPolygonF([QPointF(3, 5), QPointF(27, 10), QPointF(27, 20), QPointF(3, 25)]))
        elif self.forma_visual == "Expansión":
            painter.setPen(QPen(borde, 1.5))
            painter.setBrush(QBrush(color))
            painter.drawPolygon(QPolygonF([QPointF(3, 10), QPointF(27, 5), QPointF(27, 25), QPointF(3, 20)]))

        if option.state & QStyle.State_Selected:
            pen = QPen(QColor("#0284c7"), 1.5, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5))

    def _brazos_codo(self, largo=11):
        brazo_in = QPointF(-largo, 0)
        relativo = math.radians(self.angulo_out - self.angulo_in)
        brazo_out = QPointF(largo * math.cos(relativo), -largo * math.sin(relativo))
        return brazo_in, brazo_out

    def restaurar_borde(self):
        pass

    def restablecer_orientacion(self):
        self.angulo_in = 0.0
        self.angulo_out = 90.0
        self.setRotation(0)
        self.update()

    @staticmethod
    def _segmento_extremo_ortogonal(tuberia, al_final):
        pts = getattr(tuberia, "_puntos_trazado", [])
        if getattr(tuberia, "modo_trazado", "recto") != "ortogonal" or len(pts) < 2:
            return None
        pares = zip(reversed(pts[:-1]), reversed(pts[1:])) if al_final else zip(pts[:-1], pts[1:])
        for p_a, p_b in pares:
            linea = QLineF(p_a, p_b)
            if linea.length() > 1e-4:
                return linea.angle()
        return None

    def orientar_desde_nodos(self):
        if self.tuberia_padre is not None:
            return

        centro = self.centro_escena() if hasattr(self, "centro_escena") else self.sceneBoundingRect().center()
        ang_in = ang_out = None
        for tuberia in self.tuberias:
            if ang_in is None and tuberia.nodo_destino is self and tuberia.nodo_origen is not self:
                ang_in = self._segmento_extremo_ortogonal(tuberia, al_final=True)
                if ang_in is None:
                    ang_in = QLineF(tuberia._centro(tuberia.nodo_origen), centro).angle()
            if ang_out is None and tuberia.nodo_origen is self and tuberia.nodo_destino is not self:
                ang_out = self._segmento_extremo_ortogonal(tuberia, al_final=False)
                if ang_out is None:
                    ang_out = QLineF(centro, tuberia._centro(tuberia.nodo_destino)).angle()

        if ang_in is None and ang_out is None:
            self.restablecer_orientacion()
            return
        if ang_in is None:
            ang_in = ang_out
        if ang_out is None:
            ang_out = ang_in

        self.angulo_in = ang_in
        self.angulo_out = ang_out
        self.setRotation(-ang_in)
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            _acompanar_anclados_en_bloque(self, value)
        elif change == QGraphicsItem.ItemPositionHasChanged and not getattr(self, '_actualizando_anclaje', False):
            afectadas = []
            if self.tuberia_padre is not None:
                afectadas.append(self.tuberia_padre)
            for tuberia in self.tuberias:
                if all(tuberia is not otra for otra in afectadas):
                    afectadas.append(tuberia)
            for tuberia in afectadas:
                tuberia.actualizar_posicion()
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._finalizando_arrastre = True
        try:
            self._finalizar_colocacion()
        finally:
            self._finalizando_arrastre = False

    def _finalizar_colocacion(self):
        if self.tuberias:
            self.update()
            return

        if self.tuberia_padre is not None:
            if getattr(self.tuberia_padre, "modo_trazado", "recto") == "ortogonal":
                from ui.enrutado_ortogonal import proyectar_punto_a_polilinea

                c = (
                    self.centro_escena()
                    if hasattr(self, "centro_escena")
                    else self.sceneBoundingRect().center()
                )
                _, t_nuevo, _ = proyectar_punto_a_polilinea(
                    c, self.tuberia_padre._puntos_trazado
                )
                self.t_anclaje = t_nuevo
            self.tuberia_padre.actualizar_posicion()
            self.scene().elementos_modificados.emit()
            self.update()
            return

        candidatas = []
        centro = self.centro_escena()
        for item in self.scene().items():
            if isinstance(item, EtiquetaFlotante):
                item = item.parentItem()
            if (
                isinstance(item, TuberiaGrafica)
                and item not in candidatas
                and item not in self.tuberias
                and item._indice_paralela() == 0
                and item.distancia_a(centro) <= 24.0
            ):
                candidatas.append(item)

        if candidatas:
            centro = self.centro_escena() if hasattr(self, "centro_escena") else self.sceneBoundingRect().center()
            tuberia = min(candidatas, key=lambda t: t.distancia_a(centro))
            if self.forma_visual in self.FORMAS_DIVISORAS:
                self.insertar_en(tuberia)
            else:
                self.anclar_a(tuberia)
                self.scene().elementos_modificados.emit()

        self.update()

    def anclar_a(self, tuberia):
        if tuberia in self.tuberias:
            return

        if self.tuberia_padre is not None and self.tuberia_padre is not tuberia:
            self.desanclar()

        self.tuberia_padre = tuberia
        if self not in tuberia.accesorios_conectados:
            tuberia.accesorios_conectados.append(self)
        self.setFlag(
            QGraphicsItem.ItemIsMovable,
            getattr(self, 'esquina_indice', None) is None and (
                self.forma_visual == "Codo" or getattr(tuberia, "modo_trazado", "recto") == "ortogonal"),
        )
        if getattr(self, 'esquina_indice', None) is not None:
            self.setAcceptedMouseButtons(Qt.NoButton)
        if getattr(tuberia, "modo_trazado", "recto") == "ortogonal":
            from ui.enrutado_ortogonal import proyectar_punto_a_polilinea

            c = (
                self.centro_escena()
                if hasattr(self, "centro_escena")
                else self.sceneBoundingRect().center()
            )
            _, self.t_anclaje, _ = proyectar_punto_a_polilinea(
                c, tuberia._puntos_trazado
            )
        tuberia.actualizar_posicion()
        self.update()

    @staticmethod
    def _reanclar(accesorios, tuberias):
        for accesorio in accesorios:
            centro = accesorio.centro_escena() if hasattr(accesorio, "centro_escena") else accesorio.sceneBoundingRect().center()
            destino = min(tuberias, key=lambda t: t.distancia_a(centro))
            if getattr(accesorio, 'esquina_indice', None) is not None and len(destino._puntos_trazado) > 2:
                accesorio.esquina_indice = min(range(1, len(destino._puntos_trazado) - 1),
                    key=lambda i: QLineF(centro, destino._puntos_trazado[i]).length())
            accesorio.anclar_a(destino)

    def desanclar(self):
        tuberia = self.tuberia_padre
        self.tuberia_padre = None
        self.t_anclaje = None
        if tuberia is not None:
            if self in tuberia.accesorios_conectados:
                tuberia.accesorios_conectados.remove(self)
            tuberia.actualizar_posicion()

        escena = self.scene()
        if escena is not None and len(self.tuberias) == 2:
            TuberiaGrafica.recombinar_desde_nodo(self, escena)
            escena.elementos_modificados.emit()

        self.orientar_desde_nodos()
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.update()

    def insertar_en(self, tuberia):
        escena = self.scene()
        if escena is None:
            return False

        if len(tuberia._hermanas()) > 1:
            QMessageBox.warning(
                escena.main_window or (escena.views()[0] if escena.views() else None),
                "No se puede insertar",
                "Esta tubería tiene tuberías en paralelo. Una válvula, reducción o "
                "expansión solo puede insertarse en una tubería sin paralelas.",
            )
            return False

        if self.tuberia_padre is not None:
            self.desanclar()

        tuberia.dividir_por_nodo(self, escena)
        self.orientar_desde_nodos()
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        escena.elementos_modificados.emit()
        self.update()
        return True

    def contextMenuEvent(self, event):
        if self.tuberia_padre is None and not self.tuberias:
            event.ignore()
            return
        menu = QMenu()
        accion = menu.addAction("Desanclar")
        if menu.exec_(event.screenPos()) is accion:
            self.desanclar()
        event.accept()


MAX_BOMBAS_VISUALES = 3


class _ListaEquiposBomba(list):
    """Lista de equipos vinculada a una BombaGrafica que dispara update() en cada mutación."""

    def __init__(self, iterable=(), owner=None):
        super().__init__(iterable)
        self._owner = owner

    def _notificar(self):
        if self._owner is not None:
            self._owner.update()

    def append(self, item):
        super().append(item)
        self._notificar()

    def pop(self, index=-1):
        val = super().pop(index)
        self._notificar()
        return val

    def extend(self, iterable):
        super().extend(iterable)
        self._notificar()

    def insert(self, index, item):
        super().insert(index, item)
        self._notificar()

    def remove(self, item):
        super().remove(item)
        self._notificar()

    def clear(self):
        super().clear()
        self._notificar()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._notificar()

    def __delitem__(self, key):
        super().__delitem__(key)
        self._notificar()


class BombaGrafica(RealceGraficoMixin, QGraphicsRectItem):
    """
    Representación gráfica e interactiva de una bomba centrífuga como NODO en el lienzo CAD (estilo Stitch).
    Se coloca libre en el lienzo y se conecta a tuberías mediante la herramienta de conexión.
    """

    ANCHO = 60
    ALTO = 60
    MAX_BOMBAS_VISUALES = MAX_BOMBAS_VISUALES
    COLOR_BORDE = QColor("#0c4e77")
    COLOR_FONDO = QColor("#eff4ff")
    COLOR_TRIANGULO = QColor("#2f6690")
    COLOR_HALO = QColor("#5bb8fe")
    COLOR_PASTILLA = QColor("#0c4e77")

    def __init__(self, x=0, y=0, nombre="Bomba 1", id_bomba=1, parent=None):
        super().__init__(0, 0, self.ANCHO, self.ALTO, parent)
        self.setPos(x, y)
        self.nombre = str(nombre)
        self.id_bomba = int(id_bomba)
        self.setPen(QPen(self.COLOR_BORDE, 2.2, Qt.SolidLine))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(1)

        self.tuberias = []
        self._curvas = []  # Lista interna de objetos CurvaBomba
        self._arreglo = "individual"  # 'individual', 'serie', 'paralelo'
        self._metodo = "cuadratico"  # 'cuadratico' (por defecto) o 'lineal'
        self._equipos = _ListaEquiposBomba(
            [
                {
                    "nombre": "Bomba A",
                    "puntos": [],
                    "H": [],
                    "Q": [],
                    "eta": [],
                    "npsh": [],
                    "curva": None,
                }
            ],
            owner=self,
        )
        self.z_bomba = 0.0  # Elevación del eje en m

        # Resultados de operación calculados
        self.Q_op = None
        self.H_op = None
        self.eta_op = None
        self.potencia_hidraulica_op = None
        self.potencia_freno_op = None
        self.npsh_d = None
        self.npsh_r = None
        self.cavitacion = None
        self.estado_operacion = "OK"
        self.mensaje_operacion = ""
        self.reparto = []
        self.desglose = []

        self._tuberia_succion_override = None
        self._tuberia_descarga_override = None

        self.actualizar_tooltip()

    @property
    def arreglo(self):
        """Arreglo de la estación: 'individual', 'paralelo' o 'serie'."""
        return getattr(self, "_arreglo", "individual")

    @arreglo.setter
    def arreglo(self, valor):
        self._arreglo = str(valor) if valor is not None else "individual"
        self.update()

    @property
    def equipos(self):
        """Lista reactiva de equipos de la estación."""
        if not hasattr(self, "_equipos") or self._equipos is None:
            self._equipos = _ListaEquiposBomba(owner=self)
        return self._equipos

    @equipos.setter
    def equipos(self, valor):
        self._equipos = _ListaEquiposBomba(valor if valor is not None else (), owner=self)
        self.update()

    def num_iconos_visuales(self):
        """Retorna min(N_equipos, MAX_BOMBAS_VISUALES) iconos a dibujar."""
        n_eq = len(getattr(self, "equipos", []))
        return min(max(1, n_eq), self.MAX_BOMBAS_VISUALES)

    def num_sombras_visuales(self):
        """Retorna la cantidad de copias sombreadas detrás de la bomba principal (0, 1 o 2)."""
        return max(0, self.num_iconos_visuales() - 1)

    def texto_arreglo_visual(self):
        """Retorna 'Paralelo (N)' o 'Serie (N)' cuando N >= 2; vacío cuando N < 2."""
        n_eq = len(getattr(self, "equipos", []))
        if n_eq < 2:
            return ""
        es_serie = str(getattr(self, "arreglo", "paralelo")).lower() == "serie"
        return f"Serie ({n_eq})" if es_serie else f"Paralelo ({n_eq})"

    @property
    def metodo(self):
        """Método de la curva de la estación: 'cuadratico' o 'lineal'."""
        return getattr(self, "_metodo", "cuadratico")

    @metodo.setter
    def metodo(self, valor):
        m = "lineal" if "lineal" in str(valor).lower() else "cuadratico"
        self._metodo = m
        for eq in getattr(self, "equipos", []):
            if isinstance(eq, dict):
                if eq.get("curva") is not None and hasattr(eq["curva"], "metodo"):
                    eq["curva"].metodo = m
                eq.pop("modo", None)
                eq.pop("metodo", None)
        for c in getattr(self, "_curvas", []):
            if hasattr(c, "metodo"):
                c.metodo = m

    @property
    def curvas(self):
        """Retorna las CurvaBomba activas de los equipos configurados o la lista directa."""
        equipos = getattr(self, "equipos", [])
        activas = [eq.get("curva") for eq in equipos if isinstance(eq, dict) and eq.get("curva") is not None]
        if activas:
            return activas
        return getattr(self, "_curvas", [])

    @curvas.setter
    def curvas(self, lista):
        self._curvas = list(lista) if lista else []
        m_est = self.metodo
        if lista:
            self.equipos = []
            for idx, c in enumerate(lista):
                if hasattr(c, "metodo"):
                    c.metodo = m_est
                nom = getattr(c, "nombre", None) or f"Bomba {chr(65 + idx)}"
                q_pts = list(getattr(c, "Q", []))
                h_pts = list(getattr(c, "H", []))
                eta_pts = list(getattr(c, "eta_raw", getattr(c, "eta", []))) if getattr(c, "tiene_eficiencia", False) else []
                npsh_pts = list(getattr(c, "npsh_r", [])) if getattr(c, "tiene_npshr", False) else []
                puntos = []
                for i in range(len(q_pts)):
                    e_val = eta_pts[i] if i < len(eta_pts) else None
                    if e_val is not None and e_val > 1.0:
                        e_val = e_val / 100.0
                    puntos.append((q_pts[i], h_pts[i], e_val))
                self.equipos.append({
                    "nombre": nom,
                    "puntos": puntos,
                    "H": h_pts,
                    "Q": q_pts,
                    "eta": eta_pts,
                    "npsh": npsh_pts,
                    "curva": c,
                })
        else:
            if not getattr(self, "equipos", None):
                self.equipos = [{
                    "nombre": "Bomba A",
                    "puntos": [],
                    "H": [],
                    "Q": [],
                    "eta": [],
                    "npsh": [],
                    "curva": None,
                }]
            else:
                for eq in self.equipos:
                    eq["curva"] = None
                    eq["puntos"] = []
                    eq["H"] = []
                    eq["Q"] = []
                    eq["eta"] = []
                    eq["npsh"] = []
                    eq.pop("modo", None)
                    eq.pop("metodo", None)

    def restaurar_borde(self):
        self.setPen(QPen(self.COLOR_BORDE, 2.2, Qt.SolidLine))
        self.update()

    def centro_escena(self):
        """Retorna el centro geométrico del eje de la bomba en coordenadas de la escena."""
        return self.mapToScene(QPointF(self.ANCHO / 2.0, self.ALTO / 2.0))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            _acompanar_anclados_en_bloque(self, value)
        elif change == QGraphicsItem.ItemPositionHasChanged:
            for tuberia in self.tuberias:
                tuberia.actualizar_posicion()
        return super().itemChange(change, value)

    def boundingRect(self):
        cx = self.ANCHO / 2.0
        cy = self.ALTO / 2.0
        r_bounds = 100.0
        return QRectF(cx - r_bounds, cy - r_bounds, 2.0 * r_bounds, 2.0 * r_bounds)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.rect().adjusted(-4, -4, 4, 4))
        return path

    @property
    def tuberia_succion(self):
        if self._tuberia_succion_override is not None and self._tuberia_succion_override in self.tuberias:
            self._tuberia_succion_override.es_succion = True
            return self._tuberia_succion_override
        # Tubería que entra a la bomba (succión)
        for t in self.tuberias:
            if t.nodo_destino is self:
                t.es_succion = True
                return t
        if len(self.tuberias) >= 1:
            self.tuberias[0].es_succion = True
            return self.tuberias[0]
        return None

    @tuberia_succion.setter
    def tuberia_succion(self, tub):
        self._tuberia_succion_override = tub
        if tub is not None:
            tub.es_succion = True

    @property
    def tuberia_descarga(self):
        if self._tuberia_descarga_override is not None and self._tuberia_descarga_override in self.tuberias:
            self._tuberia_descarga_override.es_descarga = True
            return self._tuberia_descarga_override
        # Tubería que sale de la bomba (descarga)
        for t in self.tuberias:
            if t.nodo_origen is self:
                t.es_descarga = True
                return t
        if len(self.tuberias) >= 2:
            for t in self.tuberias:
                if t is not self.tuberia_succion:
                    t.es_descarga = True
                    return t
        return None

    @tuberia_descarga.setter
    def tuberia_descarga(self, tub):
        self._tuberia_descarga_override = tub
        if tub is not None:
            tub.es_descarga = True

    def _dibujar_icono_bomba(self, painter, cx, cy, r, opacidad=1.0):
        """Dibuja un icono individual de bomba centrado en (cx, cy) con la opacidad indicada."""
        painter.save()
        painter.setOpacity(painter.opacity() * opacidad)

        # Base de apoyo de hormigón / skid (skid pad inferior)
        painter.setPen(QPen(QColor("#94a3b8"), 1.0))
        painter.setBrush(QBrush(QColor("#cbd5e1")))
        painter.drawRect(QRectF(cx - 20.0, cy + r - 1.0, 40.0, 5.0))

        # Salida tangencial (boquilla / cuadrito de descarga con brida)
        painter.setPen(QPen(self.COLOR_BORDE, 2.0))
        painter.setBrush(QBrush(self.COLOR_FONDO))
        painter.drawRect(QRectF(cx + 6.0, cy - r - 5.0, 10.0, 8.0))
        painter.drawLine(QPointF(cx + 4.0, cy - r - 5.0), QPointF(cx + 18.0, cy - r - 5.0))

        # Carcasa circular de la bomba (voluta centrífuga Stitch)
        painter.setPen(QPen(self.COLOR_BORDE, 2.2))
        painter.setBrush(QBrush(self.COLOR_FONDO))
        painter.drawEllipse(QPointF(cx, cy), r, r)

        # Triángulo interior del rodete apuntando en el sentido del flujo
        triangulo = QPolygonF([
            QPointF(cx - 13.0, cy - 10.0),
            QPointF(cx + 16.0, cy),
            QPointF(cx - 13.0, cy + 10.0),
        ])
        painter.setPen(QPen(self.COLOR_BORDE, 1.5))
        painter.setBrush(QBrush(self.color_interactivo(self.COLOR_TRIANGULO)))
        painter.drawPolygon(triangulo)

        # Cubo central del eje impulsor (hub)
        painter.setPen(QPen(self.COLOR_BORDE, 1.8))
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawEllipse(QPointF(cx, cy), 4.2, 4.2)

        painter.restore()

    def paint(self, painter, option, widget=None):
        painter.save()
        try:
            painter.setRenderHint(QPainter.Antialiasing)

            cx = self.ANCHO / 2.0
            cy = self.ALTO / 2.0
            r = 24.0

            # Halo de conexión activa (cuando es nodo origen en modo conectar)
            if self.pen().style() == Qt.DashLine:
                pen_conn = QPen(QColor("#0284c7"), 2.5, Qt.DashLine)
                painter.setPen(pen_conn)
                painter.setBrush(QColor(2, 132, 199, 35))
                painter.drawEllipse(QPointF(cx, cy), r + 8.0, r + 8.0)

            # -------------------------------------------------------------
            # 1. Un pulso de enfoque al seleccionar; luego el halo queda fijo.
            # -------------------------------------------------------------
            if self.isSelected():
                pen_halo = QPen(self.COLOR_HALO, 2.0, Qt.DashLine)
                painter.setPen(pen_halo)
                painter.setBrush(QColor(91, 184, 254, 30))
                radio_halo = r + 8.0 - 3.0 * math.sin(math.pi * self._gesto)
                painter.drawEllipse(QPointF(cx, cy), radio_halo, radio_halo)
            elif self._realce > 0:
                painter.setPen(QPen(QColor(56, 189, 248, round(180 * self._realce)), 2.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), r + 5, r + 5)

            # -------------------------------------------------------------
            # 2. Iconos apilados: sombras detrás (~6 px en diagonal, opacidad decreciente) y bomba principal arriba
            # -------------------------------------------------------------
            n_sombras = self.num_sombras_visuales()
            opacidades_sombra = (0.55, 0.30)  # k=1 -> 0.55, k=2 -> 0.30
            desplazamiento_px = 6.0
            for k in range(n_sombras, 0, -1):
                op_k = opacidades_sombra[k - 1] if (k - 1) < len(opacidades_sombra) else max(0.15, 0.55 / k)
                dx_k = -desplazamiento_px * k
                dy_k = -desplazamiento_px * k
                self._dibujar_icono_bomba(painter, cx + dx_k, cy + dy_k, r, opacidad=op_k)

            # Bomba principal arriba (opacidad = 1.0)
            self._dibujar_icono_bomba(painter, cx, cy, r, opacidad=1.0)

            # -------------------------------------------------------------
            # 3. Pastilla flotante superior y texto de arreglo bajo el icono (siempre horizontales)
            # -------------------------------------------------------------
            painter.save()
            painter.translate(cx, cy)
            # Contrarrotar respecto al ángulo del ítem para que el texto siempre esté horizontal
            painter.rotate(-self.rotation())

            # Texto del arreglo bajo el icono: "Paralelo (N)" o "Serie (N)", solo cuando N >= 2
            texto_arr = self.texto_arreglo_visual()
            if texto_arr:
                font_arr = QFont("Segoe UI", 7)
                font_arr.setBold(True)
                painter.setFont(font_arr)
                fm_arr = QtGui.QFontMetrics(font_arr)
                w_arr = (
                    fm_arr.horizontalAdvance(texto_arr)
                    if hasattr(fm_arr, "horizontalAdvance")
                    else fm_arr.width(texto_arr)
                )
                h_arr = fm_arr.height()
                # Centrado, 4 px bajo el icono (base del icono en r + 4.0)
                y_arr = r + 4.0 + 4.0
                rect_arr = QRectF(-(w_arr + 6.0) / 2.0, y_arr, w_arr + 6.0, h_arr)
                painter.setPen(QColor("#0c4e77"))
                painter.drawText(rect_arr, Qt.AlignHCenter | Qt.AlignTop, texto_arr)

            texto_nom = self.nombre.upper()
            texto_z = f"z = {self.z_bomba:.2f} m"

            font_nom = QFont("Segoe UI", 8)
            font_nom.setBold(True)
            font_z = QFont("Segoe UI", 7)

            fm_nom = QtGui.QFontMetrics(font_nom)
            fm_z = QtGui.QFontMetrics(font_z)
            w_nom = fm_nom.horizontalAdvance(texto_nom) if hasattr(fm_nom, "horizontalAdvance") else fm_nom.width(texto_nom)
            w_z = fm_z.horizontalAdvance(texto_z) if hasattr(fm_z, "horizontalAdvance") else fm_z.width(texto_z)

            w_pastilla = max(w_nom, w_z) + 22.0
            w_pastilla = max(w_pastilla, 80.0)
            h_pastilla = 28.0
            y_pastilla = -(r + 14.0 + h_pastilla)

            rect_pastilla = QRectF(-w_pastilla / 2.0, y_pastilla, w_pastilla, h_pastilla)

            # Sombra suave de la pastilla
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(12, 78, 119, 35))
            painter.drawRoundedRect(rect_pastilla.translated(1.0, 2.0), 4.0, 4.0)

            # Cuerpo de la pastilla (Azul oscuro Stitch #0c4e77)
            borde_pastilla = self.COLOR_HALO if self.isSelected() else QColor("#004b73")
            painter.setPen(QPen(borde_pastilla, 1.2))
            painter.setBrush(QBrush(self.COLOR_PASTILLA))
            painter.drawRoundedRect(rect_pastilla, 4.0, 4.0)

            # Pequeño triángulo puntero hacia la bomba
            tri_puntero = QPolygonF([
                QPointF(-3.5, y_pastilla + h_pastilla),
                QPointF(3.5, y_pastilla + h_pastilla),
                QPointF(0.0, y_pastilla + h_pastilla + 4.0),
            ])
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(self.COLOR_PASTILLA))
            painter.drawPolygon(tri_puntero)

            # Texto del nombre (blanco)
            painter.setFont(font_nom)
            painter.setPen(QColor("#ffffff"))
            rect_txt_nom = QRectF(rect_pastilla.left(), rect_pastilla.top() + 2.0, rect_pastilla.width(), 13.0)
            painter.drawText(rect_txt_nom, Qt.AlignCenter, texto_nom)

            # Texto de elevación z (atenuado #cbd5e1)
            painter.setFont(font_z)
            painter.setPen(QColor("#cbd5e1"))
            rect_txt_z = QRectF(rect_pastilla.left(), rect_pastilla.top() + 14.0, rect_pastilla.width(), 12.0)
            painter.drawText(rect_txt_z, Qt.AlignCenter, texto_z)

            painter.restore()
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            painter.restore()

    def actualizar_etiqueta(self):
        """Redibuja la pastilla y actualiza el tooltip."""
        self.actualizar_tooltip()
        self.update()

    def actualizar_tooltip(self):
        n_eq = len(getattr(self, "equipos", []))
        if n_eq > 1:
            arr_txt = f"{self.arreglo.capitalize()} ({n_eq} equipos)"
        else:
            arr_txt = "Individual" if self.arreglo.lower() == "individual" else self.arreglo.capitalize()

        metodo_txt = "Ajuste cuadrático" if self.metodo == "cuadratico" else "Interpolación lineal"
        lineas = [
            f"<div style='font-family:Segoe UI, sans-serif;'>",
            f"<b style='color:#0c4e77; font-size:11pt;'>{self.nombre}</b> "
            f"<span style='color:#64748b; font-size:9pt;'>({'Estación de Bombeo' if n_eq > 1 else 'Bomba Centrífuga'})</span><br>",
            f"<span style='color:#475569;'>Arreglo: {arr_txt}</span><br>",
            f"<span style='color:#475569;'>Método: {metodo_txt}</span><br>",
            f"<span style='color:#475569;'>Cota de eje (z_bomba): {self.z_bomba:.2f} m</span><br>",
        ]

        if self.curvas:
            nombres = ", ".join(getattr(c, "nombre", f"Bomba {i+1}") for i, c in enumerate(self.curvas))
            lineas.append(f"<span style='color:#475569;'><b>Curvas asignadas:</b> {nombres}</span><br>")
            for curva in self.curvas:
                if usa_puntos(self.curvas,self.metodo):
                    lineas.append(resumen_puntos(puntos_tabla(curva))+'<br>')
                if nota_joroba(curva):
                    lineas.append(nota_joroba(curva)+'<br>')
        else:
            lineas.append("<span style='color:#94a3b8; font-style:italic;'>Sin curva H-Q configurada</span><br>")

        if self.Q_op is not None and self.H_op is not None:
            lineas.append("<hr style='border:0; border-top:1px solid #cbd5e1; margin:4px 0;'>")
            lineas.append("<b style='color:#0c4e77;'>Punto de Operación (Solver):</b><br>")
            lineas.append(f"• <b>Caudal Q:</b> {self.Q_op * 1000.0:.2f} L/s ({self.Q_op:.4f} m³/s)<br>")
            lineas.append(f"• <b>Carga H:</b> {self.H_op:.2f} m<br>")
            if self.eta_op is not None:
                lineas.append(f"• <b>Rendimiento (η):</b> {self.eta_op * 100.0:.1f} %<br>")
            else:
                lineas.append('• <b>Rendimiento (η):</b> —<br>')
            if self.potencia_freno_op is not None:
                lineas.append(f"• <b>Potencia al Freno (BHP):</b> {self.potencia_freno_op / 1000.0:.2f} kW<br>")
            elif getattr(self, "potencia_hidraulica_op", None) is not None:
                lineas.append('• <b>Potencia al Freno (BHP):</b> —<br>')
                lineas.append(f"• <b>Potencia Hidráulica (Ph):</b> {self.potencia_hidraulica_op / 1000.0:.2f} kW<br>")
            if self.npsh_d is not None:
                lineas.append(f"• <b>NPSH disponible:</b> {self.npsh_d:.2f} m<br>")
            if self.npsh_r is not None:
                lineas.append(f"• <b>NPSH requerido:</b> {self.npsh_r:.2f} m<br>")
            if self.cavitacion:
                color_cav = "#16a34a" if "SIN" in self.cavitacion.upper() else "#dc2626"
                lineas.append(f"• Cavitación: <b style='color:{color_cav};'>{self.cavitacion}</b><br>")
        else:
            lineas.append("<span style='color:#94a3b8; font-style:italic;'>Aún no calculado</span>")

        lineas.append("</div>")
        self.setToolTip("".join(lineas))
        self.update()

    def insertar_en(self, tuberia):
        """Divide una tubería e inserta la bomba como nodo conservando el trazado."""
        escena = self.scene()
        if escena is None:
            return False

        if len(tuberia._hermanas()) > 1:
            parent_w = getattr(escena, "main_window", None) or (escena.views()[0] if escena.views() else None)
            QMessageBox.warning(
                parent_w,
                "No se puede insertar",
                "Esta tubería tiene tuberías en paralelo. Una bomba solo puede insertarse "
                "en una tubería sin paralelas.",
            )
            return False

        t1, t2 = tuberia.dividir_por_nodo(self, escena)
        self.tuberia_succion = t1
        self.tuberia_descarga = t2
        self.actualizar_tooltip()
        escena.elementos_modificados.emit()
        return True

    def desanclar(self):
        """Recombina las tuberías conectadas conservando el trazado."""
        escena = self.scene()
        if len(self.tuberias) == 2 and escena is not None:
            TuberiaGrafica.recombinar_desde_nodo(self, escena)
            escena.elementos_modificados.emit()

        self._tuberia_succion_override = None
        self._tuberia_descarga_override = None
        self.Q_op = None
        self.H_op = None
        self.actualizar_tooltip()

    def to_dict(self):
        """Serializa la configuración de la estación de bombeo."""
        equipos_data = []
        for eq in getattr(self, "equipos", []):
            eq_dict = {
                "nombre": eq.get("nombre", ""),
                "puntos": list(eq.get("puntos", [])),
                "H": list(eq.get("H", [])),
                "Q": list(eq.get("Q", [])),
                "eta": list(eq.get("eta", [])),
                "npsh": list(eq.get("npsh", [])),
            }
            equipos_data.append(eq_dict)
        return {
            "id_bomba": self.id_bomba,
            "nombre": self.nombre,
            "x": float(self.pos().x()),
            "y": float(self.pos().y()),
            "z_bomba": float(self.z_bomba),
            "arreglo": self.arreglo,
            "metodo": self.metodo,
            "equipos": equipos_data,
        }

    def from_dict(self, data):
        """Carga la configuración de la estación; archivos antiguos cargan como 'cuadratico'."""
        self.nombre = data.get("nombre", self.nombre)
        self.id_bomba = int(data.get("id_bomba", self.id_bomba))
        if "x" in data and "y" in data:
            self.setPos(float(data["x"]), float(data["y"]))
        self.z_bomba = float(data.get("z_bomba", self.z_bomba))
        self.arreglo = data.get("arreglo", self.arreglo)
        metodo_raw = data.get("metodo", "cuadratico")
        self.metodo = "lineal" if "lineal" in str(metodo_raw).lower() else "cuadratico"

        if "equipos" in data:
            from motor.bombas import CurvaBomba
            self.equipos = []
            lista_curvas = []
            for eq_d in data["equipos"]:
                nom = eq_d.get("nombre", "Bomba")
                q_l = list(eq_d.get("Q", []))
                h_l = list(eq_d.get("H", []))
                eta_l = list(eq_d.get("eta", []))
                npsh_l = list(eq_d.get("npsh", []))
                puntos_l = list(eq_d.get("puntos", []))
                cb = None
                if len(q_l) >= 2 and len(h_l) >= 2:
                    try:
                        cb = CurvaBomba(
                            nom,
                            q_l,
                            h_l,
                            eta_l if eta_l else None,
                            npsh_r=npsh_l if npsh_l else None,
                            metodo=self.metodo,
                        )
                        lista_curvas.append(cb)
                    except ValueError as error:
                        raise ValueError(f'Curva inválida al cargar {nom}: {error}') from error
                    if cb is not None and not cb.valida:
                        raise ValueError(cb.mensaje)
                self.equipos.append({
                    "nombre": nom,
                    "puntos": puntos_l,
                    "H": h_l,
                    "Q": q_l,
                    "eta": eta_l,
                    "npsh": npsh_l,
                    "curva": cb,
                })
            self._curvas = lista_curvas
        self.actualizar_tooltip()


