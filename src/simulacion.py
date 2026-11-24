"""Pasos de la simulacion de produccion que ejecuta Kestra (produccion_lotes.yml).

  puntuar   --lote N  Lee el lote N de Snowflake (sin las ventas reales), pide los pronosticos a la API
                      y la API los registra en PREDICCIONES.
  etiquetar --lote N  Las ventas reales del lote N "llegan" cuando su periodo termino: se copian a
                      VENTAS_REALES. Kestra lo hace en el paso siguiente (lote N+1), respetando el horizonte.

Uso:  python -m src.simulacion puntuar --lote 1
"""
import argparse
import math
import os

import requests

from src.datos import conectar
from src.pipeline import BOOLEANAS, FEATURES

ESQUEMA = "OPERACION"
API_URL = os.getenv("API_URL", "http://localhost:8000")
TAMANO_SOLICITUD = 2_500  # filas por solicitud a la API


def leer_lote(lote: int):
    columnas = ", ".join(["STORE_ID", "SALES_DATE"] + [c.upper() for c in FEATURES])
    with conectar(ESQUEMA) as conn:
        df = conn.cursor().execute(
            f"SELECT {columnas} FROM LOTES_SIMULACION WHERE LOTE = %s ORDER BY SALES_DATE, STORE_ID",
            (lote,),
        ).fetch_pandas_all()
    df.columns = df.columns.str.lower()
    return df


def a_registros(df) -> list[dict]:
    registros = []
    for fila in df.to_dict("records"):
        r = {"store_id": int(fila.pop("store_id")), "fecha": str(fila.pop("sales_date"))}
        for k, v in fila.items():
            if v is None or (isinstance(v, float) and math.isnan(v)):
                r[k] = None
            elif k in BOOLEANAS:
                r[k] = bool(v)  # en los lotes las booleanas estan como 0/1
            else:
                r[k] = v
        registros.append(r)
    return registros


def puntuar(lote: int) -> None:
    df = leer_lote(lote)
    if df.empty:
        raise SystemExit(f"El lote {lote} no existe en LOTES_SIMULACION")
    # Repetir un lote no duplica sus predicciones
    with conectar(ESQUEMA) as conn:
        conn.cursor().execute("DELETE FROM PREDICCIONES WHERE LOTE = %s", (str(lote),))

    registros = a_registros(df)
    decisiones, respaldo, versiones = {}, False, set()
    for i in range(0, len(registros), TAMANO_SOLICITUD):
        parte = registros[i:i + TAMANO_SOLICITUD]
        r = requests.post(f"{API_URL}/predecir", json={"registros": parte, "lote": str(lote)}, timeout=300)
        r.raise_for_status()
        cuerpo = r.json()
        if not cuerpo["registrada"]:
            raise SystemExit("La API no pudo registrar las predicciones en Snowflake")
        respaldo |= cuerpo["respaldo"]
        versiones.add(cuerpo["version_modelo"])
        for p in cuerpo["predicciones"]:
            decisiones[p["decision"]] = decisiones.get(p["decision"], 0) + 1

    print(f"Lote {lote}: {len(registros)} predicciones | versiones del modelo {versiones} | "
          f"respaldo={respaldo} | decisiones {decisiones}")


def etiquetar(lote: int) -> None:
    with conectar(ESQUEMA) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS VENTAS_REALES (
                LOTE INTEGER, STORE_ID INTEGER, FECHA DATE, SALES FLOAT, ALTERADO BOOLEAN,
                LLEGADA_TS TIMESTAMP_NTZ)""")
        cur.execute("DELETE FROM VENTAS_REALES WHERE LOTE = %s", (lote,))
        cur.execute("""
            INSERT INTO VENTAS_REALES
            SELECT LOTE, STORE_ID, SALES_DATE, SALES, ALTERADO, CURRENT_TIMESTAMP()::TIMESTAMP_NTZ
            FROM LOTES_SIMULACION WHERE LOTE = %s""", (lote,))
        filas = cur.rowcount
    print(f"Lote {lote}: llegaron las ventas reales de {filas} tienda-dia")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("accion", choices=["puntuar", "etiquetar"])
    parser.add_argument("--lote", type=int, required=True)
    args = parser.parse_args()
    {"puntuar": puntuar, "etiquetar": etiquetar}[args.accion](args.lote)
