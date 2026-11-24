"""Monitoreo de un paso de la simulacion (lo ejecuta Kestra en monitoreo.yml).

En el paso N, en dos partes:
  - desempeno: llegaron las ventas reales del lote N-1. WAPE y costo de turnos del modelo y de la regla
    del gerente, diagnostico del tipo de deriva (seccion 6.2) y disparador del reentrenamiento (7.1).
    Va antes de pronosticar el lote N, para que un reentrenamiento aprobado ya pronostique ese lote.
  - lote: el lote N se acaba de pronosticar. Metricas de sistema, distribucion de predicciones y
    decisiones, calidad de datos y deriva frente al entrenamiento.
Guarda las metricas en OPERACION.MONITOREO y las alertas en OPERACION.ALERTAS.

Uso:  python -m monitoreo.monitorear --paso 2 --parte desempeno
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
from snowflake.connector.pandas_tools import write_pandas

from monitoreo.alertas import UMBRAL_WAPE, diagnosticar, evaluar
from monitoreo.deriva import PSI_ALERTA, TABLA_REFERENCIA, calcular_deriva, calidad_datos
from src.datos import conectar
from src.pipeline import FEATURES, costo_turnos, wape

ESQUEMA = "OPERACION"
API_URL = os.getenv("API_URL", "http://localhost:8000")
ULTIMO_LOTE = 8

DDL = [
    """CREATE TABLE IF NOT EXISTS MONITOREO (
        TS TIMESTAMP_NTZ, LOTE INTEGER, TIPO VARCHAR, METRICA VARCHAR, VARIABLE VARCHAR,
        VALOR FLOAT, TEXTO VARCHAR)""",
    """CREATE TABLE IF NOT EXISTS ALERTAS (
        TS TIMESTAMP_NTZ, LOTE INTEGER, TIPO VARCHAR, METRICA VARCHAR, VARIABLE VARCHAR, VALOR FLOAT,
        UMBRAL VARCHAR, VENTANA VARCHAR, SEVERIDAD VARCHAR, DESTINATARIO VARCHAR, ACCION VARCHAR)""",
]


def consultar(conn, sql: str, params=None) -> pd.DataFrame:
    df = conn.cursor().execute(sql, params).fetch_pandas_all()
    df.columns = df.columns.str.lower()
    return df


def fila(lote, tipo, metrica, valor, variable=None, texto=None) -> dict:
    return {"lote": lote, "tipo": tipo, "metrica": metrica, "variable": variable,
            "valor": None if valor is None else float(valor), "texto": texto}


# ---------------------------------------------------------------- lote recien pronosticado
def metricas_sistema(lote: int) -> list[dict]:
    m = requests.get(f"{API_URL}/metricas", params={"reiniciar": "true"}, timeout=30).json()
    return [fila(lote, "sistema", k, m[k]) for k in
            ("solicitudes", "latencia_p50_ms", "latencia_p95_ms", "tasa_4xx", "tasa_5xx")]


def metricas_predicciones(conn, lote: int) -> list[dict]:
    p = consultar(conn, "SELECT VENTAS_PRONOSTICADAS, DECISION, RESPALDO, VERSION_MODELO "
                        "FROM PREDICCIONES WHERE LOTE = %s", (str(lote),))
    filas = [fila(lote, "modelo", "predicciones", len(p))]
    for q in (10, 50, 90):
        filas.append(fila(lote, "modelo", f"prediccion_p{q}", np.percentile(p["ventas_pronosticadas"], q)))
    filas.append(fila(lote, "modelo", "prediccion_media", p["ventas_pronosticadas"].mean()))
    for decision, tasa in p["decision"].value_counts(normalize=True).items():
        filas.append(fila(lote, "modelo", "tasa_decision", tasa, variable=decision))
    filas.append(fila(lote, "modelo", "pct_respaldo", p["respaldo"].mean() * 100))
    filas.append(fila(lote, "modelo", "version_modelo", None, texto=",".join(sorted(p["version_modelo"].dropna().unique()))))
    return filas


def metricas_datos(conn, lote: int) -> list[dict]:
    columnas = ", ".join(c.upper() for c in FEATURES)
    actual = consultar(conn, f"SELECT {columnas} FROM LOTES_SIMULACION WHERE LOTE = %s", (lote,))
    ref = consultar(conn, f"SELECT {columnas} FROM {TABLA_REFERENCIA}")
    filas = [fila(lote, "datos", r.metrica, r.valor, variable=r.variable)
             for r in calidad_datos(ref, actual).itertuples()]
    for r in calcular_deriva(ref, actual).itertuples():
        filas.append(fila(lote, "deriva", "psi", r.psi, variable=r.variable, texto=r.uso))
        filas.append(fila(lote, "deriva", f"p_valor_{r.prueba}", r.p_valor, variable=r.variable))
    return filas


# ---------------------------------------------------------------- lote con ventas reales
def metricas_desempeno(conn, lote: int) -> list[dict]:
    d = consultar(conn, """
        SELECT p.VENTAS_PRONOSTICADAS, p.VENTAS_REGLA, v.SALES, v.ALTERADO
        FROM PREDICCIONES p JOIN VENTAS_REALES v
          ON p.STORE_ID = v.STORE_ID AND p.FECHA = v.FECHA AND p.LOTE = v.LOTE::VARCHAR
        WHERE v.LOTE = %s""", (lote,))
    y, modelo, regla = d["sales"], d["ventas_pronosticadas"], d["ventas_regla"]
    filas = [
        fila(lote, "desempeno", "filas_con_ventas_reales", len(d)),
        fila(lote, "desempeno", "wape_modelo", wape(y, modelo)),
        fila(lote, "desempeno", "wape_regla", wape(y, regla)),
        fila(lote, "desempeno", "costo_modelo_k2", costo_turnos(y, modelo)),
        fila(lote, "desempeno", "costo_regla_k2", costo_turnos(y, regla)),
    ]
    for alterado, g in d.groupby("alterado"):
        grupo = "tiendas_alteradas" if alterado else "tiendas_sin_alterar"
        filas.append(fila(lote, "desempeno", "wape_modelo_grupo", wape(g["sales"], g["ventas_pronosticadas"]), variable=grupo))
    return filas


def diagnostico(conn, lote: int, wape_modelo: float) -> dict:
    """Cruza la deriva de entradas del lote (calculada cuando se pronostico) con su desempeno."""
    psi = consultar(conn, "SELECT MAX(VALOR) AS PSI FROM MONITOREO "
                          "WHERE LOTE = %s AND METRICA = 'psi' AND TEXTO = 'alerta'", (lote,))
    entradas_cambian = bool(psi["psi"].iloc[0] is not None and psi["psi"].iloc[0] > PSI_ALERTA)
    desempeno_cae = wape_modelo > UMBRAL_WAPE
    return fila(lote, "desempeno", "diagnostico", None, texto=diagnosticar(entradas_cambian, desempeno_cae))


# ---------------------------------------------------------------- escritura
def guardar(conn, tabla: str, filas: list[dict], borrar: list[tuple[int, list[str]]]) -> None:
    cur = conn.cursor()
    for lote, tipos in borrar:  # repetir un paso no duplica filas
        marcadores = ", ".join(["%s"] * len(tipos))
        cur.execute(f"DELETE FROM {tabla} WHERE LOTE = %s AND TIPO IN ({marcadores})", (lote, *tipos))
    if filas:
        df = pd.DataFrame(filas)
        df.insert(0, "ts", datetime.now(timezone.utc).replace(tzinfo=None))
        texto = df.select_dtypes(include=["object", "str"]).columns
        df[texto] = df[texto].astype("string")  # columnas de texto con tipo aunque vengan vacias
        df.columns = [c.upper() for c in df.columns]
        write_pandas(conn, df, tabla, use_logical_type=True)


CALENDARIO_LOTES = 4  # reentrenamiento por calendario: cada 4 lotes con ventas reales


def disparador(conn, lote: int, wape_modelo: float) -> tuple[bool, str]:
    """Seccion 7.1. Desempeno: WAPE > umbral en 2 lotes seguidos. Calendario: cada 4 lotes.
    La deriva de datos sin caida de desempeno no dispara el reentrenamiento."""
    previo = consultar(conn, "SELECT VALOR FROM MONITOREO WHERE LOTE = %s AND METRICA = 'wape_modelo'", (lote - 1,))
    wape_previo = float(previo["valor"].iloc[0]) if len(previo) else None
    if wape_modelo > UMBRAL_WAPE and wape_previo is not None and wape_previo > UMBRAL_WAPE:
        return True, (f"Desempeno: WAPE {wape_previo:.4f} y {wape_modelo:.4f} en los lotes {lote - 1} y {lote} "
                      f"superan {UMBRAL_WAPE} (media CV + 2 desv.)")
    if lote % CALENDARIO_LOTES == 0:
        return True, f"Calendario: reentrenamiento programado cada {CALENDARIO_LOTES} lotes (lote {lote})"
    return False, ""


def monitorear(paso: int, parte: str) -> dict:
    """parte = 'desempeno': llegaron las ventas reales del lote paso-1 (antes de pronosticar el lote paso).
       parte = 'lote':      el lote paso ya se pronostico."""
    filas, borrar = [], []
    resumen = {"paso": paso, "parte": parte, "reentrenar": False, "motivo": "", "lote_eval": 0}

    with conectar(ESQUEMA) as conn:
        for sql in DDL:
            conn.cursor().execute(sql)

        if parte == "lote" and paso <= ULTIMO_LOTE:
            filas += metricas_sistema(paso) + metricas_predicciones(conn, paso) + metricas_datos(conn, paso)
            borrar.append((paso, ["sistema", "modelo", "datos", "deriva"]))
        elif parte == "desempeno" and paso >= 2:
            lote = paso - 1
            desempeno = metricas_desempeno(conn, lote)
            wape_modelo = next(f["valor"] for f in desempeno if f["metrica"] == "wape_modelo")
            filas += desempeno + [diagnostico(conn, lote, wape_modelo)]
            borrar.append((lote, ["desempeno"]))
            reentrenar, motivo = disparador(conn, lote, wape_modelo)
            resumen.update(reentrenar=reentrenar, motivo=motivo, lote_eval=lote)

        metricas = pd.DataFrame(filas)
        alertas = evaluar(metricas) if filas else []
        guardar(conn, "MONITOREO", filas, borrar)
        guardar(conn, "ALERTAS", alertas, borrar)

    for a in alertas:
        print(f"ALERTA [{a['severidad']}] lote {a['lote']} | {a['metrica']} {a['variable'] or ''} = "
              f"{a['valor']:.4f} (umbral {a['umbral']}) -> {a['destinatario']}: {a['accion']}",
              file=sys.stderr)  # Kestra muestra stderr como advertencia
    if parte == "desempeno" and filas:
        d = metricas[metricas["tipo"] == "desempeno"].set_index("metrica")
        print(f"Lote {paso - 1}: WAPE modelo {d.loc['wape_modelo', 'valor']:.4f} | "
              f"WAPE regla {d.loc['wape_regla', 'valor']:.4f} | {d.loc['diagnostico', 'texto']}")
        print(f"Reentrenar: {'SI - ' + resumen['motivo'] if resumen['reentrenar'] else 'no'}")
    print(f"Paso {paso} ({parte}): {len(filas)} metricas y {len(alertas)} alertas guardadas")
    resumen["alertas"] = len(alertas)
    print("::" + json.dumps({"outputs": resumen}) + "::")  # salidas para Kestra
    return resumen


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--paso", type=int, required=True)
    parser.add_argument("--parte", choices=["desempeno", "lote"], required=True)
    a = parser.parse_args()
    monitorear(a.paso, a.parte)
