"""Entradas e indicadores animados con geometría funcional estable."""

import weakref

from PyQt5 import sip
from PyQt5.QtCore import QEasingCurve, QEvent, QPointF, QRect, Qt, QTimer, QVariantAnimation
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QGraphicsEffect, QWidget

from ui.animaciones import movimiento_permitido, transicion


class IndicadorNavegacion(QWidget):
    """Acento que recorre el lateral al cambiar entre CAD, tabla y curvas."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self._destino = None
        self._movimiento = QVariantAnimation(self)
        self._movimiento.setEasingCurve(QEasingCurve.InOutCubic)
        self._movimiento.valueChanged.connect(self.setGeometry)
        parent.installEventFilter(self)

    def ir_a(self, boton):
        inicial = self._destino is None
        self._destino = boton
        rect = QRect(0, boton.y() + (boton.height() - 26) // 2, 4, 26)
        self._movimiento.stop()
        if inicial or not self.parentWidget().isVisible() or not movimiento_permitido():
            self.setGeometry(rect)
        else:
            self._movimiento.setStartValue(self.geometry())
            self._movimiento.setEndValue(rect)
            self._movimiento.setDuration(340)
            self._movimiento.start()
        self.show()
        self.raise_()

    def eventFilter(self, objeto, evento):
        if evento.type() in (QEvent.Show, QEvent.Resize, QEvent.LayoutRequest) and self._destino:
            boton = self._destino
            rect = QRect(0, boton.y() + (boton.height() - 26) // 2, 4, 26)
            if self._movimiento.endValue() != rect or evento.type() == QEvent.Show:
                self._movimiento.stop()
                self.setGeometry(rect)
        return False

    def paintEvent(self, evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor("#38bdf8"))
        grad.setColorAt(1, QColor("#0369a1"))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(self.rect(), 2, 2)
        p.end()


class _EntradaContenido(QWidget):
    """Anima una captura breve; el contenido real ya está disponible debajo."""

    def __init__(self, contenedor):
        super().__init__(contenedor)
        self.hide()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self._imagen = QPixmap()
        self._progreso = 1.0
        self._distancia = 22
        self._animacion = QVariantAnimation(self)
        self._animacion.setEasingCurve(QEasingCurve.OutCubic)
        self._animacion.valueChanged.connect(self._actualizar)
        self._animacion.finished.connect(self.cancelar)
        self._pendiente = QTimer(self)
        self._pendiente.setSingleShot(True)
        self._pendiente.timeout.connect(self._capturar)
        contenedor.installEventFilter(self)

    def iniciar(self, distancia):
        self.cancelar()
        self._distancia = distancia
        # Agrupa cambios de selección consecutivos y espera al layout final.
        self._pendiente.start(0)

    def _capturar(self):
        contenedor = self.parentWidget()
        if not contenedor.isVisible() or not movimiento_permitido():
            return
        self.setGeometry(contenedor.rect())
        self._imagen = contenedor.grab()
        self.show()
        self.raise_()
        QApplication.instance().installEventFilter(self)
        transicion(self._animacion, 0.0, 1.0, 320)

    def _actualizar(self, progreso):
        self._progreso = float(progreso)
        self.update()

    def cancelar(self):
        self._pendiente.stop()
        self._animacion.stop()
        self.hide()
        self._imagen = QPixmap()
        QApplication.instance().removeEventFilter(self)

    def eventFilter(self, objeto, evento):
        if objeto is self.parentWidget() and evento.type() == QEvent.Resize and self._pendiente.isActive():
            self._pendiente.start(0)
        elif objeto is self.parentWidget() and evento.type() in (QEvent.Hide, QEvent.Resize):
            self.cancelar()
        elif evento.type() in (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
            # Nada queda cubierto por una imagen vieja al empezar a interactuar.
            self.cancelar()
        return False

    def paintEvent(self, evento):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setOpacity(0.20 + 0.80 * self._progreso)
        p.drawPixmap(QPointF(self._distancia * (1.0 - self._progreso), 0), self._imagen)
        p.end()


def revelar_contenido(widget, distancia=22):
    if not widget.isVisible() or not movimiento_permitido():
        return
    if not hasattr(widget, "_entrada_contenido"):
        widget._entrada_contenido = _EntradaContenido(widget)
    widget._entrada_contenido.iniciar(distancia)


class _EntradaObjeto(QGraphicsEffect):
    """Aparición con pequeño rebote; solo se transforma el dibujo del elemento."""

    def __init__(self, item):
        super().__init__()
        self._item = weakref.ref(item)
        self._progreso = 0.0
        self._animacion = QVariantAnimation(self)
        self._animacion.setEasingCurve(QEasingCurve.OutBack)
        self._animacion.valueChanged.connect(self._actualizar)
        self._animacion.finished.connect(self._terminar)

    def _actualizar(self, progreso):
        item = self._item()
        if item is None or sip.isdeleted(item) or item.scene() is None:
            self._animacion.stop()
            self._terminar()
            return
        self._progreso = float(progreso)
        self.update()

    def _terminar(self):
        # Conservar el efecto desactivado evita borrar un QObject dentro de su señal.
        self._progreso = 1.0
        self.setEnabled(False)

    def boundingRectFor(self, rect):
        margen = max(rect.width(), rect.height()) * 0.04 + 12
        return rect.adjusted(-margen, -margen, margen, margen)

    def draw(self, painter):
        rect = self.sourceBoundingRect(Qt.LogicalCoordinates)
        centro = rect.center()
        escala = 0.78 + 0.22 * self._progreso
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(max(0.0, min(1.0, self._progreso * 1.7)))
        painter.translate(centro.x(), centro.y() + 10 * (1 - self._progreso))
        painter.scale(escala, escala)
        painter.translate(-centro.x(), -centro.y())
        pixmap, offset = self.sourcePixmap(Qt.LogicalCoordinates, QGraphicsEffect.NoPad)
        painter.drawPixmap(offset, pixmap)
        painter.restore()


def animar_entrada_item(item):
    if not movimiento_permitido() or item.scene() is None:
        return
    if not any(v.isVisible() for v in item.scene().views()):
        return
    efecto = _EntradaObjeto(item)
    item.setGraphicsEffect(efecto)
    transicion(efecto._animacion, 0.0, 1.0, 460)
