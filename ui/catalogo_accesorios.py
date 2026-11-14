"""Selector visual de accesorios para el lienzo."""

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QStyleOptionGraphicsItem, QToolButton, QVBoxLayout

from ui.graficos import AccesorioGrafico


class CatalogoAccesorios(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Catálogo de accesorios')
        self.forma_elegida = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        titulo = QLabel('Elige un accesorio')
        titulo.setStyleSheet('font-size:18px; font-weight:700; color:#103e58;')
        layout.addWidget(titulo)
        fila = QHBoxLayout()
        for forma, detalle in (('Válvula', 'Control de flujo'), ('Reducción', 'Menor diámetro'), ('Expansión', 'Mayor diámetro')):
            imagen = QPixmap(48, 48)
            imagen.fill(Qt.transparent)
            pintor = QPainter(imagen)
            pintor.translate(9, 9)
            AccesorioGrafico(forma_visual=forma).paint(pintor, QStyleOptionGraphicsItem())
            pintor.end()
            boton = QToolButton()
            boton.setObjectName('catalogo' + forma)
            boton.setText(forma + '\n' + detalle)
            boton.setIcon(QIcon(imagen))
            boton.setIconSize(QSize(48, 48))
            boton.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            boton.setMinimumSize(138, 132)
            boton.setCursor(Qt.PointingHandCursor)
            boton.setStyleSheet('QToolButton {background:#eff8fc; border:1px solid #c6e5f0; border-radius:12px; padding:8px; color:#103e58; font-size:12px;} QToolButton:hover {background:#d9f4fb; border:1px solid #0284c7;}')
            boton.clicked.connect(lambda checked=False, f=forma: self.elegir(f))
            fila.addWidget(boton)
        layout.addLayout(fila)
        ayuda = QLabel('Selecciona una tubería antes de abrir el catálogo para colocar el accesorio sobre ella.\nLas pérdidas de las esquinas se configuran con el botón + de cada quiebre.')
        ayuda.setWordWrap(True)
        ayuda.setStyleSheet('color:#52677a; font-size:12px; padding-top:8px;')
        layout.addWidget(ayuda)

    def elegir(self, forma):
        self.forma_elegida = forma
        self.accept()
