"""Punto de entrada del simulador de flujo de fluidos."""

import os
import sys
import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication, QSplashScreen

from ui.constantes import (
    APP_USER_MODEL_ID,
    ARCHIVO_ICONO,
    ARCHIVO_LOGO_PROPIO,
    ARCHIVOS_ESCUDO,
    EXTENSION_PROYECTO,
    VERSION_APP,
)
from ui.recursos import ruta_recurso
from ui.ventana.principal import MainWindow


def configurar_id_aplicacion_windows():
    """Registra el AppUserModelID en Windows para mostrar logo_1.ico en la barra de tareas."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def _primer_archivo_proyecto(argv):
    """Devuelve la primera ruta válida (.sff o .json) recibida por línea de comandos."""
    for arg in argv[1:]:
        if not arg or arg.startswith("-"):
            continue
        if os.path.isfile(arg) and arg.lower().endswith((EXTENSION_PROYECTO, ".json")):
            return arg
    return None


def cargar_archivo_desde_argumentos(window, argv):
    """Abre un archivo .sff/.json pasado por línea de comandos al iniciar el programa."""
    ruta = _primer_archivo_proyecto(argv)
    if ruta:
        return window.cargar_proyecto(ruta, confirmar_si_hay_contenido=False)
    return False


if __name__ == "__main__":
    configurar_id_aplicacion_windows()
    app = QApplication(sys.argv)
    app.setApplicationName("Simulador de Flujo de Fluidos")
    app.setApplicationVersion(VERSION_APP)
    icono_app = QIcon(ruta_recurso(ARCHIVO_ICONO))
    if not icono_app.isNull():
        app.setWindowIcon(icono_app)

    archivo_inicial = _primer_archivo_proyecto(sys.argv) is not None

    # -------------------------------------------------------------
    # Splash Screen Setup
    # -------------------------------------------------------------
    logos_splash = [] if archivo_inicial else [ARCHIVOS_ESCUDO, (ARCHIVO_LOGO_PROPIO,)]
    splash = None
    
    for nombres_logo in logos_splash:
        pixmap = None
        for img_name in nombres_logo:
            img_path = ruta_recurso(img_name)
            if os.path.exists(img_path):
                pixmap = QPixmap(img_path)
                break
                
        if pixmap and not pixmap.isNull():
            splash_pixmap = QPixmap(600, 400)
            splash_pixmap.fill(Qt.white)
            
            painter = QPainter(splash_pixmap)
            scaled_logo = pixmap.scaled(400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (600 - scaled_logo.width()) // 2
            y = (400 - scaled_logo.height()) // 2
            painter.drawPixmap(x, y, scaled_logo)
            painter.end()
            
            if splash is None:
                splash = QSplashScreen(splash_pixmap, Qt.WindowStaysOnTopHint)
                if not icono_app.isNull():
                    splash.setWindowIcon(icono_app)
                splash.show()
            else:
                splash.setPixmap(splash_pixmap)
                
            app.processEvents()
            time.sleep(2.0)

    window = MainWindow()
    window.show()
    cargar_archivo_desde_argumentos(window, sys.argv)

    if splash:
        splash.finish(window)
        
    sys.exit(app.exec_())
