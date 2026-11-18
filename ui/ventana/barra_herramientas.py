"""Barra de herramientas y creación de elementos en el lienzo."""

import json
import math
import os
import random

from PyQt5 import QtGui
from PyQt5.QtCore import QPointF, QSize, Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAction,
    QComboBox,
    QDialog,
    QFileDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QWidget,
)

from ui.graficos import (
    AccesorioGrafico,
    BombaGrafica,
    CuadroTextoGrafico,
    FormaGrafica,
    NodoUnionGrafico,
    TanqueGrafico,
    TuberiaGrafica,
)
from motor import MotorFluidos
from ui.dialogos import DialogoFluido
from ui.asociacion_archivos import registrar_asociacion_proyecto
from ui.constantes import (
    EXTENSION_PROYECTO,
    FACTORES_SI,
    TEMA_STITCH,
    TOOLTIP_BOMBA,
)
from ui.validacion_datos import validar_proyecto
from ui.iconos import crear_icono_herramienta
from ui.controles_modernos import MenuOpciones
from ui.transiciones import animar_entrada_item
from ui.ventana.invalidacion import bloquear_senales, invalidar_resultados


def normalizar_datos_fluido(datos):
    """Migra JSON antiguos: Pv desde su T y Patm estándar si falta el dato nuevo.

    La temperatura por defecto solo se usa al inicializar/migrar el fluido;
    los solvers reciben las presiones guardadas y nunca deducen Pv desde T.
    """
    if not isinstance(datos,dict):
        raise ValueError('Las propiedades del fluido deben ser un objeto JSON.')
    salida = dict(rho=float(datos.get('rho',1000.0)),mu=float(datos.get('mu',0.001)),
                  P_atm=float(datos.get('P_atm',101325.0)))
    salida['P_vap'] = (float(datos['P_vap']) if 'P_vap' in datos else
                       MotorFluidos.presion_vapor_agua(float(datos.get('temperatura',20.0))))
    if not all(math.isfinite(v) for v in salida.values()):
        raise ValueError('Las propiedades del fluido deben ser finitas.')
    if min(salida['rho'],salida['mu'],salida['P_atm']) <= 0 or salida['P_vap'] < 0:
        raise ValueError('Densidad, viscosidad o presiones absolutas del fluido inválidas.')
    return salida


class BarraHerramientasMixin:
    """Barra de herramientas y creación de elementos en el lienzo."""

    def _build_toolbar(self):
        toolbar = QToolBar("Elementos")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFixedHeight(62)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        if toolbar.layout() is not None:
            toolbar.layout().setContentsMargins(14, 8, 14, 8)
            toolbar.layout().setSpacing(6)

        self.btn_tanque = QPushButton(
            crear_icono_herramienta("tanque", TEMA_STITCH["primary"]), "Tanque"
        )
        self.btn_tanque.setIconSize(QSize(18, 18))
        self.btn_tanque.setFixedHeight(36)
        self.btn_tanque.setCursor(Qt.PointingHandCursor)
        self.btn_tanque.setToolTip("Añadir tanque al lienzo")
        self.btn_tanque.clicked.connect(self._add_tanque)
        toolbar.addWidget(self.btn_tanque)

        self.btn_union = QPushButton(
            crear_icono_herramienta("union", TEMA_STITCH["primary"]), "Unión"
        )
        self.btn_union.setIconSize(QSize(18, 18))
        self.btn_union.setFixedHeight(36)
        self.btn_union.setCursor(Qt.PointingHandCursor)
        self.btn_union.setToolTip("Añadir nodo de unión")
        self.btn_union.clicked.connect(self._add_union)
        toolbar.addWidget(self.btn_union)

        self.conectar_action = QAction(
            crear_icono_herramienta("conectar", TEMA_STITCH["secondary"]), "Conectar", self
        )
        self.conectar_action.setCheckable(True)
        self.conectar_action.setToolTip("Conectar tanques, bombas y nodos con una tubería")

        self.btn_conectar = QPushButton(
            crear_icono_herramienta("conectar", TEMA_STITCH["secondary"]), "Conectar"
        )
        self.btn_conectar.setObjectName("toolbarToggleBtn")
        self.btn_conectar.setIconSize(QSize(18, 18))
        self.btn_conectar.setCheckable(True)
        self.btn_conectar.setFixedHeight(36)
        self.btn_conectar.setCursor(Qt.PointingHandCursor)
        self.btn_conectar.setToolTip("Conectar tanques, bombas y nodos con una tubería")

        def _sync_conectar_desde_accion(activo):
            if self.btn_conectar.isChecked() != activo:
                self.btn_conectar.blockSignals(True)
                self.btn_conectar.setChecked(activo)
                self.btn_conectar.blockSignals(False)
            self._toggle_modo_conexion(activo)

        def _sync_conectar_desde_boton(activo):
            if self.conectar_action.isChecked() != activo:
                self.conectar_action.setChecked(activo)
            else:
                self._toggle_modo_conexion(activo)

        self.conectar_action.toggled.connect(_sync_conectar_desde_accion)
        self.btn_conectar.toggled.connect(_sync_conectar_desde_boton)
        toolbar.addWidget(self.btn_conectar)

        self.btn_accesorio = QPushButton(
            crear_icono_herramienta("accesorio", TEMA_STITCH["tertiary"]), "Accesorio"
        )
        self.btn_accesorio.setIconSize(QSize(18, 18))
        self.btn_accesorio.setFixedHeight(36)
        self.btn_accesorio.setCursor(Qt.PointingHandCursor)
        self.btn_accesorio.setToolTip("Catálogo de válvulas, reducciones y expansiones")
        self.btn_accesorio.clicked.connect(self._abrir_catalogo_accesorios)
        toolbar.addWidget(self.btn_accesorio)

        self.btn_bomba = QPushButton(
            crear_icono_herramienta("bomba", TEMA_STITCH["primary"]), "Bomba"
        )
        self.btn_bomba.setIconSize(QSize(18, 18))
        self.btn_bomba.setFixedHeight(36)
        self.btn_bomba.setCursor(Qt.PointingHandCursor)
        self.btn_bomba.setToolTip(TOOLTIP_BOMBA)
        self.btn_bomba.clicked.connect(self._add_bomba)
        toolbar.addWidget(self.btn_bomba)

        # Menú desplegable para Formas ("Añadir Forma" ajustado siempre al texto completo)
        menu_formas = MenuOpciones(self, 300)
        for titulo, detalle, icono, tipo in (
            ('Línea', 'Trazo auxiliar para tu diagrama', 'linea', FormaGrafica.TIPO_LINEA),
            ('Flecha', 'Indica una dirección o un recorrido', 'flecha', FormaGrafica.TIPO_FLECHA),
            ('Flecha Doble', 'Señala distancias o ambos sentidos', 'flecha_doble', FormaGrafica.TIPO_DOBLE_FLECHA),
        ):
            menu_formas.agregar(titulo, detalle, icono,
                lambda checked=False, t=tipo: self._add_forma(t))

        self.btn_formas = QPushButton(
            crear_icono_herramienta("formas", TEMA_STITCH["primary"]), "Formas"
        )
        self.btn_formas.setObjectName("toolbarDropdownBtn")
        self.btn_formas.setIconSize(QSize(17, 17))
        self.btn_formas.setCursor(Qt.PointingHandCursor)
        self.btn_formas.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_formas.setFixedHeight(36)
        f_btn = QFont("Inter", 10)
        f_btn.setWeight(QFont.Medium)
        ancho_txt = QtGui.QFontMetrics(f_btn).horizontalAdvance("Formas")
        self.btn_formas.setMinimumWidth(ancho_txt + 38)
        self.btn_formas.setMenu(menu_formas)
        toolbar.addWidget(self.btn_formas)

        self.btn_texto = QPushButton(
            crear_icono_herramienta("texto", TEMA_STITCH["primary"]), "Texto"
        )
        self.btn_texto.setObjectName("toolbarToggleBtn")
        self.btn_texto.setIconSize(QSize(17, 17))
        self.btn_texto.setCheckable(True)
        self.btn_texto.setFixedHeight(36)
        self.btn_texto.setCursor(Qt.PointingHandCursor)
        self.btn_texto.toggled.connect(self._toggle_modo_texto)
        toolbar.addWidget(self.btn_texto)

        toolbar.addSeparator()

        self.btn_fluido = QPushButton(
            crear_icono_herramienta("fluido", TEMA_STITCH["primary"]), "Fluido"
        )
        self.btn_fluido.setObjectName("ghostPrimaryToolbarBtn")
        self.btn_fluido.setIconSize(QSize(17, 17))
        self.btn_fluido.setFixedHeight(36)
        self.btn_fluido.setToolTip("Propiedades del fluido")
        self.btn_fluido.setCursor(Qt.PointingHandCursor)
        self.btn_fluido.clicked.connect(self._on_propiedades_fluido)
        toolbar.addWidget(self.btn_fluido)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self.btn_eliminar = QPushButton(
            crear_icono_herramienta("eliminar", TEMA_STITCH["error"]), "Eliminar"
        )
        self.btn_eliminar.setObjectName("dangerToolbarBtn")
        self.btn_eliminar.setIconSize(QSize(16, 16))
        self.btn_eliminar.setFixedHeight(36)
        self.btn_eliminar.setCursor(Qt.PointingHandCursor)
        self.btn_eliminar.clicked.connect(self._on_eliminar_seleccion)
        toolbar.addWidget(self.btn_eliminar)

        toolbar.addSeparator()

        self.btn_guardar = QPushButton(
            crear_icono_herramienta("guardar", TEMA_STITCH["on_surface_variant"]), "Guardar"
        )
        self.btn_guardar.setObjectName("neutralToolbarBtn")
        self.btn_guardar.setIconSize(QSize(16, 16))
        self.btn_guardar.setFixedHeight(36)
        self.btn_guardar.setCursor(Qt.PointingHandCursor)
        self.btn_guardar.clicked.connect(self._on_guardar_proyecto_clicked)
        toolbar.addWidget(self.btn_guardar)

        self.btn_cargar = QPushButton(
            crear_icono_herramienta("cargar", TEMA_STITCH["on_surface_variant"]), "Abrir"
        )
        self.btn_cargar.setObjectName("neutralToolbarBtn")
        self.btn_cargar.setIconSize(QSize(16, 16))
        self.btn_cargar.setFixedHeight(36)
        self.btn_cargar.setToolTip("Abrir proyecto guardado")
        self.btn_cargar.setCursor(Qt.PointingHandCursor)
        self.btn_cargar.clicked.connect(self._on_cargar_proyecto_clicked)
        toolbar.addWidget(self.btn_cargar)

        # Menú de ejemplos precargados
        menu_ejemplos = MenuOpciones(self, 360)
        for titulo, detalle, icono, handler in (
            ('Fricción simple', 'Un tramo entre dos tanques', 'ruta_recta', self._cargar_ejemplo_friccion_simple),
            ('Tuberías en serie', 'Pérdidas acumuladas en varios tramos', 'ruta_ortogonal', self._cargar_ejemplo_serie),
            ('Tuberías en paralelo', 'Reparto del caudal entre ramales', 'rama_simple', self._cargar_ejemplo_paralelo),
            ('Sistema con 1 bomba', 'Curva y punto de operación', 'bomba', self._cargar_ejemplo_bomba_simple),
            ('Bomba + Red ramificada', 'Bombeo y distribución en una red', 'rama_red', self._cargar_ejemplo_bomba_ramificada),
        ):
            menu_ejemplos.agregar(titulo, detalle, icono, handler)

        self.btn_ejemplos = QPushButton(
            crear_icono_herramienta("rama_red", TEMA_STITCH["primary"]), "Ejemplos"
        )
        self.btn_ejemplos.setObjectName("toolbarDropdownBtn")
        self.btn_ejemplos.setIconSize(QSize(16, 16))
        self.btn_ejemplos.setFixedHeight(36)
        self.btn_ejemplos.setCursor(Qt.PointingHandCursor)
        self.btn_ejemplos.setMenu(menu_ejemplos)
        toolbar.addWidget(self.btn_ejemplos)

        if hasattr(self, "top_bars_layout"):
            self.top_bars_layout.addWidget(toolbar)
        else:
            self.addToolBar(toolbar)
        self.main_toolbar = toolbar

    def _on_placeholder_proximamente(self):
        QMessageBox.information(
            self, "Próximamente", "Función disponible en una próxima versión."
        )

    def _on_eliminar_seleccion(self):
        self.canvas_view.scene().borrar_seleccion()

    def _on_propiedades_fluido(self):
        dialogo = DialogoFluido(
            self.fluido_rho,
            self.fluido_mu,
            P_atm=self.fluido_P_atm,
            P_vap=self.fluido_P_vap,
            parent=self,
        )
        if dialogo.exec_() == QDialog.Accepted:
            nuevo_rho, nuevo_mu, nueva_pabs, nueva_pvap = dialogo.valores()
            if (
                abs(nuevo_rho - self.fluido_rho) > 1e-12
                or abs(nuevo_mu - self.fluido_mu) > 1e-12
                or nueva_pabs != self.fluido_P_atm
                or nueva_pvap != self.fluido_P_vap
            ):
                self.fluido_rho, self.fluido_mu = nuevo_rho, nuevo_mu
                self.fluido_P_atm, self.fluido_P_vap = nueva_pabs, nueva_pvap
                self._on_elementos_modificados()

    def _factor_si(self, unidad):
        try:
            return FACTORES_SI[unidad]
        except KeyError:
            raise ValueError(f"Unidad desconocida: {unidad!r}")

    def _a_si(self, valor, unidad):
        return valor * self._factor_si(unidad)

    def _desde_si(self, valor_si, unidad):
        return valor_si / self._factor_si(unidad)

    def _reset_selector_trazado(self):
        """Restablece el selector global de trazado a 'Recto'."""
        self.trazado_global = "recto"
        if hasattr(self, "combo_trazado_global") and self.combo_trazado_global is not None:
            self.combo_trazado_global.blockSignals(True)
            idx = self.combo_trazado_global.findText("Trazado: Recto")
            if idx >= 0:
                self.combo_trazado_global.setCurrentIndex(idx)
            else:
                self.combo_trazado_global.setCurrentText("Trazado: Recto")
            self.combo_trazado_global.blockSignals(False)
        scene = getattr(self, "canvas_view", None)
        scene = scene.scene() if scene else None
        if scene is not None:
            scene.trazado_global = "recto"

    def _on_guardar_proyecto_clicked(self):
        self.guardar_proyecto()

    def guardar_proyecto(self, ruta_archivo=None, *args, **kwargs):
        """Serializa y guarda el estado actual del lienzo y proyecto en formato JSON (.sff / .json)."""
        try:
            if not ruta_archivo or not isinstance(ruta_archivo, str):
                filtro_sff = f"Proyecto de Simulador (*{EXTENSION_PROYECTO})"
                ruta, filtro_elegido = QFileDialog.getSaveFileName(
                    self,
                    "Guardar Proyecto",
                    f"proyecto{EXTENSION_PROYECTO}",
                    f"{filtro_sff};;Archivos JSON (*.json);;Todos los archivos (*.*)",
                )
                if not ruta:
                    return False
                if not os.path.splitext(ruta)[1]:
                    ext = (
                        ".json"
                        if "json" in (filtro_elegido or "").lower()
                        else EXTENSION_PROYECTO
                    )
                    ruta += ext
                ruta_archivo = ruta

            datos = self._serializar_proyecto()

            with open(ruta_archivo, "w", encoding="utf-8") as f:
                json.dump(datos, f, indent=2, ensure_ascii=False)

            if ruta_archivo.lower().endswith(EXTENSION_PROYECTO):
                registrar_asociacion_proyecto()

            return True
        except Exception as err:
            QMessageBox.critical(
                self,
                "Error al Guardar",
                f"No se pudo guardar el proyecto en el archivo:\n{err}",
            )
            return False

    def _serializar_proyecto(self, validar=True):
        """Serializa todos los elementos del lienzo, referencias y configuración a un diccionario."""
        scene = self.canvas_view.scene()

        accesorios_escena = [i for i in scene.items() if isinstance(i, AccesorioGrafico)]
        for idx_acc, acc in enumerate(accesorios_escena):
            if getattr(acc, "id_accesorio", None) is None:
                acc.id_accesorio = idx_acc + 1

        def _id_nodo(nodo):
            if isinstance(nodo, TanqueGrafico):
                return {"tipo": "tanque", "id": nodo.id_tanque, "nombre": nodo.nombre}
            elif isinstance(nodo, NodoUnionGrafico):
                return {"tipo": "union", "id": nodo.id_union, "nombre": nodo.nombre}
            elif isinstance(nodo, BombaGrafica):
                return {"tipo": "bomba", "id": nodo.id_bomba, "nombre": nodo.nombre}
            elif isinstance(nodo, AccesorioGrafico):
                return {
                    "tipo": "accesorio",
                    "id": getattr(nodo, "id_accesorio", None),
                    "nombre": getattr(nodo, "forma_visual", "Accesorio"),
                }
            return None

        # 1. Tanques
        tanques_data = []
        for t in [i for i in scene.items() if isinstance(i, TanqueGrafico)]:
            tanques_data.append({
                "id_tanque": t.id_tanque,
                "nombre": t.nombre,
                "x": float(t.pos().x()),
                "y": float(t.pos().y()),
                "elevacion_z": float(getattr(t, "elevacion_z", 0.0)),
                "presion_P": float(getattr(t, "presion_P", 0.0)),
                "abierto_atmosfera": bool(getattr(t, "abierto_atmosfera", True)),
                "color_fondo": t.color_fondo.name() if hasattr(t, "color_fondo") else "#7dd3fc",
            })

        # 2. Uniones
        uniones_data = []
        for u in [i for i in scene.items() if isinstance(i, NodoUnionGrafico)]:
            uniones_data.append({
                "id_union": u.id_union,
                "nombre": u.nombre,
                "x": float(u.pos().x()),
                "y": float(u.pos().y()),
                "energia_supuesta": float(getattr(u, "energia_supuesta", 0.0)),
            })

        # 3. Bombas
        bombas_data = []
        for b in [i for i in scene.items() if isinstance(i, BombaGrafica)]:
            bombas_data.append(b.to_dict())

        # 4. Tuberías
        tuberias_data = []
        for tub in [i for i in scene.items() if isinstance(i, TuberiaGrafica)]:
            d_tub = tub.to_dict()
            d_tub["nodo_origen"] = _id_nodo(tub.nodo_origen)
            d_tub["nodo_destino"] = _id_nodo(tub.nodo_destino)
            d_tub["direccion_inicial"] = getattr(tub, "direccion_inicial", "H")
            if getattr(tub, "_color_personalizado", None) is not None:
                d_tub["color_personalizado"] = tub._color_personalizado.name()
            tuberias_data.append(d_tub)

        # 5. Accesorios
        accesorios_data = []
        for acc in accesorios_escena:
            tub_padre_info = None
            if acc.tuberia_padre is not None:
                tub_padre_info = {
                    "id_tuberia": acc.tuberia_padre.id_tuberia,
                    "nombre": acc.tuberia_padre.nombre,
                }
            accesorios_data.append({
                "id_accesorio": acc.id_accesorio,
                "forma_visual": acc.forma_visual,
                "tipo_perdida": acc.tipo_perdida,
                "valor": float(acc.valor),
                "x": float(acc.pos().x()),
                "y": float(acc.pos().y()),
                "angulo_in": float(getattr(acc, "angulo_in", 0.0)),
                "angulo_out": float(getattr(acc, "angulo_out", 90.0)),
                "rotation": float(acc.rotation()),
                "t_anclaje": getattr(acc, "t_anclaje", None),
                "tuberia_padre": tub_padre_info,
                "es_divisor": bool(acc.tuberias and acc.tuberia_padre is None),
                "esquina_indice": getattr(acc, 'esquina_indice', None),
            })

        # 6. Formas y Textos (decorativos)
        formas_data = []
        for f in [i for i in scene.items() if isinstance(i, FormaGrafica)]:
            formas_data.append({
                "x": float(f.pos().x()),
                "y": float(f.pos().y()),
                "x1": float(f.p1.x()),
                "y1": float(f.p1.y()),
                "x2": float(f.p2.x()),
                "y2": float(f.p2.y()),
                "tipo_forma": f.tipo_forma,
                "estilo_linea": f.estilo_linea,
                "color": f.color.name(),
                "grosor": f.grosor,
                "texto": getattr(f, "texto", ""),
            })

        textos_data = []
        for tx in [i for i in scene.items() if isinstance(i, CuadroTextoGrafico)]:
            textos_data.append({
                "x": float(tx.pos().x()),
                "y": float(tx.pos().y()),
                "texto": tx.toPlainText(),
                "tamano_clave": getattr(tx, "tamano_clave", "Mediano"),
                "color_texto": tx.color_texto.name() if hasattr(tx, "color_texto") else "#0f172a",
                "negrita": bool(getattr(tx, "negrita", False)),
            })

        # 7. Dashboard selections
        dashboard_data = {
            "modo": self.stack_modo.currentIndex() if hasattr(self, "stack_modo") else 0,
            "punto1_texto": self.combo_punto1.currentText() if hasattr(self, "combo_punto1") else "",
            "punto2_texto": self.combo_punto2.currentText() if hasattr(self, "combo_punto2") else "",
            "union_texto": self.combo_uniones.currentText() if hasattr(self, "combo_uniones") else "",
        }

        # 8. Contadores
        contadores_data = {
            "contador_tanques": getattr(self, "contador_tanques", 1),
            "contador_tuberias": getattr(self, "contador_tuberias", 1),
            "contador_uniones": getattr(self, "contador_uniones", 1),
            "contador_bombas": getattr(self, "contador_bombas", 1),
        }

        # 9. Fluido
        fluido_data = {
            "rho": getattr(self, "fluido_rho", 1000.0),
            "mu": getattr(self, "fluido_mu", 0.001),
            "P_atm": self.fluido_P_atm,
            "P_vap": self.fluido_P_vap,
            "trazado_global": getattr(self, "trazado_global", "recto"),
        }

        proyecto = {
            "version": "1.0",
            "contadores": contadores_data,
            "fluido": fluido_data,
            "dashboard": dashboard_data,
            "tanques": tanques_data,
            "uniones": uniones_data,
            "bombas": bombas_data,
            "tuberias": tuberias_data,
            "accesorios": accesorios_data,
            "formas": formas_data,
            "textos": textos_data,
        }
        if validar:
            normalizar_datos_fluido(fluido_data)
            validar_proyecto(proyecto,fluido_data['rho'])
        return proyecto

    def _on_cargar_proyecto_clicked(self):
        self.cargar_proyecto()

    def nuevo_proyecto(self):
        """Reinicia el proyecto y restablece el selector global a 'Recto'."""
        self._reset_selector_trazado()

    def cargar_proyecto(self, ruta_archivo=None, confirmar_si_hay_contenido=True, *args, **kwargs):
        """Carga y reconstruye un proyecto desde un archivo JSON."""
        try:
            self._reset_selector_trazado()
            if not ruta_archivo or not isinstance(ruta_archivo, str):
                scene = self.canvas_view.scene()
                tiene_elementos = any(
                    isinstance(
                        i,
                        (
                            TanqueGrafico,
                            NodoUnionGrafico,
                            BombaGrafica,
                            TuberiaGrafica,
                            AccesorioGrafico,
                            FormaGrafica,
                            CuadroTextoGrafico,
                        ),
                    )
                    for i in scene.items()
                )
                if tiene_elementos and confirmar_si_hay_contenido:
                    resp = QMessageBox.question(
                        self,
                        "Cargar Proyecto",
                        "El lienzo actual contiene elementos.\n"
                        "¿Deseas descartar el diseño actual y cargar un archivo?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if resp != QMessageBox.Yes:
                        return False

                ruta, _ = QFileDialog.getOpenFileName(
                    self,
                    "Cargar Proyecto",
                    "",
                    (
                        f"Proyectos de Simulador (*{EXTENSION_PROYECTO} *.json);;"
                        f"Proyecto de Simulador (*{EXTENSION_PROYECTO});;"
                        "Archivos JSON (*.json);;"
                        "Todos los archivos (*.*)"
                    ),
                )
                if not ruta:
                    return False
                ruta_archivo = ruta

            with open(ruta_archivo, "r", encoding="utf-8") as f:
                datos = json.load(f)

            self._deserializar_proyecto(datos)
            return True
        except Exception as err:
            QMessageBox.critical(
                self,
                "Error al Cargar",
                f"No se pudo cargar el proyecto desde el archivo:\n{err}",
            )
            return False

    def _deserializar_proyecto(self, datos):
        """Reconstruye sin señales, invalida una vez y después resuelve si procede."""
        if not isinstance(datos,dict):
            raise ValueError('El proyecto JSON debe ser un objeto.')
        # Compatibilidad: una caché antigua de Hj ni se valida como dato ni se usa.
        # La copia evita modificar el diccionario suministrado por el llamador.
        datos = dict(datos)
        if isinstance(datos.get('uniones'), list):
            datos['uniones'] = [
                {k:v for k,v in u.items() if k != 'hj_calculada'} if isinstance(u, dict) else u
                for u in datos['uniones']]
        fluido_normalizado = normalizar_datos_fluido(datos.get('fluido',{}))
        validar_proyecto(datos,fluido_normalizado['rho'])
        scene = self.canvas_view.scene()
        cargando_previo = getattr(self, '_cargando_proyecto', False)
        self._cargando_proyecto = True
        try:
            with bloquear_senales(scene):
                modo = self._reconstruir_proyecto(datos, fluido_normalizado)
        finally:
            self._cargando_proyecto = cargando_previo
            if not cargando_previo:
                invalidar = getattr(self, '_on_elementos_modificados', None)
                if callable(invalidar):
                    invalidar()
                else:
                    invalidar_resultados(scene.items(), self)
        if cargando_previo:
            return
        # No se emite elementos_modificados después: borraría el nuevo resultado.
        if modo == 1 and hasattr(self, "boton_ramificado"):
            self.boton_ramificado.click()
        elif hasattr(self, "boton_bernoulli"):
            self.boton_bernoulli.click()

    def _reconstruir_proyecto(self, datos, fluido_normalizado):
        """Parte estructural de la carga; el llamador bloquea señales de escena."""
        scene = self.canvas_view.scene()

        # Limpiar escena
        if hasattr(scene, "cancelar_conexion"):
            scene.cancelar_conexion()

        for tub in [i for i in scene.items() if isinstance(i, TuberiaGrafica)]:
            scene._eliminar_tuberia(tub)
        for acc in [i for i in scene.items() if isinstance(i, AccesorioGrafico)]:
            scene._eliminar_accesorio(acc)
        for t in [i for i in scene.items() if isinstance(i, TanqueGrafico)]:
            scene._eliminar_tanque(t)
        for u in [i for i in scene.items() if isinstance(i, NodoUnionGrafico)]:
            scene._eliminar_union(u)
        for b in [i for i in scene.items() if isinstance(i, BombaGrafica)]:
            scene._eliminar_bomba(b)
        for item in list(scene.items()):
            if isinstance(item, (FormaGrafica, CuadroTextoGrafico)):
                scene.removeItem(item)

        scene.clearSelection()
        self.tuberia_seleccionada = None
        self.tanque_seleccionado = None
        self.accesorio_seleccionado = None
        self.bomba_seleccionada = None
        self.nodo_union_seleccionado = None
        self.texto_seleccionado = None
        self.forma_seleccionada = None

        if hasattr(self, "_limpiar_panel_content"):
            self._limpiar_panel_content()
        if hasattr(self, "lbl_panel_title"):
            self.lbl_panel_title.setText("Propiedades del Sistema")

        # RECONSTRUCCIÓN EN ORDEN ESPECIFICADO:
        # 1) Tanques y nodos
        mapa_nodos = {}

        for t_data in datos.get("tanques", []):
            t = TanqueGrafico(
                x=float(t_data.get("x", 0.0)),
                y=float(t_data.get("y", 0.0)),
                id_tanque=t_data.get("id_tanque"),
            )
            t.elevacion_z = float(t_data.get("elevacion_z", 0.0))
            t.presion_P = float(t_data.get("presion_P", 0.0))
            t.abierto_atmosfera = bool(t_data.get("abierto_atmosfera", True))
            if "color_fondo" in t_data:
                t.color_fondo = QColor(t_data["color_fondo"])
            t.actualizar_etiqueta()
            scene.addItem(t)
            mapa_nodos[("tanque", t.id_tanque)] = t
            mapa_nodos[t.nombre] = t

        for u_data in datos.get("uniones", []):
            u = NodoUnionGrafico(
                x=float(u_data.get("x", 0.0)),
                y=float(u_data.get("y", 0.0)),
                id_union=u_data.get("id_union"),
            )
            u.energia_supuesta = float(u_data.get("energia_supuesta", 0.0))
            u.actualizar_etiqueta()
            scene.addItem(u)
            mapa_nodos[("union", u.id_union)] = u
            mapa_nodos[u.nombre] = u

        # Accesorios divisores que funcionan como nodos
        for acc_data in datos.get("accesorios", []):
            if acc_data.get("es_divisor"):
                acc = AccesorioGrafico(
                    x=float(acc_data.get("x", 0.0)),
                    y=float(acc_data.get("y", 0.0)),
                    forma_visual=acc_data.get("forma_visual", "Reducción"),
                    tipo_perdida=acc_data.get("tipo_perdida", "K"),
                    valor=float(acc_data.get("valor", 0.0)),
                )
                acc.angulo_in = float(acc_data.get("angulo_in", 0.0))
                acc.angulo_out = float(acc_data.get("angulo_out", 90.0))
                if "rotation" in acc_data:
                    acc.setRotation(float(acc_data["rotation"]))
                scene.addItem(acc)
                acc_id = acc_data.get("id_accesorio")
                acc.id_accesorio = acc_id
                mapa_nodos[("accesorio", acc_id)] = acc
                mapa_nodos[acc.forma_visual] = acc

        # Instanciar bombas como nodos para permitir conexión de tuberías
        mapa_bombas = {}
        for b_data in datos.get("bombas", []):
            b_id = b_data.get("id_bomba", 1)
            b_nom = b_data.get("nombre", f"Bomba {b_id}")
            bomba = BombaGrafica(
                x=float(b_data.get("x", 0.0)),
                y=float(b_data.get("y", 0.0)),
                nombre=b_nom,
                id_bomba=b_id,
            )
            scene.addItem(bomba)
            mapa_nodos[("bomba", b_id)] = bomba
            mapa_nodos[b_nom] = bomba
            mapa_bombas[b_id] = (bomba, b_data)

        # 2) Tuberías
        def _resolver_nodo(ref):
            if not ref:
                return None
            if isinstance(ref, dict):
                tipo = ref.get("tipo")
                nid = ref.get("id")
                nom = ref.get("nombre")
                if (tipo, nid) in mapa_nodos:
                    return mapa_nodos[(tipo, nid)]
                if nom in mapa_nodos:
                    return mapa_nodos[nom]
            elif isinstance(ref, str) and ref in mapa_nodos:
                return mapa_nodos[ref]
            return None

        mapa_tuberias = {}
        for tub_data in datos.get("tuberias", []):
            nodo_orig = _resolver_nodo(tub_data.get("nodo_origen"))
            nodo_dest = _resolver_nodo(tub_data.get("nodo_destino"))
            if nodo_orig is None or nodo_dest is None:
                continue

            tub = TuberiaGrafica(
                nodo_orig,
                nodo_dest,
                id_tuberia=tub_data.get("id_tuberia"),
            )
            tub.from_dict(tub_data)
            if "nombre" in tub_data:
                tub.nombre = tub_data["nombre"]
            if "caudal_Q" in tub_data:
                tub.caudal_Q = float(tub_data["caudal_Q"])
            tub._q_por_energia = tub_data.get('_q_por_energia',False)
            tub._d_por_energia = tub_data.get('_d_por_energia',False)
            for u_k in ("u_Q", "u_L", "u_D", "u_eps"):
                if u_k in tub_data:
                    setattr(tub, u_k, tub_data[u_k])
            if "direccion_inicial" in tub_data:
                tub.direccion_inicial = tub_data["direccion_inicial"]
            if "color_personalizado" in tub_data and tub_data["color_personalizado"]:
                tub._color_personalizado = QColor(tub_data["color_personalizado"])

            scene.addItem(tub)
            tub.actualizar_posicion()
            tub.actualizar_etiqueta()
            mapa_tuberias[tub.id_tuberia] = tub
            mapa_tuberias[tub.nombre] = tub

        # 3) Accesorios y reanclarlos a su tubería
        for acc_data in datos.get("accesorios", []):
            if acc_data.get("es_divisor"):
                continue

            acc = AccesorioGrafico(
                x=float(acc_data.get("x", 0.0)),
                y=float(acc_data.get("y", 0.0)),
                forma_visual=acc_data.get("forma_visual", "Válvula"),
                tipo_perdida=acc_data.get("tipo_perdida", "K"),
                valor=float(acc_data.get("valor", 0.0)),
            )
            if acc_data.get('esquina_indice') is not None:
                acc.esquina_indice = int(acc_data['esquina_indice'])
            acc.angulo_in = float(acc_data.get("angulo_in", 0.0))
            acc.angulo_out = float(acc_data.get("angulo_out", 90.0))
            if "rotation" in acc_data:
                acc.setRotation(float(acc_data["rotation"]))
            acc_id = acc_data.get("id_accesorio")
            if acc_id is not None:
                acc.id_accesorio = acc_id

            scene.addItem(acc)

            tub_info = acc_data.get("tuberia_padre")
            if tub_info:
                id_t = tub_info.get("id_tuberia") if isinstance(tub_info, dict) else tub_info
                nom_t = tub_info.get("nombre") if isinstance(tub_info, dict) else str(tub_info)
                tub_padre = mapa_tuberias.get(id_t) or mapa_tuberias.get(nom_t)
                if tub_padre is not None:
                    acc.anclar_a(tub_padre)
                    if acc_data.get("t_anclaje") is not None:
                        acc.t_anclaje = float(acc_data["t_anclaje"])
                        tub_padre.actualizar_posicion()
            acc.update()

        # 4) Bombas: configurar curvas, equipos, arreglos y elevación
        for b_id, (bomba, b_data) in mapa_bombas.items():
            bomba.from_dict(b_data)
            bomba.actualizar_tooltip()
            bomba.update()

        for b_data in datos.get("bombas", []):
            b_id = b_data.get("id_bomba", 1)
            if b_id not in mapa_bombas:
                b_nom = b_data.get("nombre", f"Bomba {b_id}")
                bomba = BombaGrafica(
                    x=float(b_data.get("x", 0.0)),
                    y=float(b_data.get("y", 0.0)),
                    nombre=b_nom,
                    id_bomba=b_id,
                )
                scene.addItem(bomba)
                bomba.from_dict(b_data)
                bomba.actualizar_tooltip()

        # Formas y Textos (decorativos)
        for f_data in datos.get("formas", []):
            forma = FormaGrafica(
                x1=float(f_data.get("x1", 0.0)),
                y1=float(f_data.get("y1", 0.0)),
                x2=float(f_data.get("x2", 100.0)),
                y2=float(f_data.get("y2", 0.0)),
                tipo=f_data.get("tipo_forma", FormaGrafica.TIPO_LINEA),
            )
            forma.setPos(float(f_data.get("x", 0.0)), float(f_data.get("y", 0.0)))
            forma.estilo_linea = f_data.get("estilo_linea", FormaGrafica.ESTILO_CONTINUA)
            if "color" in f_data:
                forma.color = QColor(f_data["color"])
            forma.grosor = int(f_data.get("grosor", 3))
            forma.texto = f_data.get("texto", "")
            forma.actualizar_etiqueta()
            scene.addItem(forma)

        for tx_data in datos.get("textos", []):
            tx = CuadroTextoGrafico(
                x=float(tx_data.get("x", 0.0)),
                y=float(tx_data.get("y", 0.0)),
                texto=tx_data.get("texto", ""),
            )
            tx.tamano_clave = tx_data.get("tamano_clave", "Mediano")
            if "color_texto" in tx_data:
                tx.set_color(tx_data["color_texto"])
            tx.set_negrita(tx_data.get("negrita", False))
            scene.addItem(tx)

        # Restaura los contadores de IDs
        contadores = datos.get("contadores", {})
        max_t = max([t.id_tanque for t in scene.items() if isinstance(t, TanqueGrafico)] + [0])
        max_tub = max([t.id_tuberia for t in scene.items() if isinstance(t, TuberiaGrafica)] + [0])
        max_u = max([u.id_union for u in scene.items() if isinstance(u, NodoUnionGrafico)] + [0])
        max_b = max([b.id_bomba for b in scene.items() if isinstance(b, BombaGrafica)] + [0])

        self.contador_tanques = int(contadores.get("contador_tanques", max_t + 1))
        self.contador_tuberias = int(contadores.get("contador_tuberias", max_tub + 1))
        self.contador_uniones = int(contadores.get("contador_uniones", max_u + 1))
        self.contador_bombas = int(contadores.get("contador_bombas", max_b + 1))
        scene._contador_tuberias_local = self.contador_tuberias

        # Restaura propiedades del fluido y trazado
        fluido = datos.get("fluido", {})
        self.fluido_rho, self.fluido_mu = fluido_normalizado['rho'], fluido_normalizado['mu']
        self.fluido_P_atm, self.fluido_P_vap = fluido_normalizado['P_atm'], fluido_normalizado['P_vap']
        if "trazado_global" in fluido:
            self.trazado_global = fluido["trazado_global"]
            scene.trazado_global = self.trazado_global
            if hasattr(self, "combo_trazado_global") and self.combo_trazado_global is not None:
                self.combo_trazado_global.blockSignals(True)
                txt_trazado = "Trazado: Ortogonal" if self.trazado_global == "ortogonal" else "Trazado: Recto"
                idx_tz = self.combo_trazado_global.findText(txt_trazado)
                if idx_tz >= 0:
                    self.combo_trazado_global.setCurrentIndex(idx_tz)
                self.combo_trazado_global.blockSignals(False)

        # Actualiza los combos del dashboard
        self._refrescar_combos_dashboard()
        dashboard_data = datos.get("dashboard", {})
        modo = int(dashboard_data.get("modo", 0))
        if hasattr(self, "_cambiar_modo_dashboard"):
            self._cambiar_modo_dashboard(modo)

        p1_txt = dashboard_data.get("punto1_texto")
        if p1_txt and hasattr(self, "combo_punto1"):
            idx1 = self.combo_punto1.findText(p1_txt)
            if idx1 >= 0:
                self.combo_punto1.setCurrentIndex(idx1)

        p2_txt = dashboard_data.get("punto2_texto")
        if p2_txt and hasattr(self, "combo_punto2"):
            idx2 = self.combo_punto2.findText(p2_txt)
            if idx2 >= 0:
                self.combo_punto2.setCurrentIndex(idx2)

        u_txt = dashboard_data.get("union_texto")
        if u_txt and hasattr(self, "combo_uniones"):
            idx_u = self.combo_uniones.findText(u_txt)
            if idx_u >= 0:
                self.combo_uniones.setCurrentIndex(idx_u)

        return modo

    def _toggle_modo_conexion(self, activo):
        if activo and hasattr(self, "btn_texto") and self.btn_texto.isChecked():
            self.btn_texto.setChecked(False)
        scene = self.canvas_view.scene()
        scene.modo_conexion = activo
        scene.trazado_global = getattr(self, "trazado_global", "recto")
        if not activo:
            scene.cancelar_conexion()

    def _toggle_modo_texto(self, activo):
        if activo and hasattr(self, "conectar_action") and self.conectar_action.isChecked():
            self.conectar_action.setChecked(False)
        scene = self.canvas_view.scene()
        scene.modo_texto = activo
        if hasattr(self, "btn_texto"):
            color_ico = TEMA_STITCH["secondary"] if activo else TEMA_STITCH["primary"]
            self.btn_texto.setIcon(crear_icono_herramienta("texto", color_ico))
        if activo:
            self.canvas_view.viewport().setCursor(Qt.IBeamCursor)
        else:
            self.canvas_view.viewport().unsetCursor()

    def _add_cuadro_texto(self, pos=None):
        scene = self.canvas_view.scene()
        if pos is None:
            pos = self.canvas_view.mapToScene(self.canvas_view.viewport().rect().center())
        cuadro = CuadroTextoGrafico(pos.x(), pos.y())
        scene.addItem(cuadro)
        if hasattr(self, "btn_texto") and self.btn_texto.isChecked():
            self.btn_texto.setChecked(False)
        else:
            scene.modo_texto = False
            self.canvas_view.viewport().unsetCursor()
        scene.clearSelection()
        cuadro.setSelected(True)
        cuadro.activar_edicion(seleccionar_todo=True)
        return cuadro

    def _add_tanque(self):
        scene = self.canvas_view.scene()
        centro = self.canvas_view.mapToScene(self.canvas_view.viewport().rect().center())
        dx = random.randint(-60, 60)
        dy = random.randint(-60, 60)
        tanque = TanqueGrafico(
            centro.x() + dx, centro.y() + dy, id_tanque=self.contador_tanques
        )
        self.contador_tanques += 1
        scene.addItem(tanque)
        scene.elementos_modificados.emit()
        scene.clearSelection()
        tanque.setSelected(True)
        animar_entrada_item(tanque)

    def _add_union(self):
        scene = self.canvas_view.scene()
        centro = self.canvas_view.mapToScene(self.canvas_view.viewport().rect().center())
        union = NodoUnionGrafico(
            centro.x() - NodoUnionGrafico.DIAMETRO / 2,
            centro.y() - NodoUnionGrafico.DIAMETRO / 2,
            id_union=self.contador_uniones,
        )
        self.contador_uniones += 1
        scene.addItem(union)
        scene.elementos_modificados.emit()
        scene.clearSelection()
        union.setSelected(True)
        animar_entrada_item(union)

    def _abrir_catalogo_accesorios(self):
        from ui.catalogo_accesorios import CatalogoAccesorios
        dialogo = CatalogoAccesorios(self)
        if dialogo.exec_() == QDialog.Accepted:
            self._add_accesorio(dialogo.forma_elegida)

    def _add_accesorio(self, forma="Válvula"):
        self.conectar_action.setChecked(False)
        scene = self.canvas_view.scene()
        centro = self.canvas_view.mapToScene(self.canvas_view.viewport().rect().center())
        seleccion = scene.selectedItems()
        tuberia = seleccion[0] if len(seleccion) == 1 and isinstance(seleccion[0], TuberiaGrafica) else None
        if tuberia is not None:
            centro = tuberia.path().pointAtPercent(0.5)
        accesorio = AccesorioGrafico(
            centro.x() - AccesorioGrafico.ANCHO / 2,
            centro.y() - AccesorioGrafico.ALTO / 2,
            forma_visual=forma,
        )
        scene.addItem(accesorio)
        if tuberia is not None:
            if forma in AccesorioGrafico.FORMAS_DIVISORAS:
                accesorio.insertar_en(tuberia)
            else:
                accesorio.anclar_a(tuberia)
        scene.elementos_modificados.emit()
        scene.clearSelection()
        accesorio.setSelected(True)
        animar_entrada_item(accesorio)
        return accesorio

    def _add_bomba(self):
        self.conectar_action.setChecked(False)
        scene = self.canvas_view.scene()
        centro = self.canvas_view.mapToScene(self.canvas_view.viewport().rect().center())
        dx = random.randint(-40, 40)
        dy = random.randint(-40, 40)
        if not hasattr(self, "contador_bombas"):
            self.contador_bombas = 1
        bomba = BombaGrafica(
            centro.x() + dx - BombaGrafica.ANCHO / 2,
            centro.y() + dy - BombaGrafica.ALTO / 2,
            nombre=f"Bomba {self.contador_bombas}",
            id_bomba=self.contador_bombas,
        )
        self.contador_bombas += 1
        scene.addItem(bomba)
        scene.elementos_modificados.emit()
        scene.clearSelection()
        bomba.setSelected(True)
        animar_entrada_item(bomba)

    def _add_forma(self, tipo):
        scene = self.canvas_view.scene()
        centro = self.canvas_view.mapToScene(self.canvas_view.viewport().rect().center())
        forma = FormaGrafica(
            x1=centro.x() - 50, y1=centro.y(),
            x2=centro.x() + 50, y2=centro.y(),
            tipo=tipo
        )
        scene.addItem(forma)
        scene.clearSelection()
        forma.setSelected(True)
        animar_entrada_item(forma)

    def _preparar_escena_ejemplo(self, rho=1000.0, mu=0.001):
        """Limpia el lienzo actual y prepara el fluido y controles para cargar un ejemplo."""
        if hasattr(self, "conectar_action") and self.conectar_action.isChecked():
            self.conectar_action.setChecked(False)
        scene = self.canvas_view.scene()
        scene.cancelar_conexion()
        scene.clearSelection()

        tipos_objetivo = (
            TuberiaGrafica,
            TanqueGrafico,
            BombaGrafica,
            NodoUnionGrafico,
            AccesorioGrafico,
            FormaGrafica,
            CuadroTextoGrafico,
        )
        for item in list(scene.items()):
            if isinstance(item, TuberiaGrafica):
                item.desconectar()
        for item in list(scene.items()):
            if isinstance(item, tipos_objetivo):
                scene.removeItem(item)

        for attr in ("tuberia_seleccionada", "tanque_seleccionado", "nodo_union_seleccionado", "forma_seleccionada", "texto_seleccionado"):
            if hasattr(self, attr):
                setattr(self, attr, None)
        self._perfiles_calculados = {}
        self.datos_exportacion = None
        if hasattr(self, "texto_resultados") and self.texto_resultados is not None:
            self.texto_resultados.clear()
        if hasattr(self, "_limpiar_barra_perdidas"):
            self._limpiar_barra_perdidas()

        self.fluido_rho = float(rho)
        self.fluido_mu = float(mu)
        self._reset_selector_trazado()
        return scene

    @staticmethod
    def _crear_tanque_ejemplo(scene, x, y, id_tanque, elevacion_z, abierto=True, presion=0.0):
        tanque = TanqueGrafico(x, y, id_tanque=id_tanque)
        tanque.elevacion_z = float(elevacion_z)
        tanque.presion_P = float(presion)
        tanque.abierto_atmosfera = bool(abierto)
        tanque.actualizar_etiqueta()
        scene.addItem(tanque)
        return tanque

    @staticmethod
    def _crear_tuberia_ejemplo(
        scene,
        origen,
        destino,
        id_tuberia,
        longitud,
        diametro,
        rugosidad=0.00015,
        caudal_Q=0.0,
        nombre=None,
    ):
        tub = TuberiaGrafica(origen, destino, id_tuberia=id_tuberia)
        if nombre:
            tub.nombre = nombre
        tub.longitud = float(longitud)
        tub.diametro = float(diametro)
        tub.rugosidad = float(rugosidad)
        tub.caudal_Q = float(caudal_Q)
        tub.modo_trazado = "recto"
        scene.addItem(tub)
        tub.actualizar_posicion()
        tub.actualizar_etiqueta()
        return tub

    def _finalizar_ejemplo(self, modo_dashboard=0, punto1=0, punto2=1):
        """Sincroniza contadores, combos del dashboard y encuadre tras cargar un ejemplo."""
        scene = self.canvas_view.scene()
        items = scene.items()
        max_tq = max([getattr(i, "id_tanque", 0) or 0 for i in items if isinstance(i, TanqueGrafico)], default=0)
        max_tu = max([getattr(i, "id_tuberia", 0) or 0 for i in items if isinstance(i, TuberiaGrafica)], default=0)
        max_un = max([getattr(i, "id_union", 0) or 0 for i in items if isinstance(i, NodoUnionGrafico)], default=0)
        max_bm = max([getattr(i, "id_bomba", 0) or 0 for i in items if isinstance(i, BombaGrafica)], default=0)

        self.contador_tanques = max_tq + 1
        self.contador_tuberias = max_tu + 1
        self.contador_uniones = max_un + 1
        self.contador_bombas = max_bm + 1

        self._refrescar_combos_dashboard()
        if hasattr(self, "_cambiar_modo_dashboard"):
            self._cambiar_modo_dashboard(modo_dashboard)
        if hasattr(self, "btn_tab_simple"):
            self.btn_tab_simple.setChecked(modo_dashboard == 0)
        if hasattr(self, "btn_tab_ramificado"):
            self.btn_tab_ramificado.setChecked(modo_dashboard == 1)

        if modo_dashboard == 0:
            if hasattr(self, "combo_punto1") and self.combo_punto1.count() > punto1:
                self.combo_punto1.setCurrentIndex(punto1)
            if hasattr(self, "combo_punto2") and self.combo_punto2.count() > punto2:
                self.combo_punto2.setCurrentIndex(punto2)

        scene.elementos_modificados.emit()
        if hasattr(self.canvas_view, "zoom_reset"):
            self.canvas_view.zoom_reset()

    def _cargar_ejemplo_friccion_simple(self):
        """Ejemplo simple de pérdida por fricción en una sola tubería entre dos tanques."""
        scene = self._preparar_escena_ejemplo()
        # Escala vertical proporcional a z (8 px/m): T1(25 m) -> anchor 186, T2(5 m) -> anchor 346
        t1 = self._crear_tanque_ejemplo(scene, 100, 160, id_tanque=1, elevacion_z=25.0)
        t2 = self._crear_tanque_ejemplo(scene, 600, 320, id_tanque=2, elevacion_z=5.0)
        self._crear_tuberia_ejemplo(
            scene,
            t1,
            t2,
            id_tuberia=1,
            longitud=120.0,
            diametro=0.15,
            rugosidad=0.00015,
            caudal_Q=0.04,
            nombre="Tubería 1",
        )
        self._finalizar_ejemplo(modo_dashboard=0)

    def _cargar_ejemplo_serie(self):
        """Ejemplo simple de tuberías en serie entre dos tanques con un nodo de unión."""
        scene = self._preparar_escena_ejemplo()
        # Escala vertical proporcional a z y Hj resuelta (~25.40 m, 9 px/m):
        # T1(30 m) -> anchor 186, J-1(25.40 m) -> centro 228, T2(10 m) -> anchor 366
        t1 = self._crear_tanque_ejemplo(scene, 80, 160, id_tanque=1, elevacion_z=30.0)
        union = NodoUnionGrafico(380, 220, id_union=1)
        scene.addItem(union)
        t2 = self._crear_tanque_ejemplo(scene, 680, 340, id_tanque=2, elevacion_z=10.0)

        self._crear_tuberia_ejemplo(scene, t1, union, id_tuberia=1, longitud=80.0, diametro=0.20, rugosidad=0.00015)
        self._crear_tuberia_ejemplo(scene, union, t2, id_tuberia=2, longitud=60.0, diametro=0.15, rugosidad=0.00015)
        self._finalizar_ejemplo(modo_dashboard=0)

    def _cargar_ejemplo_paralelo(self):
        """Ejemplo simple de dos ramales en paralelo entre dos tanques."""
        scene = self._preparar_escena_ejemplo()
        # Escala vertical proporcional a z (10 px/m): T1(20 m) -> anchor 236, T2(12 m) -> anchor 316
        t1 = self._crear_tanque_ejemplo(scene, 90, 210, id_tanque=1, elevacion_z=20.0)
        t2 = self._crear_tanque_ejemplo(scene, 630, 290, id_tanque=2, elevacion_z=12.0)

        self._crear_tuberia_ejemplo(
            scene, t1, t2, id_tuberia=1, longitud=100.0, diametro=0.20, rugosidad=0.00015, caudal_Q=0.05, nombre="Tubería 1 (Ramal A)"
        )
        self._crear_tuberia_ejemplo(
            scene, t1, t2, id_tuberia=2, longitud=120.0, diametro=0.15, rugosidad=0.00015, caudal_Q=0.03, nombre="Tubería 2 (Ramal B)"
        )
        self._finalizar_ejemplo(modo_dashboard=0)

    def _cargar_ejemplo_bomba_simple(self):
        """Ejemplo simple de impulsión entre dos tanques con 1 bomba centrífuga."""
        scene = self._preparar_escena_ejemplo()
        # Escala vertical proporcional a z (10 px/m): T2(18 m) -> 166, T1(2 m) -> 326, Bomba(1 m) -> 336
        t1 = self._crear_tanque_ejemplo(scene, 70, 300, id_tanque=1, elevacion_z=2.0)

        bomba = BombaGrafica(370, 306, nombre="Bomba 1", id_bomba=1)
        bomba.z_bomba = 1.0
        bomba.arreglo = "individual"
        q_pts = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10]
        h_pts = [32.0, 30.8, 28.4, 24.6, 19.4, 12.6]
        eta_pts = [0.0, 0.48, 0.72, 0.80, 0.75, 0.60]
        npsh_pts = [1.8, 2.0, 2.5, 3.3, 4.4, 5.8]
        curva = MotorFluidos.CurvaBomba(
            "Bomba 1", q_pts, h_pts, eta=eta_pts, npsh_r=npsh_pts, modo="ajuste"
        )
        bomba.curvas = [curva]
        bomba.actualizar_etiqueta()
        scene.addItem(bomba)

        t2 = self._crear_tanque_ejemplo(scene, 770, 140, id_tanque=2, elevacion_z=18.0)
        self._crear_tuberia_ejemplo(
            scene, t1, bomba, id_tuberia=1, longitud=8.0, diametro=0.20, rugosidad=0.00015, nombre="Tubería 1 (Succión)"
        )
        self._crear_tuberia_ejemplo(
            scene, bomba, t2, id_tuberia=2, longitud=60.0, diametro=0.15, rugosidad=0.00015, nombre="Tubería 2 (Impulsión)"
        )
        self._finalizar_ejemplo(modo_dashboard=0)

    def _cargar_ejemplo_bomba_ramificada(self):
        """Carga en el lienzo el problema de las diapositivas 5 y 7: Bomba en Red Ramificada."""
        scene = self._preparar_escena_ejemplo(rho=1000.0, mu=0.001)
        # Disposición visual compacta por alturas:
        # T2(12 m) > J-1 > T3(8 m) > T1/Bomba(2 m), manteniendo las cotas numéricas z intactas
        t1 = self._crear_tanque_ejemplo(scene, 60, 320, id_tanque=1, elevacion_z=2.0)

        bomba = BombaGrafica(300, 316, id_bomba=1)
        bomba.z_bomba = 2.0
        bomba.arreglo = "individual"
        q_pts = [0.0, 0.05, 0.10, 0.15, 0.18, 0.20]
        h_pts = [-614.13 * (q ** 2) + 18.382 * q + 23.763 for q in q_pts]
        curva = MotorFluidos.CurvaBomba("Bomba PPTX", q_pts, h_pts, modo="ajuste")
        bomba.curvas = [curva]
        bomba.equipos = [
            {
                "nombre": "Bomba PPTX",
                "Q": q_pts,
                "H": h_pts,
                "puntos": list(zip(q_pts, h_pts)),
                "curva": curva,
            }
        ]
        bomba.actualizar_etiqueta()
        scene.addItem(bomba)

        union = NodoUnionGrafico(640, 202, id_union=1)
        scene.addItem(union)

        t2 = self._crear_tanque_ejemplo(scene, 1140, 140, id_tanque=2, elevacion_z=12.0)
        t3 = self._crear_tanque_ejemplo(scene, 900, 260, id_tanque=3, elevacion_z=8.0)

        self._crear_tuberia_ejemplo(
            scene, t1, bomba, id_tuberia=1, longitud=5.0, diametro=0.2, rugosidad=0.0001, nombre="Tubería 1 (Succión)"
        )
        self._crear_tuberia_ejemplo(
            scene, bomba, union, id_tuberia=2, longitud=10.0, diametro=0.2, rugosidad=0.0001, nombre="Tubería 1 (Impulsión)"
        )
        self._crear_tuberia_ejemplo(
            scene, union, t2, id_tuberia=3, longitud=12.0, diametro=0.05, rugosidad=0.0001, nombre="Tubería 2"
        )
        self._crear_tuberia_ejemplo(
            scene, union, t3, id_tuberia=4, longitud=12.0, diametro=0.1, rugosidad=0.0001, nombre="Tubería 3"
        )
        self._finalizar_ejemplo(modo_dashboard=1)
