"""Diálogo y envío automático de reportes de error con descripción y foto adjunta."""

import base64
import json
import mimetypes
import os
import platform
import urllib.error
import urllib.request
import uuid

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QObject, QSize, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.constantes import CORREO_SOPORTE, URL_WEBHOOK_REPORTE, VERSION_APP
from ui.iconos import crear_icono_herramienta


MAX_DIMENSION_IMAGEN = 1600


def _normalizar_imagen_bytes(ruta_imagen=None, bytes_imagen=None, nombre_imagen=None):
    """Carga y comprime razonablemente una imagen a PNG/JPEG para envío rápido."""
    if bytes_imagen is None and not ruta_imagen:
        return None, None, None

    if bytes_imagen is not None:
        raw = bytes(bytes_imagen)
        nombre = nombre_imagen or "captura_error.png"
    else:
        with open(ruta_imagen, "rb") as f:
            raw = f.read()
        nombre = nombre_imagen or os.path.basename(ruta_imagen) or "captura_error.png"

    img = QImage.fromData(raw)
    if not img.isNull():
        if img.width() > MAX_DIMENSION_IMAGEN or img.height() > MAX_DIMENSION_IMAGEN:
            img = img.scaled(
                MAX_DIMENSION_IMAGEN,
                MAX_DIMENSION_IMAGEN,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        ext = os.path.splitext(nombre)[1].lower()
        formato = "JPEG" if ext in (".jpg", ".jpeg") else "PNG"
        mime = "image/jpeg" if formato == "JPEG" else "image/png"
        if ext not in (".jpg", ".jpeg", ".png"):
            nombre = os.path.splitext(nombre)[0] + ".png"
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, formato, 85 if formato == "JPEG" else -1)
        buf.close()
        raw = bytes(ba)
    else:
        mime = mimetypes.guess_type(nombre)[0] or "application/octet-stream"

    return raw, nombre, mime


def _construir_multipart(campos, archivos):
    """Construye un cuerpo multipart/form-data estándar sin dependencias externas."""
    limite = f"----SimuladorFluidosBoundary{uuid.uuid4().hex}"
    partes = []
    for clave, valor in campos.items():
        partes.append(f"--{limite}\r\n".encode("utf-8"))
        partes.append(
            f'Content-Disposition: form-data; name="{clave}"\r\n\r\n{valor}\r\n'.encode("utf-8")
        )
    for campo_archivo, nombre_archivo, mime, contenido in archivos:
        partes.append(f"--{limite}\r\n".encode("utf-8"))
        partes.append(
            (
                f'Content-Disposition: form-data; name="{campo_archivo}"; '
                f'filename="{nombre_archivo}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode("utf-8")
        )
        partes.append(contenido)
        partes.append(b"\r\n")
    partes.append(f"--{limite}--\r\n".encode("utf-8"))
    return b"".join(partes), f"multipart/form-data; boundary={limite}"


def enviar_reporte_error(
    descripcion,
    *,
    ruta_imagen=None,
    bytes_imagen=None,
    nombre_imagen=None,
    contacto="",
    destinatario=CORREO_SOPORTE,
    url_webhook=None,
    version_app=VERSION_APP,
    timeout=20.0,
    urlopen=None,
):
    """Envía automáticamente el reporte de error y la foto adjunta al correo de soporte."""
    texto_desc = str(descripcion or "").strip()
    if not texto_desc:
        raise ValueError("Escribe una descripción del error antes de enviar el reporte.")

    texto_contacto = str(contacto or "").strip()
    raw_img, nom_img, mime_img = _normalizar_imagen_bytes(
        ruta_imagen=ruta_imagen,
        bytes_imagen=bytes_imagen,
        nombre_imagen=nombre_imagen,
    )
    sistema_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
    asunto = f"[Simulador de Fluidos v{version_app}] Reporte de error"

    webhook = (
        url_webhook
        if url_webhook is not None
        else (os.environ.get("SIMULADOR_WEBHOOK_REPORTE", "").strip() or URL_WEBHOOK_REPORTE.strip())
    )
    lector = urlopen or urllib.request.urlopen

    if webhook:
        payload = {
            "destinatario": destinatario,
            "asunto": asunto,
            "descripcion": texto_desc,
            "contacto": texto_contacto or "No especificado",
            "version": str(version_app),
            "plataforma": sistema_info,
            "nombre_imagen": nom_img or "",
            "mime_imagen": mime_img or "",
            "imagen_base64": base64.b64encode(raw_img).decode("ascii") if raw_img else "",
        }
        cuerpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=cuerpo,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                "User-Agent": f"SimuladorFlujoDeFluidos/{version_app}",
            },
            method="POST",
        )
        with lector(req, timeout=timeout) as resp:
            texto_resp = resp.read().decode("utf-8", errors="replace").strip()
        if texto_resp:
            try:
                datos = json.loads(texto_resp)
                if isinstance(datos, dict) and datos.get("ok") is False:
                    raise RuntimeError(str(datos.get("error") or "El servidor rechazó el reporte."))
            except json.JSONDecodeError:
                pass
        return True

    # Canal automático directo hacia el correo del autor (multipart si hay foto, JSON AJAX si solo texto)
    campos = {
        "_subject": asunto,
        "_template": "table",
        "_captcha": "false",
        "Version": f"v{version_app}",
        "Sistema": sistema_info,
        "Contacto": texto_contacto or "No especificado",
        "Descripcion": texto_desc,
    }
    if raw_img:
        cuerpo_mp, content_type = _construir_multipart(
            campos,
            [("attachment", nom_img, mime_img, raw_img)],
        )
        url_destino = f"https://formsubmit.co/{destinatario}"
        req = urllib.request.Request(
            url_destino,
            data=cuerpo_mp,
            headers={
                "Content-Type": content_type,
                "User-Agent": f"SimuladorFlujoDeFluidos/{version_app}",
                "Referer": "https://github.com/luisacevedo15/Simulador-de-flujo-de-fluidos",
            },
            method="POST",
        )
        with lector(req, timeout=timeout) as resp:
            resp.read()
        return True

    url_ajax = f"https://formsubmit.co/ajax/{destinatario}"
    cuerpo_json = json.dumps(campos, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url_ajax,
        data=cuerpo_json,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "User-Agent": f"SimuladorFlujoDeFluidos/{version_app}",
            "Referer": "https://github.com/luisacevedo15/Simulador-de-flujo-de-fluidos",
        },
        method="POST",
    )
    with lector(req, timeout=timeout) as resp:
        resp.read()
    return True


class TrabajadorEnvioReporte(QObject):
    """Envía el reporte en segundo plano sin bloquear la interfaz."""

    completado = pyqtSignal()
    fallido = pyqtSignal(str)

    def __init__(
        self,
        descripcion,
        *,
        bytes_imagen=None,
        nombre_imagen=None,
        contacto="",
        destinatario=CORREO_SOPORTE,
    ):
        super().__init__()
        self._descripcion = descripcion
        self._bytes_imagen = bytes_imagen
        self._nombre_imagen = nombre_imagen
        self._contacto = contacto
        self._destinatario = destinatario

    def ejecutar(self):
        try:
            enviar_reporte_error(
                self._descripcion,
                bytes_imagen=self._bytes_imagen,
                nombre_imagen=self._nombre_imagen,
                contacto=self._contacto,
                destinatario=self._destinatario,
            )
            self.completado.emit()
        except urllib.error.URLError as exc:
            self.fallido.emit(f"No se pudo conectar para enviar el reporte: {exc.reason}")
        except Exception as exc:
            self.fallido.emit(str(exc))


class BandejaFotoWidget(QFrame):
    """Bandeja interactiva para subir, pegar, arrastrar o capturar una foto del error."""

    imagen_cambiada = pyqtSignal()

    def __init__(self, parent=None, ventana_captura=None):
        super().__init__(parent)
        self.setObjectName("bandejaFotoFrame")
        self.setAcceptDrops(True)
        self._ventana_captura = ventana_captura
        self._bytes_imagen = None
        self._nombre_imagen = None
        self._pixmap_actual = QPixmap()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        fila_sup = QHBoxLayout()
        fila_sup.setSpacing(10)

        self.lbl_preview = QLabel()
        self.lbl_preview.setFixedSize(72, 54)
        self.lbl_preview.setAlignment(Qt.AlignCenter)
        self.lbl_preview.setStyleSheet(
            "background-color: #ffffff; border: 1px dashed #94a3b8; border-radius: 8px;"
        )
        fila_sup.addWidget(self.lbl_preview)

        col_info = QVBoxLayout()
        col_info.setSpacing(3)
        self.lbl_estado_foto = QLabel("Sin foto adjunta (puedes arrastrar una imagen aquí)")
        self.lbl_estado_foto.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 12px; "
            "font-weight: 600; color: #1e293b; background: transparent;"
        )
        self.lbl_estado_foto.setWordWrap(True)
        col_info.addWidget(self.lbl_estado_foto)

        self.lbl_sub_foto = QLabel("Formatos admitidos: PNG, JPG, BMP, WEBP o captura directa.")
        self.lbl_sub_foto.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11px; "
            "color: #64748b; background: transparent;"
        )
        self.lbl_sub_foto.setWordWrap(True)
        col_info.addWidget(self.lbl_sub_foto)
        fila_sup.addLayout(col_info, 1)
        layout.addLayout(fila_sup)

        fila_btns = QHBoxLayout()
        fila_btns.setSpacing(8)

        self.btn_subir_foto = QPushButton(
            crear_icono_herramienta("imagen", "#0c4e77"), " Subir foto..."
        )
        self.btn_subir_foto.setIconSize(QSize(15, 15))
        self.btn_subir_foto.setCursor(Qt.PointingHandCursor)
        self.btn_subir_foto.setFixedHeight(32)
        self.btn_subir_foto.setMinimumWidth(118)
        self.btn_subir_foto.clicked.connect(self.seleccionar_archivo)
        fila_btns.addWidget(self.btn_subir_foto)

        self.btn_capturar_ventana = QPushButton("Capturar simulador")
        self.btn_capturar_ventana.setCursor(Qt.PointingHandCursor)
        self.btn_capturar_ventana.setFixedHeight(32)
        self.btn_capturar_ventana.setMinimumWidth(138)
        self.btn_capturar_ventana.setToolTip("Toma una foto automática de la ventana actual del simulador")
        self.btn_capturar_ventana.clicked.connect(self.capturar_ventana_simulador)
        fila_btns.addWidget(self.btn_capturar_ventana)

        self.btn_pegar_foto = QPushButton("Pegar captura")
        self.btn_pegar_foto.setCursor(Qt.PointingHandCursor)
        self.btn_pegar_foto.setFixedHeight(32)
        self.btn_pegar_foto.setMinimumWidth(112)
        self.btn_pegar_foto.clicked.connect(self.pegar_desde_portapapeles)
        fila_btns.addWidget(self.btn_pegar_foto)

        self.btn_quitar_foto = QPushButton("Quitar")
        self.btn_quitar_foto.setCursor(Qt.PointingHandCursor)
        self.btn_quitar_foto.setFixedHeight(32)
        self.btn_quitar_foto.setMinimumWidth(68)
        self.btn_quitar_foto.clicked.connect(self.limpiar_imagen)
        self.btn_quitar_foto.hide()
        fila_btns.addWidget(self.btn_quitar_foto)

        fila_btns.addStretch()
        layout.addLayout(fila_btns)
        self._actualizar_vista_previa()

    @property
    def bytes_imagen(self):
        return self._bytes_imagen

    @property
    def nombre_imagen(self):
        return self._nombre_imagen

    def tiene_imagen(self):
        return bool(self._bytes_imagen)

    def establecer_pixmap(self, pixmap, nombre="captura_simulador.png"):
        if pixmap is None or pixmap.isNull():
            return False
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        pixmap.save(buf, "PNG")
        buf.close()
        self._bytes_imagen = bytes(ba)
        self._nombre_imagen = nombre
        self._pixmap_actual = pixmap
        self._actualizar_vista_previa()
        self.imagen_cambiada.emit()
        return True

    def cargar_archivo(self, ruta):
        if not ruta or not os.path.isfile(ruta):
            return False
        pm = QPixmap(ruta)
        if pm.isNull():
            return False
        raw, nombre, _ = _normalizar_imagen_bytes(ruta_imagen=ruta)
        self._bytes_imagen = raw
        self._nombre_imagen = nombre
        self._pixmap_actual = pm
        self._actualizar_vista_previa()
        self.imagen_cambiada.emit()
        return True

    def seleccionar_archivo(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen del error",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp);;Todos los archivos (*.*)",
        )
        if ruta:
            if not self.cargar_archivo(ruta):
                QMessageBox.warning(self, "Imagen no válida", "No se pudo cargar la imagen seleccionada.")

    def capturar_ventana_simulador(self):
        objetivo = self._ventana_captura or self.window()
        if objetivo is None:
            return False
        pm = objetivo.grab()
        return self.establecer_pixmap(pm, "captura_simulador.png")

    def pegar_desde_portapapeles(self):
        cb = QApplication.clipboard()
        if cb is None:
            return False
        pm = cb.pixmap()
        if pm.isNull():
            img = cb.image()
            if not img.isNull():
                pm = QPixmap.fromImage(img)
        if pm.isNull():
            QMessageBox.information(
                self,
                "Portapapeles sin imagen",
                "No hay ninguna captura o imagen copiada en el portapapeles.",
            )
            return False
        return self.establecer_pixmap(pm, "captura_portapapeles.png")

    def limpiar_imagen(self):
        self._bytes_imagen = None
        self._nombre_imagen = None
        self._pixmap_actual = QPixmap()
        self._actualizar_vista_previa()
        self.imagen_cambiada.emit()

    def _actualizar_vista_previa(self):
        if self._bytes_imagen and not self._pixmap_actual.isNull():
            mini = self._pixmap_actual.scaled(
                68, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_preview.setPixmap(mini)
            kb = max(1, len(self._bytes_imagen) // 1024)
            self.lbl_estado_foto.setText(f"Foto adjunta: {self._nombre_imagen} ({kb} KB)")
            self.lbl_sub_foto.setText(
                f"Dimensiones: {self._pixmap_actual.width()} × {self._pixmap_actual.height()} px"
            )
            self.btn_quitar_foto.show()
        else:
            self.lbl_preview.setPixmap(crear_icono_herramienta("imagen", "#94a3b8").pixmap(24, 24))
            self.lbl_estado_foto.setText("Sin foto adjunta (puedes arrastrar una imagen aquí)")
            self.lbl_sub_foto.setText("Formatos admitidos: PNG, JPG, BMP, WEBP o captura directa.")
            self.btn_quitar_foto.hide()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        md = event.mimeData()
        if md.hasImage():
            img = QImage(md.imageData())
            if not img.isNull():
                self.establecer_pixmap(QPixmap.fromImage(img), "imagen_arrastrada.png")
                event.acceptProposedAction()
                return
        if md.hasUrls():
            for url in md.urls():
                ruta = url.toLocalFile()
                if ruta and self.cargar_archivo(ruta):
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)


class DialogoReportarError(QDialog):
    """Ventana modal con bandeja de descripción y bandeja de foto para reportar errores."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reportar un error")
        self.setMinimumSize(560, 490)
        self.resize(580, 520)
        self._hilo_envio = None
        self._trabajador_envio = None

        self.setStyleSheet(
            """
            QDialog {
                background-color: #f8f9ff;
            }
            QFrame#cardReporte {
                background-color: #ffffff;
                border: 1px solid #dce7f3;
                border-radius: 12px;
            }
            QFrame#bandejaFotoFrame {
                background-color: #f2f6ff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
            }
            QFrame#bandejaFotoFrame QPushButton {
                background-color: #ffffff;
                color: #1e293b;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 3px 10px;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 11.5px;
                font-weight: 600;
            }
            QFrame#bandejaFotoFrame QPushButton:hover {
                background-color: #eff6ff;
                border-color: #0284c7;
                color: #0c4e77;
            }
            QTextEdit#txtDescripcionReporte, QLineEdit#txtContactoReporte {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 8px;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12.5px;
                color: #0f172a;
            }
            QTextEdit#txtDescripcionReporte:focus, QLineEdit#txtContactoReporte:focus {
                border: 1.5px solid #0284c7;
            }
            QPushButton#btnEnviarReporte {
                background-color: #0c4e77;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 18px;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12.5px;
                font-weight: 700;
            }
            QPushButton#btnEnviarReporte:hover {
                background-color: #0284c7;
            }
            QPushButton#btnEnviarReporte:disabled {
                background-color: #94a3b8;
            }
            QPushButton#btnCancelarReporte {
                background-color: #ffffff;
                color: #475569;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 8px 16px;
                font-family: "Inter", "Segoe UI", sans-serif;
                font-size: 12.5px;
                font-weight: 600;
            }
            QPushButton#btnCancelarReporte:hover {
                background-color: #f1f5f9;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        card = QFrame()
        card.setObjectName("cardReporte")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(10)

        # Cabecera del diálogo
        fila_titulo = QHBoxLayout()
        fila_titulo.setSpacing(10)
        lbl_ico = QLabel()
        lbl_ico.setFixedSize(34, 34)
        lbl_ico.setAlignment(Qt.AlignCenter)
        lbl_ico.setStyleSheet("background-color: #fee2e2; border-radius: 8px;")
        lbl_ico.setPixmap(crear_icono_herramienta("reportar_error", "#b91c1c").pixmap(20, 20))
        fila_titulo.addWidget(lbl_ico)

        col_tit = QVBoxLayout()
        col_tit.setSpacing(2)
        lbl_titulo = QLabel("Reportar un error o anomalía")
        lbl_titulo.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 15px; "
            "font-weight: 700; color: #0b1c30;"
        )
        col_tit.addWidget(lbl_titulo)

        self.lbl_subtitulo = QLabel(f"Se enviará automáticamente a {CORREO_SOPORTE}")
        self.lbl_subtitulo.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11.5px; color: #64748b;"
        )
        col_tit.addWidget(self.lbl_subtitulo)
        fila_titulo.addLayout(col_tit, 1)
        card_layout.addLayout(fila_titulo)

        # 1. Bandeja de descripción
        lbl_desc = QLabel("1. Bandeja de descripción del error:")
        lbl_desc.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 12px; "
            "font-weight: 600; color: #1e293b; margin-top: 4px;"
        )
        card_layout.addWidget(lbl_desc)

        self.txt_descripcion = QTextEdit()
        self.txt_descripcion.setObjectName("txtDescripcionReporte")
        self.txt_descripcion.setPlaceholderText(
            "Describe qué ocurrió, en qué vista estabas y cómo reproducir el problema..."
        )
        self.txt_descripcion.setMinimumHeight(110)
        card_layout.addWidget(self.txt_descripcion, 1)

        # Campo opcional de contacto
        lbl_contacto = QLabel("Tu correo o nombre (opcional):")
        lbl_contacto.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11.5px; "
            "font-weight: 600; color: #475569;"
        )
        card_layout.addWidget(lbl_contacto)

        self.txt_contacto = QLineEdit()
        self.txt_contacto.setObjectName("txtContactoReporte")
        self.txt_contacto.setPlaceholderText("Ej. nombre@correo.com (por si deseas recibir respuesta)")
        card_layout.addWidget(self.txt_contacto)

        # 2. Bandeja para la foto
        lbl_foto = QLabel("2. Bandeja para foto o captura de pantalla:")
        lbl_foto.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 12px; "
            "font-weight: 600; color: #1e293b; margin-top: 4px;"
        )
        card_layout.addWidget(lbl_foto)

        self.bandeja_foto = BandejaFotoWidget(self, ventana_captura=parent)
        card_layout.addWidget(self.bandeja_foto)

        self.lbl_estado_envio = QLabel("")
        self.lbl_estado_envio.setStyleSheet(
            "font-family: 'Inter', 'Segoe UI', sans-serif; font-size: 11.5px; "
            "font-weight: 600; color: #0284c7;"
        )
        self.lbl_estado_envio.hide()
        card_layout.addWidget(self.lbl_estado_envio)

        # Botones inferiores
        fila_acciones = QHBoxLayout()
        fila_acciones.addStretch()

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("btnCancelarReporte")
        self.btn_cancelar.setCursor(Qt.PointingHandCursor)
        self.btn_cancelar.clicked.connect(self.reject)
        fila_acciones.addWidget(self.btn_cancelar)

        self.btn_enviar = QPushButton("Enviar reporte")
        self.btn_enviar.setObjectName("btnEnviarReporte")
        self.btn_enviar.setCursor(Qt.PointingHandCursor)
        self.btn_enviar.clicked.connect(self._on_enviar_clicked)
        fila_acciones.addWidget(self.btn_enviar)

        card_layout.addLayout(fila_acciones)
        root.addWidget(card)

    def _on_enviar_clicked(self):
        if self._hilo_envio is not None:
            return
        descripcion = self.txt_descripcion.toPlainText().strip()
        if not descripcion:
            QMessageBox.warning(
                self,
                "Descripción requerida",
                "Por favor escribe una breve descripción del error antes de enviar.",
            )
            self.txt_descripcion.setFocus()
            return

        self.btn_enviar.setEnabled(False)
        self.btn_enviar.setText("Enviando...")
        self.btn_cancelar.setEnabled(False)
        self.lbl_estado_envio.setText(f"Enviando reporte a {CORREO_SOPORTE}...")
        self.lbl_estado_envio.show()

        hilo = QThread(self)
        trabajador = TrabajadorEnvioReporte(
            descripcion,
            bytes_imagen=self.bandeja_foto.bytes_imagen,
            nombre_imagen=self.bandeja_foto.nombre_imagen,
            contacto=self.txt_contacto.text().strip(),
            destinatario=CORREO_SOPORTE,
        )
        trabajador.moveToThread(hilo)
        hilo.started.connect(trabajador.ejecutar)
        trabajador.completado.connect(self._on_envio_completado)
        trabajador.fallido.connect(self._on_envio_fallido)
        trabajador.completado.connect(hilo.quit)
        trabajador.fallido.connect(hilo.quit)
        hilo.finished.connect(trabajador.deleteLater)
        hilo.finished.connect(hilo.deleteLater)
        hilo.finished.connect(self._limpiar_hilo)

        self._hilo_envio = hilo
        self._trabajador_envio = trabajador
        hilo.start()

    def _limpiar_hilo(self):
        self._hilo_envio = None
        self._trabajador_envio = None

    def _on_envio_completado(self):
        self.lbl_estado_envio.hide()
        QMessageBox.information(
            self,
            "Reporte enviado",
            f"¡Gracias! Tu reporte fue enviado automáticamente a {CORREO_SOPORTE}.",
        )
        self.accept()

    def _on_envio_fallido(self, detalle):
        self.btn_enviar.setEnabled(True)
        self.btn_enviar.setText("Enviar reporte")
        self.btn_cancelar.setEnabled(True)
        self.lbl_estado_envio.hide()
        QMessageBox.warning(
            self,
            "Error al enviar reporte",
            f"No se pudo enviar el reporte automáticamente.\n\nDetalle: {detalle}",
        )
