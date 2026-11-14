"""Guía de trazadores con demostraciones locales, sin depender de códecs de Windows."""

from PyQt5.QtCore import QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel,
                            QPushButton, QSlider, QVBoxLayout, QWidget)

from ui.iconos import crear_icono_herramienta
from ui.recursos import ruta_recurso


class VideoDemostracion(QWidget):
    progreso = pyqtSignal(int, int)
    reproduciendo = pyqtSignal(bool)
    fallo = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self.imagen = QImage()
        self.contenedor = None
        self.duracion = self.posicion = 0
        self.bucle = True
        self.ultimo_error = ''
        self.temporizador = QTimer(self)
        self.temporizador.setTimerType(Qt.PreciseTimer)
        self.temporizador.timeout.connect(self.avanzar)

    def sizeHint(self):
        return QSize(768, 432)

    def cargar(self, archivo):
        self.cerrar()
        self.imagen = QImage()
        self.ultimo_error = ''
        try:
            import av
            self.contenedor = av.open(archivo)
            self.stream = self.contenedor.streams.video[0]
            self.duracion = int(float(self.stream.duration * self.stream.time_base) * 1000)
            self.temporizador.setInterval(max(1, round(1000 / float(self.stream.average_rate))))
            self.frames = iter(self.contenedor.decode(self.stream))
            self.avanzar()
            self.reproducir()
        except Exception as error:
            self._error(error)

    def _mostrar_frame(self, frame):
        rgb = frame.to_ndarray(format='rgb24')
        self.imagen = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888).copy()
        self.posicion = round(float(frame.time or 0) * 1000)
        self.progreso.emit(self.posicion, self.duracion)
        self.update()

    def avanzar(self):
        if self.contenedor is None:
            return
        try:
            self._mostrar_frame(next(self.frames))
        except StopIteration:
            if self.bucle:
                self.buscar(0)
            else:
                self.pausar()
                self.progreso.emit(self.duracion, self.duracion)
        except Exception as error:
            self._error(error)

    def buscar(self, milisegundos):
        if self.contenedor is None:
            return
        import av
        destino = max(0, min(milisegundos, self.duracion - self.temporizador.interval()))
        try:
            self.contenedor.seek(int(destino * av.time_base / 1000), backward=True)
            self.frames = iter(self.contenedor.decode(self.stream))
            for frame in self.frames:
                if float(frame.time or 0) * 1000 >= destino:
                    self._mostrar_frame(frame)
                    break
        except Exception as error:
            self._error(error)

    def reproducir(self):
        if self.contenedor is not None:
            if self.posicion >= self.duracion - self.temporizador.interval():
                self.buscar(0)
            self.temporizador.start()
            self.reproduciendo.emit(True)

    def pausar(self):
        self.temporizador.stop()
        self.reproduciendo.emit(False)

    def cerrar(self):
        self.pausar()
        if self.contenedor is not None:
            self.contenedor.close()
            self.contenedor = None

    def _error(self, error):
        self.cerrar()
        self.ultimo_error = str(error)
        self.fallo.emit('No se pudo reproducir la demostración. Cierra y vuelve a abrir la guía.')
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#102d40'))
        if not self.imagen.isNull():
            tamano = self.imagen.size().scaled(self.size(), Qt.KeepAspectRatio)
            destino = QRectF((self.width() - tamano.width()) / 2,
                             (self.height() - tamano.height()) / 2, tamano.width(), tamano.height())
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(destino, self.imagen)


class DialogoGuiaTrazado(QDialog):
    def __init__(self, parent=None, modo='recto'):
        super().__init__(parent)
        self.setWindowTitle('Guía visual de trazadores')
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMinimumSize(640, 420)
        disponible = self.screen().availableGeometry()
        self.resize(min(900, int(disponible.width() * .9)), min(650, int(disponible.height() * .9)))
        self.setObjectName('guiaTrazado')
        self.setStyleSheet('''
            QDialog#guiaTrazado { background:#f4f9fc; }
            QDialog#guiaTrazado QLabel { font:12px "Segoe UI"; color:#52677a; background:transparent; }
            QDialog#guiaTrazado QLabel#guiaTitulo { font-size:21px; font-weight:700; color:#103e58; }
            QDialog#guiaTrazado QPushButton { font:12px "Segoe UI"; color:#103e58;
                background:white; border:1px solid #cde2ec; border-radius:9px; padding:8px 16px; }
            QDialog#guiaTrazado QPushButton:hover { background:#e1f4fb; border-color:#67bdd8; }
            QDialog#guiaTrazado QPushButton:checked { background:#dff4fb; border:1px solid #65c3df; font-weight:600; color:#087fab; }
            QDialog#guiaTrazado QPushButton#guiaControl { padding:0; }
            QDialog#guiaTrazado QSlider::groove:horizontal { height:5px; background:#d6e6ef; border-radius:2px; }
            QDialog#guiaTrazado QSlider::sub-page:horizontal { background:#0898c4; border-radius:2px; }
            QDialog#guiaTrazado QSlider::handle:horizontal { background:#087fab; width:13px; margin:-4px 0; border-radius:6px; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        titulo = QLabel('Aprende a dibujar tus tuberías')
        titulo.setObjectName('guiaTitulo')
        layout.addWidget(titulo)
        tabs = QHBoxLayout()
        self.grupo = QButtonGroup(self)
        self.botones = {}
        for clave, texto, icono in (('recto', 'Recto', 'ruta_recta'), ('ortogonal', 'Ortogonal', 'ruta_ortogonal')):
            boton = QPushButton(crear_icono_herramienta(icono), texto)
            boton.setCheckable(True)
            boton.clicked.connect(lambda checked=False, m=clave: self.cambiar_modo(m))
            self.grupo.addButton(boton)
            self.botones[clave] = boton
            tabs.addWidget(boton)
        layout.addLayout(tabs)
        self.video = VideoDemostracion()
        layout.addWidget(self.video, 1)
        controles = QHBoxLayout()
        self.play = QPushButton()
        self.play.setObjectName('guiaControl')
        self.play.setFixedSize(36, 36)
        self.play.setIconSize(QSize(18, 18))
        self.play.clicked.connect(lambda: self.video.pausar() if self.video.temporizador.isActive() else self.video.reproducir())
        reiniciar = QPushButton(crear_icono_herramienta('reiniciar'), '')
        reiniciar.setObjectName('guiaControl')
        reiniciar.setFixedSize(36, 36)
        reiniciar.setIconSize(QSize(18, 18))
        reiniciar.setToolTip('Reiniciar video')
        reiniciar.setAccessibleName('Reiniciar video')
        reiniciar.clicked.connect(lambda: self.video.buscar(0))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderPressed.connect(self._iniciar_busqueda)
        self.slider.sliderReleased.connect(self._terminar_busqueda)
        self.tiempo = QLabel('0:00 / 0:00')
        controles.addWidget(self.play)
        controles.addWidget(reiniciar)
        controles.addWidget(self.slider, 1)
        controles.addWidget(self.tiempo)
        layout.addLayout(controles)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)
        self.video.progreso.connect(self._actualizar_progreso)
        self.video.reproduciendo.connect(self._actualizar_estado)
        self.video.fallo.connect(self._mostrar_error)
        self.cambiar_modo(modo)

    def cambiar_modo(self, modo):
        self.modo = 'ortogonal' if modo == 'ortogonal' else 'recto'
        self.botones[self.modo].setChecked(True)
        self.error.hide()
        self.video.cargar(ruta_recurso('Ortogonal.mp4' if self.modo == 'ortogonal' else 'Recto.mp4'))

    def _actualizar_estado(self, activo):
        self.play.setIcon(crear_icono_herramienta('pausa' if activo else 'play'))
        nombre = 'Pausar video' if activo else 'Reproducir video'
        self.play.setToolTip(nombre)
        self.play.setAccessibleName(nombre)

    def _mostrar_error(self, mensaje):
        self.error.setText(mensaje)
        self.error.show()

    def _actualizar_progreso(self, posicion, duracion):
        self.slider.setRange(0, duracion)
        if not self.slider.isSliderDown():
            self.slider.setValue(posicion)
        def reloj(ms):
            return f'{ms // 60000}:{ms // 1000 % 60:02d}'
        self.tiempo.setText(f'{reloj(posicion)} / {reloj(duracion)}')

    def _iniciar_busqueda(self):
        self._reanudar = self.video.temporizador.isActive()
        self.video.pausar()

    def _terminar_busqueda(self):
        self.video.buscar(self.slider.value())
        if getattr(self, '_reanudar', False):
            self.video.reproducir()

    def hideEvent(self, event):
        self.video.cerrar()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.video.cerrar()
        super().closeEvent(event)
