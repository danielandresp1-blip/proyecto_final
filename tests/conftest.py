"""Configuracion comun de las pruebas.

En CI no hay servidor de MLflow ni Snowflake: la API carga la copia del modelo de tests/fixtures
(MODELO_RUTA) y no registra predicciones (REGISTRAR_PREDICCIONES=false).
"""
import json
import math
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RAIZ = FIXTURES.parent.parent

os.environ["MODELO_RUTA"] = str(FIXTURES / "modelo")
os.environ["REGISTRAR_PREDICCIONES"] = "false"
os.environ["MODO_RESPALDO"] = "false"
sys.path.insert(0, str(RAIZ / "api"))

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def cliente():
    with TestClient(main.app) as c:  # el "with" ejecuta el arranque (carga del modelo)
        yield c


@pytest.fixture(scope="session")
def muestra() -> pd.DataFrame:
    return pd.read_parquet(FIXTURES / "muestra_prueba.parquet")


@pytest.fixture(scope="session")
def referencia() -> dict:
    return json.loads((FIXTURES / "referencia.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def modelo(cliente):
    return main.estado["modelo"]


def fila_a_registro(fila: pd.Series) -> dict:
    """Convierte una fila de la muestra al formato de entrada de la API."""
    registro = {"store_id": int(fila["store_id"]), "fecha": str(pd.Timestamp(fila["sales_date"]).date())}
    for col in main.FEATURES:
        valor = fila[col]
        if isinstance(valor, float) and math.isnan(valor):
            registro[col] = None
        elif col in main.BOOLEANAS:
            registro[col] = bool(valor)
        elif col in ("day_of_month", "day_of_week_iso", "month"):
            registro[col] = int(valor)
        elif col in main.NUMERICAS:
            registro[col] = float(valor)
        else:
            registro[col] = str(valor)
    return registro


@pytest.fixture(scope="session")
def registro_valido(muestra) -> dict:
    return fila_a_registro(muestra.iloc[0])
