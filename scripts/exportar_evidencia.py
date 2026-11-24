"""Exporta la evidencia del proyecto a docs/ en CSV (PSet 4, seccion 10).

  docs/predicciones.csv      OPERACION.PREDICCIONES (cada prediccion con sus entradas, version y run_id)
  docs/monitoreo.csv         OPERACION.MONITOREO
  docs/alertas.csv           OPERACION.ALERTAS
  docs/corridas.csv          todas las corridas del experimento 'rossmann' (mlflow.search_runs)
  docs/reentrenamientos.csv  solo las corridas con fase = 'reentrenamiento'

Se ejecuta desde la raiz del proyecto, con MLflow levantado:  python scripts/exportar_evidencia.py
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.append(str(RAIZ))

import mlflow  # noqa: E402

from src.datos import conectar  # noqa: E402
from src.pipeline import EXPERIMENTO, configurar_mlflow  # noqa: E402

DOCS = RAIZ / "docs"
TABLAS = {
    "predicciones.csv": "SELECT * FROM PREDICCIONES ORDER BY TS, LOTE, STORE_ID, FECHA",
    "monitoreo.csv": "SELECT * FROM MONITOREO ORDER BY LOTE, TIPO, METRICA, VARIABLE",
    "alertas.csv": "SELECT * FROM ALERTAS ORDER BY LOTE, SEVERIDAD, METRICA",
}


def exportar(df, nombre: str) -> None:
    ruta = DOCS / nombre
    df.to_csv(ruta, index=False, encoding="utf-8")
    print(f"{nombre:<24} {len(df):>7} filas  {ruta.stat().st_size / 1e6:6.2f} MB")


with conectar("OPERACION") as conn:
    for nombre, sql in TABLAS.items():
        df = conn.cursor().execute(sql).fetch_pandas_all()
        exportar(df, nombre)

configurar_mlflow()
corridas = mlflow.search_runs(experiment_names=[EXPERIMENTO], order_by=["start_time ASC"])
exportar(corridas, "corridas.csv")
exportar(corridas[corridas["tags.fase"] == "reentrenamiento"], "reentrenamientos.csv")
