"""Widgets auxiliares reutilizables (texto autoajustable, interruptor, hoja Excel)."""

import math

from PyQt5 import QtGui
from PyQt5.QtCore import QEasingCurve, QEvent, QRectF, Qt, QVariantAnimation
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import QCheckBox, QFrame, QSizePolicy, QTableWidget, QTextEdit

from ui.animaciones import mezclar_color, transicion


class _AutoHeightTextEdit(QTextEdit):
    """QTextEdit sin scrollbar propio que ajusta su altura al contenido para usar el único scroll del panel."""

    def __init__(self, scroll_padre=None, parent=None):
        super().__init__(parent)
        self._scroll_padre = scroll_padre
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(2)

    def _ajustar_altura(self, reset_scroll=False):
        ancho_util = self.viewport().width()
        if ancho_util <= 40:
            ancho_util = max(290, self.width() - 8)
        self.document().setTextWidth(ancho_util)
        alto_doc = int(math.ceil(self.document().size().height())) + 8
        self.setFixedHeight(max(64, alto_doc))
        self.verticalScrollBar().setValue(0)
        if reset_scroll and self._scroll_padre is not None:
            self._scroll_padre.verticalScrollBar().setValue(0)

    def setHtml(self, texto):
        super().setHtml(texto)
        self._ajustar_altura(reset_scroll=True)

    def setPlainText(self, texto):
        super().setPlainText(texto)
        self._ajustar_altura(reset_scroll=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._ajustar_altura(reset_scroll=False)


class _InterruptorStitch(QCheckBox):
    """Interruptor estilo toggle switch de Google Stitch ('Mostrar valores')."""

    def __init__(self, texto="Mostrar valores", parent=None):
        super().__init__(texto, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setChecked(False)
        f = QFont("Inter", 9)
        f.setWeight(QFont.DemiBold)
        self.setFont(f)
        ancho_txt = QtGui.QFontMetrics(f).horizontalAdvance(texto)
        self.setFixedHeight(28)
        self.setMinimumWidth(46 + ancho_txt + 12)
        self._posicion = float(self.isChecked())
        self._deslizamiento = QVariantAnimation(self)
        self._deslizamiento.setEasingCurve(QEasingCurve.OutCubic)
        self._deslizamiento.valueChanged.connect(self._actualizar_posicion)
        self.toggled.connect(self._animar_interruptor)

    def _actualizar_posicion(self, valor):
        self._posicion = float(valor)
        self.update()

    def _animar_interruptor(self, activo):
        if self.isVisible() and self.isEnabled():
            transicion(self._deslizamiento, self._posicion, float(activo), 180)
        else:
            self._deslizamiento.stop()
            self._actualizar_posicion(float(activo))

    def hideEvent(self, evento):
        self._deslizamiento.stop()
        self._actualizar_posicion(float(self.isChecked()))
        super().hideEvent(evento)

    def changeEvent(self, evento):
        if evento.type() == QEvent.EnabledChange and not self.isEnabled():
            self._deslizamiento.stop()
            self._actualizar_posicion(float(self.isChecked()))
        super().changeEvent(evento)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        activo = self.isChecked()

        track_rect = QRectF(2.0, 5.0, 34.0, 18.0)
        bg_track = mezclar_color("#cbd5e1", "#0284c7", self._posicion)
        p.setPen(Qt.NoPen)
        p.setBrush(bg_track)
        p.drawRoundedRect(track_rect, 9.0, 9.0)

        x_knob = 4.0 + 16.0 * self._posicion
        knob_rect = QRectF(x_knob, 7.0, 14.0, 14.0)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(knob_rect)

        p.setFont(self.font())
        p.setPen(QColor("#0c4e77") if activo else QColor("#41474e"))
        txt_rect = QRectF(42.0, 0.0, self.width() - 44.0, self.height())
        p.drawText(txt_rect, Qt.AlignLeft | Qt.AlignVCenter, self.text())
        p.end()


class _HojaExcelWidget(QTableWidget):
    """QTableWidget especializado para la vista de memoria de cálculo,
    con soporte para zoom con Ctrl + rueda y atajos de teclado (Ctrl++, Ctrl+-, Ctrl+0)."""
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.main_window._zoom_tabla_in()
            elif delta < 0:
                self.main_window._zoom_tabla_out()
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
                self.main_window._zoom_tabla_in()
                event.accept()
                return
            elif event.key() in (Qt.Key_Minus, Qt.Key_Underscore):
                self.main_window._zoom_tabla_out()
                event.accept()
                return
            elif event.key() == Qt.Key_0:
                self.main_window._zoom_tabla_reset()
                event.accept()
                return
        super().keyPressEvent(event)


class _ContenedorHojaExcel(QFrame):
    """Contenedor para la hoja de cálculo que aloja y reposiciona la pastilla flotante de HUD zoom."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hud = None

    def set_hud(self, hud):
        self.hud = hud
        self._reposicionar_hud()

    def _reposicionar_hud(self):
        if self.hud:
            w_disp = self.width()
            hud_w = self.hud.width() or 130
            # Pastilla flotante arriba a la derecha sobre la tabla (28px de margen para no tapar barra vertical)
            x = max(10, w_disp - hud_w - 28)
            y = 8
            self.hud.move(x, y)
            self.hud.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposicionar_hud()
