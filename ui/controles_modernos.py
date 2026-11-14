"""Menús y selectores Qt con la misma presentación que el lienzo CAD."""

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QComboBox, QListView, QMenu, QStyledItemDelegate

from ui.iconos import crear_icono_herramienta


class MenuOpciones(QMenu):
    """Mantiene acciones, teclado y cierre nativos, con dos líneas por opción."""

    def __init__(self, parent=None, ancho=328):
        super().__init__(parent)
        self.setMinimumWidth(ancho)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet('''
            QMenu { background: #ffffff; border: 1px solid #d6e6ee;
                border-radius: 12px; padding: 7px; font: 12px "Segoe UI"; }
            QMenu::item { padding: 20px 56px; }
            QMenu::separator { height: 1px; margin: 5px 12px; background: #e7eff5; }
        ''')

    def agregar(self, titulo, detalle, icono, handler):
        accion = self.addAction(crear_icono_herramienta(icono, '#087fab'), titulo)
        accion.setStatusTip(detalle)
        accion.triggered.connect(handler)
        return accion

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor('#ffffff'))
        p.setPen(QPen(QColor('#d6e6ee'), 1))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 12, 12)
        for accion in self.actions():
            r = self.actionGeometry(accion)
            if accion.isSeparator():
                p.setPen(QColor('#e7eff5'))
                p.drawLine(r.left() + 12, r.center().y(), r.right() - 12, r.center().y())
                continue
            activo = accion is self.activeAction()
            if activo or accion.isChecked():
                p.setPen(Qt.NoPen)
                p.setBrush(QColor('#e9f7fc' if activo else '#f0faf7'))
                p.drawRoundedRect(QRectF(r), 8, 8)
            icono = QRect(r.left() + 10, r.center().y() - 18, 36, 36)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#dff2fa'))
            p.drawRoundedRect(QRectF(icono), 9, 9)
            accion.icon().paint(p, icono.adjusted(7, 7, -7, -7))
            izquierda = r.left() + 58
            p.setFont(QFont('Segoe UI', 10, QFont.DemiBold))
            p.setPen(QColor('#103e58'))
            p.drawText(QRect(izquierda, r.center().y() - 18, r.width() - 80, 22), Qt.AlignVCenter, accion.text())
            p.setFont(QFont('Segoe UI', 8))
            p.setPen(QColor('#617889'))
            p.drawText(QRect(izquierda, r.center().y() + 3, r.width() - 70, 19), Qt.AlignVCenter, accion.statusTip())
            if accion.isChecked():
                p.setPen(QPen(QColor('#0d9488'), 2, Qt.SolidLine, Qt.RoundCap))
                x, y = r.right() - 17, r.center().y()
                p.drawLine(x - 4, y, x - 1, y + 3)
                p.drawLine(x - 1, y + 3, x + 5, y - 4)


class _DelegadoUnidades(QStyledItemDelegate):
    """Una misma altura para el diseño de la lista y para el dibujo de sus filas."""

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        return QSize(base.width(), max(36, base.height()))


class ComboModerno(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView())
        self.view().setItemDelegate(_DelegadoUnidades(self.view()))
        self.view().setUniformItemSizes(True)
        self.view().setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view().setStyleSheet('''
            QListView { background: white; color:#103e58; border:1px solid #cce2ee;
                padding:5px; outline:none; font:12px "Segoe UI"; }
            QListView::item { min-height:26px; padding:5px 10px; border-radius:5px; }
            QListView::item:selected { background:#dff4fb; color:#075985; }
            QListView::item:hover { background:#eff8fc; }
        ''')
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet('''
            QComboBox { background:white; color:#103e58; border:1px solid #cbdfe9;
                border-radius:8px; padding:7px 28px 7px 10px; font:12px "Segoe UI"; }
            QComboBox:hover { background:#f0faff; border-color:#67bcd8; }
            QComboBox:focus { border:1px solid #0284c7; }
            QComboBox::drop-down { border:none; width:25px; }
            QComboBox::down-arrow { image:none; }
        ''')

    def showPopup(self):
        # El popup nativo puede conservar la altura anterior a aplicar el QSS.
        # Sin este layout, las filas avanzan 17 px pero se pintan con 36 px.
        self.view().ensurePolished()
        self.view().doItemsLayout()
        super().showPopup()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor('#087fab'), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x, y = self.width() - 15, self.height() / 2
        p.drawLine(QPointF(x - 3, y - 1.5), QPointF(x, y + 1.5))
        p.drawLine(QPointF(x, y + 1.5), QPointF(x + 3, y - 1.5))


class SelectorTrazado(ComboModerno):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.menu_opciones = MenuOpciones(self, 330)
        for indice, (titulo, detalle, icono) in enumerate((
            ('Recto', 'Conexión directa entre elementos', 'ruta_recta'),
            ('Ortogonal', 'Tramos a 90° con esquinas editables', 'ruta_ortogonal'),
        )):
            accion = self.menu_opciones.agregar(titulo, detalle, icono,
                lambda checked=False, i=indice: self.setCurrentIndex(i))
            accion.setCheckable(True)

    def showPopup(self):
        for i, accion in enumerate(self.menu_opciones.actions()):
            accion.setChecked(i == self.currentIndex())
        self.menu_opciones.popup(self.mapToGlobal(QPoint(self.width() - self.menu_opciones.sizeHint().width(), self.height() + 6)))

    def hidePopup(self):
        self.menu_opciones.hide()
