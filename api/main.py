"""Servicio de prediccion de ventas Rossmann (PSet 4, seccion 2).

- Carga el modelo desde el Model Registry por alias (models:/rossmann-modelo@champion).
  Cambiar de version no requiere reconstruir la imagen: basta mover el alias y llamar a POST /recargar
  (o reiniciar el contenedor).
- Si el modelo no carga, o si MODO_RESPALDO=true, usa la regla del gerente (PSet 1) y lo indica.
- Cada prediccion queda registrada en Snowflake (PREDICCIONES) con su id, timestamp, entradas,
  salida, version del modelo y latencia.
"""
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from esquemas import Respuesta, Solicitud

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------- configuracion
MODELO_NOMBRE = os.getenv("MODELO_NOMBRE", "rossmann-modelo")
MODELO_ALIAS = os.getenv("MODELO_ALIAS", "champion")
# En CI no hay servidor de MLflow: se usa la copia exportada en tests/fixtures (MODELO_RUTA).
MODELO_RUTA = os.getenv("MODELO_RUTA")
MODO_RESPALDO = os.getenv("MODO_RESPALDO", "false").lower() == "true"
REGISTRAR = os.getenv("REGISTRAR_PREDICCIONES", "true").lower() == "true"

# Umbral de la decision: variacion del pronostico frente a la regla del gerente
UMBRAL_DECISION = float(os.getenv("UMBRAL_DECISION", "0.15"))

BOOLEANAS = [
    "is_promo", "is_promo2_active", "participates_promo2", "is_school_holiday",
    "is_state_holiday", "was_open_prev_day", "is_open_next_day", "was_promo_prev_day",
    "is_state_holiday_prev_day", "is_state_holiday_next_day",
]
NUMERICAS = [
    "sales_mean_lag42_28d", "sales_mean_lag42_dow", "day_of_month",
    "weeks_since_promo2_start", "months_since_competition_open", "competition_distance_m",
]
FEATURES = [
    *NUMERICAS,
    *BOOLEANAS,
    "store_type", "assortment", "state_holiday_type", "competition_status",
    "day_of_week_iso", "month",
]

# ---------------------------------------------------------------- estado del modelo
estado = {"modelo": None, "version": None, "run_id": None, "error": None}


def cargar_modelo() -> None:
    """Carga el modelo por alias. Si falla, el servicio queda en modo de respaldo."""
    import mlflow

    try:
        if MODELO_RUTA:
            estado["modelo"] = mlflow.sklearn.load_model(MODELO_RUTA)
            estado["version"], estado["run_id"] = "fixture", None
        else:
            cliente = mlflow.MlflowClient()
            version = cliente.get_model_version_by_alias(MODELO_NOMBRE, MODELO_ALIAS)
            estado["modelo"] = mlflow.sklearn.load_model(f"models:/{MODELO_NOMBRE}@{MODELO_ALIAS}")
            estado["version"], estado["run_id"] = version.version, version.run_id
        estado["error"] = None
        log.info("Modelo cargado: %s v%s", MODELO_NOMBRE, estado["version"])
    except Exception as e:  # noqa: BLE001 - cualquier fallo activa el respaldo
        estado.update(modelo=None, version=None, run_id=None, error=str(e)[:300])
        log.error("No se pudo cargar el modelo: %s", e)


# ---------------------------------------------------------------- registro en Snowflake
TABLA = "PREDICCIONES"
DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLA} (
    ID_PREDICCION VARCHAR, TS TIMESTAMP_NTZ, LOTE VARCHAR,
    STORE_ID INTEGER, FECHA DATE, ENTRADAS VARCHAR,
    VENTAS_PRONOSTICADAS FLOAT, VENTAS_REGLA FLOAT, AJUSTE_DOTACION_PCT FLOAT, DECISION VARCHAR,
    MODELO VARCHAR, VERSION_MODELO VARCHAR, RUN_ID VARCHAR, RESPALDO BOOLEAN, LATENCIA_MS FLOAT
)"""


def leer_llave_privada() -> bytes:
    """Lee la llave y la entrega en bytes. Se pasa como private_key (y no como private_key_file)
    porque el conector rechaza archivos con permisos amplios, que es como Docker en Windows
    monta los archivos del host."""
    from cryptography.hazmat.primitives import serialization

    with open(os.environ["LLAVE_PRIVADA_RUTA"], "rb") as f:
        llave = serialization.load_pem_private_key(f.read(), password=None)
    return llave.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def conectar_snowflake():
    import snowflake.connector

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.getenv("SNOWFLAKE_SCHEMA_OPERACION", "OPERACION"),
        private_key=leer_llave_privada(),
        enable_server_session_keep_alive_auto_detection=False,
    )


def preparar_tabla() -> None:
    if not REGISTRAR:
        return
    try:
        esquema = os.getenv("SNOWFLAKE_SCHEMA_OPERACION", "OPERACION")
        with conectar_snowflake() as conn:
            conn.cursor().execute(f"CREATE SCHEMA IF NOT EXISTS {esquema}")
            conn.cursor().execute(f"USE SCHEMA {esquema}")
            conn.cursor().execute(DDL)
    except Exception as e:  # noqa: BLE001
        log.error("No se pudo preparar la tabla %s: %s", TABLA, e)


def registrar(filas: pd.DataFrame) -> bool:
    if not REGISTRAR:
        return False
    try:
        from snowflake.connector.pandas_tools import write_pandas

        with conectar_snowflake() as conn:
            write_pandas(conn, filas, TABLA, use_logical_type=True)
        return True
    except Exception as e:  # noqa: BLE001 - la prediccion se entrega aunque falle el registro
        log.error("No se pudo registrar en %s: %s", TABLA, e)
        return False


# ---------------------------------------------------------------- logica de prediccion
def decidir(ventas_modelo: np.ndarray, ventas_regla: np.ndarray):
    """Ajuste de la dotacion frente a la regla del gerente y decision para el turno."""
    ajuste = ventas_modelo / ventas_regla - 1
    decision = np.where(ajuste > UMBRAL_DECISION, "reforzar_turnos",
                        np.where(ajuste < -UMBRAL_DECISION, "reducir_turnos", "mantener_plan"))
    return ajuste * 100, decision


@asynccontextmanager
async def ciclo_de_vida(_app: FastAPI):
    cargar_modelo()
    preparar_tabla()
    yield


app = FastAPI(title="Pronostico de ventas Rossmann", version="1.0", lifespan=ciclo_de_vida)


@app.exception_handler(RequestValidationError)
async def entrada_invalida(_request: Request, exc: RequestValidationError):
    """422 con el campo que fallo y el motivo, en lugar del detalle completo de Pydantic."""
    campos = [
        {"campo": ".".join(str(p) for p in e["loc"] if p != "body"), "mensaje": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"error": "entrada invalida", "campos": campos})


@app.get("/salud")
def salud():
    return {
        "estado": "ok",
        "modelo_cargado": estado["modelo"] is not None,
        "modo_respaldo": MODO_RESPALDO or estado["modelo"] is None,
        "error_carga": estado["error"],
    }


@app.get("/modelo")
def modelo():
    return {
        "nombre": MODELO_NOMBRE,
        "alias": MODELO_ALIAS,
        "version": estado["version"],
        "run_id": estado["run_id"],
        "modo_respaldo": MODO_RESPALDO or estado["modelo"] is None,
    }


@app.post("/recargar")
def recargar():
    """Vuelve a leer el alias del Model Registry (promocion o rollback sin reconstruir la imagen)."""
    cargar_modelo()
    return modelo()


@app.post("/predecir", response_model=Respuesta)
def predecir(solicitud: Solicitud):
    inicio = time.perf_counter()
    df = pd.DataFrame([r.model_dump() for r in solicitud.registros])
    X = df[FEATURES].copy()
    X[BOOLEANAS] = X[BOOLEANAS].astype(float)  # el modelo se entreno con booleanas como 0/1
    X[NUMERICAS] = X[NUMERICAS].astype(float)  # None -> NaN, que imputa el pipeline
    regla = df["sales_mean_lag42_dow"].to_numpy(dtype=float)

    respaldo = MODO_RESPALDO or estado["modelo"] is None
    if respaldo:
        motivo = "interruptor MODO_RESPALDO activo" if MODO_RESPALDO else "el modelo no cargo"
        ventas = regla.copy()
        nombre, version, run_id = "regla_gerente", None, None
    else:
        motivo = None
        ventas = np.clip(estado["modelo"].predict(X), 0, None)
        nombre, version, run_id = MODELO_NOMBRE, estado["version"], estado["run_id"]

    ajuste_pct, decision = decidir(ventas, regla)
    ids = [str(uuid.uuid4()) for _ in range(len(df))]
    latencia_ms = (time.perf_counter() - inicio) * 1000

    salida = pd.DataFrame({
        "ID_PREDICCION": ids,
        "TS": datetime.now(timezone.utc).replace(tzinfo=None),
        "LOTE": solicitud.lote,
        "STORE_ID": df["store_id"],
        "FECHA": pd.to_datetime(df["fecha"]).dt.date,
        "ENTRADAS": [json.dumps(r.model_dump(mode="json")) for r in solicitud.registros],
        "VENTAS_PRONOSTICADAS": ventas.round(2),
        "VENTAS_REGLA": regla.round(2),
        "AJUSTE_DOTACION_PCT": ajuste_pct.round(2),
        "DECISION": decision,
        "MODELO": nombre,
        "VERSION_MODELO": version,
        "RUN_ID": run_id,
        "RESPALDO": respaldo,
        "LATENCIA_MS": round(latencia_ms, 2),
    })
    texto = ["LOTE", "MODELO", "VERSION_MODELO", "RUN_ID"]
    salida[texto] = salida[texto].astype("string")  # evita columnas sin tipo cuando son nulas
    registrada = registrar(salida)

    return {
        "predicciones": [
            {
                "id_prediccion": f["ID_PREDICCION"],
                "store_id": int(f["STORE_ID"]),
                "fecha": f["FECHA"],
                "ventas_pronosticadas": float(f["VENTAS_PRONOSTICADAS"]),
                "ventas_regla_actual": float(f["VENTAS_REGLA"]),
                "ajuste_dotacion_pct": float(f["AJUSTE_DOTACION_PCT"]),
                "decision": f["DECISION"],
                "version_modelo": version,
            }
            for f in salida.to_dict("records")
        ],
        "modelo": nombre,
        "version_modelo": version,
        "run_id": run_id,
        "respaldo": respaldo,
        "motivo_respaldo": motivo,
        "latencia_ms": round(latencia_ms, 2),
        "registrada": registrada,
    }
