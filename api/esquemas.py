"""Esquemas de entrada y salida de la API.

La entrada coincide con la firma del modelo registrado en MLflow (rossmann-modelo): las 26 features
de src/pipeline.py (FEATURES), con sus tipos, rangos y categorias permitidas. store_id y fecha
no entran al modelo: identifican la prediccion en la tabla PREDICCIONES.
"""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Registro(BaseModel):
    """Una tienda en un dia. Las features con rezago de 42 dias las calcula quien llama (src/datos.py)."""

    model_config = ConfigDict(extra="forbid")

    # Identificadores (no son features)
    store_id: int = Field(ge=1, le=1115)
    fecha: date

    # Numericas
    sales_mean_lag42_28d: float = Field(gt=0, le=100_000)
    sales_mean_lag42_dow: float = Field(gt=0, le=100_000)  # tambien es la regla del gerente
    day_of_month: int = Field(ge=1, le=31)

    # Numericas con faltantes estructurales (la tienda no participa o no se sabe desde cuando)
    weeks_since_promo2_start: Optional[float] = Field(default=None, ge=0, le=1_000)
    months_since_competition_open: Optional[float] = Field(default=None, ge=0, le=1_500)
    competition_distance_m: Optional[float] = Field(default=None, ge=0, le=100_000)

    # Booleanas (las del dia anterior/siguiente pueden faltar en los bordes de la historia)
    is_promo: bool
    is_promo2_active: bool
    participates_promo2: bool
    is_school_holiday: bool
    is_state_holiday: bool
    was_open_prev_day: Optional[bool] = None
    is_open_next_day: Optional[bool] = None
    was_promo_prev_day: Optional[bool] = None
    is_state_holiday_prev_day: Optional[bool] = None
    is_state_holiday_next_day: Optional[bool] = None

    # Categoricas
    store_type: Literal["a", "b", "c", "d"]
    assortment: Literal["a", "b", "c"]
    state_holiday_type: Literal["none", "public", "easter", "christmas"]
    competition_status: Literal["open", "not_yet_open", "unknown_since", "no_info"]
    day_of_week_iso: int = Field(ge=1, le=7)
    month: int = Field(ge=1, le=12)


class Solicitud(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registros: list[Registro] = Field(min_length=1, max_length=50_000)
    lote: Optional[str] = Field(default=None, max_length=50)  # periodo de la simulacion


class Prediccion(BaseModel):
    id_prediccion: str
    store_id: int
    fecha: date
    ventas_pronosticadas: float
    ventas_regla_actual: float
    ajuste_dotacion_pct: float
    decision: Literal["reforzar_turnos", "mantener_plan", "reducir_turnos"]
    version_modelo: Optional[str]


class Respuesta(BaseModel):
    predicciones: list[Prediccion]
    modelo: str
    version_modelo: Optional[str]
    run_id: Optional[str]
    respaldo: bool
    motivo_respaldo: Optional[str]
    latencia_ms: float
    registrada: bool
