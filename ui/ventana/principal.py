"""Ventana principal: arma la interfaz y une todos los módulos de la ventana."""

from PyQt5 import QtGui
from PyQt5.QtWidgets import QMainWindow

from ui.constantes import ARCHIVO_ICONO
from ui.animaciones import MicroAnimaciones
from ui.asociacion_archivos import registrar_asociacion_proyecto
from ui.ventana.barra_herramientas import BarraHerramientasMixin, normalizar_datos_fluido
from ui.ventana.bernoulli import BernoulliMixin
from ui.ventana.bombas import BombasMixin
from ui.ventana.dashboard import DashboardMixin
from ui.ventana.estilos import EstilosMixin
from ui.ventana.exportacion import ExportacionMixin
from ui.ventana.interfaz import InterfazMixin
from ui.ventana.memoria_calculo import MemoriaCalculoMixin
from ui.ventana.panel_propiedades import PanelPropiedadesMixin
from ui.ventana.ramificadas import RamificadasMixin
from ui.ventana.resolucion import ResolucionMixin
from ui.ventana.vistas import VistasMixin
from ui.recursos import ruta_recurso


class MainWindow(QMainWindow, InterfazMixin, EstilosMixin, VistasMixin, BarraHerramientasMixin, PanelPropiedadesMixin, DashboardMixin, ResolucionMixin, RamificadasMixin, ExportacionMixin, MemoriaCalculoMixin, BernoulliMixin, BombasMixin):
    UNIDADES_Q = ["m³/s", "L/s", "gal/min"]
    UNIDADES_L = ["m", "cm", "mm", "in"]
    UNIDADES_D = ["m", "cm", "mm", "in"]
    UNIDADES_EPSILON = ["m", "mm"]
    TABLA_ZOOM_MIN = 0.40
    TABLA_ZOOM_MAX = 2.50
    TABLA_ZOOM_PASO = 1.10

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simulador de Fluidos  /  Ingeniería Química CAD")
        self.setWindowIcon(QtGui.QIcon(ruta_recurso(ARCHIVO_ICONO)))
        registrar_asociacion_proyecto()
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)

        self.tuberia_seleccionada = None
        self.campos_tuberia = {}
        self.tanque_seleccionado = None
        self.campos_tanque = {}
        self.nodo_union_seleccionado = None
        self.campos_nodo_union = {}
        self.forma_seleccionada = None
        self.campos_forma = {}
        self.texto_seleccionado = None
        self.campos_texto = {}
        
        self.contador_tanques = 1
        self.contador_tuberias = 1
        self.contador_uniones = 1
        self.contador_bombas = 1

        self.bomba_seleccionada = None
        self.campos_bomba = {}
        
        self.accesorio_seleccionado = None
        self.campos_accesorio = {}
        self.label_hf_tuberia = None

        self.fluido_rho = 1000.0
        self.fluido_mu = 0.001
        fluido = normalizar_datos_fluido({})
        self.fluido_P_atm, self.fluido_P_vap = fluido['P_atm'], fluido['P_vap']

        self.datos_exportacion = {}
        self._tabla_zoom = 1.0
        self._tabla_cache = None
        self.trazado_global = "recto"

        self._build_ui()
        self._build_toolbar()
        self._apply_styles()
        if hasattr(self, "_reset_selector_trazado"):
            self._reset_selector_trazado()
        self._cambiar_vista_central("cad")
        self._micro_animaciones = MicroAnimaciones(self)
        from ui.ventana.historial import HistorialProyecto
        self.historial = HistorialProyecto(self)
