"""Panel lateral de propiedades del elemento seleccionado."""

import math
import traceback

from PyQt5 import QtGui
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsItem,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.dialogos import DialogoBomba
from ui.graficos import (
    AccesorioGrafico,
    BombaGrafica,
    CuadroTextoGrafico,
    FormaGrafica,
    K_ENTRADA_TANQUE,
    NodoUnionGrafico,
    TanqueGrafico,
    TuberiaGrafica,
    normalizar_conexion_tanque,
)
from ui.constantes import COLORES_TEXTO, formatear_numero
from ui.curvas_presentacion import usa_puntos,puntos_tabla,resumen_puntos,nota_joroba
from ui.nombres_bombas import nombre_equipo_bomba
from ui.validacion_datos import validar_propiedad
from ui.ventana.invalidacion import bloquear_senales, invalidar_resultados
from ui.transiciones import revelar_contenido


class PanelPropiedadesMixin:
    """Panel lateral de propiedades del elemento seleccionado."""

    def _on_seleccion_cambiada(self):
        seleccionados = self.canvas_view.scene().selectedItems()
        # Una selección anterior de bomba no es la selección actual del lienzo.
        self.bomba_seleccionada = None
        self.campos_bomba = {}
        self.nodo_union_seleccionado = None
        self.forma_seleccionada = None
        if self.texto_seleccionado is not None:
            self.texto_seleccionado._callback_cambio = None
        self.texto_seleccionado = None

        if len(seleccionados) == 1 and isinstance(seleccionados[0], TuberiaGrafica):
            self.tuberia_seleccionada = seleccionados[0]
            self.tanque_seleccionado = None
            self.accesorio_seleccionado = None
            self.canvas_view.set_seleccion_hud(self.tuberia_seleccionada.nombre)
            self._mostrar_campos_tuberia(self.tuberia_seleccionada)
        elif len(seleccionados) == 1 and isinstance(seleccionados[0], TanqueGrafico):
            self.tuberia_seleccionada = None
            self.tanque_seleccionado = seleccionados[0]
            self.accesorio_seleccionado = None
            self.canvas_view.set_seleccion_hud(self.tanque_seleccionado.nombre)
            self._mostrar_campos_tanque(self.tanque_seleccionado)
        elif len(seleccionados) == 1 and isinstance(seleccionados[0], BombaGrafica):
            self.tuberia_seleccionada = None
            self.tanque_seleccionado = None
            self.accesorio_seleccionado = None
            self.bomba_seleccionada = seleccionados[0]
            self.canvas_view.set_seleccion_hud(self.bomba_seleccionada.nombre)
            self._mostrar_campos_bomba(self.bomba_seleccionada)
        elif len(seleccionados) == 1 and isinstance(seleccionados[0], AccesorioGrafico):
            self.tuberia_seleccionada = None
            self.tanque_seleccionado = None
            self.accesorio_seleccionado = seleccionados[0]
            self.canvas_view.set_seleccion_hud(
                'Pérdida en esquina' if getattr(self.accesorio_seleccionado, 'esquina_indice', None) is not None
                else self.accesorio_seleccionado.forma_visual)
            self._mostrar_campos_accesorio(self.accesorio_seleccionado)
        elif len(seleccionados) == 1 and isinstance(seleccionados[0], NodoUnionGrafico):
            self.tuberia_seleccionada = None
            self.tanque_seleccionado = None
            self.accesorio_seleccionado = None
            self.nodo_union_seleccionado = seleccionados[0]
            self.canvas_view.set_seleccion_hud(self.nodo_union_seleccionado.nombre)
            self._mostrar_campos_nodo_union(self.nodo_union_seleccionado)
        elif len(seleccionados) == 1 and isinstance(seleccionados[0], FormaGrafica):
            self.tuberia_seleccionada = None
            self.tanque_seleccionado = None
            self.accesorio_seleccionado = None
            self.forma_seleccionada = seleccionados[0]
            self.canvas_view.set_seleccion_hud(self.forma_seleccionada.tipo_forma)
            self._mostrar_campos_forma(self.forma_seleccionada)
        elif len(seleccionados) == 1 and isinstance(seleccionados[0], CuadroTextoGrafico):
            self.tuberia_seleccionada = None
            self.tanque_seleccionado = None
            self.accesorio_seleccionado = None
            self.texto_seleccionado = seleccionados[0]
            self.canvas_view.set_seleccion_hud("Texto")
            self._mostrar_campos_texto(self.texto_seleccionado)
        else:
            self.tuberia_seleccionada = None
            self.tanque_seleccionado = None
            self.accesorio_seleccionado = None
            if len(seleccionados) > 1:
                self.canvas_view.set_seleccion_hud(f"{len(seleccionados)} elementos")
            else:
                self.canvas_view.set_seleccion_hud("Ninguna")
            self._mostrar_dashboard()

        revelar_contenido(self.panel_scroll.viewport())

    def _on_elementos_modificados(self):
        if getattr(self, '_cargando_proyecto', False) or getattr(self, '_invalidando_resultados', False):
            return
        scene = self.canvas_view.scene()
        invalidar_resultados(getattr(scene, 'items', lambda: [])(), self)
        if hasattr(self, 'historial'):
            self.historial.programar()
        if not getattr(scene, 'selectedItems', lambda: [None])():
            self._mostrar_dashboard()

    def _mostrar_campos_tuberia(self, tuberia):
        if hasattr(self, "lbl_panel_subtitle"):
            self.lbl_panel_subtitle.setText("PROPIEDADES DEL ELEMENTO")
        if hasattr(self, 'lbl_panel_title'):
            self.lbl_panel_title.setText(f"Propiedades de la {tuberia.nombre}")
        self._limpiar_panel_content()
        self.campos_tanque = {}
        self.campos_accesorio = {}
        self.campos_forma = {}

        encabezado = QLabel("Elemento seleccionado: Tubería")
        encabezado.setObjectName("panelLabel")
        encabezado.setWordWrap(True)
        self.panel_content_layout.addWidget(encabezado)

        definicion_campos = (
            ("Q", "Caudal Q", "caudal_Q", "u_Q", self.UNIDADES_Q),
            ("L", "Longitud L", "longitud", "u_L", self.UNIDADES_L),
            ("D", "Diámetro D", "diametro", "u_D", self.UNIDADES_D),
            ("epsilon", "Rugosidad ε", "rugosidad", "u_eps", self.UNIDADES_EPSILON),
        )

        self.campos_tuberia = {}
        for clave, etiqueta_texto, atributo, atributo_unidad, opciones in definicion_campos:
            etiqueta = QLabel(etiqueta_texto)
            etiqueta.setObjectName("panelLabel")
            self.panel_content_layout.addWidget(etiqueta)

            campo = QLineEdit()
            campo.setObjectName("panelLineEdit")
            valor_actual = getattr(tuberia, atributo)
            if valor_actual:
                campo.setText(str(valor_actual))

            refrescar = atributo in ("longitud", "diametro")
            campo.textEdited.connect(
                lambda texto, t=tuberia, a=atributo, r=refrescar: self._guardar_campo_numerico(
                    t, a, texto, r
                )
            )

            combo = QComboBox()
            combo.setObjectName("panelComboBox")
            combo.addItems(opciones)
            combo.setCurrentText(getattr(tuberia, atributo_unidad))
            combo.currentTextChanged.connect(
                lambda texto, t=tuberia, a=atributo_unidad, r=refrescar: self._guardar_unidad(
                    t, a, texto, r
                )
            )

            fila = QWidget()
            fila_layout = QHBoxLayout(fila)
            fila_layout.setContentsMargins(0, 0, 0, 0)
            fila_layout.setSpacing(6)
            fila_layout.addWidget(campo, 1)
            fila_layout.addWidget(combo)
            self.panel_content_layout.addWidget(fila)

            self.campos_tuberia[clave] = campo

        k_acc = getattr(tuberia, "sumatoria_K_accesorios", tuberia.sumatoria_K)
        label_accesorios = QLabel(
            f"Accesorios conectados: K total = {formatear_numero(k_acc)}, "
            f"Le/D total = {formatear_numero(tuberia.sumatoria_Le_D)}"
        )
        label_accesorios.setObjectName("panelLabel")
        label_accesorios.setWordWrap(True)
        self.panel_content_layout.addWidget(label_accesorios)
        self.label_accesorios_tuberia = label_accesorios

        self.label_hf_tuberia = QLabel()
        self.label_hf_tuberia.setObjectName("panelLabel")
        self.label_hf_tuberia.setWordWrap(True)
        self.panel_content_layout.addWidget(self.label_hf_tuberia)
        self._refrescar_label_hf(tuberia)

        boton_color = QPushButton("Cambiar Color")
        boton_color.setObjectName("colorButton")
        boton_color.setCursor(Qt.PointingHandCursor)
        self.panel_content_layout.addWidget(boton_color)
        boton_color.clicked.connect(
            lambda _checked=False, t=tuberia: self._cambiar_color(
                t,
                "color_personalizado",
                t.color_personalizado if t.color_personalizado is not None else t.pen().color(),
            )
        )

    def _mostrar_campos_accesorio(self, accesorio):
        es_esquina = getattr(accesorio, 'esquina_indice', None) is not None
        if hasattr(self, "lbl_panel_subtitle"):
            self.lbl_panel_subtitle.setText("PROPIEDADES DEL ELEMENTO")
        if hasattr(self, 'lbl_panel_title'):
            self.lbl_panel_title.setText("Pérdida en esquina" if es_esquina else "Propiedades del Accesorio")
        self._limpiar_panel_content()
        self.campos_tuberia = {}
        self.campos_tanque = {}
        self.campos_forma = {}

        encabezado = QLabel(
            f"{accesorio.tuberia_padre.nombre} · Esquina {accesorio.esquina_indice}" if es_esquina
            else "Elemento seleccionado: Accesorio")
        encabezado.setObjectName("panelLabel")
        encabezado.setWordWrap(True)
        self.panel_content_layout.addWidget(encabezado)

        etiqueta_forma = QLabel("Forma visual")
        etiqueta_forma.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(etiqueta_forma)

        combo_forma = QComboBox()
        combo_forma.setObjectName("panelComboBox")
        if es_esquina:
            combo_forma.addItem('Pérdida en esquina')
            combo_forma.setEnabled(False)
        else:
            combo_forma.addItems(AccesorioGrafico.FORMAS)
            combo_forma.setCurrentText(accesorio.forma_visual)
        self.panel_content_layout.addWidget(combo_forma)
        if es_esquina:
            etiqueta_forma.hide()
            combo_forma.hide()

        etiqueta_tipo = QLabel("Tipo de pérdida")
        etiqueta_tipo.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(etiqueta_tipo)

        combo_tipo = QComboBox()
        combo_tipo.setObjectName("panelComboBox")
        combo_tipo.addItems(AccesorioGrafico.TIPOS_PERDIDA)
        combo_tipo.setCurrentText(accesorio.tipo_perdida)
        self.panel_content_layout.addWidget(combo_tipo)

        etiqueta_valor = QLabel("Valor numérico")
        etiqueta_valor.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(etiqueta_valor)

        campo_valor = QLineEdit()
        campo_valor.setObjectName("panelLineEdit")
        if accesorio.valor:
            campo_valor.setText(str(accesorio.valor))
        self.panel_content_layout.addWidget(campo_valor)

        self.campos_accesorio = {
            "forma": combo_forma,
            "tipo": combo_tipo,
            "valor": campo_valor,
        }

        combo_forma.currentTextChanged.connect(
            lambda texto, a=accesorio: self._on_forma_accesorio_cambiada(a, texto)
        )
        combo_tipo.currentTextChanged.connect(
            lambda texto, a=accesorio: self._on_tipo_accesorio_cambiado(a, texto)
        )
        campo_valor.textChanged.connect(
            lambda texto, a=accesorio: self._guardar_campo_numerico(a, "valor", texto)
        )

    def _on_forma_accesorio_cambiada(self, accesorio, forma):
        accesorio.forma_visual = forma
        if forma in AccesorioGrafico.FORMAS_DIVISORAS and accesorio.tuberia_padre is not None:
            accesorio.insertar_en(accesorio.tuberia_padre)
        elif accesorio.tuberia_padre is not None:
            accesorio.setFlag(
                QGraphicsItem.ItemIsMovable,
                forma == "Codo" or getattr(accesorio.tuberia_padre, "modo_trazado", "recto") == "ortogonal",
            )
        accesorio.update()
        self._on_elementos_modificados()

    def _on_tipo_accesorio_cambiado(self, accesorio, texto):
        setattr(accesorio, "tipo_perdida", texto)
        padre = getattr(accesorio, 'tuberia_padre', None)
        if padre is not None and hasattr(padre, '_sincronizar_botones_esquina'):
            padre._sincronizar_botones_esquina()
        self._on_elementos_modificados()

    def _limpiar_layout_propiedades(self):
        """Elimina todos los widgets y sub-layouts del layout contenedor de propiedades."""
        self._limpiar_panel_content()

    def _mostrar_propiedades_bomba(self, bomba):
        """Alias para _mostrar_campos_bomba."""
        self._mostrar_campos_bomba(bomba)

    def _mostrar_campos_bomba(self, bomba):
        try:
            if hasattr(self, "lbl_panel_subtitle"):
                self.lbl_panel_subtitle.setText("PROPIEDADES DEL ELEMENTO")
            if hasattr(self, "lbl_panel_title"):
                self.lbl_panel_title.setText(f"Propiedades de la {bomba.nombre}")
            self._limpiar_panel_content()
            self.campos_tuberia = {}
            self.campos_tanque = {}
            self.campos_accesorio = {}
            self.campos_nodo_union = {}
            self.campos_forma = {}

            encabezado = QLabel(f"Elemento seleccionado: {bomba.nombre}")
            encabezado.setObjectName("panelLabel")
            encabezado.setStyleSheet("font-weight: 600; color: #0c4e77; font-size: 13px;")
            encabezado.setWordWrap(True)
            self.panel_content_layout.addWidget(encabezado)

            # 1. Nombre
            etiqueta_nombre = QLabel("Nombre de la bomba")
            etiqueta_nombre.setObjectName("panelLabel")
            self.panel_content_layout.addWidget(etiqueta_nombre)

            campo_nombre = QLineEdit()
            campo_nombre.setObjectName("panelLineEdit")
            campo_nombre.setText(bomba.nombre)
            self.panel_content_layout.addWidget(campo_nombre)

            # 2. Cota de eje z_bomba
            etiqueta_z = QLabel("Cota del eje z_bomba (m)")
            etiqueta_z.setObjectName("panelLabel")
            self.panel_content_layout.addWidget(etiqueta_z)

            campo_z = QLineEdit()
            campo_z.setObjectName("panelLineEdit")
            campo_z.setText(str(bomba.z_bomba))
            self.panel_content_layout.addWidget(campo_z)

            # 3. Sección Equipos de Bombeo (Estilo Stitch)
            sec_equipos = QFrame()
            sec_equipos.setStyleSheet("""
                QFrame {
                    background-color: #f8fafc;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                }
            """)
            lay_sec = QVBoxLayout(sec_equipos)
            lay_sec.setContentsMargins(8, 8, 8, 8)
            lay_sec.setSpacing(6)

            tit_equipos = QLabel("EQUIPOS DE BOMBEO")
            tit_equipos.setStyleSheet("font-weight: 700; color: #0c4e77; font-size: 11px; letter-spacing: 0.5px; border: none; background: transparent;")
            lay_sec.addWidget(tit_equipos)

            # Selector Método de la curva (Estación)
            frame_metodo = QWidget()
            frame_metodo.setStyleSheet("border: none; background: transparent;")
            lay_metodo = QVBoxLayout(frame_metodo)
            lay_metodo.setContentsMargins(0, 0, 0, 0)
            lay_metodo.setSpacing(2)

            lay_met_top = QHBoxLayout()
            lay_met_top.setContentsMargins(0, 0, 0, 0)
            lay_met_top.setSpacing(6)
            lbl_met_tit = QLabel("Método de la curva:")
            lbl_met_tit.setStyleSheet("font-weight: 600; color: #334155; font-size: 11px; border: none;")

            combo_metodo = QComboBox()
            combo_metodo.setObjectName("comboMetodoCurva")
            combo_metodo.addItems(["Ajuste cuadrático", "Interpolación lineal"])
            metodo_actual = getattr(bomba, "metodo", "cuadratico")
            idx_met = 1 if metodo_actual == "lineal" else 0
            combo_metodo.blockSignals(True)
            combo_metodo.setCurrentIndex(idx_met)
            combo_metodo.blockSignals(False)
            combo_metodo.setFixedHeight(26)
            combo_metodo.setStyleSheet("""
                QComboBox {
                    background-color: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: 600;
                    color: #0c4e77;
                }
            """)
            combo_metodo.currentTextChanged.connect(
                lambda txt, b=bomba: self._on_metodo_bomba_cambiado(b, txt)
            )
            lay_met_top.addWidget(lbl_met_tit)
            lay_met_top.addWidget(combo_metodo)
            lay_met_top.addStretch()
            lay_metodo.addLayout(lay_met_top)

            lbl_met_ayuda = QLabel('Interpolación lineal entre los puntos de la tabla.' if usa_puntos(bomba.curvas,metodo_actual)
                                  else 'Ajuste cuadrático: H = a + b·Q + c·Q².')
            lbl_met_ayuda.setStyleSheet("color: #64748b; font-size: 10px; border: none; background: transparent;")
            lbl_met_ayuda.setWordWrap(True)
            lay_metodo.addWidget(lbl_met_ayuda)
            lay_sec.addWidget(frame_metodo)

            # Selector de Arreglo (visible cuando hay 2 o más equipos)
            num_eq = len(getattr(bomba, "equipos", []))
            frame_arr = QWidget()
            frame_arr.setStyleSheet("border: none; background: transparent;")
            lay_arr = QHBoxLayout(frame_arr)
            lay_arr.setContentsMargins(0, 0, 0, 0)
            lay_arr.setSpacing(6)

            lbl_arr_tit = QLabel("Arreglo:")
            lbl_arr_tit.setStyleSheet("font-weight: 600; color: #334155; font-size: 11px; border: none;")
            combo_arr = QComboBox()
            combo_arr.addItems(["Paralelo", "Serie"])
            idx_cur_arr = 1 if bomba.arreglo.lower() == "serie" else 0
            combo_arr.blockSignals(True)
            combo_arr.setCurrentIndex(idx_cur_arr)
            combo_arr.blockSignals(False)
            combo_arr.setFixedHeight(26)
            combo_arr.setStyleSheet("""
                QComboBox {
                    background-color: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: 600;
                    color: #0c4e77;
                }
            """)
            combo_arr.currentTextChanged.connect(
                lambda txt, b=bomba: self._on_arreglo_bomba_cambiado(b, txt.lower())
            )
            lay_arr.addWidget(lbl_arr_tit)
            lay_arr.addWidget(combo_arr)
            lay_arr.addStretch()
            lay_sec.addWidget(frame_arr)

            # Selector Arreglo: Paralelo / Serie visible cuando hay 2 o más equipos
            frame_arr.setVisible(num_eq >= 2)

            # Lista de equipos (Bomba A, Bomba B...) con botón "Editar curva" por equipo
            for idx_eq, eq in enumerate(getattr(bomba, "equipos", [])):
                row_eq = QFrame()
                row_eq.setStyleSheet("""
                    QFrame {
                        background-color: #ffffff;
                        border: 1px solid #e2e8f0;
                        border-radius: 6px;
                    }
                """)
                lay_row_eq = QVBoxLayout(row_eq)
                lay_row_eq.setContentsMargins(8, 5, 8, 5)
                lay_row_eq.setSpacing(3)

                f_top_eq = QWidget()
                f_top_eq.setStyleSheet("border: none; background: transparent;")
                lay_top_eq = QHBoxLayout(f_top_eq)
                lay_top_eq.setContentsMargins(0, 0, 0, 0)
                lay_top_eq.setSpacing(6)

                nom_eq = nombre_equipo_bomba(eq,curva=eq.get('curva'),indice=idx_eq,
                    nombre_estacion=bomba.nombre if num_eq==1 else None)
                lbl_nom_eq = QLabel(f"<b>{nom_eq}</b>")
                lbl_nom_eq.setStyleSheet("color: #0b1c30; font-size: 11px; border: none; background: transparent;")
                lay_top_eq.addWidget(lbl_nom_eq)

                tiene_curva = (eq.get("curva") is not None)
                badge_eq = QLabel("✓ Curva" if tiene_curva else "⚠ Sin curva")
                badge_eq.setStyleSheet(
                    "color: #16a34a; font-size: 10px; font-weight: 600; border: none; background: transparent;"
                    if tiene_curva
                    else "color: #d97706; font-size: 10px; font-weight: 600; border: none; background: transparent;"
                )
                lay_top_eq.addWidget(badge_eq)
                lay_top_eq.addStretch()

                btn_edit_eq = QPushButton("⚙ Editar curva")
                btn_edit_eq.setFixedHeight(24)
                btn_edit_eq.setCursor(Qt.PointingHandCursor)
                btn_edit_eq.setStyleSheet("""
                    QPushButton {
                        background-color: #eff4ff;
                        color: #0c4e77;
                        font-weight: 600;
                        font-size: 10px;
                        border: 1px solid #c4e1ff;
                        border-radius: 4px;
                        padding: 2px 8px;
                    }
                    QPushButton:hover {
                        background-color: #dce9ff;
                    }
                """)
                btn_edit_eq.clicked.connect(
                    lambda _, b=bomba, e=eq, i=idx_eq: self._abrir_dialogo_bomba_equipo(b, e, i)
                )
                lay_top_eq.addWidget(btn_edit_eq)
                lay_row_eq.addWidget(f_top_eq)

                if tiene_curva:
                    curva_obj = eq.get('curva')
                    if usa_puntos(bomba.curvas,metodo_actual):
                        txt_err = resumen_puntos(puntos_tabla(curva_obj))
                    else:
                        txt_err = f"Error máx. del ajuste: {curva_obj.error_max_ajuste:.2f} m"
                    if nota_joroba(curva_obj):
                        txt_err += '; '+nota_joroba(curva_obj)
                    lbl_err = QLabel(txt_err)
                    lbl_err.setStyleSheet('color: #64748b; font-size: 10px; border: none; background: transparent;')
                    lbl_err.setWordWrap(True)
                    row_eq.setToolTip(txt_err)
                    lay_row_eq.addWidget(lbl_err)

                lay_sec.addWidget(row_eq)

            # Botones "Agregar bomba" y "Quitar"
            lay_btns_eq = QHBoxLayout()
            lay_btns_eq.setContentsMargins(0, 2, 0, 2)
            lay_btns_eq.setSpacing(6)

            btn_add_bomba = QPushButton("+ Agregar bomba")
            btn_add_bomba.setFixedHeight(26)
            btn_add_bomba.setCursor(Qt.PointingHandCursor)
            btn_add_bomba.setStyleSheet("""
                QPushButton {
                    background-color: #eff4ff;
                    color: #0c4e77;
                    font-weight: 600;
                    font-size: 11px;
                    border: 1px solid #c4e1ff;
                    border-radius: 5px;
                    padding: 3px 10px;
                }
                QPushButton:hover {
                    background-color: #dce9ff;
                }
            """)
            btn_add_bomba.clicked.connect(lambda _, b=bomba: self._agregar_equipo_bomba(b))
            lay_btns_eq.addWidget(btn_add_bomba)

            btn_del_bomba = QPushButton("− Quitar")
            btn_del_bomba.setFixedHeight(26)
            btn_del_bomba.setCursor(Qt.PointingHandCursor)
            btn_del_bomba.setEnabled(num_eq > 1)
            btn_del_bomba.setStyleSheet("""
                QPushButton {
                    background-color: #fff1f2;
                    color: #be123c;
                    font-weight: 600;
                    font-size: 11px;
                    border: 1px solid #fecdd3;
                    border-radius: 5px;
                    padding: 3px 10px;
                }
                QPushButton:hover {
                    background-color: #ffe4e6;
                }
                QPushButton:disabled {
                    background-color: #f1f5f9;
                    color: #94a3b8;
                    border: 1px solid #e2e8f0;
                }
            """)
            btn_del_bomba.clicked.connect(lambda _, b=bomba: self._quitar_equipo_bomba(b))
            lay_btns_eq.addWidget(btn_del_bomba)

            lay_sec.addLayout(lay_btns_eq)
            self.panel_content_layout.addWidget(sec_equipos)

            # 4. Estado de conexión en el lienzo
            conectada = bool(bomba.tuberias)
            lbl_estado = QLabel(
                "✓ Conectada (succión / descarga)" if conectada else "⚡ Libre (arrastre sobre tubería)"
            )
            lbl_estado.setStyleSheet(
                "color: #16a34a; font-size: 11px;" if conectada else "color: #d97706; font-size: 11px;"
            )
            self.panel_content_layout.addWidget(lbl_estado)

            self.campos_bomba = {
                "nombre": campo_nombre,
                "z_bomba": campo_z,
                "metodo": combo_metodo,
            }

            campo_nombre.textChanged.connect(
                lambda texto, b=bomba: self._on_nombre_bomba_cambiado(b, texto)
            )
            campo_z.textChanged.connect(
                lambda texto, b=bomba: self._guardar_campo_numerico(b, "z_bomba", texto)
            )
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Error en Panel de Propiedades",
                f"Error al mostrar propiedades de la bomba:\n{e}",
            )

    def _abrir_dialogo_bomba_equipo(self, bomba, equipo, idx):
        dialogo = DialogoBomba(bomba, self, equipo=equipo, idx_equipo=idx)
        if dialogo.exec_() == QDialog.Accepted:
            self._mostrar_campos_bomba(bomba)
            self.canvas_view.set_seleccion_hud(bomba.nombre)
            self.canvas_view.scene().elementos_modificados.emit()
            if hasattr(self, "egl_chart"):
                self.egl_chart.limpiar_datos()

    def _abrir_dialogo_bomba(self, bomba):
        eq = bomba.equipos[0] if getattr(bomba, "equipos", None) else None
        self._abrir_dialogo_bomba_equipo(bomba, eq, 0)

    def _agregar_equipo_bomba(self, bomba):
        idx = len(getattr(bomba, "equipos", []))
        letra = chr(65 + idx) if idx < 26 else str(idx + 1)
        nuevo_eq = {
            "nombre": f"Bomba {letra}",
            "puntos": [],
            "H": [],
            "Q": [],
            "eta": [],
            "npsh": [],
            "curva": None,
        }
        bomba.equipos.append(nuevo_eq)
        if bomba.arreglo.lower() == "individual":
            bomba.arreglo = "paralelo"
        bomba.actualizar_tooltip()
        self._mostrar_campos_bomba(bomba)
        self.canvas_view.scene().elementos_modificados.emit()

    def _quitar_equipo_bomba(self, bomba):
        if len(getattr(bomba, "equipos", [])) <= 1:
            return
        bomba.equipos.pop()
        bomba.curvas = [eq["curva"] for eq in bomba.equipos if eq.get("curva") is not None]
        bomba.actualizar_tooltip()
        self._mostrar_campos_bomba(bomba)
        self.canvas_view.scene().elementos_modificados.emit()

    def _on_nombre_bomba_cambiado(self, bomba, texto):
        bomba.nombre = texto.strip() or "Bomba"
        bomba.actualizar_tooltip()
        self.canvas_view.set_seleccion_hud(bomba.nombre)

    def _on_arreglo_bomba_cambiado(self, bomba, texto):
        bomba.arreglo = texto.lower()
        bomba.actualizar_tooltip()
        self.canvas_view.scene().elementos_modificados.emit()

    def _on_metodo_bomba_cambiado(self, bomba, texto):
        nuevo_metodo = "lineal" if "lineal" in str(texto).lower() else "cuadratico"
        if getattr(bomba, "metodo", "cuadratico") == nuevo_metodo:
            return
        bomba.metodo = nuevo_metodo
        bomba.actualizar_tooltip()
        if hasattr(self, "_limpiar_resultados_bomba"):
            self._limpiar_resultados_bomba(bomba)
        else:
            bomba.Q_op = None
            bomba.H_op = None
            bomba.eta_op = None
            bomba.potencia_hidraulica_op = None
            bomba.potencia_freno_op = None
            bomba.npsh_d = None
            bomba.npsh_r = None
            bomba.cavitacion = None
            bomba.reparto = []
            bomba.desglose = []
            bomba.estado_operacion = "SIN_CALCULAR"
            bomba.mensaje_operacion = ""
        if hasattr(self, "texto_resultados") and self.texto_resultados is not None:
            self.texto_resultados.clear()
        if hasattr(self, "_limpiar_barra_perdidas"):
            self._limpiar_barra_perdidas()
        if not (hasattr(self, "_limpiar_resultados_bomba") and getattr(self, "bomba_seleccionada", None) is bomba):
            self._mostrar_campos_bomba(bomba)
        if hasattr(self, "canvas_view") and self.canvas_view is not None and self.canvas_view.scene() is not None:
            self.canvas_view.scene().elementos_modificados.emit()

    def _guardar_campo_numerico(self, objeto, atributo, texto, refrescar_etiqueta=False):
        texto = texto.strip()
        if texto == "":
            valor = 0.0
        else:
            try:
                valor = float(texto.replace(',','.'))
            except ValueError:
                self._ultimo_error_validacion = f'{atributo} debe ser un número finito.'
                if hasattr(self,'texto_resultados'):
                    self.texto_resultados.setPlainText(f'Dato inválido: {self._ultimo_error_validacion}')
                if hasattr(self, "_limpiar_barra_perdidas"):
                    self._limpiar_barra_perdidas()
                return False
        try:
            validar_propiedad(objeto,atributo,valor,self.fluido_rho)
        except ValueError as error:
            self._ultimo_error_validacion = str(error)
            if hasattr(self,'texto_resultados'):
                self.texto_resultados.setPlainText(f'Dato inválido: {error}')
            if hasattr(self, "_limpiar_barra_perdidas"):
                self._limpiar_barra_perdidas()
            return False
        self._ultimo_error_validacion = None
        previo = getattr(objeto, atributo, None)
        procedencia_previa = (
            getattr(objeto, '_q_por_energia', False) if atributo == 'caudal_Q' else
            getattr(objeto, '_d_por_energia', False) if atributo == 'diametro' else False)
        setattr(objeto, atributo, valor)
        padre = getattr(objeto, 'tuberia_padre', None)
        if atributo == 'valor' and padre is not None and hasattr(padre, '_sincronizar_botones_esquina'):
            padre._sincronizar_botones_esquina()
        if atributo == "caudal_Q":
            objeto._q_por_energia = False
        elif atributo == "diametro":
            objeto._d_por_energia = False
        if refrescar_etiqueta and hasattr(objeto, "actualizar_etiqueta"):
            objeto.actualizar_etiqueta()
        if previo != valor or procedencia_previa:
            self._on_elementos_modificados()

    def _guardar_unidad(self, tuberia, atributo_unidad, texto, refrescar_etiqueta=False):
        previo = getattr(tuberia, atributo_unidad, None)
        setattr(tuberia, atributo_unidad, texto)
        if refrescar_etiqueta:
            tuberia.actualizar_etiqueta()
        if previo != texto:
            self._on_elementos_modificados()

    def _refrescar_label_accesorios(self, tuberia):
        lbl = getattr(self, "label_accesorios_tuberia", None)
        if lbl is None or getattr(self, "tuberia_seleccionada", None) is not tuberia:
            return
        k_acc = getattr(tuberia, "sumatoria_K_accesorios", tuberia.sumatoria_K)
        lbl.setText(
            f"Accesorios conectados: K total = {formatear_numero(k_acc)}, "
            f"Le/D total = {formatear_numero(tuberia.sumatoria_Le_D)}"
        )

    def _construir_tarjeta_conexion_tanque(self, tuberia, extremo, tanque, titulo):
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }"
            "QLabel { border: none; background: transparent; }"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)

        lbl_tit = QLabel(titulo)
        lbl_tit.setStyleSheet("font-weight: 700; color: #0c4e77; font-size: 11px;")
        lbl_tit.setWordWrap(True)
        lay.addWidget(lbl_tit)

        attr_conn = "conexion_origen" if extremo == "origen" else "conexion_destino"
        cfg_ini = normalizar_conexion_tanque(getattr(tuberia, attr_conn, None))

        lbl_modo = QLabel("Condición entre tanque y tubería")
        lbl_modo.setObjectName("panelLabel")
        lay.addWidget(lbl_modo)

        combo_modo = QComboBox()
        combo_modo.setObjectName("panelComboBox")
        combo_modo.addItem("No considerar (K = 0)", "ninguno")
        combo_modo.addItem("Salida del tanque (hacia tubería)", "salida")
        combo_modo.addItem("Entrada al tanque (desde tubería)", "entrada")
        idx_modo = combo_modo.findData(cfg_ini["modo"])
        combo_modo.setCurrentIndex(idx_modo if idx_modo >= 0 else 0)
        lay.addWidget(combo_modo)

        panel_k = QWidget()
        lay_k = QVBoxLayout(panel_k)
        lay_k.setContentsMargins(0, 2, 0, 0)
        lay_k.setSpacing(4)

        lbl_k = QLabel("Valor de K")
        lbl_k.setObjectName("panelLabel")
        lay_k.addWidget(lbl_k)

        campo_k = QLineEdit()
        campo_k.setObjectName("panelLineEdit")
        campo_k.setPlaceholderText("Ingresa K (ej: 0.50)")
        lay_k.addWidget(campo_k)

        lbl_info_entrada = QLabel("En entrada al tanque, K = 1.0 siempre (disipación cinética total).")
        lbl_info_entrada.setObjectName("panelLabel")
        lbl_info_entrada.setStyleSheet("color: #0369a1; font-size: 11px;")
        lbl_info_entrada.setWordWrap(True)
        lay_k.addWidget(lbl_info_entrada)
        lay.addWidget(panel_k)

        def _sincronizar_visibilidad(modo_act, k_act):
            es_salida = modo_act == "salida"
            es_entrada = modo_act == "entrada"
            panel_k.setVisible(es_salida or es_entrada)
            lbl_info_entrada.setVisible(es_entrada)
            with bloquear_senales(campo_k):
                campo_k.setEnabled(es_salida)
                if es_entrada:
                    campo_k.setText(formatear_numero(K_ENTRADA_TANQUE))
                elif es_salida:
                    campo_k.setText(formatear_numero(k_act))
                else:
                    campo_k.setText("")
            card.updateGeometry()

        _sincronizar_visibilidad(cfg_ini["modo"], cfg_ini["K"])

        def _aplicar_cambio(modo_nuevo, k_nuevo):
            previo = normalizar_conexion_tanque(getattr(tuberia, attr_conn, None))
            nuevo = tuberia.establecer_conexion_tanque(extremo, modo_nuevo, "", k_nuevo)
            if tanque is not None and hasattr(tanque, "update"):
                tanque.update()
            self._refrescar_label_accesorios(tuberia)
            if previo != nuevo:
                self._on_elementos_modificados()

        def on_modo_cambiado():
            modo_sel = combo_modo.currentData()
            if modo_sel == "ninguno":
                _sincronizar_visibilidad("ninguno", 0.0)
                _aplicar_cambio("ninguno", 0.0)
            elif modo_sel == "entrada":
                _sincronizar_visibilidad("entrada", K_ENTRADA_TANQUE)
                _aplicar_cambio("entrada", K_ENTRADA_TANQUE)
            else:
                cfg_act = normalizar_conexion_tanque(getattr(tuberia, attr_conn, None))
                k_sug = float(cfg_act["K"]) if cfg_act["modo"] == "salida" and float(cfg_act["K"]) > 0 else 0.5
                _sincronizar_visibilidad("salida", k_sug)
                _aplicar_cambio("salida", k_sug)

        def on_k_editado(texto):
            if combo_modo.currentData() != "salida":
                return
            txt = texto.strip()
            if txt == "":
                k_val = 0.0
            else:
                try:
                    k_val = float(txt.replace(",", "."))
                except ValueError:
                    self._ultimo_error_validacion = "K debe ser un número finito."
                    if hasattr(self, "texto_resultados"):
                        self.texto_resultados.setPlainText(f"Dato inválido: {self._ultimo_error_validacion}")
                    if hasattr(self, "_limpiar_barra_perdidas"):
                        self._limpiar_barra_perdidas()
                    return
            try:
                validar_propiedad(tuberia, "K", k_val, self.fluido_rho)
            except ValueError as error:
                self._ultimo_error_validacion = str(error)
                if hasattr(self, "texto_resultados"):
                    self.texto_resultados.setPlainText(f"Dato inválido: {error}")
                if hasattr(self, "_limpiar_barra_perdidas"):
                    self._limpiar_barra_perdidas()
                return
            self._ultimo_error_validacion = None
            _aplicar_cambio("salida", k_val)

        combo_modo.currentIndexChanged.connect(lambda _idx: on_modo_cambiado())
        campo_k.textEdited.connect(on_k_editado)

        controles = {
            "card": card,
            "modo": combo_modo,
            "k": campo_k,
            "panel_k": panel_k,
            "info_entrada": lbl_info_entrada,
        }
        return card, controles

    def _mostrar_campos_tanque(self, tanque):
        if hasattr(self, "lbl_panel_subtitle"):
            self.lbl_panel_subtitle.setText("PROPIEDADES DEL ELEMENTO")
        if hasattr(self, 'lbl_panel_title'):
            self.lbl_panel_title.setText(f"Propiedades del {tanque.nombre}")
        self._limpiar_panel_content()
        self.campos_tuberia = {}
        self.campos_accesorio = {}
        self.campos_forma = {}

        encabezado = QLabel("Elemento seleccionado: Tanque")
        encabezado.setObjectName("panelLabel")
        encabezado.setWordWrap(True)
        self.panel_content_layout.addWidget(encabezado)

        etiqueta_z = QLabel("Elevación z (m)")
        etiqueta_z.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(etiqueta_z)

        campo_z = QLineEdit()
        campo_z.setObjectName("panelLineEdit")
        campo_z.setText(str(tanque.elevacion_z))
        self.panel_content_layout.addWidget(campo_z)

        check_atmosfera = QCheckBox("Abierto a la atmósfera")
        check_atmosfera.setObjectName("panelCheckBox")
        check_atmosfera.setChecked(tanque.abierto_atmosfera)
        self.panel_content_layout.addWidget(check_atmosfera)

        etiqueta_p = QLabel("Presión Manométrica P (Pa)")
        etiqueta_p.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(etiqueta_p)

        campo_p = QLineEdit()
        campo_p.setObjectName("panelLineEdit")
        campo_p.setText(str(tanque.presion_P))
        campo_p.setEnabled(not tanque.abierto_atmosfera)
        self.panel_content_layout.addWidget(campo_p)

        self.campos_tanque = {
            "z": campo_z,
            "atmosfera": check_atmosfera,
            "P": campo_p,
        }

        campo_z.textChanged.connect(
            lambda texto, t=tanque: self._guardar_campo_numerico(t, "elevacion_z", texto, True)
        )
        campo_p.textChanged.connect(
            lambda texto, t=tanque: self._guardar_campo_numerico(t, "presion_P", texto, True)
        )
        check_atmosfera.toggled.connect(
            lambda marcado, t=tanque, c=campo_p: self._on_atmosfera_toggled(t, c, marcado)
        )

        boton_color = QPushButton("Cambiar Color")
        boton_color.setObjectName("colorButton")
        boton_color.setCursor(Qt.PointingHandCursor)
        self.panel_content_layout.addWidget(boton_color)
        boton_color.clicked.connect(
            lambda _checked=False, t=tanque: self._cambiar_color(t, "color_fondo", t.color_fondo)
        )

        tuberias_tanque = [
            t for t in getattr(tanque, "tuberias", ())
            if isinstance(t, TuberiaGrafica) and hasattr(t, "establecer_conexion_tanque")
        ]
        if tuberias_tanque:
            tit_conn = QLabel("CONEXIONES CON TUBERÍAS")
            tit_conn.setStyleSheet(
                "font-weight: 700; color: #0c4e77; font-size: 11px; "
                "letter-spacing: 0.4px; margin-top: 8px;"
            )
            self.panel_content_layout.addWidget(tit_conn)
            conns_tq = []
            for tub in sorted(
                tuberias_tanque,
                key=lambda x: (getattr(x, "id_tuberia", None) is None, getattr(x, "id_tuberia", None) or 0),
            ):
                ext = "origen" if tub.nodo_origen is tanque else "destino"
                card, ctrls = self._construir_tarjeta_conexion_tanque(
                    tub, ext, tanque, f"Conexión con {tub.nombre}"
                )
                self.panel_content_layout.addWidget(card)
                conns_tq.append(ctrls)
            self.campos_tanque["conexiones"] = conns_tq

    def _cambiar_color(self, item, atributo, color_inicial):
        color = QColorDialog.getColor(QColor(color_inicial), self, "Seleccionar color")
        if color.isValid():
            setattr(item, atributo, color)
            item.update()

    def _mostrar_campos_forma(self, forma):
        if hasattr(self, "lbl_panel_subtitle"):
            self.lbl_panel_subtitle.setText("PROPIEDADES DEL ELEMENTO")
        if hasattr(self, 'lbl_panel_title'):
            self.lbl_panel_title.setText(f"Propiedades de {forma.tipo_forma}")
        self._limpiar_panel_content()
        self.campos_tuberia = {}
        self.campos_tanque = {}
        self.campos_accesorio = {}

        encabezado = QLabel(f"Elemento seleccionado: {forma.tipo_forma}")
        encabezado.setObjectName("panelLabel")
        encabezado.setWordWrap(True)
        self.panel_content_layout.addWidget(encabezado)

        lbl_texto = QLabel("Texto")
        lbl_texto.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(lbl_texto)

        campo_texto = QLineEdit()
        campo_texto.setObjectName("panelLineEdit")
        campo_texto.setText(forma.texto)
        self.panel_content_layout.addWidget(campo_texto)
        
        def crear_icono_grosor(g):
            pixmap = QPixmap(80, 20)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(Qt.black, g))
            painter.drawLine(5, 10, 75, 10)
            painter.end()
            return QtGui.QIcon(pixmap)

        def crear_icono_estilo(estilo):
            pixmap = QPixmap(80, 20)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(Qt.black, 2)
            if estilo == FormaGrafica.ESTILO_PUNTEADA:
                pen.setStyle(Qt.DotLine)
            elif estilo == FormaGrafica.ESTILO_GUIONES:
                pen.setStyle(Qt.DashLine)
            else:
                pen.setStyle(Qt.SolidLine)
            painter.setPen(pen)
            painter.drawLine(5, 10, 75, 10)
            painter.end()
            return QtGui.QIcon(pixmap)

        lbl_grosor = QLabel("Grosor")
        lbl_grosor.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(lbl_grosor)

        campo_grosor = QComboBox()
        campo_grosor.setObjectName("panelComboBox")
        campo_grosor.setIconSize(QSize(80, 16))
        
        grosores = [1, 2, 3, 4, 5, 8, 10]
        for g in grosores:
            campo_grosor.addItem(crear_icono_grosor(g), f"{g} pt", g)
            
        idx_grosor = campo_grosor.findData(forma.grosor)
        if idx_grosor >= 0:
            campo_grosor.setCurrentIndex(idx_grosor)
        else:
            campo_grosor.addItem(crear_icono_grosor(forma.grosor), f"{forma.grosor} pt", forma.grosor)
            campo_grosor.setCurrentIndex(campo_grosor.count() - 1)
            
        self.panel_content_layout.addWidget(campo_grosor)

        lbl_estilo = QLabel("Estilo de trazo")
        lbl_estilo.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(lbl_estilo)

        campo_estilo = QComboBox()
        campo_estilo.setObjectName("panelComboBox")
        campo_estilo.setIconSize(QSize(80, 16))
        estilos = [FormaGrafica.ESTILO_CONTINUA, FormaGrafica.ESTILO_PUNTEADA, FormaGrafica.ESTILO_GUIONES]
        for est in estilos:
            campo_estilo.addItem(crear_icono_estilo(est), est)
        campo_estilo.setCurrentText(forma.estilo_linea)
        self.panel_content_layout.addWidget(campo_estilo)

        boton_color = QPushButton("Color")
        boton_color.setObjectName("colorButton")
        boton_color.setCursor(Qt.PointingHandCursor)
        self.panel_content_layout.addWidget(boton_color)

        self.campos_forma = {
            "texto": campo_texto,
            "grosor": campo_grosor,
            "estilo": campo_estilo
        }

        def cambiar_texto(t):
            forma.texto = t
            forma.actualizar_etiqueta()
        campo_texto.textChanged.connect(cambiar_texto)
        
        def cambiar_grosor(idx):
            val = campo_grosor.itemData(idx)
            if val is not None:
                forma.grosor = int(val)
                forma.actualizar_etiqueta()
                forma.update()
        campo_grosor.currentIndexChanged.connect(cambiar_grosor)
        
        def cambiar_estilo(t):
            forma.estilo_linea = t
            forma.update()
        campo_estilo.currentTextChanged.connect(cambiar_estilo)

        boton_color.clicked.connect(
            lambda _checked=False, f=forma: self._cambiar_color(f, "color", f.color)
        )

    def _mostrar_campos_texto(self, cuadro):
        if hasattr(self, "lbl_panel_subtitle"):
            self.lbl_panel_subtitle.setText("PROPIEDADES DEL ELEMENTO")
        if hasattr(self, "lbl_panel_title"):
            self.lbl_panel_title.setText("Propiedades del Texto")
        self._limpiar_panel_content()
        self.campos_tuberia = {}
        self.campos_tanque = {}
        self.campos_accesorio = {}
        self.campos_forma = {}
        self.campos_nodo_union = {}

        encabezado = QLabel("Elemento seleccionado: Cuadro de Texto")
        encabezado.setObjectName("panelLabel")
        encabezado.setWordWrap(True)
        self.panel_content_layout.addWidget(encabezado)

        lbl_contenido = QLabel("Contenido")
        lbl_contenido.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(lbl_contenido)

        editor = QTextEdit()
        editor.setObjectName("panelTextEdit")
        editor.setFixedHeight(78)
        editor.setPlainText(cuadro.toPlainText())
        self.panel_content_layout.addWidget(editor)

        lbl_tam = QLabel("Tamaño y estilo")
        lbl_tam.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(lbl_tam)

        fila_estilo_widget = QWidget()
        fila_estilo = QHBoxLayout(fila_estilo_widget)
        fila_estilo.setContentsMargins(0, 0, 0, 0)
        fila_estilo.setSpacing(6)

        seg_tam = QFrame()
        seg_tam.setObjectName("segmentedContainer")
        seg_tam_layout = QHBoxLayout(seg_tam)
        seg_tam_layout.setContentsMargins(3, 3, 3, 3)
        seg_tam_layout.setSpacing(3)

        botones_tam = {}
        for nombre_tam in ("Pequeño", "Mediano", "Grande"):
            btn_t = QPushButton(nombre_tam)
            btn_t.setObjectName("segTabBtn")
            btn_t.setCheckable(True)
            btn_t.setChecked(cuadro.tamano_clave == nombre_tam)
            btn_t.setCursor(Qt.PointingHandCursor)
            botones_tam[nombre_tam] = btn_t
            seg_tam_layout.addWidget(btn_t, 1)

        btn_negrita = QPushButton("N")
        btn_negrita.setObjectName("boldToggleBtn")
        btn_negrita.setCheckable(True)
        btn_negrita.setChecked(cuadro.negrita)
        btn_negrita.setFixedSize(34, 32)
        btn_negrita.setCursor(Qt.PointingHandCursor)
        btn_negrita.setToolTip("Negrita")

        fila_estilo.addWidget(seg_tam, 1)
        fila_estilo.addWidget(btn_negrita, 0)
        self.panel_content_layout.addWidget(fila_estilo_widget)

        lbl_col = QLabel("Color del texto")
        lbl_col.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(lbl_col)

        fila_colores_widget = QWidget()
        fila_colores = QHBoxLayout(fila_colores_widget)
        fila_colores.setContentsMargins(0, 0, 0, 0)
        fila_colores.setSpacing(6)

        botones_muestras = {}

        def actualizar_anillos():
            actual_hex = cuadro.color_texto.name().lower()
            for hex_c, btn_m in botones_muestras.items():
                activo = hex_c.lower() == actual_hex
                borde_str = "2.5px solid #0284c7" if activo else "1.5px solid #cbd5e1"
                btn_m.setStyleSheet(
                    f"QPushButton {{ background-color: {hex_c}; border: {borde_str}; "
                    f"border-radius: 12px; }}"
                )

        def elegir_color(hex_c):
            cuadro.set_color(hex_c)
            actualizar_anillos()

        for hex_color in COLORES_TEXTO:
            btn_m = QPushButton()
            btn_m.setFixedSize(24, 24)
            btn_m.setCursor(Qt.PointingHandCursor)
            btn_m.setToolTip(hex_color)
            btn_m.clicked.connect(lambda _c=False, hc=hex_color: elegir_color(hc))
            botones_muestras[hex_color] = btn_m
            fila_colores.addWidget(btn_m)

        btn_otro = QPushButton("Otro…")
        btn_otro.setObjectName("colorButton")
        btn_otro.setCursor(Qt.PointingHandCursor)
        fila_colores.addWidget(btn_otro, 1)
        self.panel_content_layout.addWidget(fila_colores_widget)
        actualizar_anillos()

        def abrir_dialogo_color():
            color = QColorDialog.getColor(cuadro.color_texto, self, "Seleccionar color de texto")
            if color.isValid():
                cuadro.set_color(color)
                actualizar_anillos()

        btn_otro.clicked.connect(abrir_dialogo_color)

        def seleccionar_tamano(clave):
            cuadro.set_tamano(clave)
            for k, b in botones_tam.items():
                b.setChecked(k == clave)

        for k_tam, b_tam in botones_tam.items():
            b_tam.clicked.connect(lambda _c=False, k=k_tam: seleccionar_tamano(k))

        btn_negrita.toggled.connect(cuadro.set_negrita)

        sincronizando = {"activo": False}

        def desde_editor():
            if sincronizando["activo"]:
                return
            sincronizando["activo"] = True
            cuadro.setPlainText(editor.toPlainText())
            sincronizando["activo"] = False

        def desde_lienzo(nuevo_texto):
            if sincronizando["activo"]:
                return
            sincronizando["activo"] = True
            if editor.toPlainText() != nuevo_texto:
                editor.setPlainText(nuevo_texto)
            sincronizando["activo"] = False

        editor.textChanged.connect(desde_editor)
        cuadro._callback_cambio = desde_lienzo

        self.campos_texto = {
            "editor": editor,
            "botones_tam": botones_tam,
            "btn_negrita": btn_negrita,
            "botones_muestras": botones_muestras,
            "btn_otro": btn_otro,
        }

    def _mostrar_campos_nodo_union(self, union):
        if hasattr(self, "lbl_panel_subtitle"):
            self.lbl_panel_subtitle.setText("PROPIEDADES DEL ELEMENTO")
        if hasattr(self, 'lbl_panel_title'):
            self.lbl_panel_title.setText(f"Propiedades de la {union.nombre}")
        self._limpiar_panel_content()
        self.campos_tuberia = {}
        self.campos_tanque = {}
        self.campos_accesorio = {}
        self.campos_forma = {}

        encabezado = QLabel("Elemento seleccionado: Unión")
        encabezado.setObjectName("panelLabel")
        encabezado.setWordWrap(True)
        self.panel_content_layout.addWidget(encabezado)

        etiqueta_hj = QLabel("Energía supuesta Hj (m)")
        etiqueta_hj.setObjectName("panelLabel")
        self.panel_content_layout.addWidget(etiqueta_hj)

        campo_hj = QLineEdit()
        campo_hj.setObjectName("panelLineEdit")
        campo_hj.setPlaceholderText("Automático")
        if union.energia_supuesta != 0.0:
            campo_hj.setText(str(union.energia_supuesta))
        self.panel_content_layout.addWidget(campo_hj)

        ayuda = QLabel("Deja vacío para auto-calcular, o ingresa un valor para modo tanteo")
        ayuda.setObjectName("panelLabel")
        ayuda.setWordWrap(True)
        self.panel_content_layout.addWidget(ayuda)

        self.campos_nodo_union = {"Hj": campo_hj}

        campo_hj.textChanged.connect(
            lambda texto, n=union: self._guardar_campo_numerico(n, "energia_supuesta", texto)
        )

    def _on_atmosfera_toggled(self, tanque, campo_presion, marcado):
        tanque.abierto_atmosfera = marcado
        if marcado:
            tanque.presion_P = 0.0
            with bloquear_senales(campo_presion):
                campo_presion.setText("0.0")
            campo_presion.setEnabled(False)
        else:
            campo_presion.setEnabled(True)
        tanque.actualizar_etiqueta()
        tanque.update()
        self._on_elementos_modificados()

    def _refrescar_label_hf(self, tuberia):
        if self.label_hf_tuberia is None or self.tuberia_seleccionada is not tuberia:
            return
        if tuberia.hf_calculado is None:
            texto = "Pérdida de carga hf: sin calcular"
        else:
            texto = f"Pérdida de carga hf = {tuberia.hf_calculado:.4f} m"
        self.label_hf_tuberia.setText(texto)

    def _limpiar_panel_content(self):
        self.label_hf_tuberia = None
        self.label_accesorios_tuberia = None

        def limpiar_item(item):
            if item is None:
                return
            widget = item.widget()
            if widget is not None:
                if widget is self.dashboard_widget:
                    widget.hide()
                    return
                widget.hide()
                widget.deleteLater()
                return
            layout = item.layout()
            if layout is not None:
                while layout.count():
                    hijo = layout.takeAt(0)
                    limpiar_item(hijo)
                layout.deleteLater()

        while self.panel_content_layout.count():
            item = self.panel_content_layout.takeAt(0)
            limpiar_item(item)
