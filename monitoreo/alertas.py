"""Definicion y evaluacion de las alertas (seccion 6.3).

Cada alerta sigue la plantilla del enunciado: metrica, umbral, ventana, severidad, quien la recibe
y accion. Se avisan en el log de Kestra y quedan en OPERACION.ALERTAS.
"""
import pandas as pd

from monitoreo.deriva import PSI_ALERTA

# Validacion cruzada del champion en el PSet 3 (HistGradientBoosting ajustado, corrida d6e81855...)
WAPE_CV_MEDIA = 0.0869
WAPE_CV_STD = 0.0038
UMBRAL_WAPE = round(WAPE_CV_MEDIA + 2 * WAPE_CV_STD, 4)  # 0,0945: deriva conceptual o de datos con impacto

ALERTAS = {
    "psi": dict(
        umbral=f"> {PSI_ALERTA}", ventana="1 lote", severidad="Alta", destinatario="Equipo de datos",
        accion="Revisar la fuente de la variable y evaluar reentrenamiento si el desempeno cae"),
    "wape_modelo": dict(
        umbral=f"> {UMBRAL_WAPE} (media CV + 2 desv.)", ventana="1 lote", severidad="Alta",
        destinatario="Equipo de datos",
        accion="Diagnosticar el tipo de deriva; 2 lotes seguidos disparan el reentrenamiento"),
    "modelo_peor_que_regla": dict(
        umbral="WAPE modelo > WAPE regla", ventana="1 lote", severidad="Critica",
        destinatario="Equipo de datos y jefe de operaciones de tiendas",
        accion="Si se repite tras reentrenar, activar MODO_RESPALDO (criterio de retirada)"),
    "categorias_no_vistas": dict(
        umbral="> 0", ventana="1 lote", severidad="Media", destinatario="Equipo de datos",
        accion="Revisar la fuente y los tests de dbt; el modelo ignora la categoria nueva"),
    "pct_fuera_de_rango": dict(
        umbral="> 5%", ventana="1 lote", severidad="Media", destinatario="Equipo de datos",
        accion="Revisar la fuente; el modelo extrapola fuera de lo que vio al entrenar"),
    "latencia_p95_ms": dict(
        umbral="> 10.000 ms", ventana="1 lote", severidad="Media", destinatario="Equipo de plataforma",
        accion="Revisar la API y la escritura en Snowflake"),
    "tasa_5xx": dict(
        umbral="> 1%", ventana="1 lote", severidad="Alta", destinatario="Equipo de plataforma",
        accion="Revisar los logs de la API; el lote puede quedar sin pronostico"),
    "pct_respaldo": dict(
        umbral="> 0%", ventana="1 lote", severidad="Alta", destinatario="Equipo de datos",
        accion="Verificar por que el servicio usa la regla del gerente (modelo no cargo o interruptor activo)"),
}


def _alerta(tipo: str, lote: int, metrica: str, variable, valor: float) -> dict:
    return {"lote": lote, "tipo": tipo, "metrica": metrica, "variable": variable,
            "valor": float(valor), **ALERTAS[metrica]}


def evaluar(metricas: pd.DataFrame) -> list[dict]:
    """metricas: filas de MONITOREO (lote, tipo, metrica, variable, valor) recien calculadas."""
    alertas = []
    for m in metricas.itertuples():
        if m.metrica == "psi" and m.texto == "alerta" and m.valor > PSI_ALERTA:
            alertas.append(_alerta(m.tipo, m.lote, "psi", m.variable, m.valor))
        elif m.metrica == "categorias_no_vistas" and m.valor > 0:
            alertas.append(_alerta(m.tipo, m.lote, m.metrica, m.variable, m.valor))
        elif m.metrica == "pct_fuera_de_rango" and m.valor > 5:
            alertas.append(_alerta(m.tipo, m.lote, m.metrica, m.variable, m.valor))
        elif m.metrica == "latencia_p95_ms" and m.valor > 10_000:
            alertas.append(_alerta(m.tipo, m.lote, m.metrica, None, m.valor))
        elif m.metrica == "tasa_5xx" and m.valor > 0.01:
            alertas.append(_alerta(m.tipo, m.lote, m.metrica, None, m.valor))
        elif m.metrica == "pct_respaldo" and m.valor > 0:
            alertas.append(_alerta(m.tipo, m.lote, m.metrica, None, m.valor))
        elif m.metrica == "wape_modelo" and m.valor > UMBRAL_WAPE:
            alertas.append(_alerta(m.tipo, m.lote, m.metrica, None, m.valor))

    desempeno = metricas[metricas["tipo"] == "desempeno"].set_index("metrica")["valor"]
    if {"wape_modelo", "wape_regla"} <= set(desempeno.index) and desempeno["wape_modelo"] > desempeno["wape_regla"]:
        lote = int(metricas.loc[metricas["tipo"] == "desempeno", "lote"].iloc[0])
        alertas.append(_alerta("desempeno", lote, "modelo_peor_que_regla", None, desempeno["wape_modelo"]))
    return alertas


def diagnosticar(entradas_cambian: bool, desempeno_cae: bool) -> str:
    """Tabla de la seccion 6.2."""
    if entradas_cambian and not desempeno_cae:
        return "Deriva de datos sin impacto"
    if entradas_cambian and desempeno_cae:
        return "Deriva de datos con impacto"
    if desempeno_cae:
        return "Deriva conceptual"
    return "Sin deriva"
