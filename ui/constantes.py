"""Constantes, tema visual y textos de la aplicación."""

FACTORES_SI = {
    "m³/s": 1.0,
    "L/s": 1.0e-3,
    "gal/min": 3.785411784e-3 / 60.0,
    "m": 1.0,
    "cm": 1.0e-2,
    "mm": 1.0e-3,
    "in": 0.0254,
    "Pa": 1.0,
    "kPa": 1000.0,
    "bar": 100000.0,
    "atm": 101325.0,
    "mmHg": 133.322,
    "psi": 6894.757293168,
}


TAMANOS_TEXTO = {"Pequeño": 10, "Mediano": 14, "Grande": 22}


COLORES_TEXTO = ["#0f172a", "#0284c7", "#dc2626", "#16a34a", "#d97706", "#64748b"]


TEMA_STITCH = {
    "surface": "#f8f9ff",
    "surface_lowest": "#ffffff",
    "surface_low": "#eff4ff",
    "surface_container": "#e5eeff",
    "surface_high": "#dce9ff",
    "primary": "#0c4e77",
    "primary_container": "#2f6690",
    "on_primary_container": "#c4e1ff",
    "secondary": "#006398",
    "tertiary": "#3a4c5e",
    "on_surface": "#0b1c30",
    "on_surface_variant": "#41474e",
    "outline": "#72787f",
    "outline_variant": "#c1c7cf",
    "error": "#ba1a1a",
    "error_container": "#ffdad6",
    # Navegación lateral
    "nav_bar_width": 70,
    "nav_active_bg": "#dce9ff",
    "nav_active_border": "#b6d3f8",
    "nav_active_text": "#0c4e77",
    "nav_hover_bg": "#f1f5f9",
    "nav_hover_border": "#e2e8f0",
    # HUDs flotantes sobre lienzo
    "hud_bg": "rgba(255, 255, 255, 0.90)",
    "hud_border": "#d8e2ee",
    "hud_text": "#334155",
    "hud_accent": "#0c4e77",
    # Barra de estado inferior
    "status_bg": "#ffffff",
    "status_border": "#e2e8f0",
    "status_text": "#64748b",
}


def formatear_numero(valor):
    return f"{valor + 0.0:g}"


ARCHIVO_ICONO = "logo_1.ico"


ARCHIVO_ICONO_PROYECTO = "Gota_archivo_para_los_json.ico"


VERSION_APP = "1.0.1"


REPOSITORIO_GITHUB = "luisacevedo15/Simulador-de-flujo-de-fluidos"


APP_USER_MODEL_ID = "luisacevedo15.SimuladorFlujoDeFluidos.App"


EXTENSION_PROYECTO = ".sff"


PROGID_PROYECTO = "SimuladorFlujoFluidos.Proyecto"


DESCRIPCION_TIPO_PROYECTO = "Proyecto de Simulador de Flujo de Fluidos"


ARCHIVOS_ESCUDO = ("logo_3.png",)


ARCHIVO_LOGO_PROPIO = "logo_2.jpg"


TEXTO_AUTOR = "Autor: Luis Acevedo Suarez | luisacevedos@unmsm.edu.pe"


# -------------------------------------------------------------
# Constantes visuales y de reporte para Bombas Centrífugas
# -------------------------------------------------------------
NOMBRE_BOMBA = "Bomba"
TOOLTIP_BOMBA = "Añadir bomba centrífuga al lienzo (arrastrar sobre una tubería para insertarla)"
ETIQUETA_REPORTE_BOMBA = "BOMBA CENTRÍFUGA"
ETIQUETA_SUCCION = "Tubería de Succión"
ETIQUETA_DESCARGA = "Tubería de Impulsión / Descarga"
COLOR_BOMBA = "#0284c7"
COLOR_BOMBA_LIBRE = "#0284c7"
COLOR_BOMBA_CONECTADA = "#0369a1"

