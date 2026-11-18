"""Movimiento breve, local y sin alterar geometría ni datos del simulador."""

import os
import sys
from functools import lru_cache

from PyQt5 import sip
from PyQt5.QtCore import QEasingCurve, QEvent, QObject, QPointF, QRectF, Qt, QVariantAnimation
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QGraphicsEffect, QPushButton, QToolButton, QWidget


@lru_cache(maxsize=1)
def movimiento_permitido():
    """Respeta la preferencia de accesibilidad de Windows y una opción de entorno."""
    if os.environ.get("SIMULADOR_REDUCIR_MOVIMIENTO", "").lower() in ("1", "true", "si"):
        return False
    if sys.platform == "win32":
        import ctypes
        activo = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(activo), 0):
            return bool(activo.value)  # SPI_GETCLIENTAREAANIMATION
    return True


def mezclar_color(origen, destino, progreso):
    a, b = QColor(origen), QColor(destino)
    t = max(0.0, min(1.0, float(progreso)))
    return QColor(*(round(x + (y - x) * t) for x, y in zip(a.getRgb(), b.getRgb())))


def transicion(animacion, inicio, fin, duracion=160):
    """Reutiliza una animación: invertir el gesto no acumula trabajos pendientes."""
    animacion.stop()
    animacion.setDuration(duracion if movimiento_permitido() else 0)
    animacion.setStartValue(float(inicio))
    animacion.setEndValue(float(fin))
    animacion.start()


def radio_boton(boton):
    nombre = boton.objectName()
    if nombre in ("navBtnReport", "navBtnGithub"):
        return 14.0
    if nombre.startswith("navBtn"):
        return 16.0
    if nombre == "bernoulliButton":
        return 18.0
    if nombre in ("segTabBtnLeft", "segTabBtnRight", "segTabBtn"):
        return 12.0
    if boton.parentWidget() and boton.parentWidget().objectName() == "mainToolbar":
        return 15.0
    return min(10.0, boton.height() / 2.0)


class _EfectoBoton(QGraphicsEffect):
    """Eleva y comprime el dibujo, manteniendo fija el área de interacción."""

    def __init__(self, boton):
        super().__init__(boton)
        self.boton = boton
        self.elevacion = 0.0
        self.presion = 0.0

    def boundingRectFor(self, rect):
        return rect.adjusted(-6, -7, 6, 8)

    def draw(self, painter):
        if abs(self.elevacion) < 0.001 and abs(self.presion) < 0.001:
            painter.save()
            self.drawSource(painter)
            painter.restore()
            return
        rect = self.sourceBoundingRect(Qt.LogicalCoordinates)
        if rect.isEmpty():
            return
        # 3 px de elevación y hasta 6% de compresión, sin mover el layout.
        escala = 1.0 - 0.06 * self.presion
        dy = -3.0 * self.elevacion + 1.5 * self.presion
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.boton.isEnabled() and self.elevacion > 0:
            sombra = QColor(12, 78, 119, round(24 * self.elevacion))
            painter.setPen(Qt.NoPen)
            painter.setBrush(sombra)
            painter.drawRoundedRect(rect.adjusted(3, 3, -3, -1), radio_boton(self.boton), radio_boton(self.boton))
        centro = rect.center()
        painter.translate(centro.x(), centro.y() + dy)
        painter.scale(escala, escala)
        painter.translate(-centro.x(), -centro.y())
        self.drawSource(painter)
        painter.restore()


class _RealceBoton(QWidget):
    """Brillo y onda visibles sobre el estilo; nunca captura foco ni clics."""

    def __init__(self, boton):
        super().__init__(boton)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self._nivel = 0.0
        self._pulso = 1.0
        self._barrido = 1.0
        self._presion = 0.0
        self._origen = QPointF(boton.rect().center())
        self._hover = QVariantAnimation(self)
        self._hover.setEasingCurve(QEasingCurve.OutCubic)
        self._hover.valueChanged.connect(self._actualizar_hover)
        self._clic = QVariantAnimation(self)
        self._clic.setEasingCurve(QEasingCurve.OutCubic)
        self._clic.valueChanged.connect(self._actualizar_clic)
        self._brillo = QVariantAnimation(self)
        self._brillo.setEasingCurve(QEasingCurve.InOutSine)
        self._brillo.valueChanged.connect(self._actualizar_brillo)
        self._resorte = QVariantAnimation(self)
        self._resorte.valueChanged.connect(self._actualizar_presion)
        self._efecto = _EfectoBoton(boton)
        boton.setGraphicsEffect(self._efecto)
        boton.installEventFilter(self)
        boton.pressed.connect(self._pulsar)
        boton.released.connect(self._soltar)
        self.setGeometry(boton.rect())
        self.show()

    def _actualizar_hover(self, valor):
        self._nivel = float(valor)
        self._efecto.elevacion = self._nivel if movimiento_permitido() else 0.0
        self._efecto.update()
        self.update()

    def _actualizar_clic(self, valor):
        self._pulso = float(valor)
        self.update()

    def _pulsar(self):
        if movimiento_permitido():
            transicion(self._clic, 0.0, 1.0, 480)
            self._resorte.setEasingCurve(QEasingCurve.OutCubic)
            transicion(self._resorte, self._presion, 1.0, 100)

    def _soltar(self):
        if movimiento_permitido():
            # Incluso un clic rápido muestra la compresión antes de recuperarse.
            self._resorte.setEasingCurve(QEasingCurve.OutBack)
            transicion(self._resorte, max(0.85, self._presion), 0.0, 340)

    def _actualizar_presion(self, valor):
        self._presion = float(valor)
        self._efecto.presion = self._presion
        self._efecto.update()

    def _actualizar_brillo(self, valor):
        self._barrido = float(valor)
        self.update()

    def _reposo(self):
        for animacion in (self._hover, self._clic, self._brillo, self._resorte):
            animacion.stop()
        self._nivel, self._pulso, self._barrido, self._presion = 0.0, 1.0, 1.0, 0.0
        self._efecto.elevacion = self._efecto.presion = 0.0
        self._efecto.update()
        self.update()

    def eventFilter(self, boton, evento):
        tipo = evento.type()
        if tipo == QEvent.Show:
            # Los QToolButton creados por QAction reciclan su caché al ocultar
            # la barra. Invalidarla evita conservar una captura vacía al volver.
            self._efecto.setEnabled(False)
            self._efecto.setEnabled(True)
            boton.update()
        elif tipo == QEvent.Resize:
            self.setGeometry(boton.rect())
        elif tipo in (QEvent.Enter, QEvent.Leave):
            destino = float(tipo == QEvent.Enter and boton.isEnabled())
            transicion(self._hover, self._nivel, destino, 240)
            if destino and movimiento_permitido():
                transicion(self._brillo, 0.0, 1.0, 620)
        elif tipo == QEvent.MouseButtonPress:
            self._origen = QPointF(evento.pos())
        elif tipo == QEvent.KeyPress:
            self._origen = QPointF(boton.rect().center())
        elif tipo in (QEvent.Hide, QEvent.EnabledChange):
            self._reposo()
        return False

    def paintEvent(self, evento):
        if not self.parentWidget().isEnabled():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radio = min(radio_boton(self.parentWidget()), rect.height() / 2)
        clip = QPainterPath()
        clip.addRoundedRect(rect, radio, radio)
        p.setClipPath(clip)
        peligro = self.parentWidget().objectName() in ("dangerToolbarBtn", "navBtnReport")
        color = QColor("#ba1a1a" if peligro else "#0284c7")
        primario = self.parentWidget().objectName() in ("bernoulliButton", "navBtnActive")
        if primario:
            color = QColor("#ffffff")
        color.setAlpha(round(110 * self._nivel))
        p.setPen(QPen(color, 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, radio, radio)
        if self._pulso < 1.0:
            color.setAlpha(round(75 * (1.0 - self._pulso)))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            radio_clic = max(self.width(), self.height()) * self._pulso
            p.drawEllipse(self._origen, radio_clic, radio_clic)
        if self._barrido < 1.0:
            ancho = max(35.0, self.width() * 0.4)
            x = -ancho + (self.width() + 2 * ancho) * self._barrido
            grad = QLinearGradient(x - ancho, 0, x + ancho, self.height())
            tono = QColor("#ffffff" if primario else "#38bdf8")
            tono.setAlpha(0)
            grad.setColorAt(0, tono)
            grad.setColorAt(1, tono)
            tono.setAlpha(70 if primario else 28)
            grad.setColorAt(0.5, tono)
            p.fillPath(clip, grad)
        p.end()


class MicroAnimaciones(QObject):
    """Incluye también controles creados posteriormente en paneles y diálogos."""

    def __init__(self, ventana):
        super().__init__(ventana)
        self._ventana = ventana
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, objeto, evento):
        if (evento.type() == QEvent.Show
                and isinstance(objeto, (QPushButton, QToolButton))
                and self._ventana.isAncestorOf(objeto)
                and not hasattr(objeto, "_micro_realce")):
            objeto._micro_realce = _RealceBoton(objeto)
        return False


class RealceGraficoMixin:
    """Aclara el objeto bajo el cursor sin mover sus anclajes ni conexiones."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._realce = 0.0
        self._animacion_realce = None
        self._gesto = 1.0
        self._animacion_gesto = None
        self.setAcceptHoverEvents(True)

    def _animar_realce(self, destino):
        if self._animacion_realce is None:
            self._animacion_realce = QVariantAnimation()
            self._animacion_realce.setEasingCurve(QEasingCurve.OutCubic)
            self._animacion_realce.valueChanged.connect(self._actualizar_realce)
        transicion(self._animacion_realce, self._realce, destino, 180)

    def _actualizar_realce(self, valor):
        if sip.isdeleted(self):
            self._animacion_realce.stop()
            return
        self._realce = float(valor)
        self.update()

    def color_interactivo(self, color):
        return mezclar_color(color, QColor(color).lighter(118), self._realce)

    def hoverEnterEvent(self, evento):
        self._animar_realce(1.0)
        self._animar_gesto()
        super().hoverEnterEvent(evento)

    def hoverLeaveEvent(self, evento):
        self._animar_realce(0.0)
        super().hoverLeaveEvent(evento)

    def itemChange(self, cambio, valor):
        if cambio == self.ItemSelectedHasChanged and valor:
            self._animar_gesto()
        if cambio == self.ItemSceneChange and getattr(self, "_animacion_realce", None) is not None:
            self._animacion_realce.stop()
            self._realce = 0.0
        if cambio == self.ItemSceneChange and getattr(self, "_animacion_gesto", None) is not None:
            self._animacion_gesto.stop()
            self._gesto = 1.0
        return super().itemChange(cambio, valor)

    def _animar_gesto(self):
        if not movimiento_permitido() or self.scene() is None:
            return
        if self._animacion_gesto is None:
            self._animacion_gesto = QVariantAnimation()
            self._animacion_gesto.valueChanged.connect(self._actualizar_gesto)
        transicion(self._animacion_gesto, 0.0, 1.0, 1100)

    def _actualizar_gesto(self, valor):
        if sip.isdeleted(self):
            self._animacion_gesto.stop()
            return
        self._gesto = float(valor)
        self.update()
