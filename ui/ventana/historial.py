"""Historial de entradas del proyecto; cada arrastre se guarda como un cambio."""

import json
from copy import deepcopy

from PyQt5.QtCore import QEvent, QObject, QTimer, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction, QApplication

from ui.ventana.barra_herramientas import normalizar_datos_fluido
from ui.ventana.invalidacion import bloquear_senales


class HistorialProyecto(QObject):
    LIMITE = 100

    def __init__(self, ventana):
        super().__init__(ventana)
        self.ventana = ventana
        self.restaurando = False
        self.estados = [self._estado()]
        self.indice = 0
        self.temporizador = QTimer(self)
        self.temporizador.setSingleShot(True)
        self.temporizador.timeout.connect(self.registrar)
        self.accion = QAction('Deshacer', ventana)
        self.accion.setShortcut(QKeySequence.Undo)
        self.accion.triggered.connect(self.deshacer)
        ventana.addAction(self.accion)
        self.accion_rehacer = QAction('Rehacer', ventana)
        self.accion_rehacer.setShortcuts([QKeySequence('Ctrl+Y'), QKeySequence('Ctrl+Shift+Z')])
        self.accion_rehacer.triggered.connect(self.rehacer)
        ventana.addAction(self.accion_rehacer)
        # Mantener disponible Ctrl+Z aunque el último cambio aún esté pendiente.
        ventana.canvas_view.scene().changed.connect(self.programar)
        ventana.canvas_view.scene().elementos_modificados.connect(self.programar)
        QApplication.instance().installEventFilter(self)

    def _estado(self):
        datos = self.ventana._serializar_proyecto(validar=False)
        # La selección del dashboard y los resultados automáticos no son ediciones.
        datos.pop('dashboard', None)
        for tubo in datos['tuberias']:
            for campo, bandera in (('caudal_Q', '_q_por_energia'), ('diametro', '_d_por_energia')):
                if tubo.get(bandera):
                    tubo[campo] = 0.0
                tubo[bandera] = False
        for coleccion in ('tanques', 'uniones', 'bombas', 'tuberias', 'accesorios', 'formas', 'textos'):
            datos[coleccion].sort(key=lambda item: json.dumps(item, sort_keys=True))
        # Comparar objetos evita registrar 6000 y 6000.0 como cambios distintos.
        return deepcopy(datos)

    def programar(self, *args):
        if not self.restaurando:
            self.temporizador.start(350)

    def registrar(self):
        self.temporizador.stop()
        if self.restaurando:
            return
        if QApplication.mouseButtons() != Qt.NoButton:
            self.programar()
            return
        estado = self._estado()
        if estado != self.estados[self.indice]:
            del self.estados[self.indice + 1:]
            self.estados.append(estado)
            self.estados = self.estados[-self.LIMITE:]
            self.indice = len(self.estados) - 1

    def eventFilter(self, objeto, evento):
        # Antes de otra acción, termina la anterior aunque no haya vencido el timer.
        if evento.type() == QEvent.MouseButtonPress and not self.restaurando:
            if objeto.isWidgetType() and objeto.window() is self.ventana:
                # El estado ya es estable al presionar; mouseButtons incluye el clic actual.
                self.temporizador.stop()
                estado = self._estado()
                if estado != self.estados[self.indice]:
                    del self.estados[self.indice + 1:]
                    self.estados.append(estado)
                    self.estados = self.estados[-self.LIMITE:]
                    self.indice = len(self.estados) - 1
        if evento.type() in (QEvent.MouseButtonRelease, QEvent.KeyRelease):
            if objeto.isWidgetType() and objeto.window() is self.ventana:
                self.programar()
        return False

    def _restaurar(self, indice):
        if not 0 <= indice < len(self.estados):
            return
        self.temporizador.stop()
        self.restaurando = True
        ventana = self.ventana
        escena = ventana.canvas_view.scene()
        datos = deepcopy(self.estados[indice])
        # Conservar el modo de análisis, sin recalcular ni abrir diálogos al deshacer.
        datos['dashboard'] = {'modo': ventana.stack_modo.currentIndex()}
        ventana._cargando_proyecto = True
        try:
            with bloquear_senales(escena):
                ventana._reconstruir_proyecto(datos, normalizar_datos_fluido(datos['fluido']))
            self.indice = indice
        finally:
            ventana._cargando_proyecto = False
            self.restaurando = False
        ventana._on_elementos_modificados()
        ventana._mostrar_dashboard()
        ventana.statusBar().showMessage('Cambio revertido' if indice < len(self.estados) - 1 else 'Cambio restaurado', 2500)

    def deshacer(self):
        self.registrar()
        self._restaurar(self.indice - 1)

    def rehacer(self):
        self.registrar()
        self._restaurar(self.indice + 1)
