"""Exporta lo que necesitan las pruebas en CI, donde no hay servidor de MLflow ni Snowflake.

- tests/fixtures/modelo/              copia del champion (mlflow.sklearn.save_model)
- tests/fixtures/muestra_prueba.parquet  periodo de prueba completo (2015-06-20 a 2015-07-31)
- tests/fixtures/referencia.json      version, run_id y WAPE de prueba registrados en MLflow

Se ejecuta una vez, desde la raiz del proyecto, con MLflow levantado (docker compose up -d mlflow):
    python scripts/exportar_fixtures.py
"""
import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.append(str(RAIZ))

import mlflow  # noqa: E402
from mlflow import MlflowClient  # noqa: E402

from src.datos import agregar_features, cargar_obt  # noqa: E402
from src.pipeline import FEATURES, TARGET, TIPOS_CONFIABLES, configurar_mlflow, preparar_datos, wape  # noqa: E402

FIXTURES = RAIZ / "tests" / "fixtures"
NOMBRE, ALIAS = "rossmann-modelo", "champion"

configurar_mlflow()
cliente = MlflowClient()
version = cliente.get_model_version_by_alias(NOMBRE, ALIAS)
wape_registrado = cliente.get_run(version.run_id).data.metrics["wape_prueba"]
modelo = mlflow.sklearn.load_model(f"models:/{NOMBRE}@{ALIAS}")

# 1. Copia del modelo
destino = FIXTURES / "modelo"
if destino.exists():
    shutil.rmtree(destino)
clase = type(modelo.named_steps["modelo"])
mlflow.sklearn.save_model(
    modelo, str(destino),
    skops_trusted_types=TIPOS_CONFIABLES + [f"{clase.__module__}.{clase.__name__}"],
)

# 2. Periodo de prueba completo
_, prueba = preparar_datos(agregar_features(cargar_obt()))
columnas = ["store_id", "sales_date", TARGET] + FEATURES
prueba[columnas].to_parquet(FIXTURES / "muestra_prueba.parquet", index=False)

# 3. Referencia para la prueba de modelo
reproducido = wape(prueba[TARGET], modelo.predict(prueba[FEATURES]))
referencia = {
    "modelo": NOMBRE,
    "alias": ALIAS,
    "version": version.version,
    "run_id": version.run_id,
    "wape_prueba_registrado": wape_registrado,
    "filas": len(prueba),
}
(FIXTURES / "referencia.json").write_text(json.dumps(referencia, indent=2), encoding="utf-8")

print(json.dumps(referencia, indent=2))
print("WAPE reproducido al exportar:", reproducido)
