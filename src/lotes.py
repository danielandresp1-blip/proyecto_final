"""Construye los lotes de la simulacion de produccion (PSet 4, seccion 5).

El modelo no recibe trafico real, asi que se simula con el periodo de prueba, que no se uso para
entrenar ni para elegir hiperparametros: 2015-06-20 a 2015-07-31 (42 dias, 40.282 tienda-dia).
Se divide en 8 lotes sucesivos de 5 o 6 dias (6 semanas no alcanzan para los 8 lotes minimos).

Deriva inducida (escenario de prueba, no un hecho de Rossmann): en los lotes 6, 7 y 8 abre un
competidor cerca de las tiendas tipo "a".
  - Deriva de datos:  competition_distance_m de esas tiendas x 0,1
  - Cambio en la relacion con el target: sus ventas reales (sales) x 0,8
Las features de ventas con rezago de 42 dias no cambian: usan dias anteriores al competidor.

Las tablas de origen (OBT) no se modifican: el resultado se escribe en OPERACION.LOTES_SIMULACION.

Uso (desde la raiz del proyecto):  python -m src.lotes
"""
import pandas as pd
from snowflake.connector.pandas_tools import write_pandas

from src.datos import agregar_features, cargar_obt, conectar
from src.pipeline import FEATURES, TARGET, preparar_datos

ESQUEMA = "OPERACION"
TABLA = "LOTES_SIMULACION"

INICIO = pd.Timestamp("2015-06-20")
DIAS_POR_LOTE = [5, 5, 5, 5, 5, 5, 6, 6]  # suman 42

LOTES_CON_DERIVA = [6, 7, 8]
TIPO_AFECTADO = "a"
FACTOR_DISTANCIA = 0.1
FACTOR_VENTAS = 0.8


def calendario_lotes() -> pd.DataFrame:
    filas, inicio = [], INICIO
    for lote, dias in enumerate(DIAS_POR_LOTE, start=1):
        fin = inicio + pd.Timedelta(days=dias - 1)
        filas.append({"lote": lote, "inicio": inicio, "fin": fin})
        inicio = fin + pd.Timedelta(days=1)
    return pd.DataFrame(filas)


def asignar_lote(fechas: pd.Series) -> pd.Series:
    cal = calendario_lotes()
    lote = pd.Series(pd.NA, index=fechas.index, dtype="Int64")
    for f in cal.itertuples():
        lote[(fechas >= f.inicio) & (fechas <= f.fin)] = f.lote
    return lote


def inducir_deriva(lotes: pd.DataFrame) -> pd.DataFrame:
    df = lotes.copy()
    afectadas = df["lote"].isin(LOTES_CON_DERIVA) & (df["store_type"] == TIPO_AFECTADO)
    df["alterado"] = afectadas
    df[TARGET] = df[TARGET].astype(float)  # en la OBT las ventas son enteras; x 0,8 da decimales
    df["competition_distance_m"] = df["competition_distance_m"].astype(float)
    df.loc[afectadas, "competition_distance_m"] *= FACTOR_DISTANCIA
    df.loc[afectadas, TARGET] *= FACTOR_VENTAS
    return df


def construir_lotes() -> pd.DataFrame:
    _, prueba = preparar_datos(agregar_features(cargar_obt()))
    lotes = prueba[["store_id", "sales_date", TARGET] + FEATURES].copy()
    lotes["lote"] = asignar_lote(lotes["sales_date"])
    assert lotes["lote"].notna().all(), "Hay dias de prueba fuera del calendario de lotes"
    return inducir_deriva(lotes)


def guardar(lotes: pd.DataFrame) -> None:
    salida = lotes.copy()
    salida["sales_date"] = salida["sales_date"].dt.date
    salida.columns = [c.upper() for c in salida.columns]
    with conectar() as conn:
        conn.cursor().execute(f"CREATE SCHEMA IF NOT EXISTS {ESQUEMA}")
        write_pandas(conn, salida, TABLA, schema=ESQUEMA, auto_create_table=True,
                     overwrite=True, use_logical_type=True)


if __name__ == "__main__":
    lotes = construir_lotes()
    guardar(lotes)
    resumen = lotes.groupby("lote").agg(
        desde=("sales_date", "min"), hasta=("sales_date", "max"),
        filas=("store_id", "size"), alteradas=("alterado", "sum"), ventas=(TARGET, "sum"),
    )
    print(resumen.to_string())
    print(f"\nGuardado en {ESQUEMA}.{TABLA}: {len(lotes)} filas")
