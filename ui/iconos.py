"""Dibujo de los íconos de las herramientas del lienzo."""

from PyQt5 import QtGui
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def crear_icono_herramienta(tipo, color_hex="#0c4e77"):
    """Genera iconos vectoriales limpios estilo Stitch usando QPainter sin depender de imágenes externas."""
    pm = QPixmap(24, 24)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex)
    pen = QPen(c, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)

    if tipo == "play":
        p.setBrush(c)
        p.drawPolygon(QPolygonF([QPointF(8, 5), QPointF(19, 12), QPointF(8, 19)]))
    elif tipo == "pausa":
        p.setBrush(c)
        p.drawRoundedRect(6, 5, 4, 14, 1, 1)
        p.drawRoundedRect(14, 5, 4, 14, 1, 1)
    elif tipo == "reiniciar":
        p.drawArc(QRectF(5, 5, 14, 14), 140 * 16, -300 * 16)
        p.drawLine(5, 4, 5, 10)
        p.drawLine(5, 10, 11, 10)
    elif tipo == "simulador_header":
        # Icono precision_manufacturing de Stitch (brazo industrial de precisión)
        p.drawLine(3, 20, 21, 20)
        p.drawRoundedRect(5, 16, 6, 4, 1, 1)
        p.drawLine(8, 16, 12, 7)
        p.setBrush(c)
        p.drawEllipse(QPointF(12, 7), 2.0, 2.0)
        p.setBrush(Qt.NoBrush)
        p.drawLine(12, 7, 18, 10)
        p.drawLine(18, 8, 20, 9)
        p.drawLine(17, 12, 19, 13)
    elif tipo == "tanque":
        # Icono propane_tank de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawLine(9, 3, 15, 3)
        p.drawLine(10, 3, 10, 6)
        p.drawLine(14, 3, 14, 6)
        p.drawRoundedRect(5, 6, 14, 14, 3, 3)
        p.drawLine(5, 11, 19, 11)
        p.drawLine(5, 15, 19, 15)
    elif tipo == "union":
        # Icono adjust de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(12, 12), 7.5, 7.5)
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(12, 12), 3.0, 3.0)
    elif tipo == "conectar":
        # Icono hub de Stitch
        p.drawLine(12, 12, 6, 6)
        p.drawLine(12, 12, 18, 6)
        p.drawLine(12, 12, 6, 18)
        p.drawLine(12, 12, 18, 18)
        p.setBrush(c)
        p.drawEllipse(QPointF(12, 12), 2.6, 2.6)
        p.setBrush(QColor("#ffffff"))
        for pt in (QPointF(6, 6), QPointF(18, 6), QPointF(6, 18), QPointF(18, 18)):
            p.drawEllipse(pt, 2.2, 2.2)
    elif tipo == "accesorio":
        # Icono valve de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawLine(7, 5, 17, 5)
        p.drawLine(12, 5, 12, 11)
        p.drawLine(4, 11, 20, 11)
        p.drawLine(4, 17, 20, 17)
        p.drawLine(7, 9, 7, 19)
        p.drawLine(17, 9, 17, 19)
        p.drawRect(9, 11, 6, 6)
    elif tipo == "bomba":
        # Icono de bomba centrífuga estilo Stitch (carcasa circular, descarga tangencial con brida, triángulo de rodete y cubo central)
        cx, cy = 11.5, 13.0
        r = 6.8
        p.setBrush(Qt.NoBrush)
        # 1. Carcasa / voluta circular
        p.drawEllipse(QPointF(cx, cy), r, r)
        # 2. Descarga tangencial superior derecha con brida
        p.drawRect(QRectF(cx + 1.5, 3.5, 4.0, 4.5))
        p.drawLine(QPointF(cx, 3.5), QPointF(cx + 7.0, 3.5))
        # 3. Base de apoyo (skid pad) inferior
        p.drawLine(QPointF(cx - 5.5, cy + r + 1.5), QPointF(cx + 5.5, cy + r + 1.5))
        # 4. Triángulo impulsor apuntando en sentido del flujo
        poly_imp = QPolygonF([
            QPointF(cx - 3.8, cy - 3.5),
            QPointF(cx - 3.8, cy + 3.5),
            QPointF(cx + 4.5, cy),
        ])
        p.setBrush(c)
        p.drawPolygon(poly_imp)
        # 5. Eje / cubo central blanco
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(cx, cy), 1.5, 1.5)

    elif tipo in ("linea", "flecha", "flecha_doble", "ruta_recta"):
        p.drawLine(4, 12, 20, 12)
        if tipo in ("flecha", "flecha_doble"):
            p.drawLine(15, 7, 20, 12)
            p.drawLine(15, 17, 20, 12)
        if tipo == "flecha_doble":
            p.drawLine(9, 7, 4, 12)
            p.drawLine(9, 17, 4, 12)
        if tipo == "ruta_recta":
            p.drawEllipse(QPointF(4, 12), 2, 2)
            p.drawEllipse(QPointF(20, 12), 2, 2)
    elif tipo == "ruta_ortogonal":
        p.drawLine(4, 6, 12, 6)
        p.drawLine(12, 6, 12, 18)
        p.drawLine(12, 18, 20, 18)
        p.drawEllipse(QPointF(4, 6), 2, 2)
        p.drawEllipse(QPointF(20, 18), 2, 2)
    elif tipo == "formas":
        p.drawLine(4, 18, 19, 5)
        p.drawLine(19, 5, 13, 5)
        p.drawLine(19, 5, 19, 11)
    elif tipo == "eliminar":
        pen_eliminar = QPen(c, 1.9, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen_eliminar)
        p.drawLine(5, 7, 19, 7)
        p.drawLine(9, 7, 9, 4)
        p.drawLine(15, 7, 15, 4)
        p.drawLine(9, 4, 15, 4)
        p.drawRect(7, 7, 10, 13)
        p.drawLine(10, 10, 10, 17)
        p.drawLine(14, 10, 14, 17)
    elif tipo == "fluido":
        # Icono science (matraz Erlenmeyer) de Stitch
        path = QPainterPath()
        path.moveTo(9, 4)
        path.lineTo(15, 4)
        path.moveTo(10.5, 4)
        path.lineTo(10.5, 9)
        path.lineTo(5.5, 18.5)
        path.lineTo(18.5, 18.5)
        path.lineTo(13.5, 9)
        path.lineTo(13.5, 4)
        p.setPen(QPen(c, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.drawLine(8, 14, 16, 14)
    elif tipo == "guardar":
        p.setBrush(Qt.NoBrush)
        poly = QPolygonF([
            QPointF(5, 4), QPointF(16, 4), QPointF(20, 8), QPointF(20, 20), QPointF(5, 20)
        ])
        p.drawPolygon(poly)
        p.drawRect(8, 4, 7, 5)
        p.drawRect(8, 13, 8, 7)
    elif tipo == "cargar":
        p.setBrush(Qt.NoBrush)
        poly = QPolygonF([
            QPointF(3, 6), QPointF(9, 6), QPointF(11, 8), QPointF(21, 8), QPointF(21, 19), QPointF(3, 19)
        ])
        p.drawPolygon(poly)
    elif tipo == "excel":
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(5, 3, 14, 18, 2, 2)
        p.drawLine(8, 9, 16, 9)
        p.drawLine(8, 13, 16, 13)
        p.drawLine(8, 17, 13, 17)
    elif tipo == "cad":
        # Icono view_in_ar de Stitch (cubo isométrico dentro de 4 escuadras)
        p.setBrush(Qt.NoBrush)
        # Escuadras exteriores
        p.drawLine(3, 7, 3, 3); p.drawLine(3, 3, 7, 3)
        p.drawLine(17, 3, 21, 3); p.drawLine(21, 3, 21, 7)
        p.drawLine(3, 17, 3, 21); p.drawLine(3, 21, 7, 21)
        p.drawLine(17, 21, 21, 21); p.drawLine(21, 21, 21, 17)
        # Cubo central
        hex_poly = QPolygonF([
            QPointF(12, 6.5), QPointF(17, 9.3), QPointF(17, 14.7),
            QPointF(12, 17.5), QPointF(7, 14.7), QPointF(7, 9.3)
        ])
        p.drawPolygon(hex_poly)
        p.drawLine(QPointF(7, 9.3), QPointF(12, 12))
        p.drawLine(QPointF(17, 9.3), QPointF(12, 12))
        p.drawLine(QPointF(12, 12), QPointF(12, 17.5))
    elif tipo == "tabla":
        # Icono table_chart de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(4, 4, 16, 16, 2, 2)
        p.drawLine(4, 9, 20, 9)
        p.drawLine(9, 9, 9, 20)
        p.drawLine(15, 9, 15, 20)
    elif tipo == "texto":
        p.setBrush(Qt.NoBrush)
        p.drawLine(5, 5, 19, 5)
        p.drawLine(5, 5, 5, 8)
        p.drawLine(19, 5, 19, 8)
        p.drawLine(12, 5, 12, 19)
        p.drawLine(9, 19, 15, 19)
    elif tipo == "curvas":
        # Icono show_chart de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawLine(3, 17, 9, 11)
        p.drawLine(9, 11, 13, 15)
        p.drawLine(13, 15, 21, 7)
        p.setBrush(c)
        for pt in (QPointF(3, 17), QPointF(9, 11), QPointF(13, 15), QPointF(21, 7)):
            p.drawEllipse(pt, 1.8, 1.8)
    elif tipo == "rama_simple":
        # Icono alt_route de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawLine(12, 20, 12, 12)
        p.drawLine(12, 12, 7, 6)
        p.drawLine(12, 12, 17, 6)
        p.drawLine(7, 6, 7, 9)
        p.drawLine(7, 6, 10, 6)
        p.drawLine(17, 6, 17, 9)
        p.drawLine(17, 6, 14, 6)
    elif tipo == "rama_red":
        # Icono device_hub de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawLine(12, 6, 12, 12)
        p.drawLine(12, 12, 6, 18)
        p.drawLine(12, 12, 18, 18)
        p.setBrush(c)
        p.drawEllipse(QPointF(12, 6), 2.3, 2.3)
        p.drawEllipse(QPointF(6, 18), 2.3, 2.3)
        p.drawEllipse(QPointF(18, 18), 2.3, 2.3)
    elif tipo == "flecha_atras":
        # Icono arrow_back de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawLine(19, 12, 5, 12)
        p.drawLine(5, 12, 11, 6)
        p.drawLine(5, 12, 11, 18)
    elif tipo == "curvas_vacio":
        # Icono de ejes y curva del estado vacío de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawLine(4, 4, 4, 20)
        p.drawLine(4, 20, 20, 20)
        p.drawLine(7, 15, 10, 12)
        p.drawLine(10, 12, 14, 16)
        p.drawLine(14, 16, 19, 9)
    elif tipo == "copiar":
        # Icono content_copy de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(8, 8, 11, 12, 2, 2)
        path_c = QPainterPath()
        path_c.moveTo(5, 16)
        path_c.lineTo(5, 5)
        path_c.lineTo(16, 5)
        p.drawPath(path_c)
    elif tipo in ("descargar", "exportar"):
        # Icono download / export de Stitch
        p.setBrush(Qt.NoBrush)
        p.drawLine(12, 4, 12, 14)
        p.drawLine(8, 10, 12, 14)
        p.drawLine(16, 10, 12, 14)
        p.drawLine(5, 18, 19, 18)
    elif tipo == "tabla_vacio":
        # Icono hoja de cálculo / documento del estado vacío
        p.setBrush(Qt.NoBrush)
        poly = QPolygonF([QPointF(6, 3), QPointF(14, 3), QPointF(18, 7), QPointF(18, 21), QPointF(6, 21)])
        p.drawPolygon(poly)
        p.drawLine(14, 3, 14, 7); p.drawLine(14, 7, 18, 7)
        p.drawLine(9, 11, 15, 11)
        p.drawLine(9, 14, 15, 14)
        p.drawLine(9, 17, 13, 17)
    elif tipo == "trazo_solido":
        p.setPen(QPen(c, 2.8, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(2.5, 12.0), QPointF(21.5, 12.0))
    elif tipo == "trazo_discontinuo":
        p.setPen(QPen(c, 2.8, Qt.DashLine, Qt.RoundCap))
        p.drawLine(QPointF(2.5, 12.0), QPointF(21.5, 12.0))
    elif tipo == "github":
        # Logo oficial de GitHub (Octocat en círculo recortado)
        outer = QPainterPath()
        outer.addEllipse(QPointF(12.0, 12.0), 9.6, 9.6)

        cat = QPainterPath()
        # Cabeza + orejas puntiagudas + torso inferior
        cat.moveTo(9.8, 21.8)
        cat.lineTo(9.8, 17.6)
        # Cola hacia la izquierda
        cat.cubicTo(7.2, 18.2, 6.5, 16.5, 6.0, 15.6)
        cat.cubicTo(5.6, 14.9, 5.0, 14.5, 4.6, 14.4)
        cat.cubicTo(4.3, 14.2, 4.5, 13.8, 5.1, 13.9)
        cat.cubicTo(5.9, 14.1, 6.5, 14.8, 6.9, 15.5)
        cat.cubicTo(7.6, 16.6, 8.8, 16.3, 9.9, 15.9)
        cat.cubicTo(10.0, 15.1, 10.4, 14.5, 10.9, 14.2)
        # Mejilla izquierda -> oreja izquierda
        cat.cubicTo(7.9, 13.8, 6.2, 12.6, 6.2, 9.8)
        cat.cubicTo(6.2, 8.7, 6.6, 7.8, 7.3, 7.0)
        cat.cubicTo(7.0, 6.1, 7.0, 4.9, 7.5, 4.1)
        cat.cubicTo(8.4, 4.1, 9.4, 4.7, 10.1, 5.3)
        cat.cubicTo(11.3, 5.0, 12.7, 5.0, 13.9, 5.3)
        # Oreja derecha -> mejilla derecha
        cat.cubicTo(14.6, 4.7, 15.6, 4.1, 16.5, 4.1)
        cat.cubicTo(17.0, 4.9, 17.0, 6.1, 16.7, 7.0)
        cat.cubicTo(17.4, 7.8, 17.8, 8.7, 17.8, 9.8)
        cat.cubicTo(17.8, 12.6, 16.1, 13.8, 13.1, 14.2)
        cat.cubicTo(13.7, 14.7, 14.2, 15.5, 14.2, 16.8)
        cat.lineTo(14.2, 21.8)
        cat.closeSubpath()

        logo_path = outer.subtracted(cat)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawPath(logo_path)
    elif tipo == "reportar_error":
        # Icono de reporte de bug / incidencia técnica
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(c, 1.85, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        # Cabeza y antenas
        p.drawArc(QRectF(9.0, 4.2, 6.0, 5.0), 0, 180 * 16)
        p.drawLine(QPointF(9.5, 5.2), QPointF(7.6, 3.5))
        p.drawLine(QPointF(14.5, 5.2), QPointF(16.4, 3.5))
        # Cuerpo ovalado del bug
        p.drawRoundedRect(QRectF(7.5, 7.2, 9.0, 11.5), 4.5, 4.5)
        p.drawLine(QPointF(12.0, 10.2), QPointF(12.0, 18.2))
        p.drawLine(QPointF(7.8, 10.2), QPointF(16.2, 10.2))
        # Patas laterales
        for y_pata in (9.5, 13.0, 16.3):
            p.drawLine(QPointF(4.3, y_pata), QPointF(7.4, y_pata))
            p.drawLine(QPointF(16.6, y_pata), QPointF(19.7, y_pata))
    elif tipo == "imagen":
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(3.5, 5.0, 17.0, 14.0), 2.5, 2.5)
        p.drawEllipse(QPointF(8.5, 9.5), 1.6, 1.6)
        ruta_montana = QPainterPath()
        ruta_montana.moveTo(4.5, 17.5)
        ruta_montana.lineTo(9.5, 12.8)
        ruta_montana.lineTo(13.0, 15.8)
        ruta_montana.lineTo(16.0, 12.2)
        ruta_montana.lineTo(19.5, 17.5)
        p.drawPath(ruta_montana)

    p.end()
    return QtGui.QIcon(pm)
