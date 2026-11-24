"""El modelo cargado reproduce la metrica registrada en MLflow (seccion 3.2).

La muestra es el periodo de prueba completo (2015-06-20 a 2015-07-31, 40.282 filas), el mismo
con el que se registro wape_prueba. Tolerancia: 0,0005. Cubre diferencias numericas entre
plataformas (Windows al registrar, Linux en CI) y es unas 8 veces menor que la desviacion del
WAPE entre pliegues de la CV (0,0038): una diferencia mayor indicaria otro modelo u otros datos.
"""
import numpy as np

import main

TOLERANCIA = 0.0005


def wape(y_real, y_pred) -> float:
    y_real = np.asarray(y_real, dtype=float)
    return np.abs(y_real - np.asarray(y_pred, dtype=float)).sum() / y_real.sum()


def test_modelo_reproduce_wape_registrado(modelo, muestra, referencia):
    assert len(muestra) == referencia["filas"]
    pred = modelo.predict(muestra[main.FEATURES])
    reproducido = wape(muestra["sales"], pred)
    assert abs(reproducido - referencia["wape_prueba_registrado"]) <= TOLERANCIA
