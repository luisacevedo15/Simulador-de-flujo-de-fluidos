"""Distribución adaptable de widgets, sin dependencias del modelo hidráulico."""

from PyQt5.QtCore import QRect,QSize,Qt,pyqtSignal
from PyQt5.QtGui import QFont,QFontMetrics
from PyQt5.QtWidgets import QLayout,QStackedLayout,QWidget,QPushButton


class FlowLayout(QLayout):
    """Conserva el ancho legible de cada control y pasa a otra fila si no cabe."""

    def __init__(self,parent=None):
        super().__init__(parent)
        self._items = []

    def addItem(self,item):
        self._items.append(item)

    def addWidget(self,widget,expand=False,minimum_width=None):
        super().addWidget(widget)
        self._items[-1]._flow_expand = expand
        self._items[-1]._flow_minimum_width = minimum_width

    @staticmethod
    def _preferido(item):
        tamano = item.sizeHint()
        if isinstance(item.widget(),QPushButton):
            boton = item.widget()
            # El estilo activo usa negrita; algunas fuentes de sustitución no
            # actualizan sizeHint al cambiar :checked. Reservar ambos estados.
            negrita = QFont(boton.font())
            negrita.setWeight(QFont.Bold)
            ancho_normal = boton.fontMetrics().horizontalAdvance(boton.text())
            ancho_negrita = QFontMetrics(negrita).horizontalAdvance(boton.text())
            tamano.setWidth(tamano.width()+max(0,ancho_negrita-ancho_normal)+24)
        ancho = getattr(item,'_flow_minimum_width',None)
        if ancho is not None:
            tamano.setWidth(max(tamano.width(),ancho()))
        return tamano

    def count(self):
        return len(self._items)

    def itemAt(self,index):
        return self._items[index] if 0<=index<len(self._items) else None

    def takeAt(self,index):
        return self._items.pop(index) if 0<=index<len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Horizontal)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self,width):
        return self._distribuir(QRect(0,0,width,0),False)

    def sizeHint(self):
        items = [i for i in self._items if not i.isEmpty()]
        margen = self.contentsMargins()
        return QSize(sum(self._preferido(i).width() for i in items)+max(0,len(items)-1)*max(0,self.spacing())
                     +margen.left()+margen.right(),
                     max((i.sizeHint().height() for i in items),default=0)+margen.top()+margen.bottom())

    def minimumSize(self):
        tamano = QSize()
        for item in self._items:
            if not item.isEmpty():
                tamano = tamano.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return tamano+QSize(m.left()+m.right(),m.top()+m.bottom())

    def setGeometry(self,rect):
        super().setGeometry(rect)
        self._distribuir(rect,True)

    def _distribuir(self,rect,colocar):
        m = self.contentsMargins()
        area = rect.adjusted(m.left(),m.top(),-m.right(),-m.bottom())
        espacio = max(0,self.spacing())
        x,y,alto_fila = area.x(),area.y(),0
        for item in self._items:
            if item.isEmpty():
                continue
            deseado = self._preferido(item)
            ancho = min(deseado.width(),max(0,area.width()))
            if alto_fila and x+ancho>area.x()+area.width():
                x,y,alto_fila = area.x(),y+alto_fila+espacio,0
            if getattr(item,'_flow_expand',False):
                ancho = max(0,area.x()+area.width()-x)
            alto = item.heightForWidth(ancho) if item.hasHeightForWidth() else deseado.height()
            alto = max(alto,item.minimumSize().height())
            if colocar:
                item.setGeometry(QRect(x,y,ancho,alto))
            x += ancho+espacio
            alto_fila = max(alto_fila,alto)
        return y+alto_fila-rect.y()+m.bottom()


class _LayoutPaginaActual(QStackedLayout):
    """Qt debe consultar el tamaño de la página visible también desde C++."""
    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else QSize()

    def minimumSize(self):
        w = self.currentWidget()
        return w.minimumSizeHint().expandedTo(w.minimumSize()) if w is not None else QSize()

    def hasHeightForWidth(self):
        w = self.currentWidget()
        return bool(w is not None and w.hasHeightForWidth())

    def heightForWidth(self,width):
        w = self.currentWidget()
        return w.heightForWidth(width) if w is not None and w.hasHeightForWidth() else self.sizeHint().height()


class PilaPaginaActual(QWidget):
    """Pila con la API usada por CURVAS, sin reservar espacio a páginas ocultas."""

    currentChanged = pyqtSignal(int)

    def __init__(self,parent=None):
        super().__init__(parent)
        self._pila = _LayoutPaginaActual(self)
        self._pila.setContentsMargins(0,0,0,0)
        self._pila.currentChanged.connect(self.currentChanged)
        self._pila.currentChanged.connect(self.updateGeometry)

    def addWidget(self,widget):
        return self._pila.addWidget(widget)

    def setCurrentIndex(self,index):
        self._pila.setCurrentIndex(index)

    def currentIndex(self):
        return self._pila.currentIndex()

    def currentWidget(self):
        return self._pila.currentWidget()

    def widget(self,index):
        return self._pila.widget(index)

    def count(self):
        return self._pila.count()
