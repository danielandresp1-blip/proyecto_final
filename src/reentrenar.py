"""Reentrenamiento y decision de promocion (PSet 4, secciones 4 y 7). Lo ejecuta reentrenamiento.yml.

  entrenar --lote-eval K   Reentrena con la misma preparacion (src/pipeline.py) y los hiperparametros
                           del champion, sin repetir el tuning. Datos: todo el historico del PSet 3 mas
                           los lotes etiquetados anteriores a K, con mas peso en los lotes recientes.
                           Registra la version nueva con el alias 'challenger' y compara champion y
                           challenger en el lote K, que ninguno de los dos vio al entrenar.
  decidir --version V      Aplica la decision humana: si se aprueba, 'champion' pasa a V y la API se
                           recarga; si se rechaza, el champion queda intacto. El motivo queda en MLflow.

Regla de promocion (seccion 4): el challenger reemplaza al champion si, en el mismo lote de
evaluacion, su costo de turnos mal asignados (k = 2) es menor por mas de una desviacion estandar del
costo en la validacion cruzada del champion (0,0039). Una diferencia menor puede ser azar.
"""
import argparse
import json
import os

import mlflow
import numpy as np
import pandas as pd
import requests
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.base import clone

from src.datos import agregar_features, cargar_obt, conectar
from src.pipeline import (FEATURES, TARGET, TIPOS_CONFIABLES, configurar_mlflow, costo_turnos,
                          preparar_datos, wape)

NOMBRE = "rossmann-modelo"
API_URL = os.getenv("API_URL", "http://localhost:8000")
PESO_LOTES = 10.0
# Desviacion del costo de turnos (k = 2) entre pliegues de la CV del champion (corrida tuning_hgb_mejor,
# d6e81855a4cc42c9b9219b99d7e44a41, PSet 3)
COSTO_CV_STD = 0.0039


def salida_kestra(datos: dict) -> None:
    print("::" + json.dumps({"outputs": datos}) + "::")


def leer_lotes(condicion: str, params: tuple) -> pd.DataFrame:
    """Lotes de la simulacion cuyas ventas reales ya llegaron (estan en VENTAS_REALES)."""
    columnas = ", ".join(["l.LOTE", f"l.{TARGET.upper()}"] + [f"l.{c.upper()}" for c in FEATURES])
    with conectar("OPERACION") as conn:
        df = conn.cursor().execute(
            f"SELECT {columnas} FROM LOTES_SIMULACION l "
            f"WHERE l.LOTE IN (SELECT DISTINCT LOTE FROM VENTAS_REALES) AND {condicion}", params,
        ).fetch_pandas_all()
    df.columns = df.columns.str.lower()
    return df


def entrenar(lote_eval: int, motivo: str) -> None:
    configurar_mlflow()
    cliente = MlflowClient()
    v_champion = cliente.get_model_version_by_alias(NOMBRE, "champion")
    champion = mlflow.sklearn.load_model(f"models:/{NOMBRE}@champion")

    # Datos: historico (pesa 1) + lotes etiquetados anteriores al de evaluacion (pesan PESO_LOTES)
    historico, _ = preparar_datos(agregar_features(cargar_obt()))
    recientes = leer_lotes("l.LOTE < %s", (lote_eval,))
    evaluacion = leer_lotes("l.LOTE = %s", (lote_eval,))
    if evaluacion.empty:
        raise SystemExit(f"El lote {lote_eval} todavia no tiene ventas reales")

    X = pd.concat([historico[FEATURES], recientes[FEATURES]], ignore_index=True)
    y = pd.concat([historico[TARGET], recientes[TARGET]], ignore_index=True).astype(float)
    pesos = np.r_[np.ones(len(historico)), np.full(len(recientes), PESO_LOTES)]

    challenger = clone(champion)  # misma preparacion y mismos hiperparametros, sin tuning
    challenger.fit(X, y, modelo__sample_weight=pesos)

    Xe, ye = evaluacion[FEATURES], evaluacion[TARGET].astype(float)
    pred_ch, pred_cl = champion.predict(Xe), challenger.predict(Xe)
    res = {
        "wape_champion": wape(ye, pred_ch), "wape_challenger": wape(ye, pred_cl),
        "costo_champion": costo_turnos(ye, pred_ch), "costo_challenger": costo_turnos(ye, pred_cl),
    }
    mejora = res["costo_champion"] - res["costo_challenger"]
    cumple = bool(mejora > COSTO_CV_STD)
    lotes_usados = sorted(recientes["lote"].unique().tolist())

    with mlflow.start_run(run_name=f"reentrenamiento_lote_{lote_eval}") as run:
        mlflow.set_tags({
            "fase": "reentrenamiento", "familia": "boosting", "motivo": motivo,
            "champion_previo": v_champion.version, "git_commit": os.getenv("GIT_COMMIT", "no disponible"),
        })
        mlflow.log_params({
            "lotes_entrenamiento": ",".join(map(str, lotes_usados)) or "ninguno",
            "lote_evaluacion": lote_eval, "peso_lotes": PESO_LOTES,
            "filas_historico": len(historico), "filas_lotes": len(recientes),
            "ventana": "historico completo + lotes etiquetados con mayor peso",
            "hiperparametros": f"los del champion v{v_champion.version} (sin tuning)",
        })
        mlflow.log_metrics({**{f"{k}_lote_eval": v for k, v in res.items()},
                            "mejora_costo": mejora, "umbral_promocion": COSTO_CV_STD,
                            "cumple_regla": float(cumple)})
        clase = type(challenger.named_steps["modelo"])
        info = mlflow.sklearn.log_model(
            challenger, name="modelo", registered_model_name=NOMBRE,
            signature=infer_signature(Xe.head(5), challenger.predict(Xe.head(5))), input_example=Xe.head(5),
            skops_trusted_types=TIPOS_CONFIABLES + [f"{clase.__module__}.{clase.__name__}"],
        )
    version = str(info.registered_model_version)
    cliente.set_registered_model_alias(NOMBRE, "challenger", version)

    print(f"Motivo del reentrenamiento: {motivo}")
    print(f"Datos: historico ({len(historico)} filas) + lotes {lotes_usados} ({len(recientes)} filas, peso {PESO_LOTES})")
    print(f"Lote de evaluacion: {lote_eval} ({len(evaluacion)} filas, ninguno de los dos lo vio al entrenar)")
    print(f"  Champion   v{v_champion.version}: WAPE {res['wape_champion']:.4f} | costo de turnos {res['costo_champion']:.4f}")
    print(f"  Challenger v{version}: WAPE {res['wape_challenger']:.4f} | costo de turnos {res['costo_challenger']:.4f}")
    print(f"Mejora de costo: {mejora:.4f} (umbral de promocion: {COSTO_CV_STD})")
    print(f"Regla de promocion: el challenger {'CUMPLE' if cumple else 'NO CUMPLE'}")
    salida_kestra({"version": version, "champion_previo": v_champion.version, "run_id": run.info.run_id,
                   "cumple_regla": cumple, "mejora_costo": round(mejora, 4),
                   **{k: round(v, 4) for k, v in res.items()}})


def decidir(version: str, aprobar: bool, motivo: str) -> None:
    configurar_mlflow()
    cliente = MlflowClient()
    v = cliente.get_model_version(NOMBRE, version)
    decision = "aprobado" if aprobar else "rechazado"
    for clave, valor in {"decision": decision, "motivo_decision": motivo or "sin motivo"}.items():
        cliente.set_model_version_tag(NOMBRE, version, clave, valor)
        cliente.set_tag(v.run_id, clave, valor)

    if aprobar:
        previo = cliente.get_model_version_by_alias(NOMBRE, "champion").version
        cliente.set_registered_model_alias(NOMBRE, "champion", version)
        cliente.delete_registered_model_alias(NOMBRE, "challenger")
        r = requests.post(f"{API_URL}/recargar", timeout=300)
        r.raise_for_status()
        print(f"APROBADO: champion pasa de v{previo} a v{version}. La API ahora usa v{r.json()['version']}.")
    else:
        print(f"RECHAZADO: el champion se mantiene; v{version} queda como challenger.")
    print(f"Motivo: {motivo}")
    salida_kestra({"decision": decision})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="accion", required=True)
    e = sub.add_parser("entrenar")
    e.add_argument("--lote-eval", type=int, required=True)
    e.add_argument("--motivo", default=os.getenv("MOTIVO", "sin motivo"))
    d = sub.add_parser("decidir")
    d.add_argument("--version", required=True)
    d.add_argument("--aprobar", choices=["true", "false"], required=True)
    d.add_argument("--motivo", default=os.getenv("MOTIVO", ""))
    args = parser.parse_args()
    if args.accion == "entrenar":
        entrenar(args.lote_eval, args.motivo)
    else:
        decidir(args.version, args.aprobar == "true", args.motivo)
