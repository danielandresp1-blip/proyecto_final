"""Tablero de monitoreo del modelo Rossmann (PSet 4, seccion 6.4).

Lee OPERACION.MONITOREO y OPERACION.ALERTAS de Snowflake (las escribe el flujo monitoreo de Kestra)
y el estado del servicio desde la API. Se abre en http://localhost:8501
"""
import os
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import requests
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.datos import conectar  # noqa: E402

API_URL = os.getenv("API_URL", "http://localhost:8000")
UMBRAL_WAPE = 0.0945  # media de la CV + 2 desviaciones (monitoreo/alertas.py)
PSI_ADVERTENCIA, PSI_ALERTA = 0.10, 0.25

st.set_page_config(page_title="Monitoreo Rossmann", layout="wide")


@st.cache_data(ttl=60)
def leer(sql: str) -> pd.DataFrame:
    with conectar("OPERACION") as conn:
        df = conn.cursor().execute(sql).fetch_pandas_all()
    df.columns = df.columns.str.lower()
    return df


def estado_api() -> dict:
    try:
        return requests.get(f"{API_URL}/modelo", timeout=5).json()
    except requests.RequestException:
        return {}


monitoreo = leer("SELECT LOTE, TIPO, METRICA, VARIABLE, VALOR, TEXTO FROM MONITOREO")
alertas = leer("SELECT LOTE, SEVERIDAD, TIPO, METRICA, VARIABLE, VALOR, UMBRAL, DESTINATARIO, ACCION "
               "FROM ALERTAS ORDER BY LOTE")


def metrica(nombre: str, tipo: str | None = None) -> pd.DataFrame:
    m = monitoreo[monitoreo["metrica"] == nombre]
    return m if tipo is None else m[m["tipo"] == tipo]


# ---------------------------------------------------------------- encabezado
st.title("Monitoreo del pronostico de ventas Rossmann")
api = estado_api()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Modelo en servicio", f"v{api['version']}" if api else "sin conexion")
c2.metric("Modo respaldo", "Activo" if api.get("modo_respaldo") else "Inactivo")
c3.metric("Lotes monitoreados", int(monitoreo["lote"].nunique()) if len(monitoreo) else 0)
c4.metric("Alertas", len(alertas))

if st.button("Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

# ---------------------------------------------------------------- desempeno
st.header("1. Desempeno: modelo frente a la regla del gerente")
desempeno = (monitoreo[monitoreo["tipo"] == "desempeno"]
             .pivot_table(index="lote", columns="metrica", values="valor").reset_index())
versiones = metrica("version_modelo").set_index("lote")["texto"].rename("version")

if not desempeno.empty:
    col_a, col_b = st.columns(2)
    wape = desempeno.melt("lote", ["wape_modelo", "wape_regla"], var_name="serie", value_name="WAPE")
    umbral = alt.Chart(pd.DataFrame({"y": [UMBRAL_WAPE]})).mark_rule(strokeDash=[6, 4], color="gray").encode(y="y")
    col_a.altair_chart(
        (alt.Chart(wape).mark_line(point=True).encode(
            x=alt.X("lote:O", title="Lote"), y=alt.Y("WAPE:Q"),
            color=alt.Color("serie:N", title=None), tooltip=["lote", "serie", alt.Tooltip("WAPE", format=".4f")],
        ) + umbral).properties(title=f"WAPE por lote (linea gris: umbral de alerta {UMBRAL_WAPE})"),
        use_container_width=True,
    )
    costo = desempeno.melt("lote", ["costo_modelo_k2", "costo_regla_k2"], var_name="serie", value_name="costo")
    col_b.altair_chart(
        alt.Chart(costo).mark_bar().encode(
            x=alt.X("lote:O", title="Lote"), xOffset="serie:N", y=alt.Y("costo:Q", title="Costo de turnos (k = 2)"),
            color=alt.Color("serie:N", title=None), tooltip=["lote", "serie", alt.Tooltip("costo", format=".4f")],
        ).properties(title="Costo de turnos mal asignados por lote (metrica de negocio)"),
        use_container_width=True,
    )
    tabla = desempeno.set_index("lote").join(versiones)
    tabla = tabla.join(metrica("diagnostico").set_index("lote")["texto"].rename("diagnostico"))
    st.dataframe(tabla[["version", "wape_modelo", "wape_regla", "costo_modelo_k2", "costo_regla_k2", "diagnostico"]]
                 .style.format(precision=4), use_container_width=True)
    st.caption("Lotes 6 a 8: deriva inducida (competidor cerca de las tiendas tipo a). "
               "El cambio de version indica en que lote se aprobo un reentrenamiento.")

# ---------------------------------------------------------------- deriva
st.header("2. Deriva de datos (PSI frente al entrenamiento)")
psi = metrica("psi", "deriva")
if not psi.empty:
    # Etiqueta con el uso: las informativas se miden pero no alertan
    psi = psi.assign(uso=psi["texto"],
                     etiqueta=psi["variable"] + psi["texto"].map({"alerta": "", "informativa": " (info)"}))
    st.altair_chart(
        alt.Chart(psi).mark_rect().encode(
            x=alt.X("lote:O", title="Lote"),
            y=alt.Y("etiqueta:N", title=None, sort=alt.EncodingSortField("uso"), axis=alt.Axis(labelLimit=260)),
            color=alt.Color("valor:Q", title="PSI", scale=alt.Scale(
                domain=[0, PSI_ADVERTENCIA, PSI_ALERTA, 0.5], range=["#e8f5e9", "#fff59d", "#ffb74d", "#e53935"],
                clamp=True)),  # PSI > 0,5 se pinta como el maximo (rojo)
            tooltip=["lote", "variable", "uso", alt.Tooltip("valor", format=".3f")],
        ).properties(height=380),
        use_container_width=True,
    )
    st.caption(f"PSI < {PSI_ADVERTENCIA} estable | {PSI_ADVERTENCIA} a {PSI_ALERTA} advertencia | "
               f"> {PSI_ALERTA} alerta. Solo las variables de uso 'alerta' disparan alertas; las 'informativas' "
               "(promocion, feriados y contadores de tiempo) cambian por construccion.")

# ---------------------------------------------------------------- decisiones y predicciones
st.header("3. Predicciones y decisiones")
col_c, col_d = st.columns(2)
decisiones = metrica("tasa_decision")
if not decisiones.empty:
    col_c.altair_chart(
        alt.Chart(decisiones).mark_bar().encode(
            x=alt.X("lote:O", title="Lote"), y=alt.Y("valor:Q", title="Proporcion", axis=alt.Axis(format="%")),
            color=alt.Color("variable:N", title="Decision"), tooltip=["lote", "variable", alt.Tooltip("valor", format=".1%")],
        ).properties(title="Decision sugerida por lote"),
        use_container_width=True,
    )
pred = monitoreo[monitoreo["metrica"].isin(["prediccion_p10", "prediccion_p50", "prediccion_p90"])]
if not pred.empty:
    col_d.altair_chart(
        alt.Chart(pred).mark_line(point=True).encode(
            x=alt.X("lote:O", title="Lote"), y=alt.Y("valor:Q", title="Ventas pronosticadas"),
            color=alt.Color("metrica:N", title="Percentil"),
        ).properties(title="Distribucion de las predicciones"),
        use_container_width=True,
    )

# ---------------------------------------------------------------- sistema
st.header("4. Sistema")
sistema = (monitoreo[monitoreo["tipo"] == "sistema"]
           .pivot_table(index="lote", columns="metrica", values="valor"))
if not sistema.empty:
    st.dataframe(sistema.style.format(precision=2), use_container_width=True)

# ---------------------------------------------------------------- alertas
st.header("5. Alertas")
if alertas.empty:
    st.success("Sin alertas")
else:
    st.dataframe(alertas.style.format({"valor": "{:.4f}"}), use_container_width=True, hide_index=True)
