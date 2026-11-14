"""Módulo de enrutado ortogonal para tuberías y conexiones CAD."""

import math
from PyQt5.QtCore import QPointF


def _a_qpointf(p):
    """Convierte QPointF, QPoint o tupla/lista (x, y) a QPointF."""
    if isinstance(p, QPointF):
        return QPointF(p.x(), p.y())
    if hasattr(p, "x") and hasattr(p, "y"):
        return QPointF(float(p.x()), float(p.y()))
    if isinstance(p, (tuple, list)) and len(p) >= 2:
        return QPointF(float(p[0]), float(p[1]))
    raise TypeError(f"No se puede convertir {p!r} a QPointF.")


def snap_grid(valor, grid=20):
    """Ajusta un valor escalar a la cuadrícula más cercana si grid > 0."""
    if not grid or grid <= 0:
        return float(valor)
    return float(round(float(valor) / grid) * grid)


def snap_punto_grid(punto, grid=20):
    """Ajusta un QPointF a la cuadrícula."""
    pt = _a_qpointf(punto)
    if not grid or grid <= 0:
        return pt
    return QPointF(snap_grid(pt.x(), grid), snap_grid(pt.y(), grid))


def _normalizar_direccion(d):
    """
    Normaliza una especificación de dirección a 'H', 'V' o None.
    Acepta 'H', 'V', 'horizontal', 'vertical', cardinales ('este', 'oeste', 'norte', 'sur'), etc.
    """
    if d is None:
        return None
    s = str(d).strip().upper()
    if s in (
        "H",
        "HORIZONTAL",
        "HORIZ",
        "E",
        "ESTE",
        "EAST",
        "O",
        "OESTE",
        "WEST",
        "R",
        "RIGHT",
        "DERECHA",
        "L",
        "LEFT",
        "IZQUIERDA",
    ):
        return "H"
    if s in (
        "V",
        "VERTICAL",
        "VERT",
        "N",
        "NORTE",
        "NORTH",
        "S",
        "SUR",
        "SOUTH",
        "U",
        "UP",
        "ARRIBA",
        "D",
        "DOWN",
        "ABAJO",
    ):
        return "V"
    return None


def simplificar_puntos_ortogonales(puntos, tol=1e-5):
    """
    Elimina puntos consecutivos duplicados y puntos colineales intermedios
    en una secuencia ortogonal de QPointF.
    """
    if not puntos:
        return []

    # 1. Eliminar duplicados consecutivos
    sin_dups = []
    for p in puntos:
        pt = _a_qpointf(p)
        if not sin_dups:
            sin_dups.append(pt)
        else:
            prev = sin_dups[-1]
            if abs(pt.x() - prev.x()) > tol or abs(pt.y() - prev.y()) > tol:
                sin_dups.append(pt)

    if len(sin_dups) <= 2:
        return sin_dups

    # 2. Eliminar puntos colineales intermedios
    simplificados = [sin_dups[0]]
    for i in range(1, len(sin_dups) - 1):
        A = simplificados[-1]
        B = sin_dups[i]
        C = sin_dups[i + 1]

        # ¿Es B colineal entre A y C horizontalmente?
        es_horiz = abs(A.y() - B.y()) <= tol and abs(B.y() - C.y()) <= tol
        # ¿Es B colineal entre A y C verticalmente?
        es_vert = abs(A.x() - B.x()) <= tol and abs(B.x() - C.x()) <= tol

        if es_horiz or es_vert:
            # B es redundante en la misma recta ortogonal, se descarta
            continue
        simplificados.append(B)

    simplificados.append(sin_dups[-1])
    return simplificados


def ruta_ortogonal(p0, p1, direccion_salida="H", direccion_llegada=None, grid=20):
    """
    Calcula una ruta ortogonal entre p0 y p1 retornando una lista de QPointF.

    Reglas:
    - Usa forma en L por defecto (horizontal-primero si direccion_salida=='H', vertical-primero si 'V').
    - Si las direcciones lo exigen (ambas H o ambas V), usa forma en Z con escalón intermedio
      centrado y ajustado a la cuadrícula.
    - Ajusta vértices intermedios a la cuadrícula si grid > 0.
    - Elimina puntos duplicados y colineales intermedios.
    """
    pt0 = _a_qpointf(p0)
    pt1 = _a_qpointf(p1)

    x0, y0 = pt0.x(), pt0.y()
    x1, y1 = pt1.x(), pt1.y()

    d_sal = _normalizar_direccion(direccion_salida) or "H"
    d_lleg = _normalizar_direccion(direccion_llegada)

    # Si ya están alineados horizontal o verticalmente, ruta directa
    tol = 1e-5
    if abs(x0 - x1) <= tol or abs(y0 - y1) <= tol:
        return simplificar_puntos_ortogonales([pt0, pt1], tol=tol)

    # Caso en Z: si las direcciones lo exigen (ambas H o ambas V)
    if d_sal == "H" and d_lleg == "H":
        # H a H: Salida horizontal, llegada horizontal -> Z con segmento vertical intermedio
        x_mid = snap_grid((x0 + x1) / 2.0, grid)
        if abs(x_mid - x0) <= tol or abs(x_mid - x1) <= tol:
            x_mid = (x0 + x1) / 2.0
        v1 = QPointF(x_mid, y0)
        v2 = QPointF(x_mid, y1)
        puntos_crudos = [pt0, v1, v2, pt1]
    elif d_sal == "V" and d_lleg == "V":
        # V a V: Salida vertical, llegada vertical -> Z con segmento horizontal intermedio
        y_mid = snap_grid((y0 + y1) / 2.0, grid)
        if abs(y_mid - y0) <= tol or abs(y_mid - y1) <= tol:
            y_mid = (y0 + y1) / 2.0
        v1 = QPointF(x0, y_mid)
        v2 = QPointF(x1, y_mid)
        puntos_crudos = [pt0, v1, v2, pt1]
    elif d_sal == "V":
        # Forma en L: Vertical-primero (V -> H)
        v = QPointF(x0, y1)
        puntos_crudos = [pt0, v, pt1]
    else:
        # Forma en L: Horizontal-primero (H -> V) por defecto
        v = QPointF(x1, y0)
        puntos_crudos = [pt0, v, pt1]

    return simplificar_puntos_ortogonales(puntos_crudos, tol=tol)


def ruta_multivertice(puntos, direccion_inicial="H", grid=20):
    """
    Construye una ruta ortogonal completa a través de una lista de puntos
    [origen, v1, v2, ..., destino], concatenando tramos ortogonales y
    eliminando puntos duplicados y colineales.
    """
    if not puntos:
        return []
    if len(puntos) == 1:
        return [_a_qpointf(puntos[0])]

    todos = [_a_qpointf(puntos[0])]
    dir_act = _normalizar_direccion(direccion_inicial) or "H"

    for i in range(len(puntos) - 1):
        pA = todos[-1]
        pB = _a_qpointf(puntos[i + 1])
        sub_ruta = ruta_ortogonal(
            pA, pB, direccion_salida=dir_act, direccion_llegada=None, grid=grid
        )
        if len(sub_ruta) >= 2:
            p_penult = sub_ruta[-2]
            p_ult = sub_ruta[-1]
            if abs(p_ult.x() - p_penult.x()) > 1e-5:
                dir_act = "V"
            else:
                dir_act = "H"
            todos.extend(sub_ruta[1:])
        elif len(sub_ruta) == 1:
            todos.append(sub_ruta[0])

    return simplificar_puntos_ortogonales(todos)


def longitud_polilinea(puntos):
    """Calcula la longitud total acumulada de una secuencia de QPointF."""
    if not puntos or len(puntos) < 2:
        return 0.0
    total = 0.0
    for i in range(len(puntos) - 1):
        dx = puntos[i + 1].x() - puntos[i].x()
        dy = puntos[i + 1].y() - puntos[i].y()
        total += math.hypot(dx, dy)
    return total


def _proyectar_con_indice(punto, puntos_ruta):
    """Proyecta un punto sobre la polilínea y retorna (pt_corte, t, angulo, idx_seg)."""
    pt = _a_qpointf(punto)
    if not puntos_ruta or len(puntos_ruta) < 2:
        return (pt, 0.0, 0.0, 0)

    long_total = longitud_polilinea(puntos_ruta)
    if long_total <= 0.0:
        return (puntos_ruta[0], 0.0, 0.0, 0)

    mejor_dist = float("inf")
    mejor_pt = puntos_ruta[0]
    mejor_dist_acum = 0.0
    mejor_angulo = 0.0
    mejor_idx = 0

    dist_acum = 0.0
    for i in range(len(puntos_ruta) - 1):
        pA = puntos_ruta[i]
        pB = puntos_ruta[i + 1]
        dx = pB.x() - pA.x()
        dy = pB.y() - pA.y()
        l_seg = math.hypot(dx, dy)

        if l_seg > 0:
            u = max(
                0.0,
                min(
                    1.0,
                    ((pt.x() - pA.x()) * dx + (pt.y() - pA.y()) * dy) / (l_seg * l_seg),
                ),
            )
            proj = QPointF(pA.x() + u * dx, pA.y() + u * dy)
            dist_p = math.hypot(pt.x() - proj.x(), pt.y() - proj.y())
            ang_seg = math.degrees(math.atan2(dy, dx))
        else:
            proj = pA
            dist_p = math.hypot(pt.x() - pA.x(), pt.y() - pA.y())
            ang_seg = 0.0
            u = 0.0

        if dist_p < mejor_dist:
            mejor_dist = dist_p
            mejor_pt = proj
            mejor_dist_acum = dist_acum + (u * l_seg)
            mejor_angulo = ang_seg
            mejor_idx = i

        dist_acum += l_seg

    t = max(0.0, min(1.0, mejor_dist_acum / long_total))
    return (mejor_pt, t, mejor_angulo, mejor_idx)


def proyectar_punto_a_polilinea(punto, puntos_ruta):
    """
    Proyecta un punto sobre la polilínea ortogonal dada.
    Retorna (punto_proyectado: QPointF, t: float en [0, 1], angulo: float en grados).
    """
    mejor_pt, t, mejor_angulo, _ = _proyectar_con_indice(punto, puntos_ruta)
    return (mejor_pt, t, mejor_angulo)


def direccion_inicial_polilinea(puntos, tol=1e-5):
    """Determina la orientación inicial ('H' o 'V') del primer tramo de una polilínea."""
    if not puntos or len(puntos) < 2:
        return None
    p0 = _a_qpointf(puntos[0])
    for p in puntos[1:]:
        p1 = _a_qpointf(p)
        dx = abs(p1.x() - p0.x())
        dy = abs(p1.y() - p0.y())
        if dx > tol or dy > tol:
            return "H" if dx >= dy else "V"
    return None


def dividir_polilinea_ortogonal(puntos_ruta, punto):
    """
    Divide una polilínea ortogonal en el punto más cercano sobre sus tramos.
    Retorna (pt_corte, t_corte, angulo_corte, pts_inicio, pts_fin) conservando
    todos los quiebres ortogonales a ambos lados del corte.
    """
    pts = [_a_qpointf(p) for p in (puntos_ruta or [])]
    pt = _a_qpointf(punto)
    if len(pts) < 2:
        return (pt, 0.5, 0.0, [pt, pt], [pt, pt])

    pt_corte, t_corte, angulo, idx = _proyectar_con_indice(pt, pts)
    pts1 = simplificar_puntos_ortogonales(pts[: idx + 1] + [pt_corte])
    pts2 = simplificar_puntos_ortogonales([pt_corte] + pts[idx + 1 :])

    if len(pts1) < 2:
        pts1 = [pts[0], pt_corte]
    if len(pts2) < 2:
        pts2 = [pt_corte, pts[-1]]
    return (pt_corte, t_corte, angulo, pts1, pts2)


def recombinar_polilineas_ortogonales(pts1, pts2):
    """
    Une dos polilíneas ortogonales contiguas (pts1 terminando en el nodo puente
    y pts2 comenzando en él) y simplifica únicamente el punto de empalme si es colineal.
    """
    seq1 = [_a_qpointf(p) for p in (pts1 or [])]
    seq2 = [_a_qpointf(p) for p in (pts2 or [])]
    if not seq1:
        return simplificar_puntos_ortogonales(seq2)
    if not seq2:
        return simplificar_puntos_ortogonales(seq1)
    return simplificar_puntos_ortogonales(seq1 + seq2[1:])


def punto_en_longitud_arco(t, puntos_ruta):
    """
    Retorna el punto y el ángulo tangencial sobre la polilínea para un parámetro t en [0, 1].
    Retorna (punto: QPointF, angulo: float en grados).
    """
    if not puntos_ruta:
        return (QPointF(0, 0), 0.0)
    if len(puntos_ruta) == 1:
        return (puntos_ruta[0], 0.0)

    long_total = longitud_polilinea(puntos_ruta)
    if long_total <= 0.0:
        return (puntos_ruta[0], 0.0)

    t_clamped = max(0.0, min(1.0, float(t)))
    target_s = t_clamped * long_total

    dist_acum = 0.0
    for i in range(len(puntos_ruta) - 1):
        pA = puntos_ruta[i]
        pB = puntos_ruta[i + 1]
        dx = pB.x() - pA.x()
        dy = pB.y() - pA.y()
        l_seg = math.hypot(dx, dy)

        if dist_acum + l_seg >= target_s or i == len(puntos_ruta) - 2:
            rem = target_s - dist_acum
            u = rem / l_seg if l_seg > 0 else 0.0
            u = max(0.0, min(1.0, u))
            pt = QPointF(pA.x() + u * dx, pA.y() + u * dy)
            ang = math.degrees(math.atan2(dy, dx))
            return (pt, ang)

        dist_acum += l_seg

    return (puntos_ruta[-1], 0.0)

