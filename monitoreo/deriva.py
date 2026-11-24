"""Deriva de datos: cada lote frente a la distribucion de entrenamiento (seccion 6.2).

- PSI por feature: decide la alerta.
- Kolmogorov-Smirnov (numericas) y chi-cuadrado (categoricas): respaldo estadistico. Con miles de
  filas por lote detectan diferencias minimas, por eso no deciden la alerta.

Variables que se vigilan para alertar: las de la tienda y las ventas rezagadas.
Variables informativas (se calculan pero no alertan):
  - promocion y feriados: los fija el calendario comercial y se conocen de antemano; un lote de 5 dias
    sin promocion las desplaza siempre frente al entrenamiento sin que eso sea un problema.
  - contadores de tiempo (semanas desde Promo2, meses desde la competencia): crecen por definicion. Las de calendario (dia, mes, dia anterior/siguiente)
no se miden: un lote de 5 dias nunca reproduce un ano completo.

Uso, una vez, para guardar la referencia de entrenamiento:  python -m monitoreo.deriva
"""
import numpy as np
import pandas as pd
from scipy import stats

NUMERICAS = ["sales_mean_lag42_28d", "sales_mean_lag42_dow", "competition_distance_m"]
CATEGORICAS = ["store_type", "assortment", "participates_promo2", "is_promo2_active"]
# competition_status se calcula comparando la fecha con la apertura de la competencia: con el tiempo
# las tiendas pasan de not_yet_open a open. Dio PSI 0,29 en los lotes 4 y 5, sin alterar (falsa alarma).
INFORMATIVAS = ["is_promo", "is_school_holiday", "is_state_holiday", "state_holiday_type", "competition_status"]
# Contadores que crecen con el tiempo por definicion: frente al entrenamiento (2013-2015) siempre se
# desplazan hacia valores mayores. En la primera corrida weeks_since_promo2_start dio PSI 0,34 en un
# lote sin alterar (falsa alarma), asi que se miden pero no alertan.
NUMERICAS_INFORMATIVAS = ["weeks_since_promo2_start", "months_since_competition_open"]

PSI_ADVERTENCIA = 0.10
PSI_ALERTA = 0.25
EPS = 1e-4  # evita log(0) en categorias o intervalos vacios

TABLA_REFERENCIA = "REFERENCIA_ENTRENAMIENTO"
TAMANO_REFERENCIA = 100_000


def _psi(p: np.ndarray, q: np.ndarray) -> float:
    p, q = np.clip(p, EPS, None), np.clip(q, EPS, None)
    return float(np.sum((q - p) * np.log(q / p)))


def psi_numerica(ref: pd.Series, act: pd.Series, n_bins: int = 10) -> float:
    """Intervalos por deciles de la referencia; los faltantes no entran (se miden aparte)."""
    ref, act = ref.dropna().astype(float), act.dropna().astype(float)
    cortes = np.unique(np.quantile(ref, np.linspace(0, 1, n_bins + 1)))
    cortes[0], cortes[-1] = -np.inf, np.inf
    p = np.histogram(ref, cortes)[0] / len(ref)
    q = np.histogram(act, cortes)[0] / len(act)
    return _psi(p, q)


def _como_texto(s: pd.Series) -> pd.Series:
    return s.astype(object).where(s.notna(), "faltante").astype(str)


def psi_categorica(ref: pd.Series, act: pd.Series) -> float:
    ref, act = _como_texto(ref), _como_texto(act)
    categorias = sorted(set(ref) | set(act))
    p = ref.value_counts(normalize=True).reindex(categorias, fill_value=0).to_numpy()
    q = act.value_counts(normalize=True).reindex(categorias, fill_value=0).to_numpy()
    return _psi(p, q)


def p_valor_ks(ref: pd.Series, act: pd.Series) -> float:
    return float(stats.ks_2samp(ref.dropna().astype(float), act.dropna().astype(float)).pvalue)


def p_valor_chi2(ref: pd.Series, act: pd.Series) -> float:
    ref, act = _como_texto(ref), _como_texto(act)
    tabla = pd.concat([ref.value_counts(), act.value_counts()], axis=1).fillna(0)
    if len(tabla) < 2:
        return 1.0
    return float(stats.chi2_contingency(tabla.to_numpy().T)[1])


def calcular_deriva(ref: pd.DataFrame, lote: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for col in NUMERICAS + NUMERICAS_INFORMATIVAS:
        filas.append({"variable": col, "psi": psi_numerica(ref[col], lote[col]),
                      "prueba": "ks", "p_valor": p_valor_ks(ref[col], lote[col]),
                      "uso": "alerta" if col in NUMERICAS else "informativa"})
    for col in CATEGORICAS + INFORMATIVAS:
        filas.append({"variable": col, "psi": psi_categorica(ref[col], lote[col]),
                      "prueba": "chi2", "p_valor": p_valor_chi2(ref[col], lote[col]),
                      "uso": "alerta" if col in CATEGORICAS else "informativa"})
    return pd.DataFrame(filas)


def calidad_datos(ref: pd.DataFrame, lote: pd.DataFrame) -> pd.DataFrame:
    """% de faltantes por feature, % fuera del rango de entrenamiento y categorias no vistas."""
    filas = []
    for col in NUMERICAS + NUMERICAS_INFORMATIVAS + CATEGORICAS + INFORMATIVAS:
        filas.append({"metrica": "pct_faltantes", "variable": col, "valor": lote[col].isna().mean() * 100})
    for col in NUMERICAS:
        minimo, maximo = ref[col].min(), ref[col].max()
        fuera = ((lote[col] < minimo) | (lote[col] > maximo)).mean() * 100
        filas.append({"metrica": "pct_fuera_de_rango", "variable": col, "valor": fuera})
    for col in CATEGORICAS + INFORMATIVAS:
        nuevas = set(_como_texto(lote[col])) - set(_como_texto(ref[col]))
        filas.append({"metrica": "categorias_no_vistas", "variable": col, "valor": float(len(nuevas))})
    return pd.DataFrame(filas)


def guardar_referencia() -> None:
    """Muestra fija del entrenamiento del champion (2013-02-12 a 2015-06-19)."""
    from snowflake.connector.pandas_tools import write_pandas

    from src.datos import agregar_features, cargar_obt, conectar
    from src.pipeline import FEATURES, preparar_datos

    entrenamiento, _ = preparar_datos(agregar_features(cargar_obt()))
    ref = entrenamiento[FEATURES].sample(TAMANO_REFERENCIA, random_state=42)
    ref.columns = [c.upper() for c in ref.columns]
    with conectar() as conn:
        conn.cursor().execute("CREATE SCHEMA IF NOT EXISTS OPERACION")
        write_pandas(conn, ref.reset_index(drop=True), TABLA_REFERENCIA, schema="OPERACION",
                     auto_create_table=True, overwrite=True)
    print(f"Referencia guardada en OPERACION.{TABLA_REFERENCIA}: {len(ref)} filas")


if __name__ == "__main__":
    guardar_referencia()
