"""Contratos inmutables de resultados de tramo, en SI y sin dependencias de UI.

Q y hf son magnitudes positivas o cero; origen/destino expresan la dirección.
Los IDs/puertos no suministrados se representan con None, sin inventar topología.
La serialización conserva todos los campos y rechaza números no finitos.
"""

from dataclasses import dataclass, fields, is_dataclass
import math
from typing import Literal


def _json_finito(valor, ruta):
    if valor is None or isinstance(valor, (str, bool)):
        return valor
    if isinstance(valor, (int, float)):
        if not math.isfinite(valor):
            raise ValueError(f'{ruta} debe ser finito; NaN e infinito no están permitidos.')
        return float(valor) if isinstance(valor, float) else int(valor)
    if is_dataclass(valor) and not isinstance(valor, type):
        return {campo.name: _json_finito(getattr(valor, campo.name), f'{ruta}.{campo.name}')
                for campo in fields(valor)}
    if isinstance(valor, tuple):
        return [_json_finito(v, f'{ruta}[{i}]') for i, v in enumerate(valor)]
    raise TypeError(f'{ruta}: tipo no serializable: {type(valor).__name__}.')


@dataclass(frozen=True)
class PerdidaAccesorio:
    id: str
    segmento_id: str
    x: float | None               # m desde el inicio efectivo del segmento
    K: float
    LeD: float
    hf: float                     # m, con v y f del segmento propietario

    def to_dict(self) -> dict:
        return _json_finito(self, type(self).__name__)


@dataclass(frozen=True)
class ResultadoTramo:
    id: str | None
    ramal_id: str | None
    origen: str | None
    destino: str | None
    L: float
    D: float
    eps: float
    K: float
    LeD: float
    Q: float
    Q_procedencia: Literal['dato', 'calculado']
    D_procedencia: Literal['dato', 'calculado']
    area: float
    v: float
    Re: float
    f: float | None
    ley: Literal['reposo', 'laminar', 'colebrook']
    regimen: str
    hf_distribuida: float
    hf_localizada: float
    hf_total: float
    accesorios: tuple[PerdidaAccesorio, ...]

    def __post_init__(self):
        # frozen no basta si el llamador entrega una lista mutable de accesorios.
        accesorios = tuple(self.accesorios)
        if not all(isinstance(a, PerdidaAccesorio) for a in accesorios):
            raise TypeError('accesorios debe contener objetos PerdidaAccesorio.')
        object.__setattr__(self, 'accesorios', accesorios)

    @property
    def rugosidad_relativa(self):
        return self.eps / self.D

    @property
    def inv_raiz_f(self):
        return None if self.f is None else 1 / math.sqrt(self.f)

    @property
    def karman(self):
        return None if self.f is None else self.Re * math.sqrt(self.f)

    def to_dict(self) -> dict:
        return _json_finito(self, type(self).__name__)


@dataclass(frozen=True)
class ResultadoBomba:
    id: str
    estacion_id: str
    etapa: int
    activa: bool
    Q: float
    H: float
    Q_min: float
    Q_max: float
    en_dominio: bool
    potencia_hidraulica: float
    potencia_eje: float | None
    eficiencia: float | None
    NPSHd: float | None
    NPSHr: float | None
    cavitacion: Literal['seguro', 'riesgo', 'desconocido']
    estado: str
    desconocidos: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, 'desconocidos', tuple(self.desconocidos))

    def to_dict(self) -> dict:
        return _json_finito(self, type(self).__name__)


@dataclass(frozen=True)
class ResultadoEstacion:
    id: str
    etapas: tuple[tuple[str, ...], ...]
    Q: float
    H: float
    potencia_hidraulica: float
    potencia_eje: float | None
    eficiencia: float | None
    balances: tuple[tuple[float, float], ...]  # (masa m3/s, energía m) por etapa
    bombas: tuple[ResultadoBomba, ...]
    estado: str
    mensaje: str
    iteraciones: int
    residuo_masa: float
    residuo_energia: float
    residuo_masa_relativo: float
    residuo_energia_relativo: float
    residuo_ecuacion: float
    tramos: tuple[ResultadoTramo, ...] = ()
    hf_succion: float = 0.0
    desconocidos: tuple[str, ...] = ()

    def __post_init__(self):
        for nombre in ('bombas', 'tramos', 'desconocidos'):
            object.__setattr__(self, nombre, tuple(getattr(self, nombre)))
        for nombre in ('etapas', 'balances'):
            object.__setattr__(self, nombre, tuple(tuple(v) for v in getattr(self, nombre)))

    @property
    def convergio(self):
        return self.estado == 'OK'

    @property
    def cavitacion(self):
        activas = [b.cavitacion for b in self.bombas if b.activa]
        if 'riesgo' in activas:
            return 'riesgo'
        if not activas or 'desconocido' in activas:
            return 'desconocido'
        return 'seguro'

    @property
    def NPSHd(self):
        primera = [b for b in self.bombas if b.etapa == 1 and b.activa]
        return min(b.NPSHd for b in primera) if primera and all(b.NPSHd is not None for b in primera) else None

    @property
    def NPSHr(self):
        # Resumen de compatibilidad; nunca convierte un dato ausente en seguridad.
        primera = [b for b in self.bombas if b.etapa == 1 and b.activa]
        return max(b.NPSHr for b in primera) if primera and all(b.NPSHr is not None for b in primera) else None

    def to_dict(self) -> dict:
        return _json_finito(self, type(self).__name__)


@dataclass(frozen=True)
class PuntoPerfil:
    s: float
    z: float | None
    EGL: float
    HGL: float
    v: float
    tipo: Literal['entrada', 'tubería', 'accesorio', 'borde', 'cambio de diámetro', 'bomba', 'salida']
    etiqueta: str
    tramo_id: str | None = None
    perdida: float = 0.0
    H_bomba: float = 0.0

    def to_dict(self) -> dict:
        return _json_finito(self, type(self).__name__)


@dataclass(frozen=True)
class PerfilRuta:
    id: str
    puntos: tuple[PuntoPerfil, ...]
    H_inicio: float
    H_final: float
    H_final_calculada: float
    hf_distribuida: float
    hf_localizada: float
    H_bombas: float
    residuo_energia: float
    residuo_energia_relativo: float
    estado: str
    mensaje: str

    def __post_init__(self):
        object.__setattr__(self, 'puntos', tuple(self.puntos))

    def to_dict(self) -> dict:
        return _json_finito(self, type(self).__name__)


@dataclass(frozen=True)
class PuntoCurva:
    Q: float
    H: float | None
    valido: bool
    estado: str
    eficiencia: float | None = None
    NPSHr: float | None = None

    def to_dict(self) -> dict:
        return _json_finito(self, type(self).__name__)
