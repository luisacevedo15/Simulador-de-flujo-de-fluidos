"""Acceso a archivos del proyecto (logos, íconos) compatible con PyInstaller."""

import os
import sys

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QImage, QPixmap


def ruta_recurso(nombre):
    """Obtiene la ruta absoluta al recurso, compatible con PyInstaller (.exe)"""
    try:
        # PyInstaller crea una carpeta temporal y guarda la ruta en sys._MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Este archivo está en ui/: la raíz del proyecto (donde están los logos) es la
        # carpeta padre de ui/.
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, nombre)


def _recortar_margen_vacio(imagen, umbral_blanco=245, relleno=3):
    ancho, alto = imagen.width(), imagen.height()
    factor = min(1.0, 256.0 / max(ancho, alto))
    muestra = imagen.scaled(
        max(1, int(ancho * factor)), max(1, int(alto * factor)),
        Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
    )
    x_min, y_min, x_max, y_max = muestra.width(), muestra.height(), -1, -1
    for y in range(muestra.height()):
        for x in range(muestra.width()):
            c = muestra.pixelColor(x, y)
            if c.alpha() > 16 and min(c.red(), c.green(), c.blue()) < umbral_blanco:
                x_min, x_max = min(x_min, x), max(x_max, x)
                y_min, y_max = min(y_min, y), max(y_min, y)
    if x_max < 0:
        return imagen
    caja = QRect(
        int(x_min / factor) - relleno,
        int(y_min / factor) - relleno,
        int((x_max - x_min + 1) / factor) + 2 * relleno,
        int((y_max - y_min + 1) / factor) + 2 * relleno,
    )
    return imagen.copy(caja.intersected(imagen.rect()))


def cargar_logo(nombres, alto_px):
    if isinstance(nombres, str):
        nombres = (nombres,)
    for nombre in nombres:
        imagen = QImage(ruta_recurso(nombre))
        if imagen.isNull():
            continue
        es_opaco = not imagen.hasAlphaChannel()
        imagen = imagen.convertToFormat(QImage.Format_ARGB32)
        imagen = _recortar_margen_vacio(imagen)
        imagen = imagen.scaledToHeight(alto_px * 2, Qt.SmoothTransformation)
        return QPixmap.fromImage(imagen), es_opaco
    return None, False
