"""Pruebas unitarias e integración UI para redes multi-nudo en árbol (Caso 2)
y redes mixtas serie-paralelo generalizadas con nudos (Caso 3).
"""

import io
import os

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from motor import MotorFluidos
from ui.graficos import AccesorioGrafico, NodoUnionGrafico, TanqueGrafico, TuberiaGrafica
from ui.ventana.principal import MainWindow


@pytest.fixture
def ventana():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    app.processEvents()
    yield w
    try:
        w.canvas_view.scene().selectionChanged.disconnect()
    except Exception:
        pass
    w.close()
    w.deleteLater()
    app.processEvents()


def _tanque(scene, x, y, tid, z):
    t = TanqueGrafico(x, y, id_tanque=tid)
    t.elevacion_z = z
    t.abierto_atmosfera = True
    scene.addItem(t)
    return t


def _union(scene, x, y, uid):
    u = NodoUnionGrafico(x, y, id_union=uid)
    scene.addItem(u)
    return u


def _tubo(scene, origen, destino, tid, L=100.0, D=0.20, Q=0.0, eps=0.00015, nombre=None):
    tub = TuberiaGrafica(origen, destino, id_tuberia=tid)
    if nombre:
        tub.nombre = nombre
    tub.longitud = L
    tub.diametro = D
    tub.caudal_Q = Q
    tub.rugosidad = eps
    scene.addItem(tub)
    return tub


def _verificar_excel_exportable(w):
    assert w.datos_exportacion, "Se esperaba datos_exportacion poblados"
    bio = io.BytesIO()
    w._escribir_libro_excel(bio)
    assert len(bio.getvalue()) > 500


# ==============================================================================
# 1. PRUEBAS DEL MOTOR HIDRÁULICO (SI PURO)
# ==============================================================================


def test_motor_multinudo_cascada_y_equivalencia_doble_nudo():
    # A) Equivalencia exacta con resolver_doble_nudo (2 nudos internos, 4 tanques)
    tramos_j = [
        {"tuberia": "t1", "id_nudo": "J", "H": 40.0, "L": 100.0, "D": 0.25, "eps": 0.00015, "K": 0.5, "LeD": 0.0},
        {"tuberia": "t2", "id_nudo": "J", "H": 30.0, "L": 120.0, "D": 0.20, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
    ]
    tramos_k = [
        {"tuberia": "t4", "id_nudo": "K", "H": 12.0, "L": 110.0, "D": 0.15, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
        {"tuberia": "t5", "id_nudo": "K", "H": 5.0, "L": 130.0, "D": 0.12, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
    ]
    central = {"tuberia": "tc", "L": 80.0, "D": 0.22, "eps": 0.00015, "K": 0.2, "LeD": 0.0}
    res_dn = MotorFluidos.resolver_doble_nudo(tramos_j, central, tramos_k, 1000.0, 0.001)
    res_dn.verificar()
    Hj_ref, Hk_ref, _, _ = res_dn

    terminales_dn = {"T1": 40.0, "T2": 30.0, "T4": 12.0, "T5": 5.0}
    tramos_mn = [
        {"origen": "T1", "destino": "J", **tramos_j[0]},
        {"origen": "T2", "destino": "J", **tramos_j[1]},
        {"origen": "J", "destino": "K", **central},
        {"origen": "K", "destino": "T4", **tramos_k[0]},
        {"origen": "K", "destino": "T5", **tramos_k[1]},
    ]
    res_mn = MotorFluidos.resolver_red_ramificada_multinudo(["J", "K"], terminales_dn, tramos_mn, 1000.0, 0.001)
    res_mn.verificar()
    H_mn, _ = res_mn
    assert H_mn["J"] == pytest.approx(Hj_ref, rel=1e-7, abs=1e-6)
    assert H_mn["K"] == pytest.approx(Hk_ref, rel=1e-7, abs=1e-6)

    # B) Cascada de 4 nudos internos en Y/árbol con segmentos compuestos
    terminales_4 = {"T1": 60.0, "T2": 48.0, "T3": 28.0, "T4": 18.0, "T5": 10.0, "T6": 4.0}
    tramos_4 = [
        {"origen": "T1", "destino": "J1", "segmentos": [
            {"L": 50.0, "D": 0.30, "eps": 0.00015, "K": 0.5, "LeD": 0.0},
            {"L": 60.0, "D": 0.25, "eps": 0.00015, "K": 1.2, "LeD": 0.0},
        ]},
        {"origen": "T2", "destino": "J1", "L": 90.0, "D": 0.20, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
        {"origen": "J1", "destino": "J2", "L": 70.0, "D": 0.25, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
        {"origen": "J2", "destino": "T3", "L": 100.0, "D": 0.15, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
        {"origen": "J2", "destino": "J3", "L": 80.0, "D": 0.22, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
        {"origen": "J3", "destino": "T4", "L": 120.0, "D": 0.15, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
        {"origen": "J3", "destino": "J4", "L": 65.0, "D": 0.18, "eps": 0.00015, "K": 0.3, "LeD": 0.0},
        {"origen": "J4", "destino": "T5", "L": 90.0, "D": 0.12, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
        {"origen": "J4", "destino": "T6", "L": 110.0, "D": 0.12, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
    ]
    res_4 = MotorFluidos.resolver_red_ramificada_multinudo(
        ["J1", "J2", "J3", "J4"], terminales_4, tramos_4, 1000.0, 0.001
    )
    res_4.verificar()
    H_4, resultados_4 = res_4
    assert H_4["J1"] > H_4["J2"] > H_4["J3"] > H_4["J4"]
    assert res_4.residuo_masa_relativo <= 1e-8
    assert res_4.residuo_energia_relativo <= 1e-8
    assert len(resultados_4) == len(tramos_4)


def test_motor_paralelo_serie_anidado_energia_y_caudal():
    # T1 -> J1 -> (ramal superior [J1->JA->J2] || ramal inferior [J1->J2]) -> J3 -> T2
    sp = {
        "tipo": "serie",
        "origen": "T1",
        "destino": "T2",
        "hijos": [
            {"tipo": "tramo", "origen": "T1", "destino": "J1", "L": 40.0, "D": 0.25, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
            {
                "tipo": "paralelo",
                "origen": "J1",
                "destino": "J2",
                "ramas": [
                    {
                        "tipo": "serie",
                        "origen": "J1",
                        "destino": "J2",
                        "hijos": [
                            {"tipo": "tramo", "origen": "J1", "destino": "JA", "L": 50.0, "D": 0.15, "eps": 0.00015, "K": 0.5, "LeD": 0.0},
                            {"tipo": "tramo", "origen": "JA", "destino": "J2", "L": 60.0, "D": 0.14, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
                        ],
                    },
                    {"tipo": "tramo", "origen": "J1", "destino": "J2", "L": 120.0, "D": 0.16, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
                ],
            },
            {"tipo": "tramo", "origen": "J2", "destino": "T2", "L": 70.0, "D": 0.22, "eps": 0.00015, "K": 0.0, "LeD": 0.0},
        ],
    }

    r_en = MotorFluidos.resolver_paralelo_serie(sp, 1000.0, 0.001, H_disponible=25.0, H_inicio=35.0)
    r_en.verificar()
    Q_en, hf_en, tramos_en, H_nodos_en = r_en
    assert hf_en == pytest.approx(25.0, rel=1e-8)
    assert Q_en > 0.0
    assert set(H_nodos_en) == {"J1", "JA", "J2"}
    assert 35.0 > H_nodos_en["J1"] > H_nodos_en["JA"] > H_nodos_en["J2"] > 10.0

    # Conservación exacta en el paralelo: Q_JA + Q_inferior == Q_en
    q_ja = next(r["Q"] for r in tramos_en if r["origen"] == "JA")
    q_inf = next(r["Q"] for r in tramos_en if r["origen"] == "J1" and r["destino"] == "J2")
    assert q_ja + q_inf == pytest.approx(Q_en, rel=1e-8)

    # Ida y vuelta por caudal impuesto
    r_q = MotorFluidos.resolver_paralelo_serie(sp, 1000.0, 0.001, Q_total=Q_en, H_inicio=35.0)
    r_q.verificar()
    assert r_q[1] == pytest.approx(25.0, rel=1e-8)


# ==============================================================================
# 2. PRUEBAS UI — CASO 2: REDES RAMIFICADAS CON MÚLTIPLES NUDOS + SERIE
# ==============================================================================


@pytest.mark.parametrize("modo_ortogonal", [False, True])
def test_ui_caso2_cascada_tres_nudos_ramificados_y_trazado(ventana, modo_ortogonal):
    w = ventana
    w._preparar_escena_ejemplo()
    w.combo_trazado_global.setCurrentIndex(1 if modo_ortogonal else 0)
    scene = w.canvas_view.scene()

    # 3 nudos ramificados en cascada J1 -- J2 -- J3 conectados a 5 reservorios
    t1 = _tanque(scene, 60, 120, 1, 50.0)
    t2 = _tanque(scene, 60, 320, 2, 35.0)
    j1 = _union(scene, 240, 220, 1)
    t3 = _tanque(scene, 420, 80, 3, 25.0)
    j2 = _union(scene, 420, 220, 2)
    j3 = _union(scene, 600, 220, 3)
    t4 = _tanque(scene, 780, 120, 4, 15.0)
    t5 = _tanque(scene, 780, 320, 5, 8.0)

    # Algunos tramos dibujados en sentido inverso para verificar independencia de dirección
    tubs = [
        _tubo(scene, t1, j1, 1, L=100.0, D=0.25),
        _tubo(scene, t2, j1, 2, L=120.0, D=0.20),
        _tubo(scene, j2, j1, 3, L=90.0, D=0.25),   # Invertida j2 -> j1
        _tubo(scene, j2, t3, 4, L=100.0, D=0.15),
        _tubo(scene, j2, j3, 5, L=80.0, D=0.20),
        _tubo(scene, t4, j3, 6, L=110.0, D=0.15),  # Invertida t4 -> j3
        _tubo(scene, j3, t5, 7, L=130.0, D=0.12),
    ]

    w._refrescar_combos_dashboard()
    assert w.combo_uniones.count() == 1
    assert "multi-nudo" in w.combo_uniones.currentText().lower()

    QTest.mouseClick(w.boton_ramificado, Qt.LeftButton)

    assert j1.hj_calculada is not None
    assert j2.hj_calculada is not None
    assert j3.hj_calculada is not None
    assert j1.hj_calculada > j2.hj_calculada > j3.hj_calculada

    # Todos los tramos deben quedar resueltos con caudal y flechas de flujo válidas
    for tub in tubs:
        assert tub.caudal_Q > 0
        assert tub.hf_calculado > 0
        assert tub.sentido_flujo_calculado in (1, -1)

    # El tramo troncal dibujado invertido (j2 -> j1) fluye realmente de j1 a j2 -> signo -1
    assert tubs[2].sentido_flujo_calculado == -1
    # El tramo j3 -> t4 dibujado invertido (t4 -> j3) fluye de j3 a t4 -> signo -1
    assert tubs[5].sentido_flujo_calculado == -1

    # Verificar continuidad en todos los nodos usando signos de flujo reales
    for j_node in (j1, j2, j3):
        balance = 0.0
        for t in j_node.tuberias:
            q_si = w._a_si(t.caudal_Q, t.u_Q)
            # Flujo real de origen a destino según sentido_flujo_calculado:
            sale_de_j = (
                (t.nodo_origen is j_node and t.sentido_flujo_calculado == 1)
                or (t.nodo_destino is j_node and t.sentido_flujo_calculado == -1)
            )
            balance += q_si if sale_de_j else -q_si
        assert abs(balance) <= 1e-8

    assert w.datos_exportacion["tipo_sistema"] == "Sistema Ramificado (Multi-Nudo)"
    assert len(w.egl_chart.series) >= 2
    _verificar_excel_exportable(w)


def test_ui_caso2_doble_nudo_con_nudo_serie_y_accesorio(ventana):
    w = ventana
    w._preparar_escena_ejemplo()
    scene = w.canvas_view.scene()

    # T1 -- J_serie(deg 2) -- J1 -- Acc -- J2 -- T3, T4, y T2 -- J1
    t1 = _tanque(scene, 40, 120, 1, 45.0)
    j_ser = _union(scene, 140, 120, 9)
    t2 = _tanque(scene, 40, 320, 2, 32.0)
    j1 = _union(scene, 260, 220, 1)
    acc = AccesorioGrafico(360, 205, forma_visual="Válvula", tipo_perdida="K", valor=2.5)
    scene.addItem(acc)
    j2 = _union(scene, 480, 220, 2)
    t3 = _tanque(scene, 680, 120, 3, 18.0)
    t4 = _tanque(scene, 680, 320, 4, 10.0)

    _tubo(scene, t1, j_ser, 1, L=50.0, D=0.25)
    _tubo(scene, j_ser, j1, 2, L=60.0, D=0.22)
    _tubo(scene, t2, j1, 3, L=100.0, D=0.20)
    _tubo(scene, j1, acc, 4, L=45.0, D=0.22)
    _tubo(scene, acc, j2, 5, L=45.0, D=0.22)
    _tubo(scene, j2, t3, 6, L=110.0, D=0.15)
    _tubo(scene, j2, t4, 7, L=120.0, D=0.15)

    w._refrescar_combos_dashboard()
    assert w.combo_uniones.count() == 1
    assert "multi-nudo" in w.combo_uniones.currentText().lower()

    QTest.mouseClick(w.boton_ramificado, Qt.LeftButton)

    assert j1.hj_calculada is not None
    assert j2.hj_calculada is not None
    assert j_ser.hj_calculada is not None
    assert t1.elevacion_z > j_ser.hj_calculada > j1.hj_calculada > j2.hj_calculada
    _verificar_excel_exportable(w)


def test_ui_caso2_un_nudo_ramificado_y_un_nudo_serie(ventana):
    w = ventana
    w._preparar_escena_ejemplo()
    scene = w.canvas_view.scene()

    t1 = _tanque(scene, 40, 200, 1, 40.0)
    j_ser = _union(scene, 180, 200, 9)
    j1 = _union(scene, 360, 200, 1)
    t2 = _tanque(scene, 600, 100, 2, 18.0)
    t3 = _tanque(scene, 600, 300, 3, 10.0)

    _tubo(scene, t1, j_ser, 1, L=60.0, D=0.25)
    _tubo(scene, j_ser, j1, 2, L=80.0, D=0.20)
    _tubo(scene, j1, t2, 3, L=100.0, D=0.15)
    _tubo(scene, j1, t3, 4, L=120.0, D=0.15)

    w._refrescar_combos_dashboard()
    assert w.combo_uniones.count() == 1
    QTest.mouseClick(w.boton_ramificado, Qt.LeftButton)

    assert j1.hj_calculada is not None
    assert 40.0 > j1.hj_calculada > 10.0
    _verificar_excel_exportable(w)


def test_ui_caso2_red_con_ciclo_multitanque_rechaza_limpiamente(ventana):
    w = ventana
    w._preparar_escena_ejemplo()
    scene = w.canvas_view.scene()

    t1 = _tanque(scene, 60, 200, 1, 40.0)
    j1 = _union(scene, 240, 200, 1)
    j2 = _union(scene, 440, 200, 2)
    t2 = _tanque(scene, 640, 120, 2, 15.0)
    t3 = _tanque(scene, 640, 280, 3, 10.0)

    _tubo(scene, t1, j1, 1, L=80.0, D=0.25)
    _tubo(scene, j1, j2, 2, L=100.0, D=0.15)
    _tubo(scene, j1, j2, 3, L=120.0, D=0.15)  # Ciclo en paralelo en red de 3 tanques
    _tubo(scene, j2, t2, 4, L=90.0, D=0.15)
    _tubo(scene, j2, t3, 5, L=90.0, D=0.15)

    analisis = w._analizar_componente_multinudo(j1)
    assert not analisis["valida"]
    assert analisis["motivo"] == "ciclo"


# ==============================================================================
# 3. PRUEBAS UI — CASO 3: PARALELO + SERIE CON NUDOS (BERNOULLI ENTRE 2 TANQUES)
# ==============================================================================


def test_ui_caso3_paralelo_entre_nudos_con_cambio_auto_a_recto_y_energia(ventana):
    w = ventana
    w._preparar_escena_ejemplo()
    w.combo_trazado_global.setCurrentIndex(1)  # Iniciar en Ortogonal
    scene = w.canvas_view.scene()

    t1 = _tanque(scene, 60, 200, 1, 35.0)
    j1 = _union(scene, 240, 200, 1)
    j2 = _union(scene, 460, 200, 2)
    t2 = _tanque(scene, 660, 200, 2, 10.0)

    # Cadena principal en ortogonal: T1 -> J1 -> J2 -> T2
    t_in = _tubo(scene, t1, j1, 1, L=50.0, D=0.25)
    t_p1 = _tubo(scene, j1, j2, 2, L=120.0, D=0.15)
    t_out = _tubo(scene, j2, t2, 3, L=60.0, D=0.22)
    for t_prev in (t_in, t_p1, t_out):
        t_prev.modo_trazado = "ortogonal"

    # Añadir 2da tubería paralela J1 -> J2 mediante clic en lienzo (activa cambio automático a Recto)
    w.resize(1200, 800)
    w.canvas_view.centerOn(350, 200)
    QApplication.processEvents()
    scene.modo_conexion = True
    p_j1 = w.canvas_view.mapFromScene(j1.sceneBoundingRect().center())
    p_j2 = w.canvas_view.mapFromScene(j2.sceneBoundingRect().center())
    QTest.mouseClick(w.canvas_view.viewport(), Qt.LeftButton, pos=p_j1)
    QTest.mouseClick(w.canvas_view.viewport(), Qt.LeftButton, pos=p_j2)
    QApplication.processEvents()

    assert w.combo_trazado_global.currentIndex() == 0  # Cambió a Recto automáticamente
    assert w.canvas_view.hud_notificacion_frame.isVisible()
    assert t_p1.modo_trazado == "recto"

    t_p2 = next(
        item for item in scene.items()
        if isinstance(item, TuberiaGrafica) and item not in (t_in, t_p1, t_out)
    )
    assert t_p2.modo_trazado == "recto"
    t_p2.longitud = 150.0
    t_p2.diametro = 0.12
    t_p2.rugosidad = 0.00015

    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)
    w.combo_punto2.setCurrentIndex(1)

    # Sin Q ingresado: resuelve automáticamente por energía disponible H1 - H2 = 25 m
    QTest.mouseClick(w.boton_bernoulli, Qt.LeftButton)

    assert j1.hj_calculada is not None
    assert j2.hj_calculada is not None
    assert 35.0 > j1.hj_calculada > j2.hj_calculada > 10.0

    q_in = w._a_si(t_in.caudal_Q, t_in.u_Q)
    q_out = w._a_si(t_out.caudal_Q, t_out.u_Q)
    q_p1 = w._a_si(t_p1.caudal_Q, t_p1.u_Q)
    q_p2 = w._a_si(t_p2.caudal_Q, t_p2.u_Q)
    assert q_in == pytest.approx(q_out, rel=1e-8)
    assert q_p1 + q_p2 == pytest.approx(q_in, rel=1e-8)

    # Pérdida idéntica en ambas ramas paralelas
    assert t_p1.hf_calculado == pytest.approx(t_p2.hf_calculado, rel=1e-7)
    assert t_in.hf_calculado + t_p1.hf_calculado + t_out.hf_calculado == pytest.approx(25.0, rel=1e-7)

    for tub in (t_in, t_p1, t_p2, t_out):
        assert tub.sentido_flujo_calculado == 1

    assert len(w.egl_chart.series) == 2
    assert w.datos_exportacion["tipo_sistema"] == "Sistema Mixto (Paralelo-Serie)"
    _verificar_excel_exportable(w)


def test_ui_caso3_paralelo_y_dos_tramos_serie_con_caudal_impuesto(ventana):
    w = ventana
    w._preparar_escena_ejemplo()
    scene = w.canvas_view.scene()

    # T1 <==> J1 --> J2 --> T2 con tramo J2->T2 dibujado invertido y Q = 0.08 m³/s impuesto en serie
    t1 = _tanque(scene, 60, 200, 1, 30.0)
    j1 = _union(scene, 280, 200, 1)
    j2 = _union(scene, 480, 200, 2)
    t2 = _tanque(scene, 680, 200, 2, 10.0)

    r_a = _tubo(scene, t1, j1, 1, L=100.0, D=0.16)
    r_b = _tubo(scene, j1, t1, 2, L=140.0, D=0.14)      # Dibujada al revés j1 -> t1
    s1 = _tubo(scene, j1, j2, 3, L=60.0, D=0.22, Q=0.08)
    s2 = _tubo(scene, t2, j2, 4, L=80.0, D=0.22)        # Dibujada al revés t2 -> j2

    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)
    w.combo_punto2.setCurrentIndex(1)
    QTest.mouseClick(w.boton_bernoulli, Qt.LeftButton)

    assert w._a_si(s1.caudal_Q, s1.u_Q) == pytest.approx(0.08, rel=1e-8)
    assert w._a_si(s2.caudal_Q, s2.u_Q) == pytest.approx(0.08, rel=1e-8)
    assert w._a_si(r_a.caudal_Q, r_a.u_Q) + w._a_si(r_b.caudal_Q, r_b.u_Q) == pytest.approx(0.08, rel=1e-8)
    assert r_a.hf_calculado == pytest.approx(r_b.hf_calculado, rel=1e-7)
    assert r_a.sentido_flujo_calculado == 1
    assert r_b.sentido_flujo_calculado == -1
    assert s1.sentido_flujo_calculado == 1
    assert s2.sentido_flujo_calculado == -1
    assert j1.hj_calculada is not None and j2.hj_calculada is not None
    assert j1.hj_calculada < 30.0
    assert j2.hj_calculada == pytest.approx(j1.hj_calculada - s1.hf_calculado, rel=1e-7)
    _verificar_excel_exportable(w)


def test_ui_caso3_paralelo_con_rama_compuesta_accesorio(ventana):
    w = ventana
    w._preparar_escena_ejemplo()
    scene = w.canvas_view.scene()

    # T1 -> J1 (ramal directo + ramal con Accesorio en serie) -> T2 (desbalanceado len 2 vs 3)
    t1 = _tanque(scene, 60, 200, 1, 32.0)
    acc = AccesorioGrafico(190, 280, forma_visual="Válvula", tipo_perdida="K", valor=1.5)
    scene.addItem(acc)
    j1 = _union(scene, 340, 200, 1)
    t2 = _tanque(scene, 620, 200, 2, 12.0)

    r_directo = _tubo(scene, t1, j1, 1, L=120.0, D=0.16)
    r_sub1 = _tubo(scene, t1, acc, 2, L=70.0, D=0.15)
    r_sub2 = _tubo(scene, acc, j1, 3, L=60.0, D=0.14)
    s_out = _tubo(scene, j1, t2, 4, L=90.0, D=0.22)

    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)
    w.combo_punto2.setCurrentIndex(1)
    QTest.mouseClick(w.boton_bernoulli, Qt.LeftButton)

    q_out = w._a_si(s_out.caudal_Q, s_out.u_Q)
    q_dir = w._a_si(r_directo.caudal_Q, r_directo.u_Q)
    q_s1 = w._a_si(r_sub1.caudal_Q, r_sub1.u_Q)
    q_s2 = w._a_si(r_sub2.caudal_Q, r_sub2.u_Q)
    assert q_s1 == pytest.approx(q_s2, rel=1e-8)
    assert q_dir + q_s1 == pytest.approx(q_out, rel=1e-8)
    assert r_directo.hf_calculado == pytest.approx(r_sub1.hf_calculado + r_sub2.hf_calculado, rel=1e-7)
    assert j1.hj_calculada is not None
    assert 32.0 > j1.hj_calculada > 12.0
    _verificar_excel_exportable(w)


def test_ui_caso3_puente_cruzado_no_descomponible_informa_claramente(ventana):
    w = ventana
    w._preparar_escena_ejemplo()
    scene = w.canvas_view.scene()

    # Puente de Wheatstone T1-J1-J2-T2 con T1-J2 y J1-T2 (no descomponible en serie-paralelo)
    t1 = _tanque(scene, 60, 200, 1, 30.0)
    j1 = _union(scene, 260, 120, 1)
    j2 = _union(scene, 260, 280, 2)
    t2 = _tanque(scene, 500, 200, 2, 10.0)

    _tubo(scene, t1, j1, 1, L=50.0, D=0.2)
    _tubo(scene, t1, j2, 2, L=60.0, D=0.2)
    _tubo(scene, j1, j2, 3, L=40.0, D=0.15)
    _tubo(scene, j1, t2, 4, L=70.0, D=0.2)
    _tubo(scene, j2, t2, 5, L=80.0, D=0.2)

    w._refrescar_combos_dashboard()
    w.combo_punto1.setCurrentIndex(0)
    w.combo_punto2.setCurrentIndex(1)
    QTest.mouseClick(w.boton_bernoulli, Qt.LeftButton)

    assert "no descomponibles" in w.texto_resultados.toPlainText().lower()
