"""Reproducción real de los clips y ciclo de vida de la guía del botón ?."""

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QSignalSpy, QTest

from test_grafico_bombas_ui import app
from test_interfaz_regresiones import ventana
from ui.guia_trazado import VideoDemostracion
from ui.recursos import ruta_recurso


@pytest.mark.parametrize('archivo', ['Recto.mp4', 'Ortogonal.mp4'])
def test_decodifica_pausa_busca_repite_y_libera_video(app, archivo):
    video = VideoDemostracion()
    try:
        video.cargar(ruta_recurso(archivo))
        assert not video.ultimo_error and not video.imagen.isNull()
        assert video.imagen.width() == 1280 and video.imagen.height() == 720
        assert video.duracion > 2000 and video.temporizador.isActive()
        QTest.qWait(120)
        assert video.posicion > 0
        video.pausar()
        posicion = video.posicion
        QTest.qWait(100)
        assert video.posicion == posicion
        destino = video.duracion // 2
        video.buscar(destino)
        assert destino <= video.posicion <= destino + 40
        video.buscar(video.duracion - 80)
        for _ in range(5):
            video.avanzar()
        assert video.posicion < 200  # El final vuelve al inicio.
        video.bucle = False
        video.buscar(video.duracion - 80)
        video.reproducir()
        for _ in range(5):
            video.avanzar()
        assert not video.temporizador.isActive()
    finally:
        video.cerrar()
    assert video.contenedor is None and not video.temporizador.isActive()


def test_boton_abre_modo_actual_sin_modificar_proyecto_y_cierra_reproductor(ventana):
    w = ventana
    w.combo_trazado_global.setCurrentText('Trazado: Ortogonal')
    antes = w._serializar_proyecto()
    QTest.mouseClick(w.btn_ayuda_trazado, Qt.LeftButton)
    guia = w._guia_trazado
    assert guia.modo == 'ortogonal' and guia.isVisible()
    w.mostrar_ayuda_trazado()
    assert w._guia_trazado is guia
    QTest.mouseClick(guia.botones['recto'], Qt.LeftButton)
    assert guia.modo == 'recto' and not guia.video.imagen.isNull()
    assert w._serializar_proyecto() == antes
    guia.video.pausar()
    guia.slider.setValue(1000)
    guia._terminar_busqueda()
    assert 1000 <= guia.video.posicion <= 1040
    reproductor = guia.video
    guia.close()
    assert reproductor.contenedor is None and not reproductor.temporizador.isActive()
    assert w._guia_trazado is None


def test_video_ausente_no_cierra_la_aplicacion(app, tmp_path):
    video = VideoDemostracion()
    errores = QSignalSpy(video.fallo)
    video.cargar(str(tmp_path / 'no-existe.mp4'))
    assert len(errores) == 1
    assert video.ultimo_error and video.contenedor is None
    assert not video.temporizador.isActive()
