"""Invalidación idempotente sin imports de Qt ni estado global.

Opera sobre atributos y protocolos mínimos, de modo que admite objetos de prueba.
Modificar resultados es un efecto deliberado: no es una función pura matemática.
0.0 es la representación existente de Q/D desconocidos; las banderas conservan
la procedencia para persistirla, sin convertir un resultado en dato impuesto.
"""

from contextlib import contextmanager


@contextmanager
def bloquear_senales(objeto):
    """Restaura el estado previo incluso ante errores; admite dobles sin Qt."""
    bloquear = getattr(objeto, 'blockSignals', None)
    previo = bloquear(True) if callable(bloquear) else None
    try:
        yield
    finally:
        if callable(bloquear):
            bloquear(bool(previo))


def _llamar(objeto, metodo, *args):
    funcion = getattr(objeto, metodo, None)
    if callable(funcion):
        funcion(*args)


def limpiar_datos_bomba(bomba, estado='SIN_CALCULAR', mensaje=''):
    """Solo datos calculados; equipos, curvas y propiedades de entrada se conservan."""
    for nombre in ('Q_op', 'H_op', 'eta_op', 'potencia_hidraulica_op',
                   'potencia_freno_op', 'npsh_d', 'npsh_r', 'cavitacion'):
        setattr(bomba, nombre, None)
    if hasattr(bomba,'resultado_estacion'):
        bomba.resultado_estacion = None
    bomba.reparto = []
    bomba.desglose = []
    bomba.estado_operacion = estado
    bomba.mensaje_operacion = mensaje


def limpiar_desglose_tuberia(tuberia):
    """No toca accesorios ni hf dado: son entradas, no un desglose calculado."""
    tuberia.hf_dist_calculado = None
    tuberia.hf_loc_calculado = None
    for nombre in ('desglose', 'desglose_perdidas', 'perdidas_segmentos',
                   'historial_iteraciones', 'resultado_tramo', 'resultado_tramo_sup',
                   '_resultado_tramo_resuelto', 'sentido_flujo_calculado'):
        if not hasattr(tuberia, nombre):
            continue
        actual = getattr(tuberia, nombre)
        vacio = ({} if isinstance(actual, dict) else [] if isinstance(actual, list)
                 else () if isinstance(actual, tuple) else None)
        setattr(tuberia, nombre, vacio)


def asignar_sentido_flujo(tuberia, sentido):
    """Fija o limpia el sentido de flujo visual respecto a origen->destino (1, -1, 0 o None)."""
    valor = int(sentido) if sentido in (1, -1, 0) else None
    fn = getattr(tuberia, 'establecer_sentido_flujo', None)
    if callable(fn):
        fn(valor)
        return
    if hasattr(tuberia, 'sentido_flujo_calculado') and getattr(tuberia, 'sentido_flujo_calculado') == valor:
        return
    _llamar(tuberia, 'prepareGeometryChange')
    tuberia.sentido_flujo_calculado = valor
    _llamar(tuberia, 'update')


def limpiar_sentido_flujo_escena(scene):
    """Limpia las flechas calculadas previas en todas las tuberías de la escena."""
    if scene is None:
        return
    obtener_items = getattr(scene, 'items', None)
    if not callable(obtener_items):
        return
    for item in obtener_items():
        if hasattr(item, 'sentido_flujo_calculado') or all(
            hasattr(item, c) for c in ('longitud', 'diametro', 'caudal_Q')
        ):
            asignar_sentido_flujo(item, None)


def aplicar_sentido_flujo_ruta(nodo_inicio, ruta, signo=1):
    """Orienta una cadena de tuberías desde nodo_inicio (signo=1) o hacia él (signo=-1)."""
    nodo = nodo_inicio
    for tuberia in ruta:
        origen = getattr(tuberia, 'nodo_origen', None)
        destino = getattr(tuberia, 'nodo_destino', None)
        if signo == 0:
            asignar_sentido_flujo(tuberia, 0)
        else:
            hacia_adelante = (origen is nodo)
            asignar_sentido_flujo(tuberia, (1 if hacia_adelante else -1) * signo)
        if origen is nodo:
            nodo = destino
        elif destino is nodo:
            nodo = origen


def invalidar_resultados(elementos=(), ventana=None, limpiar_bomba=None):
    """Limpia todos los resultados; conserva exclusivamente los Q/D del usuario.

    Los objetos se reconocen por sus atributos, sin depender de clases gráficas.
    En la ventana real se reutiliza _limpiar_resultados_bomba; sin ventana existe
    una limpieza de datos equivalente y también testeable sin Qt.
    """
    if getattr(ventana, '_invalidando_resultados', False):
        return
    if ventana is not None:
        ventana._invalidando_resultados = True
    try:
        limpiar_bomba = limpiar_bomba or getattr(ventana, '_limpiar_resultados_bomba', None)
        vistos = set()
        for elemento in elementos:
            if id(elemento) in vistos:
                continue
            vistos.add(id(elemento))
            if all(hasattr(elemento, campo) for campo in ('longitud', 'diametro', 'caudal_Q')):
                _llamar(elemento, 'prepareGeometryChange')
                elemento.hf_calculado = None
                limpiar_desglose_tuberia(elemento)
                if getattr(elemento, '_q_por_energia', False):
                    elemento.caudal_Q = 0.0
                if getattr(elemento, '_d_por_energia', False):
                    elemento.diametro = 0.0
                _llamar(elemento, 'actualizar_etiqueta')
                _llamar(elemento, 'update')
                if getattr(ventana, 'tuberia_seleccionada', None) is elemento:
                    campos = getattr(ventana, 'campos_tuberia', {})
                    for clave, bandera in (('Q', '_q_por_energia'), ('D', '_d_por_energia')):
                        if getattr(elemento, bandera, False) and clave in campos:
                            with bloquear_senales(campos[clave]):
                                _llamar(campos[clave], 'setText', '')
                    _llamar(ventana, '_refrescar_label_hf', elemento)
            if hasattr(elemento, 'hj_calculada'):
                elemento.hj_calculada = None
                _llamar(elemento, 'actualizar_etiqueta')
            if hasattr(elemento, 'id_bomba') or all(hasattr(elemento, c) for c in ('Q_op', 'H_op')):
                if callable(limpiar_bomba):
                    limpiar_bomba(elemento)
                else:
                    limpiar_datos_bomba(elemento)
                    _llamar(elemento, 'actualizar_tooltip')

        if ventana is not None:
            ventana.datos_exportacion = {}
            ventana._tabla_cache = None
            ventana._ultimo_datos_grafico_bombas = None
            ventana._perfiles_calculados = {}
            _llamar(getattr(ventana, 'egl_chart', None), 'limpiar_datos')
            grafico = getattr(ventana, 'grafico_bombas', None)
            _llamar(grafico, 'limpiar_datos')
            if grafico is not None and hasattr(grafico, 'reparto'):
                grafico.reparto = []
            for campo in ('_marcador_op_hq_pos', '_marcador_op_eta_pos'):
                if grafico is not None and hasattr(grafico, campo):
                    setattr(grafico, campo, None)
            tabla = getattr(ventana, 'tabla_excel_preview', None)
            _llamar(tabla, 'clearContents')
            _llamar(tabla, 'setRowCount', 0)
            _llamar(tabla, 'setColumnCount', 0)
            _llamar(getattr(ventana, 'texto_resultados', None), 'clear')
            _llamar(ventana, '_limpiar_barra_perdidas')
            _llamar(getattr(ventana, 'contenedor_barras', None), 'hide')
            _llamar(getattr(ventana, 'boton_excel', None), 'hide')
            _llamar(ventana, '_mostrar_tabla_vacia')
            _llamar(ventana, '_sincronizar_estado_bomba_curvas')
    finally:
        if ventana is not None:
            ventana._invalidando_resultados = False
