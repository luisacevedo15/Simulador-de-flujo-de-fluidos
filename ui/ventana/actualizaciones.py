"""Integración de búsqueda y descarga de actualizaciones en la ventana principal."""

import os
import sys
import tempfile

from PyQt5.QtCore import QThread, QUrl, Qt
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QApplication, QMessageBox, QProgressDialog

from ui.actualizador import (
    TrabajadorConsultaActualizacion,
    TrabajadorDescargaActualizacion,
    lanzar_actualizacion_silenciosa,
)
from ui.constantes import REPOSITORIO_GITHUB, VERSION_APP


class ActualizacionesMixin:
    """Gestiona la consulta de nuevas versiones y la actualización del instalador."""

    def _inicializar_actualizaciones(self):
        self._actualizacion_disponible = None
        self._hilo_consulta_act = None
        self._trabajador_consulta_act = None
        self._hilo_descarga_act = None
        self._trabajador_descarga_act = None
        self._dialogo_descarga_act = None
        self._verificacion_manual_act = False

    def _iniciar_verificacion_actualizaciones_silenciosa(self):
        self._iniciar_consulta_actualizacion(manual=False)

    def _on_buscar_actualizaciones_clicked(self):
        info = getattr(self, "_actualizacion_disponible", None)
        if info is not None:
            self._preguntar_e_instalar_actualizacion(info)
            return
        self._iniciar_consulta_actualizacion(manual=True)

    def _iniciar_consulta_actualizacion(self, manual=False):
        if getattr(self, "_hilo_consulta_act", None) is not None:
            return

        self._verificacion_manual_act = bool(manual)
        btn = getattr(self, "btn_buscar_actualizacion", None)
        if manual and btn is not None:
            btn.setEnabled(False)
            btn.setText("Buscando...")

        hilo = QThread(self)
        trabajador = TrabajadorConsultaActualizacion(
            repositorio=REPOSITORIO_GITHUB,
            version_actual=VERSION_APP,
        )
        trabajador.moveToThread(hilo)
        hilo.started.connect(trabajador.ejecutar)
        trabajador.finalizado.connect(self._on_resultado_actualizacion)
        trabajador.finalizado.connect(hilo.quit)
        hilo.finished.connect(trabajador.deleteLater)
        hilo.finished.connect(hilo.deleteLater)
        hilo.finished.connect(self._limpiar_hilo_consulta_actualizacion)

        self._hilo_consulta_act = hilo
        self._trabajador_consulta_act = trabajador
        hilo.start()

    def _limpiar_hilo_consulta_actualizacion(self):
        self._hilo_consulta_act = None
        self._trabajador_consulta_act = None

    def _on_resultado_actualizacion(self, info, error):
        manual = getattr(self, "_verificacion_manual_act", False)
        btn = getattr(self, "btn_buscar_actualizacion", None)

        if info is not None:
            self._actualizacion_disponible = info
            if btn is not None:
                btn.setEnabled(True)
                btn.setText(f"Actualizar a v{info.version_remota}")
                btn.setToolTip(
                    f"Nueva versión v{info.version_remota} disponible en GitHub Releases"
                )
                btn.setProperty("updateAvailable", "true")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
            if manual:
                self._preguntar_e_instalar_actualizacion(info)
            return

        if btn is not None:
            btn.setEnabled(True)
            btn.setText("Buscar actualizaciones")
            btn.setProperty("updateAvailable", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if not manual:
            return

        if error:
            QMessageBox.warning(
                self,
                "Actualizaciones",
                f"No se pudo comprobar si hay actualizaciones.\n\nDetalle: {error}",
            )
            return

        QMessageBox.information(
            self,
            "Actualizaciones",
            f"Ya estás usando la versión más reciente (v{VERSION_APP}).",
        )

    def _preguntar_e_instalar_actualizacion(self, info):
        tamano_txt = (
            f" ({info.tamano_bytes / (1024 * 1024):.1f} MB)"
            if info.tamano_bytes > 0
            else ""
        )
        notas = info.notas[:500] + ("..." if len(info.notas) > 500 else "")
        mensaje = (
            f"Hay una nueva versión disponible: v{info.version_remota}{tamano_txt}.\n"
            f"Versión instalada actualmente: v{VERSION_APP}."
        )
        if notas:
            mensaje += f"\n\nNovedades:\n{notas}"

        if not getattr(sys, "frozen", False):
            mensaje += (
                "\n\nEstás ejecutando el simulador desde código fuente Python. "
                "¿Deseas abrir la página de descargas en GitHub?"
            )
            resp = QMessageBox.question(
                self,
                "Actualización disponible",
                mensaje,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if resp == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(info.url_release))
            return

        mensaje += (
            "\n\nEl instalador se descargará y actualizará el programa automáticamente "
            "sin perder tus proyectos guardados. ¿Deseas actualizar ahora?"
        )
        resp = QMessageBox.question(
            self,
            "Actualización disponible",
            mensaje,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if resp == QMessageBox.Yes:
            self._descargar_y_aplicar_actualizacion(info)

    def _descargar_y_aplicar_actualizacion(self, info):
        if getattr(self, "_hilo_descarga_act", None) is not None:
            return

        destino = os.path.join(tempfile.gettempdir(), info.nombre_asset)
        dialogo = QProgressDialog(
            f"Descargando {info.nombre_asset}...",
            "Cancelar",
            0,
            100,
            self,
        )
        dialogo.setWindowTitle("Descargando actualización")
        dialogo.setWindowModality(Qt.WindowModal)
        dialogo.setMinimumDuration(0)
        dialogo.setValue(0)

        hilo = QThread(self)
        trabajador = TrabajadorDescargaActualizacion(info.url_descarga, destino)
        trabajador.moveToThread(hilo)

        dialogo.canceled.connect(trabajador.cancelar)
        hilo.started.connect(trabajador.ejecutar)
        trabajador.progreso.connect(self._on_progreso_descarga_actualizacion)
        trabajador.completado.connect(self._on_descarga_actualizacion_completa)
        trabajador.fallido.connect(self._on_descarga_actualizacion_fallida)
        trabajador.completado.connect(hilo.quit)
        trabajador.fallido.connect(hilo.quit)
        hilo.finished.connect(trabajador.deleteLater)
        hilo.finished.connect(hilo.deleteLater)
        hilo.finished.connect(self._limpiar_hilo_descarga_actualizacion)

        self._dialogo_descarga_act = dialogo
        self._hilo_descarga_act = hilo
        self._trabajador_descarga_act = trabajador
        dialogo.show()
        hilo.start()

    def _limpiar_hilo_descarga_actualizacion(self):
        self._hilo_descarga_act = None
        self._trabajador_descarga_act = None

    def _on_progreso_descarga_actualizacion(self, recibido, total):
        dialogo = getattr(self, "_dialogo_descarga_act", None)
        if dialogo is None:
            return
        if total > 0:
            dialogo.setRange(0, 100)
            dialogo.setValue(min(99, int(recibido * 100 / total)))
        else:
            dialogo.setRange(0, 0)

    def _on_descarga_actualizacion_completa(self, ruta_instalador):
        dialogo = getattr(self, "_dialogo_descarga_act", None)
        if dialogo is not None:
            dialogo.close()
            self._dialogo_descarga_act = None

        try:
            ruta_app = sys.executable if getattr(sys, "frozen", False) else None
            lanzar_actualizacion_silenciosa(ruta_instalador, ruta_app)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Actualización",
                f"Se descargó el instalador en:\n{ruta_instalador}\n\n"
                f"Pero no pudo iniciarse automáticamente ({exc}). Ejecútalo manualmente.",
            )
            return

        QApplication.instance().quit()

    def _on_descarga_actualizacion_fallida(self, detalle):
        dialogo = getattr(self, "_dialogo_descarga_act", None)
        if dialogo is not None:
            dialogo.close()
            self._dialogo_descarga_act = None
        if "cancelada" in str(detalle).lower():
            return
        QMessageBox.warning(
            self,
            "Error de descarga",
            f"No se pudo descargar la actualización.\n\nDetalle: {detalle}",
        )

    def _detener_hilos_actualizacion(self):
        trabajador = getattr(self, "_trabajador_descarga_act", None)
        if trabajador is not None:
            trabajador.cancelar()
        for attr in ("_hilo_consulta_act", "_hilo_descarga_act"):
            hilo = getattr(self, attr, None)
            if hilo is not None and hilo.isRunning():
                hilo.quit()
                hilo.wait(1000)
