# Simulador de flujo de fluidos

Proyecto dividido en módulos por responsabilidad.

## Estructura

```
simulador/
├── main.py                      Punto de entrada (ejecutar este archivo)
├── motor/                       Cálculo hidráulico (sin interfaz gráfica)
│   ├── motor_fluidos.py         Clase MotorFluidos (une fricción, redes, bombas y ramificadas)
│   ├── friccion.py              Darcy-Weisbach, Colebrook, Kármán, cálculo de Q y D
│   ├── redes.py                 Redes ramificadas, doble nudo y serie por energía
│   ├── bombas.py                Bombas centrífugas, curvas H-Q, series, paralelo, NPSH
│   └── bomba_ramificada.py      Bombas en redes ramificadas (balance en nudo j, método de 6 fases)
└── ui/                          Interfaz gráfica (PyQt5)
    ├── constantes.py            Factores SI, textos y tema visual
    ├── recursos.py              Ruta a logos e íconos
    ├── iconos.py                Dibujo de los íconos de herramientas
    ├── reportes.py              Componentes HTML de los reportes
    ├── widgets.py               Widgets auxiliares
    ├── dialogos.py              Diálogos de fluido y de suposiciones
    ├── escena.py                Escena y vista del lienzo CAD
    ├── perfil_egl.py            Gráfico de la línea de energía (EGL/HGL)
    ├── graficos.py              Tanques, tuberías, accesorios, nodos y textos
    └── ventana/                 Ventana principal, separada en mixins
        ├── principal.py         MainWindow (une todos los mixins)
        ├── interfaz.py          Construcción de paneles, lienzo y cabecera
        ├── estilos.py           Hoja de estilos
        ├── barra_herramientas.py
        ├── vistas.py            Vistas CAD / TABLA / CURVAS
        ├── panel_propiedades.py
        ├── dashboard.py
        ├── resolucion.py        Tuberías en serie y en paralelo
        ├── ramificadas.py       Uniones ramificadas y doble nudo
        ├── bernoulli.py
        ├── exportacion.py       Exportar a Excel
        └── memoria_calculo.py   Hojas de memoria de cálculo
```

## Ejecutar

Desde la carpeta `simulador/`:

```
python -m pip install -r requirements.txt
python main.py
```

Los archivos de imagen (`logo_1.ico`, `logo_2.jpg`, `logo_3.png`) deben estar en la carpeta `simulador/`, al lado de `main.py`.

Se requiere Python 3.10 o posterior. `requirements.txt` incluye PyQt5 (interfaz),
numpy (curvas de bombas), XlsxWriter (exportación), openpyxl (vista previa y
verificación de Excel), pyinstaller (compilación con `python build_exe.py`) y
pytest (tests). No se necesita SciPy.

El botón **?**, junto al selector de trazado, abre una guía con las demostraciones
`Recto.mp4` y `Ortogonal.mp4`. Incluye controles con iconos para reproducir,
pausar y reiniciar, además de una barra de avance. Los clips se repiten sin
sonido y se leen desde la raíz del proyecto; se incluyen al compilar
con `build_exe.py`. La reproducción usa PyAV (`av` en `requirements.txt`).

Para verificar el proyecto sin crear ventanas:

```powershell
python -m pytest -q
```

La barra usa botones tipo cápsula que se elevan al señalarse y se comprimen
con una recuperación elástica al pulsarlos. Un brillo los recorre una vez.
El indicador lateral se desliza entre vistas; los paneles aparecen mediante
un breve desplazamiento y fundido. Los objetos nuevos entran con un pequeño
rebote visual; el agua de los tanques oscila brevemente al señalarlos y las
bombas responden con un halo. Los interruptores conservan su deslizamiento.
No hay ciclos permanentes ni cambios en la geometría o los datos de la red.
Las transiciones de paneles ceden inmediatamente al clic, teclado o rueda.
Se respeta la opción de animaciones de Windows.
También pueden desactivarse al iniciar con `SIMULADOR_REDUCIR_MOVIMIENTO=1`.

## Datos y convención hidráulica

El motor recibe unidades SI y rechaza NaN, infinitos y datos fuera de dominio:
L, D conocido, rho y mu son positivos; eps, K y Le/D no negativos. Q es siempre
una magnitud no negativa (m³/s). La orientación se declara aparte: en serie
inicio→fin, en bombas aspiración→descarga y en cada ramal mediante `direccion`
(`Entra a la unión` o `Sale de la unión`). Los balances netos y las cotas/cargas
pueden tener signo; un Q de entrada negativo se rechaza, no se convierte con abs.

La UI y el JSON conservan D=0 como diámetro desconocido únicamente cuando hay
un Q conocido positivo y hf o altura disponible para resolverlo. El motor que
requiere D conocido rechaza D=0 e indica que debe usarse `calcular_D` con Q y hf.
Q=0 conserva el significado de caudal nulo/incógnita de la UI. Al guardar se
persisten `_q_por_energia` y `_d_por_energia`; los archivos antiguos sin esos
campos se leen con ambos en false, porque no permiten reconstruir su procedencia.

Cada ejecución devuelve su propio `historial_iteraciones`. No existe una lista
mutable en `MotorFluidos`: el historial se obtiene del resultado, y ejecuciones
sucesivas o concurrentes no lo comparten. `limpiar_iteraciones()` solo limpia el
contexto activo, sin modificar resultados ya devueltos.

La curva del sistema ramificado expande sus límites de Q/H con un máximo de
expansiones, valida masa y energía a 1e-8 relativo y devuelve estado y diagnósticos
por punto. Agotar un límite de búsqueda no equivale a converger.

## Transición laminar–turbulento

Criterio hidráulico: **conservar el salto en
Re=2000**. La constante `RE_LIMITE_LAMINAR` no cambia: para Re<2000 se utiliza
f=64/Re; para Re>=2000, Colebrook del profesor (0.86·ln). Con eps/D=0, f pasa
aproximadamente de 0.032 a 0.050. No se interpola una zona de transición. Si una
carga cae en el hueco producido por ese salto, el solver debe informar falta de
convergencia; no se ajusta la ley para forzar un resultado.

## Dónde tocar cada cosa

- Cambiar una fórmula de pérdidas → `motor/friccion.py`
- Cambiar cómo se resuelve una red simple o ramificada → `motor/redes.py` o `ui/ventana/resolucion.py` / `ramificadas.py`
- Cambiar bombas o cálculo de bombas en redes ramificadas → `motor/bombas.py` y `motor/bomba_ramificada.py`
- Cambiar colores o tamaños → `ui/constantes.py` y `ui/ventana/estilos.py`
- Cambiar cómo se dibuja un accesorio o bomba → `ui/graficos.py`
- Cambiar el panel de propiedades → `ui/ventana/panel_propiedades.py`
- Cambiar memorias de cálculo en Excel → `ui/ventana/memoria_calculo.py` y `exportacion.py`
