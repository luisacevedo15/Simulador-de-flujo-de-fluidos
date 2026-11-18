"""Integración de auto-actualización silenciosa con verificación SHA256 en la ventana principal."""

from PyQt5.QtCore import QThread, QTimer
from PyQt5.QtWidgets import QApplication

from ui.actualizador import (
    LOGGER,
    TrabajadorAutoActualizacion,
    es_paquete_microsoft_store,
    lanzar_actualizacion_silenciosa,
)
from ui.constantes import REPOSITORIO_GITHUB, VERSION_APP


class ActualizacionesMixin:
    """Gestiona la consulta, descarga verificada por SHA256 y actualización silenciosa."""

    def _inicializar_actualizaciones(self):
        self._actualizacion_disponible = None
        self._hilo_consulta_act = None
        self._trabajador_consulta_act = None
        self._hilo_descarga_act = None
        self._trabajador_descarga_act = None
        self._dialogo_descarga_act = None
        self._verificacion_manual_act = False

    def _iniciar_verificacion_actualizaciones_silenciosa(self):
        """Punto de entrada automático al abrir la app y para el botón manual."""
        self._iniciar_actualizacion_automatica()

    def _on_buscar_actualizaciones_clicked(self):
        """El botón manual 'Buscar actualizaciones' invoca la misma función automática."""
        self._iniciar_actualizacion_automatica()

    def _iniciar_consulta_actualizacion(self, manual=False):
        self._verificacion_manual_act = bool(manual)
        self._iniciar_actualizacion_automatica()

    def _iniciar_actualizacion_automatica(self):
        if es_paquete_microsoft_store():
            return
        if getattr(self, "_hilo_consulta_act", None) is not None:
            return

        btn = getattr(self, "btn_buscar_actualizacion", None)
        if btn is not None:
            btn.setText("Buscar actualizaciones")

        hilo = QThread(self)
        trabajador = TrabajadorAutoActualizacion(
            repositorio=REPOSITORIO_GITHUB,
            version_actual=VERSION_APP,
        )
        trabajador.moveToThread(hilo)
        hilo.started.connect(trabajador.ejecutar)
        trabajador.actualizacion_lista.connect(self._on_actualizacion_lista_para_instalar)
        trabajador.sin_actualizacion.connect(self._on_sin_actualizacion_disponible)
        trabajador.fallo_silencioso.connect(self._on_fallo_actualizacion_silencioso)

        trabajador.actualizacion_lista.connect(hilo.quit)
        trabajador.sin_actualizacion.connect(hilo.quit)
        trabajador.fallo_silencioso.connect(hilo.quit)
        hilo.finished.connect(trabajador.deleteLater)
        hilo.finished.connect(hilo.deleteLater)
        hilo.finished.connect(self._limpiar_hilo_consulta_actualizacion)

        self._hilo_consulta_act = hilo
        self._trabajador_consulta_act = trabajador
        hilo.start()

    def _limpiar_hilo_consulta_actualizacion(self):
        self._hilo_consulta_act = None
        self._trabajador_consulta_act = None

    def _mostrar_aviso_discreto_actualizacion(self, texto):
        """Muestra un aviso discreto no bloqueante en el lienzo y barra de estado."""
        canvas = getattr(self, "canvas_view", None)
        if canvas is not None and hasattr(canvas, "mostrar_notificacion"):
            canvas.mostrar_notificacion(texto, duracion_ms=8000)
        status = getattr(self, "status_bar", None)
        if status is not None:
            status.showMessage(f"  {texto}", 8000)
        btn = getattr(self, "btn_buscar_actualizacion", None)
        if btn is not None:
            btn.setText(texto)
            btn.setProperty("updateAvailable", "true")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_actualizacion_lista_para_instalar(self, info, ruta_instalador):
        self._actualizacion_disponible = info
        aviso = f"Actualizando a v{info.version_remota}…"
        self._mostrar_aviso_discreto_actualizacion(aviso)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

        try:
            lanzar_actualizacion_silenciosa(ruta_instalador)
        except Exception as exc:
            LOGGER.error("No se pudo lanzar el instalador silencioso: %s", exc)
            self._restablecer_boton_actualizacion()
            return

        if app is not None:
            QTimer.singleShot(250, app.quit)

    def _on_sin_actualizacion_disponible(self):
        self._restablecer_boton_actualizacion()

    def _on_fallo_actualizacion_silencioso(self, detalle):
        LOGGER.warning("Fallo silencioso registrado en UI de actualizaciones: %s", detalle)
        self._restablecer_boton_actualizacion()

    def _restablecer_boton_actualizacion(self):
        btn = getattr(self, "btn_buscar_actualizacion", None)
        if btn is not None:
            btn.setEnabled(True)
            btn.setText("Buscar actualizaciones")
            btn.setProperty("updateAvailable", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_resultado_actualizacion(self, info, error):
        """Compatibilidad con pruebas de estado del botón y manejo silencioso de errores."""
        if error or info is None:
            if error:
                LOGGER.warning("Error de actualización ignorado silenciosamente: %s", error)
            self._restablecer_boton_actualizacion()
            return

        self._actualizacion_disponible = info
        self._mostrar_aviso_discreto_actualizacion(f"Actualizando a v{info.version_remota}…")

    def _detener_hilos_actualizacion(self):
        for attr in ("_trabajador_consulta_act", "_trabajador_descarga_act"):
            trabajador = getattr(self, attr, None)
            if trabajador is not None and hasattr(trabajador, "cancelar"):
                trabajador.cancelar()
        for attr in ("_hilo_consulta_act", "_hilo_descarga_act"):
            hilo = getattr(self, attr, None)
            if hilo is not None and hilo.isRunning():
                hilo.quit()
                hilo.wait(1000)
