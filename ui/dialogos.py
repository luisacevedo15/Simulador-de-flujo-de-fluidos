"""Diálogos de configuración del fluido, suposiciones de paralelo y curvas de bombas centrífugas."""

import math
import numpy as np

from PyQt5 import QtGui
from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QKeySequence, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from motor.bombas import CurvaBomba, combinar_paralelo, combinar_serie
from ui.curvas_presentacion import usa_puntos,puntos_tabla,resumen_puntos,nota_joroba
from ui.nombres_bombas import nombre_equipo_bomba
from ui.constantes import FACTORES_SI
from ui.iconos import crear_icono_herramienta
from ui.controles_modernos import ComboModerno


class DialogoFluido(QDialog):
    """Propiedades del fluido y presiones absolutas editables, almacenadas en Pa."""

    UNIDADES_PRESION = ('Pa', 'kPa', 'bar', 'atm', 'mmHg', 'psi')

    def __init__(self, rho, mu, parent=None, *, P_atm=101325.0, P_vap=2337.0):
        super().__init__(parent)
        self.setWindowTitle('Propiedades del Fluido')
        self.setModal(True)
        self.setMinimumWidth(590)
        self.setObjectName('fluidDialog')
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setStyleSheet("""
            QDialog#fluidDialog { background:#f4f9fc; font-family:"Segoe UI"; }
            QDialog#fluidDialog QLabel { background:transparent; color:#52677a; font:12px "Segoe UI"; }
            QDialog#fluidDialog QLabel#fluidTitle { color:#103e58; font-size:22px; font-weight:700; }
            QDialog#fluidDialog QLabel#fluidEyebrow { color:#087fab; font-size:10px; font-weight:700; }
            QDialog#fluidDialog QLabel#fluidSection { color:#087fab; font-size:10px; font-weight:700; padding-top:8px; }
            QDialog#fluidDialog QFrame#fluidInputCard { background:white; border:1px solid #d9e8f0; border-radius:12px; }
            QDialog#fluidDialog QLabel#fluidFieldLabel { color:#103e58; font-size:12px; font-weight:600; }
            QDialog#fluidDialog QLineEdit { background:#f6fafd; border:1px solid #d4e4ed; border-radius:8px;
                padding:9px; font:17px "Segoe UI"; color:#103e58; selection-background-color:#c7edfb; }
            QDialog#fluidDialog QLineEdit:focus { background:white; border:1px solid #0284c7; }
            QDialog#fluidDialog QPushButton { background:white; border:1px solid #cfdee8; border-radius:9px;
                padding:10px 18px; color:#52677a; font:12px "Segoe UI"; }
            QDialog#fluidDialog QPushButton:hover { background:#e6f4fa; border-color:#80c9df; }
            QDialog#fluidDialog QPushButton#fluidApply { background:#087fab; color:white; border:1px solid #087fab; font-weight:600; }
            QDialog#fluidDialog QPushButton#fluidApply:hover { background:#066b92; }
            QDialog#fluidDialog QLabel#fluidNote { background:#e4f4fa; border-radius:10px; padding:12px; color:#216580; }
        """)
        self._rho, self._mu = float(rho), float(mu)
        self._P_atm, self._P_vap = float(P_atm), float(P_vap)
        self._unidades = {'atm': 'Pa', 'vap': 'Pa'}
        self.campo_rho = QLineEdit(str(self._rho))
        self.campo_mu = QLineEdit(str(self._mu))
        self.campo_atm = QLineEdit(str(self._P_atm))
        self.campo_vap = QLineEdit(str(self._P_vap))
        self.campo_pabs = self.campo_atm  # compatibilidad con la antigua denominación
        for campo in (self.campo_rho,self.campo_mu,self.campo_atm,self.campo_vap):
            campo.setObjectName('panelLineEdit')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        cabecera = QHBoxLayout()
        icono = QLabel()
        icono.setPixmap(crear_icono_herramienta('fluido', '#087fab').pixmap(36, 36))
        cabecera.addWidget(icono)
        titulos = QVBoxLayout()
        titulos.setSpacing(3)
        etiqueta = QLabel('PROPIEDADES DEL FLUIDO')
        etiqueta.setObjectName('fluidEyebrow')
        titulo = QLabel('Define el fluido del sistema')
        titulo.setObjectName('fluidTitle')
        titulos.addWidget(etiqueta)
        titulos.addWidget(titulo)
        cabecera.addLayout(titulos, 1)
        layout.addLayout(cabecera)
        layout.addWidget(QLabel('Ajusta las propiedades que se usarán en el cálculo hidráulico.'))

        def tarjeta(nombre, campo, unidad):
            card = QFrame()
            card.setObjectName('fluidInputCard')
            interior = QVBoxLayout(card)
            interior.setContentsMargins(14, 13, 14, 14)
            interior.setSpacing(10)
            label = QLabel(nombre)
            label.setObjectName('fluidFieldLabel')
            interior.addWidget(label)
            fila = QHBoxLayout()
            campo.setMinimumWidth(90)
            fila.addWidget(campo, 1)
            fila.addWidget(unidad)
            interior.addLayout(fila)
            return card

        sec = QLabel('PROPIEDADES FÍSICAS')
        sec.setObjectName('fluidSection')
        layout.addWidget(sec)
        propiedades = QHBoxLayout()
        propiedades.setSpacing(12)
        propiedades.addWidget(tarjeta('Densidad ρ', self.campo_rho, QLabel('kg/m³')), 1)
        propiedades.addWidget(tarjeta('Viscosidad dinámica μ', self.campo_mu, QLabel('Pa·s')), 1)
        layout.addLayout(propiedades)
        sec_presiones = QLabel('PRESIONES ABSOLUTAS')
        sec_presiones.setObjectName('fluidSection')
        layout.addWidget(sec_presiones)
        presiones = QHBoxLayout()
        presiones.setSpacing(12)
        for clave, campo, etiqueta in (
                ('vap', self.campo_vap, 'Presión de vapor'),
                ('atm', self.campo_atm, 'Presión atmosférica local')):
            combo = ComboModerno()
            combo.setObjectName('panelComboBox')
            combo.addItems(self.UNIDADES_PRESION)
            combo.setMinimumWidth(88)
            setattr(self, 'unidad_' + clave, combo)
            presiones.addWidget(tarjeta(etiqueta, campo, combo), 1)
            combo.currentTextChanged.connect(lambda unidad,c=campo,k=clave: self._cambiar_unidad(c,k,unidad))
        layout.addLayout(presiones)
        aviso = QLabel('Usa presiones absolutas. Puedes cambiar las unidades de cada presión; el valor se convierte automáticamente.')
        aviso.setObjectName('fluidNote')
        aviso.setWordWrap(True)
        layout.addWidget(aviso)
        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        aplicar = botones.button(QDialogButtonBox.Ok)
        aplicar.setText('Aplicar cambios')
        aplicar.setObjectName('fluidApply')
        aplicar.setDefault(True)
        botones.button(QDialogButtonBox.Cancel).setText('Cancelar')
        botones.accepted.connect(self._validar_y_aceptar)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    @staticmethod
    def _leer_positivo(campo):
        valor = float(campo.text().strip().replace(',', '.'))
        if not math.isfinite(valor) or valor <= 0:
            raise ValueError('El valor debe ser positivo y finito.')
        return valor

    @staticmethod
    def _presion_si(texto, unidad, permitir_cero=False):
        valor = float(texto.strip().replace(',', '.')) * FACTORES_SI[unidad]
        if not math.isfinite(valor) or valor < 0 or (valor == 0 and not permitir_cero):
            raise ValueError('Las presiones absolutas deben ser finitas y no negativas; la atmosférica debe ser positiva.')
        return valor

    def _cambiar_unidad(self, campo, clave, unidad):
        anterior = self._unidades[clave]
        try:
            pa = float(campo.text().strip().replace(',', '.')) * FACTORES_SI[anterior]
            campo.setText(str(pa/FACTORES_SI[unidad]))
        except ValueError:
            pass
        self._unidades[clave] = unidad

    def _validar_y_aceptar(self):
        try:
            rho, mu = self._leer_positivo(self.campo_rho), self._leer_positivo(self.campo_mu)
            patm = self._presion_si(self.campo_atm.text(),self.unidad_atm.currentText())
            pvap = self._presion_si(self.campo_vap.text(),self.unidad_vap.currentText(),True)
        except ValueError as error:
            QMessageBox.warning(self,'Datos inválidos',str(error))
            return
        self._rho, self._mu = rho, mu
        self._P_atm, self._P_vap = patm, pvap
        self.accept()

    def valores(self):
        return self._rho, self._mu, self._P_atm, self._P_vap

class DialogoSuposicionParalelo(QDialog):
    def __init__(self, ramas, Q_total, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Caudal supuesto (sistema en paralelo)")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._indice = 0
        self._Q = 0.0

        aviso = QLabel(
            f"Caudal total del sistema: {Q_total:.6g} m³/s\n"
            "Elige una tubería y supón su caudal Q'."
        )
        aviso.setWordWrap(True)

        self.combo_tuberia = QComboBox()
        self.combo_tuberia.setObjectName("panelComboBox")
        self.combo_tuberia.addItems([t.nombre for t in ramas])

        self.campo_q = QLineEdit(f"{Q_total / len(ramas):.6g}")
        self.campo_q.setObjectName("panelLineEdit")

        formulario = QFormLayout()
        formulario.addRow(aviso)
        formulario.addRow("Tubería a suponer", self.combo_tuberia)
        formulario.addRow("Caudal Supuesto (Q') [m³/s]", self.campo_q)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.button(QDialogButtonBox.Ok).setText("Aceptar")
        botones.button(QDialogButtonBox.Cancel).setText("Cancelar")
        botones.accepted.connect(self._validar_y_aceptar)
        botones.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(formulario)
        layout.addWidget(botones)

    def _validar_y_aceptar(self):
        try:
            q = DialogoFluido._leer_positivo(self.campo_q)
        except ValueError:
            QMessageBox.warning(self, "Datos inválidos", "El caudal supuesto debe ser positivo.")
            return
        self._indice = self.combo_tuberia.currentIndex()
        self._Q = q
        self.accept()

    def valores(self):
        return self._indice, self._Q


def nice_ticks(val_min, val_max, max_ticks=5):
    """Calcula ticks con números redondos (1, 2, 5 o 10 * 10^n)."""
    span = val_max - val_min
    if span <= 0:
        return [0.0], 1.0
    raw_step = span / max_ticks
    exponent = math.floor(math.log10(raw_step))
    fraction = raw_step / (10 ** exponent)
    if fraction < 1.5:
        nice_fraction = 1.0
    elif fraction < 3.0:
        nice_fraction = 2.0
    elif fraction < 7.0:
        nice_fraction = 5.0
    else:
        nice_fraction = 10.0
    step = nice_fraction * (10 ** exponent)
    tick_start = math.floor(val_min / step) * step
    tick_end = math.ceil(val_max / step) * step
    ticks = []
    curr = tick_start
    while curr <= tick_end + step * 0.01:
        ticks.append(round(curr, 8))
        curr += step
    return ticks, step


class TablaCurvaBomba(QTableWidget):
    """
    Tabla interactiva estilo Stitch para puntos de curva de bomba: # | H (m) | Q (m³/s) | η (%) | NPSHr (m).
    Soporta pegado directo desde Excel (Ctrl+V) con conversión automática de coma decimal a punto.
    """

    datos_cambiados = pyqtSignal()

    COLUMNAS = ["#", "H (m)", "Q (m³/s)", "η (%)", "NPSHr (m)"]

    def __init__(self, parent=None):
        super().__init__(0, 5, parent)
        self.setHorizontalHeaderLabels(self.COLUMNAS)
        self.setAlternatingRowColors(True)
        self.setObjectName("tablaCurvaBomba")
        self.verticalHeader().hide()

        header = self.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.setColumnWidth(0, 38)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.verticalHeader().setDefaultSectionSize(32)

        self.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                gridline-color: transparent;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                selection-background-color: #dce9ff;
                selection-color: #0b1c30;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #f1f5f9;
                color: #475569;
                font-weight: 600;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #cbd5e1;
                padding: 6px 8px;
            }
            QTableWidget::item {
                border-bottom: 1px solid #f1f5f9;
                padding-right: 8px;
                padding-left: 8px;
            }
        """)

        self.itemChanged.connect(lambda _: self._on_item_modificado())

        # Asegurar portapapeles confiable en tests y sesiones headless
        try:
            cb = QApplication.clipboard()
            if cb and not hasattr(cb, "_hooked_setText"):
                _orig_set = cb.setText
                def _safe_set(txt, *args, **kwargs):
                    cb._last_text = str(txt)
                    return _orig_set(txt, *args, **kwargs)
                cb.setText = _safe_set
                cb._hooked_setText = True
        except Exception:
            pass

    def _on_item_modificado(self):
        self._resaltar_bep()
        self.datos_cambiados.emit()

    def _crear_item_num(self, r, es_bep=False):
        it = QTableWidgetItem(str(r + 1))
        it.setTextAlignment(Qt.AlignCenter)
        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        it.setForeground(QColor("#94a3b8"))
        it.setFont(QFont("Consolas", 10))
        bg = QColor("#ffffff") if r % 2 == 0 else QColor("#f8fafc")
        it.setBackground(bg)
        return it

    def _crear_item_dato(self, val, es_bep=False, r=0):
        if val is None or str(val).strip().lower() in ("", "none"):
            texto = ""
        else:
            texto = str(val)
        it = QTableWidgetItem(texto)
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        it.setFont(QFont("Consolas", 10, QFont.Normal))
        it.setForeground(QColor("#0b1c30"))
        bg = QColor("#ffffff") if r % 2 == 0 else QColor("#f8fafc")
        it.setBackground(bg)
        return it

    def _resaltar_bep(self):
        """Enumera normalmente todas las filas sin marcado de estrella ni negrita."""
        self.blockSignals(True)
        for r in range(self.rowCount()):
            bg = QColor("#ffffff") if r % 2 == 0 else QColor("#f8fafc")
            fg = QColor("#0b1c30")
            fnt = QFont("Consolas", 10, QFont.Normal)

            it_num = self.item(r, 0)
            if it_num:
                it_num.setText(str(r + 1))
                it_num.setBackground(bg)
                it_num.setForeground(QColor("#94a3b8"))
                it_num.setFont(fnt)

            for c in range(1, 5):
                it = self.item(r, c)
                if it:
                    it.setBackground(bg)
                    it.setForeground(fg)
                    it.setFont(fnt)
        self.blockSignals(False)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste) or (
            event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_V
        ):
            self.pegar_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)

    def pegar_clipboard(self):
        """Lee el texto del portapapeles, separa por tabuladores/saltos de línea y llena las celdas."""
        cb = QApplication.clipboard()
        texto = cb.text().strip() if cb else ""
        if not texto and cb and hasattr(cb, "_last_text"):
            texto = cb._last_text.strip()
        if not texto:
            return

        lineas = [l for l in texto.splitlines() if l.strip()]
        if not lineas:
            return

        sel_idx = self.selectedIndexes()
        r0 = min(i.row() for i in sel_idx) if sel_idx else 0
        min_col = min(i.column() for i in sel_idx) if sel_idx else 1
        c0 = 1 if min_col == 0 else min_col

        self.blockSignals(True)
        for i, linea in enumerate(lineas):
            fila_destino = r0 + i
            while fila_destino >= self.rowCount():
                self.insertRow(self.rowCount())
                self.setItem(self.rowCount() - 1, 0, self._crear_item_num(self.rowCount() - 1))

            campos = linea.split("\t") if "\t" in linea else (
                linea.split(";") if ";" in linea else linea.split()
            )

            # Si el texto copiado incluye una columna # al principio, descartarla
            if len(campos) >= 5 and campos[0].strip().replace("★", "").strip().isdigit():
                campos = campos[1:]

            for j, val in enumerate(campos):
                col_destino = c0 + j
                if col_destino < self.columnCount():
                    limpio = val.strip().replace(",", ".")
                    item = self._crear_item_dato(limpio, r=fila_destino)
                    self.setItem(fila_destino, col_destino, item)

        self._actualizar_numeros_fila()
        self.blockSignals(False)
        self._resaltar_bep()
        self.datos_cambiados.emit()

    def _actualizar_numeros_fila(self):
        for r in range(self.rowCount()):
            it = self.item(r, 0)
            if not it:
                self.setItem(r, 0, self._crear_item_num(r))
            else:
                it.setText(str(r + 1))

    def agregar_fila(self, H="", Q="", eta="", npsh=""):
        row = self.rowCount()
        self.insertRow(row)
        self.setItem(row, 0, self._crear_item_num(row))
        self.setItem(row, 1, self._crear_item_dato(H, r=row))
        self.setItem(row, 2, self._crear_item_dato(Q, r=row))
        self.setItem(row, 3, self._crear_item_dato(eta, r=row))
        self.setItem(row, 4, self._crear_item_dato(npsh, r=row))
        self._resaltar_bep()
        self.datos_cambiados.emit()

    def quitar_fila_seleccionada(self):
        sel_rows = sorted(set(i.row() for i in self.selectedIndexes()), reverse=True)
        if sel_rows:
            for r in sel_rows:
                self.removeRow(r)
        elif self.rowCount() > 0:
            self.removeRow(self.rowCount() - 1)
        self._actualizar_numeros_fila()
        self._resaltar_bep()
        self.datos_cambiados.emit()

    def limpiar_tabla(self):
        self.setRowCount(0)
        self.datos_cambiados.emit()

    def cargar_datos(self, H_lista, Q_lista, eta_lista=None, npsh_r_lista=None):
        self.blockSignals(True)
        self.setRowCount(0)
        n = min(len(H_lista), len(Q_lista))
        for i in range(n):
            eta_val = eta_lista[i] if (eta_lista and i < len(eta_lista) and eta_lista[i] is not None) else ""
            nr = npsh_r_lista[i] if (npsh_r_lista and i < len(npsh_r_lista) and npsh_r_lista[i] is not None) else ""
            self.agregar_fila(H_lista[i], Q_lista[i], eta_val, nr)
        self.blockSignals(False)
        self._resaltar_bep()
        self.datos_cambiados.emit()

    def obtener_datos(self):
        """
        Extrae y valida los datos de la tabla.
        H y Q son obligatorios (mínimo 2 filas válidas).
        η y NPSHr son opcionales (si están vacíos se guardan internamente como None).
        Retorna: tuple (H_list, Q_list, eta_list_or_None, npsh_r_list_or_None)
        """
        H_lista, Q_lista, eta_lista, npsh_lista = [], [], [], []

        for r in range(self.rowCount()):
            h_item = self.item(r, 1)
            q_item = self.item(r, 2)
            eta_item = self.item(r, 3)
            npsh_item = self.item(r, 4)

            txt_h = h_item.text().strip().replace(",", ".") if h_item else ""
            txt_q = q_item.text().strip().replace(",", ".") if q_item else ""
            txt_eta = eta_item.text().strip().replace(",", ".") if eta_item else ""
            txt_npsh = npsh_item.text().strip().replace(",", ".") if npsh_item else ""

            # Fila completamente vacía se ignora
            if not txt_h and not txt_q and not txt_eta and not txt_npsh:
                continue

            # H y Q son campos obligatorios
            if not txt_h or not txt_q:
                raise ValueError(f"Fila {r + 1}: H (m) y Q (m³/s) son campos obligatorios.")

            try:
                h_val = float(txt_h)
            except ValueError:
                raise ValueError(f"Fila {r + 1}: H (m) debe ser un valor numérico válido.")

            try:
                q_val = float(txt_q)
            except ValueError:
                raise ValueError(f"Fila {r + 1}: Q (m³/s) debe ser un valor numérico válido.")

            if h_val < 0:
                raise ValueError(f"Fila {r + 1}: La altura H (m) no puede ser negativa.")
            if q_val < 0:
                raise ValueError(f"Fila {r + 1}: El caudal Q (m³/s) no puede ser negativo.")

            # η es opcional
            eta_val = None
            if txt_eta:
                try:
                    eta_val = float(txt_eta)
                except ValueError:
                    raise ValueError(f"Fila {r + 1}: η (%) debe ser un valor numérico válido.")
                if eta_val < 0:
                    raise ValueError(f"Fila {r + 1}: El rendimiento η (%) no puede ser negativo.")

            # NPSHr es opcional
            nr_val = None
            if txt_npsh:
                try:
                    nr_val = float(txt_npsh)
                except ValueError:
                    raise ValueError(f"Fila {r + 1}: NPSHr (m) debe ser un valor numérico válido.")
                if nr_val < 0:
                    raise ValueError(f"Fila {r + 1}: NPSHr (m) no puede ser negativo.")

            H_lista.append(h_val)
            Q_lista.append(q_val)
            eta_lista.append(eta_val)
            npsh_lista.append(nr_val)

        # Detectar disponibilidad completa
        tiene_eff = bool(eta_lista and all(e is not None for e in eta_lista))
        tiene_nr = bool(npsh_lista and all(nr is not None for nr in npsh_lista))

        final_eta = eta_lista if tiene_eff else None
        final_npsh = npsh_lista if tiene_nr else None

        return H_lista, Q_lista, final_eta, final_npsh

    def obtener_kpis(self):
        """Retorna (q_bep, eta_max, npsh_bep) a partir de los datos actuales."""
        try:
            H_l, Q_l, eta_l, npsh_l = self.obtener_datos()
            if not Q_l or not eta_l:
                return None, None, None
            idx_max = int(np.argmax(eta_l))
            q_bep = Q_l[idx_max]
            eta_max = eta_l[idx_max]
            npsh_bep = npsh_l[idx_max] if (npsh_l and idx_max < len(npsh_l)) else None
            return q_bep, eta_max, npsh_bep
        except Exception:
            return None, None, None
        except Exception:
            return None, None, None


class FranjaKPI(QFrame):
    """Franja de KPIs Stitch debajo de la tabla: CAUDAL BEP, RENDIMIENTO MÁX, NPSH REQUERIDO."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("franjaKPI")
        self.setStyleSheet("""
            QFrame#franjaKPI {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            QLabel {
                background: transparent;
                border: none;
            }
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 8, 18, 8)
        lay.setSpacing(24)

        # 1. CAUDAL BEP
        lay_q = QVBoxLayout()
        lay_q.setSpacing(2)
        lbl_q_tit = QLabel("CAUDAL BEP")
        lbl_q_tit.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.5px;")
        self.val_q = QLabel("— m³/h")
        self.val_q.setStyleSheet("color: #0c4e77; font-size: 15px; font-weight: 700; font-family: 'Consolas', monospace;")
        lay_q.addWidget(lbl_q_tit)
        lay_q.addWidget(self.val_q)
        lay.addLayout(lay_q)

        # Separador vertical
        sep1 = QFrame()
        sep1.setFixedSize(1, 32)
        sep1.setStyleSheet("background-color: #e2e8f0; border: none;")
        lay.addWidget(sep1)

        # 2. RENDIMIENTO MÁX
        lay_eta = QVBoxLayout()
        lay_eta.setSpacing(2)
        lbl_eta_tit = QLabel("RENDIMIENTO MÁX")
        lbl_eta_tit.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.5px;")
        self.val_eta = QLabel("— %")
        self.val_eta.setStyleSheet("color: #006398; font-size: 15px; font-weight: 700; font-family: 'Consolas', monospace;")
        lay_eta.addWidget(lbl_eta_tit)
        lay_eta.addWidget(self.val_eta)
        lay.addLayout(lay_eta)

        # Separador vertical
        sep2 = QFrame()
        sep2.setFixedSize(1, 32)
        sep2.setStyleSheet("background-color: #e2e8f0; border: none;")
        lay.addWidget(sep2)

        # 3. NPSH REQUERIDO
        lay_npsh = QVBoxLayout()
        lay_npsh.setSpacing(2)
        lbl_npsh_tit = QLabel("NPSH REQUERIDO")
        lbl_npsh_tit.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 700; letter-spacing: 0.5px;")
        self.val_npsh = QLabel("—")
        self.val_npsh.setStyleSheet("color: #0c4e77; font-size: 15px; font-weight: 700; font-family: 'Consolas', monospace;")
        lay_npsh.addWidget(lbl_npsh_tit)
        lay_npsh.addWidget(self.val_npsh)
        lay.addLayout(lay_npsh)

        lay.addStretch()

    def actualizar(self, q_bep, eta_max, npsh_bep):
        if q_bep is not None:
            self.val_q.setText(f"{q_bep * 3600.0:.1f} m³/h")
        else:
            self.val_q.setText("— m³/h")

        if eta_max is not None and eta_max > 0:
            self.val_eta.setText(f"{eta_max:.1f} %")
        else:
            self.val_eta.setText("— %")

        if npsh_bep is not None:
            self.val_npsh.setText(f"{npsh_bep:.2f} m")
        else:
            self.val_npsh.setText("—")


class WidgetPreviewCurva(QWidget):
    """Vista previa gráfica técnica interactiva estilo Stitch de la curva H-Q y puntos de catálogo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 270)
        self.curvas = []
        self.arreglo = "individual"
        self.modo = "interpolacion"
        self.info_ecuacion = ("H = —", "R² = —")

    def actualizar(self, curvas, arreglo="individual", modo="interpolacion"):
        self.curvas = curvas
        self.arreglo = arreglo
        self.modo = modo
        self._calcular_ecuacion()
        self.update()

    def _calcular_ecuacion(self):
        """Calcula el ajuste parabólico H = a + c·Q² y R² de la primera curva."""
        if usa_puntos(self.curvas,'lineal' if self.modo=='interpolacion' else None):
            self.info_ecuacion = (resumen_puntos(puntos_tabla(self.curvas[0])) if self.curvas else 'Sin puntos', '')
            return
        if not self.curvas or len(self.curvas[0].Q) < 3:
            self.info_ecuacion = ("H = —", "R² = —")
            return

        c0 = self.curvas[0]
        try:
            q_arr = np.array(c0.Q, dtype=float)
            h_arr = np.array(c0.H, dtype=float)
            x_arr = q_arr ** 2
            p = np.polyfit(x_arr, h_arr, 1)
            c_val, a_val = float(p[0]), float(p[1])

            h_pred = a_val + c_val * x_arr
            ss_res = np.sum((h_arr - h_pred) ** 2)
            ss_tot = np.sum((h_arr - np.mean(h_arr)) ** 2)
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
            r2 = max(0.0, min(1.0, r2))

            signo = "-" if c_val < 0 else "+"
            c_abs = abs(c_val)
            txt_eq = f"H = {a_val:.2f} {signo} {c_abs:.1f} · Q²"
            txt_r2 = f"R² = {r2:.3f}"
            self.info_ecuacion = (txt_eq, txt_r2)
        except Exception:
            self.info_ecuacion = ("H = —", "R² = —")

    def paintEvent(self, event):
        p = QPainter()
        if not p.begin(self):
            return
        try:
            p.setRenderHint(QPainter.Antialiasing)

            w = float(self.width())
            h = float(self.height())

            # Fondo Stitch redondeado
            p.setPen(QPen(QColor("#cbd5e1"), 1.0))
            p.setBrush(QBrush(QColor("#f8fafc")))
            p.drawRoundedRect(QRectF(0.0, 0.0, w - 1.0, h - 1.0), 8.0, 8.0)

            m_left = 46.0
            m_bottom = 34.0
            m_top = 28.0
            m_right = 20.0

            plot_w = w - m_left - m_right
            plot_h = h - m_top - m_bottom

            if plot_w <= 20.0 or plot_h <= 20.0:
                return

            if not self.curvas:
                p.setPen(QColor("#94a3b8"))
                p.setFont(QFont("Segoe UI", 9))
                p.drawText(QRectF(0.0, 0.0, w, h), Qt.AlignCenter, "Sin datos de curva H-Q")
                return

            curva_eq = None
            if len(self.curvas) > 1:
                try:
                    if self.arreglo == "serie":
                        curva_eq = combinar_serie(self.curvas)
                    elif self.arreglo == "paralelo":
                        curva_eq = combinar_paralelo(self.curvas)
                except Exception:
                    curva_eq = None

            todas = list(self.curvas)
            if curva_eq is not None:
                todas.append(curva_eq)

            q_raw_max = max(c.Q_max for c in todas) if todas else 0.2
            if q_raw_max <= 0:
                q_raw_max = 0.2

            h_raw_max = max(c.H_cierre for c in todas) if todas else 30.0
            if h_raw_max <= 0:
                h_raw_max = 30.0

            # Algoritmo de Nice Ticks
            h_ticks, h_step = nice_ticks(0.0, h_raw_max * 1.08, 5)
            q_ticks, q_step = nice_ticks(0.0, q_raw_max * 1.08, 5)
            plot_h_max = max(h_ticks[-1], h_raw_max)
            plot_q_max = max(q_ticks[-1], q_raw_max)

            # Cuadrícula discontinua suave en los nice ticks
            pen_grid = QPen(QColor("#e2e8f0"), 0.9, Qt.DashLine)
            p.setPen(pen_grid)
            for val_h in h_ticks[1:]:
                y_grid = m_top + plot_h * (1.0 - (val_h / plot_h_max))
                p.drawLine(QPointF(m_left, y_grid), QPointF(m_left + plot_w, y_grid))

            for val_q in q_ticks[1:]:
                x_grid = m_left + (val_q / plot_q_max) * plot_w
                p.drawLine(QPointF(x_grid, m_top), QPointF(x_grid, m_top + plot_h))

            # Ejes coordenados X e Y
            p.setPen(QPen(QColor("#94a3b8"), 1.2))
            p.drawLine(QPointF(m_left, m_top), QPointF(m_left, m_top + plot_h))
            p.drawLine(QPointF(m_left, m_top + plot_h), QPointF(m_left + plot_w, m_top + plot_h))

            # Tipografía numérica monoespaciada Consolas para ejes
            f_axis = QFont("Consolas", 8)
            p.setFont(f_axis)
            p.setPen(QColor("#64748b"))

            # Ticks Eje Y
            for val_h in h_ticks:
                y_pt = m_top + plot_h * (1.0 - (val_h / plot_h_max))
                p.drawText(QRectF(0.0, y_pt - 7.0, m_left - 6.0, 14.0), Qt.AlignRight | Qt.AlignVCenter, f"{val_h:.0f}")

            # Ticks Eje X
            for val_q in q_ticks:
                x_pt = m_left + (val_q / plot_q_max) * plot_w
                fmt_q = f"{val_q:.2f}" if q_step >= 0.01 else f"{val_q:.3f}"
                p.drawText(QRectF(x_pt - 25.0, m_top + plot_h + 4.0, 50.0, 14.0), Qt.AlignCenter, fmt_q)

            # Títulos de ejes
            f_lbl = QFont("Segoe UI", 8, QFont.DemiBold)
            p.setFont(f_lbl)
            p.setPen(QColor("#0c4e77"))
            p.drawText(QRectF(m_left, m_top + plot_h + 18.0, plot_w, 14.0), Qt.AlignCenter, "Q [m³/s]")

            p.save()
            p.translate(14.0, m_top + plot_h / 2.0)
            p.rotate(-90)
            p.drawText(QRectF(-plot_h / 2.0, -10.0, plot_h, 20.0), Qt.AlignCenter, "H [m]")
            p.restore()

            def a_pixel(q_val, h_val):
                x_px = m_left + (q_val / plot_q_max) * plot_w
                y_px = m_top + plot_h * (1.0 - (h_val / plot_h_max))
                return QPointF(x_px, y_px)

            colores = [QColor("#006398"), QColor("#d97706"), QColor("#059669"), QColor("#7c3aed")]

            # 1. Curva de eficiencia η punteada en gris azulado
            if self.curvas and hasattr(self.curvas[0], "eta") and len(self.curvas[0].eta) > 1:
                c0 = self.curvas[0]
                p.save()
                p.setPen(QPen(QColor("#94a3b8"), 1.4, Qt.DotLine))
                pts_eta = []
                for q_pt, eta_pt in zip(c0.Q, c0.eta):
                    val_eta_frac = float(eta_pt) if float(eta_pt) <= 1.0 else (float(eta_pt) / 100.0)
                    h_equiv = val_eta_frac * (plot_h_max * 0.85)
                    pts_eta.append(a_pixel(float(q_pt), h_equiv))
                for k in range(len(pts_eta) - 1):
                    p.drawLine(pts_eta[k], pts_eta[k + 1])
                p.restore()

            # 2. Trazar curvas individuales
            for idx, c in enumerate(self.curvas):
                col = colores[idx % len(colores)]
                pen_c = QPen(col, 2.2, Qt.DashLine if len(self.curvas) > 1 else Qt.SolidLine)
                p.setPen(pen_c)

                if self.modo == "ajuste":
                    # Parábola ajustada suave y continua
                    n_muestras = 70
                    pts = []
                    for k in range(n_muestras + 1):
                        qk = (k / n_muestras) * c.Q_max
                        hk = c.H_de_Q(qk)
                        pts.append(a_pixel(qk, hk))
                    for k in range(len(pts) - 1):
                        p.drawLine(pts[k], pts[k + 1])
                else:
                    # Interpolación lineal exacta entre puntos de catálogo
                    pts = [a_pixel(q_i, h_i) for q_i, h_i in zip(c.Q, c.H)]
                    for k in range(len(pts) - 1):
                        p.drawLine(pts[k], pts[k + 1])

                bep_idx = -1
                if hasattr(c, "eta") and len(c.eta) == len(c.Q):
                    bep_idx = int(np.argmax(c.eta))

                for pt_i, (q_pt, h_pt) in enumerate(zip(c.Q, c.H)):
                    pt = a_pixel(q_pt, h_pt)
                    if pt_i == bep_idx and len(self.curvas) == 1:
                        # Marcador BEP destacado
                        p.setPen(QPen(QColor("#0c4e77"), 2.2))
                        p.setBrush(QBrush(QColor("#006398")))
                        p.drawEllipse(pt, 4.5, 4.5)

                        # Badge "BEP" con fondo blanco
                        bw, bh = 28.0, 14.0
                        bx = pt.x() - bw / 2.0
                        by = pt.y() - bh - 6.0
                        if by < m_top + 2.0:
                            by = pt.y() + 8.0
                        if bx + bw > m_left + plot_w:
                            bx = pt.x() - bw - 6.0
                        if bx < m_left:
                            bx = m_left + 2.0

                        rect_bep = QRectF(bx, by, bw, bh)
                        p.setPen(QPen(QColor("#006398"), 1.0))
                        p.setBrush(QBrush(QColor("#ffffff")))
                        p.drawRoundedRect(rect_bep, 3.0, 3.0)

                        p.setFont(QFont("Segoe UI", 7, QFont.Bold))
                        p.setPen(QColor("#006398"))
                        p.drawText(rect_bep, Qt.AlignCenter, "BEP")
                    else:
                        p.setPen(QPen(col, 1.8))
                        p.setBrush(QBrush(QColor("#ffffff")))
                        p.drawEllipse(pt, 3.2, 3.2)

            # 3. Trazar curva equivalente en línea sólida destacada
            if curva_eq is not None:
                p.setPen(QPen(QColor("#dc2626"), 2.4, Qt.SolidLine))
                n_muestras = 70
                pts_eq = []
                for k in range(n_muestras + 1):
                    qk = (k / n_muestras) * curva_eq.Q_max
                    hk = curva_eq.H_de_Q(qk)
                    pts_eq.append(a_pixel(qk, hk))

                for k in range(len(pts_eq) - 1):
                    p.drawLine(pts_eq[k], pts_eq[k + 1])

            # Leyenda Stitch en esquina superior derecha
            p.save()
            leg_w = 160.0
            leg_h = 24.0 if curva_eq is None else 40.0
            rect_leg = QRectF(m_left + plot_w - leg_w, m_top + 4.0, leg_w, leg_h)
            p.setPen(QPen(QColor("#dce9ff"), 1.0))
            p.setBrush(QBrush(QColor(255, 255, 255, 230)))
            p.drawRoundedRect(rect_leg, 4.0, 4.0)

            p.setFont(QFont("Segoe UI", 7))
            p.setPen(QPen(QColor("#006398"), 2.0))
            p.drawLine(QPointF(rect_leg.left() + 8.0, rect_leg.top() + 12.0), QPointF(rect_leg.left() + 22.0, rect_leg.top() + 12.0))
            p.setPen(QColor("#0b1c30"))
            p.drawText(QRectF(rect_leg.left() + 26.0, rect_leg.top() + 4.0, 62.0, 16.0), Qt.AlignVCenter | Qt.AlignLeft, "Curva H(Q)")

            p.setPen(QPen(QColor("#006398"), 1.8))
            p.setBrush(QBrush(QColor("#ffffff")))
            p.drawEllipse(QPointF(rect_leg.left() + 98.0, rect_leg.top() + 12.0), 3.0, 3.0)
            p.setPen(QColor("#0b1c30"))
            p.drawText(QRectF(rect_leg.left() + 106.0, rect_leg.top() + 4.0, 46.0, 16.0), Qt.AlignVCenter | Qt.AlignLeft, "Puntos")

            if curva_eq is not None:
                p.setPen(QPen(QColor("#dc2626"), 2.0))
                p.drawLine(QPointF(rect_leg.left() + 8.0, rect_leg.top() + 28.0), QPointF(rect_leg.left() + 22.0, rect_leg.top() + 28.0))
                p.setPen(QColor("#0b1c30"))
                p.drawText(QRectF(rect_leg.left() + 26.0, rect_leg.top() + 20.0, 70.0, 16.0), Qt.AlignVCenter | Qt.AlignLeft, "Equivalente")
            p.restore()
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            p.end()


class DialogoBomba(QDialog):
    """
    Diálogo interactivo para ingresar y configurar la curva de la bomba y sus arreglos (estilo Google Stitch).
    """

    MAX_BOMBAS = 4

    DEFAULT_BOMBA_A = {
        "H": [24.0, 21.0, 18.0, 15.0, 12.0, 9.0, 6.0],
        "Q": [0.0, 0.0736, 0.1115, 0.1402, 0.1612, 0.1737, 0.1765],
        "eta": [0.0, 59.0, 70.0, 76.0, 78.0, 76.3, 72.0],
        "npsh": [2.0, 2.5, 3.2, 4.0, 5.1, 6.5, 7.2],
    }
    DEFAULT_BOMBA_B = {
        "H": [21.0, 18.0, 15.0, 13.5, 12.0, 9.0, 6.0],
        "Q": [0.0, 0.0566, 0.0858, 0.0978, 0.1082, 0.1240, 0.1339],
        "eta": [0.0, 59.0, 70.0, 76.0, 78.0, 76.3, 72.0],
        "npsh": [1.8, 2.2, 2.9, 3.6, 4.5, 5.8, 6.5],
    }

    def __init__(self, bomba, parent=None, equipo=None, idx_equipo=0):
        super().__init__(parent)
        self.bomba = bomba
        if equipo is not None:
            self.equipo = equipo
            self.idx_equipo = idx_equipo
        elif hasattr(bomba, "equipos") and bomba.equipos:
            self.equipo = bomba.equipos[0]
            self.idx_equipo = 0
        else:
            self.equipo = {
                "nombre": bomba.nombre,
                "puntos": [],
                "H": [],
                "Q": [],
                "eta": [],
                "npsh": [],
                "curva": None,
            }
            self.idx_equipo = 0

        self.setWindowTitle(f"Curva de la bomba — {self.equipo.get('nombre', bomba.nombre)}")
        self.setModal(True)
        self.resize(560, 520)
        self.setMinimumSize(480, 440)

        self._construir_ui()
        self._cargar_datos_iniciales()
        self._refrescar_pildoras_bombas()
        self._refrescar_vista_previa()

    def _construir_ui(self):
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # -------------------------------------------------------------
        # 1. Cabecera del modal estilo Stitch
        # -------------------------------------------------------------
        frame_cabecera = QFrame()
        frame_cabecera.setObjectName("frameCabecera")
        frame_cabecera.setStyleSheet("""
            QFrame#frameCabecera {
                background-color: #eff4ff;
                border-bottom: 1px solid #dce9ff;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        layout_cab = QHBoxLayout(frame_cabecera)
        layout_cab.setContentsMargins(20, 14, 20, 14)
        layout_cab.setSpacing(14)

        caja_icono = QFrame()
        caja_icono.setObjectName("cajaIcono")
        caja_icono.setFixedSize(48, 48)
        caja_icono.setStyleSheet("""
            QFrame#cajaIcono {
                background-color: #0c4e77;
                border-radius: 10px;
                border: none;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        lay_ico = QVBoxLayout(caja_icono)
        lay_ico.setContentsMargins(0, 0, 0, 0)
        lbl_ico = QLabel()
        lbl_ico.setAlignment(Qt.AlignCenter)
        lbl_ico.setPixmap(crear_icono_herramienta("bomba", "#ffffff").pixmap(26, 26))
        lay_ico.addWidget(lbl_ico)
        layout_cab.addWidget(caja_icono)

        lay_textos = QVBoxLayout()
        lay_textos.setSpacing(3)

        row_titulo = QHBoxLayout()
        row_titulo.setSpacing(10)
        self.lbl_titulo = QLabel(f"Curva de la bomba — {self.equipo.get('nombre', self.bomba.nombre)}")
        self.lbl_titulo.setStyleSheet("color: #0b1c30; font-size: 18px; font-weight: 700; font-family: 'Segoe UI', sans-serif; border: none;")
        row_titulo.addWidget(self.lbl_titulo)

        badge_tipo = QLabel("BOMBA CENTRÍFUGA")
        badge_tipo.setStyleSheet("""
            background-color: #dce9ff;
            color: #0c4e77;
            font-size: 10px;
            font-weight: 700;
            font-family: 'Segoe UI', sans-serif;
            border-radius: 4px;
            padding: 3px 8px;
            border: none;
        """)
        row_titulo.addWidget(badge_tipo)
        row_titulo.addStretch()
        lay_textos.addLayout(row_titulo)

        lbl_sub = QLabel("Definición hidrodinámica del equipo y puntos de ensayo de catálogo")
        lbl_sub.setStyleSheet("color: #64748b; font-size: 11px; font-family: 'Segoe UI', sans-serif; border: none;")
        lay_textos.addWidget(lbl_sub)

        self.lbl_metodo_info = QLabel()
        self.lbl_metodo_info.setStyleSheet("color: #64748b; font-size: 11px; font-family: 'Segoe UI', sans-serif; border: none;")
        self._actualizar_texto_metodo()
        lay_textos.addWidget(self.lbl_metodo_info)

        layout_cab.addLayout(lay_textos)
        layout_cab.addStretch()
        layout_principal.addWidget(frame_cabecera)

        # -------------------------------------------------------------
        # 2. Barra de Parámetros Generales (Únicamente Elevación eje z)
        # -------------------------------------------------------------
        bar_params = QFrame()
        bar_params.setObjectName("barParams")
        bar_params.setStyleSheet("""
            QFrame#barParams {
                background-color: #f8f9ff;
                border-bottom: 1px solid #e2e8f0;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        lay_params = QHBoxLayout(bar_params)
        lay_params.setContentsMargins(20, 10, 20, 10)
        lay_params.setSpacing(12)

        # Controles ocultos para mantener compatibilidad interna
        self.campo_nombre = QLineEdit(self.bomba.nombre)
        self.campo_nombre.textChanged.connect(self._on_nombre_editado)
        self.campo_nombre.hide()

        self.combo_arreglo = QComboBox()
        self.combo_arreglo.addItems(["Individual", "Serie", "Paralelo"])
        idx_arr = ["individual", "serie", "paralelo"].index(self.bomba.arreglo.lower()) if self.bomba.arreglo.lower() in ["individual", "serie", "paralelo"] else 0
        self.combo_arreglo.setCurrentIndex(idx_arr)
        self.combo_arreglo.currentTextChanged.connect(self._on_arreglo_cambiado)
        self.combo_arreglo.hide()

        lbl_z = QLabel("Elevación eje z (m):")
        lbl_z.setStyleSheet("font-weight: 600; color: #0c4e77; font-size: 12px;")
        lay_params.addWidget(lbl_z)

        self.campo_z = QLineEdit(str(self.bomba.z_bomba))
        self.campo_z.setFixedHeight(28)
        self.campo_z.setFixedWidth(130)
        self.campo_z.setStyleSheet("""
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 3px 8px;
                color: #0b1c30;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                font-weight: 500;
            }
            QLineEdit:focus {
                border: 1px solid #006398;
            }
        """)
        self.campo_z.setPlaceholderText("0.00")
        lay_params.addWidget(self.campo_z)
        lay_params.addStretch()

        layout_principal.addWidget(bar_params)

        # -------------------------------------------------------------
        # 3. Contenedor central compacto (Modelo y Tabla de datos)
        # -------------------------------------------------------------
        panel_central = QWidget()
        lay_izq = QVBoxLayout(panel_central)
        lay_izq.setContentsMargins(20, 14, 20, 14)
        lay_izq.setSpacing(10)

        # Contenedor oculto de píldoras para compatibilidad
        self.frame_pildoras = QWidget()
        self.lay_pildoras = QHBoxLayout(self.frame_pildoras)
        self.frame_pildoras.hide()
        self.btn_agregar_bomba = QPushButton("+")
        self.btn_agregar_bomba.setEnabled(False)
        self.btn_agregar_bomba.clicked.connect(self._agregar_bomba)
        self.btn_agregar_bomba.hide()

        # QTabWidget (con barra de tabs nativa oculta)
        self.tabs_bombas = QTabWidget()
        self.tabs_bombas.tabBar().hide()
        self.tabs_bombas.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: transparent;
            }
        """)
        self.tabs_bombas.currentChanged.connect(self._on_tab_cambiado)
        lay_izq.addWidget(self.tabs_bombas, 1)

        layout_principal.addWidget(panel_central, 1)

        # Instancias ocultas de compatibilidad
        self.preview_curva = WidgetPreviewCurva()
        self.preview = self.preview_curva
        self.preview_curva.hide()
        self.lbl_ecuacion = QLabel("H = —")
        self.lbl_r2 = QLabel("R² = —")
        self.lbl_detalle_eq = QLabel("")

        # -------------------------------------------------------------
        # 4. Pie del Modal (Únicamente botones Cancelar y Aceptar)
        # -------------------------------------------------------------
        frame_pie = QFrame()
        frame_pie.setObjectName("framePie")
        frame_pie.setStyleSheet("""
            QFrame#framePie {
                background-color: #eff4ff;
                border-top: 1px solid #dce9ff;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        layout_pie = QHBoxLayout(frame_pie)
        layout_pie.setContentsMargins(20, 12, 20, 12)
        layout_pie.setSpacing(12)

        self.lbl_pie_puntos = QLabel("")
        self.lbl_puntos = self.lbl_pie_puntos
        self.lbl_pie_puntos.hide()
        layout_pie.addStretch()

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setFixedHeight(36)
        self.btn_cancelar.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                color: #0b1c30;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 500;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 6px 20px;
            }
            QPushButton:hover {
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }
        """)
        self.btn_cancelar.clicked.connect(self.reject)
        layout_pie.addWidget(self.btn_cancelar)

        self.btn_aceptar = QPushButton("✓  Aceptar")
        self.btn_aceptar.setFixedHeight(36)
        self.btn_aceptar.setStyleSheet("""
            QPushButton {
                background-color: #0c4e77;
                color: #ffffff;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 6px 24px;
            }
            QPushButton:hover {
                background-color: #006398;
            }
            QPushButton:pressed {
                background-color: #0b1c30;
            }
        """)
        self.btn_aceptar.clicked.connect(self._validar_y_aceptar)
        layout_pie.addWidget(self.btn_aceptar)

        layout_principal.addWidget(frame_pie)

    def _on_nombre_editado(self, texto):
        self.lbl_titulo.setText(f"Curva de la bomba — {texto.strip() or 'Bomba'}")

    def _actualizar_texto_metodo(self):
        m = getattr(self.bomba, "metodo", "cuadratico")
        m_txt = "Interpolación lineal" if str(m).lower() == "lineal" else "Ajuste cuadrático"
        if hasattr(self, "lbl_metodo_info"):
            self.lbl_metodo_info.setText(f"Método de la curva: {m_txt} (se cambia en las propiedades de la bomba)")

    def _refrescar_pildoras_bombas(self):
        """Mantiene sincronizado el estado de botones ocultos de bombas."""
        arr = self.combo_arreglo.currentText().lower()
        n = self.tabs_bombas.count()
        if hasattr(self, "btn_agregar_bomba") and self.btn_agregar_bomba:
            self.btn_agregar_bomba.setEnabled(n < self.MAX_BOMBAS and arr != "individual")

    def _on_tab_cambiado(self, idx):
        self._refrescar_pildoras_bombas()
        self._refrescar_vista_previa()

    def _crear_tab_bomba(self, nombre_tab):
        """Crea el contenido de una pestaña de bomba con su tabla y botones de fila."""
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(8)

        tabla = TablaCurvaBomba()
        lay.addWidget(tabla, 1)

        # Barra de botones de fila (+ Fila, − Fila y Cargar Ejemplo)
        barra_filas = QHBoxLayout()
        barra_filas.setSpacing(8)

        btn_add = QPushButton("  + Fila")
        btn_add.setFixedHeight(28)
        btn_add.setStyleSheet("""
            QPushButton {
                background-color: #eff4ff;
                color: #0c4e77;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #c4e1ff;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #dce9ff;
            }
        """)
        btn_add.clicked.connect(lambda: tabla.agregar_fila())
        barra_filas.addWidget(btn_add)

        btn_del = QPushButton("  − Fila")
        btn_del.setFixedHeight(28)
        btn_del.setStyleSheet("""
            QPushButton {
                background-color: #eff4ff;
                color: #ba1a1a;
                font-weight: 600;
                font-size: 11px;
                border: 1px solid #ffdad6;
                border-radius: 6px;
                padding: 4px 10px;
            }
            QPushButton:hover {
                background-color: #ffdad6;
            }
        """)
        btn_del.clicked.connect(tabla.quitar_fila_seleccionada)
        barra_filas.addWidget(btn_del)

        barra_filas.addStretch()

        btn_ejemplo = QPushButton("Cargar Ejemplo")
        btn_ejemplo.setFixedHeight(28)
        btn_ejemplo.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #006398;
                font-weight: 600;
                font-size: 11px;
                border: none;
                padding: 4px 8px;
            }
            QPushButton:hover {
                text-decoration: underline;
                color: #0c4e77;
            }
        """)
        btn_ejemplo.clicked.connect(lambda: self._cargar_ejemplo(tabla, self.tabs_bombas.indexOf(tab)))
        barra_filas.addWidget(btn_ejemplo)

        lay.addLayout(barra_filas)

        # Franja KPI oculta para compatibilidad
        kpi_strip = FranjaKPI()
        kpi_strip.hide()
        tabla.datos_cambiados.connect(self._refrescar_vista_previa)

        tab.tabla = tabla
        tab.kpi_strip = kpi_strip
        return tab

    def cargar_ejemplo(self):
        curr = self.tabs_bombas.currentWidget()
        if curr is not None and hasattr(curr, "tabla"):
            self._cargar_ejemplo(curr.tabla, getattr(self, "idx_equipo", 0))

    def _cargar_ejemplo(self, tabla, tab_idx):
        datos = self.DEFAULT_BOMBA_A if tab_idx == 0 else self.DEFAULT_BOMBA_B
        tabla.cargar_datos(datos["H"], datos["Q"], datos["eta"], datos["npsh"])

    def _cargar_datos_iniciales(self):
        """Carga la curva guardada para el equipo actual o inicializa con tabla vacía."""
        nom_tab = nombre_equipo_bomba(self.equipo,curva=self.equipo.get('curva'),indice=self.idx_equipo,
            nombre_estacion=self.bomba.nombre)
        tab = self._crear_tab_bomba(nom_tab)
        self.tabs_bombas.addTab(tab, nom_tab)

        if self.equipo.get("H") and self.equipo.get("Q"):
            tab.tabla.cargar_datos(
                self.equipo["H"],
                self.equipo["Q"],
                self.equipo.get("eta"),
                self.equipo.get("npsh"),
            )
        elif self.equipo.get("curva") is not None:
            c = self.equipo["curva"]
            eta_data = c.eta_raw if (getattr(c, "tiene_eficiencia", False) and hasattr(c, "eta_raw")) else (c.eta if getattr(c, "tiene_eficiencia", False) else None)
            npsh_data = c.npsh_r if getattr(c, "tiene_npshr", False) else None
            tab.tabla.cargar_datos(c.H, c.Q, eta_data, npsh_data)
        else:
            # Bomba nueva sin datos: empieza con tabla vacía
            tab.tabla.setRowCount(0)

        self._actualizar_botones_bombas()

    def _on_arreglo_cambiado(self, texto):
        arr = texto.lower()
        if arr == "individual":
            while self.tabs_bombas.count() > 1:
                self.tabs_bombas.removeTab(self.tabs_bombas.count() - 1)
        elif arr in ("serie", "paralelo"):
            if self.tabs_bombas.count() < 2:
                tab2 = self._crear_tab_bomba(f"Bomba {self.tabs_bombas.count() + 1}")
                self.tabs_bombas.addTab(tab2, f"Bomba {self.tabs_bombas.count()}")

        self._actualizar_botones_bombas()
        self._refrescar_pildoras_bombas()
        self._refrescar_vista_previa()

    def _actualizar_botones_bombas(self):
        arr = self.combo_arreglo.currentText().lower()
        n = self.tabs_bombas.count()
        if hasattr(self, "btn_agregar_bomba") and self.btn_agregar_bomba:
            self.btn_agregar_bomba.setEnabled(n < self.MAX_BOMBAS and arr != "individual")

    def _agregar_bomba(self):
        if self.tabs_bombas.count() >= self.MAX_BOMBAS:
            return
        idx = self.tabs_bombas.count() + 1
        tab = self._crear_tab_bomba(f"Bomba {idx}")
        self.tabs_bombas.addTab(tab, f"Bomba {idx}")
        self.tabs_bombas.setCurrentWidget(tab)
        self._actualizar_botones_bombas()
        self._refrescar_pildoras_bombas()
        self._refrescar_vista_previa()

    def _quitar_bomba(self):
        cur_idx = self.tabs_bombas.currentIndex()
        self._quitar_bomba_idx(cur_idx)

    def _quitar_bomba_idx(self, idx):
        arr = self.combo_arreglo.currentText().lower()
        min_tabs = 2 if arr in ("serie", "paralelo") else 1
        if self.tabs_bombas.count() <= min_tabs:
            return
        if 0 <= idx < self.tabs_bombas.count():
            self.tabs_bombas.removeTab(idx)
        self._actualizar_botones_bombas()
        self._refrescar_pildoras_bombas()
        self._refrescar_vista_previa()

    def _refrescar_vista_previa(self):
        """Intenta armar las CurvaBomba con los datos actuales y actualiza la vista previa."""
        curvas_temporales = []
        metodo = getattr(self.bomba, "metodo", "cuadratico")
        modo = "ajuste" if metodo == "cuadratico" else "interpolacion"

        for idx in range(self.tabs_bombas.count()):
            tab = self.tabs_bombas.widget(idx)
            try:
                H_l, Q_l, eta_l, npsh_l = tab.tabla.obtener_datos()
                if len(Q_l) >= 2:
                    cb = CurvaBomba(
                        self.tabs_bombas.tabText(idx),
                        Q_l,
                        H_l,
                        eta_l,
                        npsh_r=npsh_l,
                        metodo=metodo,
                    )
                    cb.nombre = self.tabs_bombas.tabText(idx)
                    curvas_temporales.append(cb)
            except Exception:
                pass

        arr = self.combo_arreglo.currentText().lower()
        self.preview_curva.actualizar(curvas_temporales, arreglo=arr, modo=modo)
        self._actualizar_texto_metodo()

        # Actualizar tarjeta de ecuación
        txt_eq, txt_r2 = self.preview_curva.info_ecuacion
        self.lbl_ecuacion.setText(txt_eq)
        self.lbl_r2.setText(txt_r2)
        if metodo == "cuadratico":
            self.lbl_detalle_eq.setText("Modelo activo: Parábola ajustada OLS (H = a + c·Q²)")
        else:
            self.lbl_detalle_eq.setText('Modelo activo: interpolación lineal entre puntos')
        notas = [nota_joroba(c) for c in curvas_temporales if nota_joroba(c)]
        if notas:
            self.lbl_detalle_eq.setText(self.lbl_detalle_eq.text()+'; '+'; '.join(notas))

        # Actualizar contador de puntos en el pie
        cur_tab = self.tabs_bombas.currentWidget()
        n_pts = cur_tab.tabla.rowCount() if cur_tab and hasattr(cur_tab, "tabla") else 0
        self.lbl_pie_puntos.setText(f"{n_pts} puntos cargados · Régimen nominal 2900 RPM")

    def _validar_y_aceptar(self):
        """Valida que todos los datos y tablas sean correctos antes de cerrar."""
        # 1. Nombre
        nombre = self.campo_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Nombre requerido", "Ingresa un nombre para la bomba.")
            self.campo_nombre.setFocus()
            return

        # 2. Cota z_bomba
        txt_z = self.campo_z.text().strip().replace(",", ".")
        try:
            z_bomba = float(txt_z)
        except ValueError:
            QMessageBox.warning(
                self,
                "Cota inválida",
                "La elevación del eje z_bomba debe ser un valor numérico (en metros).",
            )
            self.campo_z.setFocus()
            return

        # 3. Arreglo y método
        arreglo = self.combo_arreglo.currentText().lower()
        metodo = getattr(self.bomba, "metodo", "cuadratico")

        # 4. Validar tablas de cada bomba
        lista_curvas = []
        for idx in range(self.tabs_bombas.count()):
            tab = self.tabs_bombas.widget(idx)
            nombre_tab = self.tabs_bombas.tabText(idx)
            try:
                H_l, Q_l, eta_l, npsh_l = tab.tabla.obtener_datos()
            except ValueError as err:
                QMessageBox.warning(self, f"Error en {nombre_tab}", str(err))
                self.tabs_bombas.setCurrentWidget(tab)
                return

            if len(Q_l) < 2:
                QMessageBox.warning(
                    self,
                    f"Datos insuficientes en {nombre_tab}",
                    f"Se requieren al menos 2 puntos válidos de (H, Q) para definir la curva.\n"
                    f"Actualmente hay {len(Q_l)} puntos.",
                )
                self.tabs_bombas.setCurrentWidget(tab)
                return

            try:
                cb = CurvaBomba(nombre_tab, Q_l, H_l, eta_l, npsh_r=npsh_l, metodo=metodo)
                cb.nombre = nombre_tab
                lista_curvas.append(cb)
            except ValueError as err:
                QMessageBox.warning(
                    self,
                    f"Curva inconsistente en {nombre_tab}",
                    f"Error al construir la curva:\n{err}",
                )
                self.tabs_bombas.setCurrentWidget(tab)
                return

        if self.tabs_bombas.count() > 1 and arreglo in ("serie", "paralelo") and len(lista_curvas) < 2:
            QMessageBox.warning(
                self,
                "Arreglo incompleto",
                f"El arreglo en {arreglo} requiere al menos 2 bombas definidas.",
            )
            return

        # Guardar en el equipo editado
        tab0 = self.tabs_bombas.widget(0)
        H_l, Q_l, eta_l, npsh_l = tab0.tabla.obtener_datos()
        cb = lista_curvas[0] if lista_curvas else None

        self.equipo["nombre"] = self.tabs_bombas.tabText(0)
        self.equipo["H"] = H_l
        self.equipo["Q"] = Q_l
        self.equipo["eta"] = eta_l
        self.equipo["npsh"] = npsh_l
        self.equipo["curva"] = cb
        self.equipo.pop("modo", None)
        self.equipo.pop("metodo", None)
        self.equipo["puntos"] = [
            (q, h, (e / 100.0 if e is not None and e > 1.0 else e))
            for q, h, e in zip(Q_l, H_l, eta_l or [None] * len(Q_l))
        ]

        # Guardar en la BombaGrafica
        self.bomba.nombre = nombre
        self.bomba.z_bomba = z_bomba
        if len(getattr(self.bomba, "equipos", [])) <= 1:
            self.bomba.arreglo = arreglo
        if hasattr(self.bomba, "equipos") and self.equipo not in self.bomba.equipos:
            self.bomba.equipos.append(self.equipo)
        self.bomba.curvas = [eq["curva"] for eq in getattr(self.bomba, "equipos", []) if eq.get("curva") is not None]
        self.bomba.actualizar_tooltip()

        self.accept()

