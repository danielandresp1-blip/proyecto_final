"""Comportamientos que el modelo debe cumplir segun el negocio (seccion 3.3).

Se evaluan en promedio sobre 2.000 dias de la muestra (semilla fija) y no fila por fila:
un modelo de arboles puede tener casos aislados no monotonos sin que eso sea un error de negocio.
"""
import pytest

import main


@pytest.fixture(scope="module")
def dias(muestra):
    return muestra.sample(2_000, random_state=42)[main.FEATURES].copy()


def test_activar_la_promocion_no_reduce_el_pronostico(modelo, dias):
    """La promocion es la variable conocida de antemano mas asociada a las ventas (+39%, PSet 3)."""
    con, sin = dias.copy(), dias.copy()
    con["is_promo"], sin["is_promo"] = 1.0, 0.0
    assert modelo.predict(con).mean() > modelo.predict(sin).mean()


def test_mayor_venta_habitual_aumenta_el_pronostico(modelo, dias):
    """Si la tienda vendio mas en el mismo dia de la semana (rezago de 42 dias), se espera vender mas."""
    mas = dias.copy()
    mas["sales_mean_lag42_dow"] = mas["sales_mean_lag42_dow"] * 1.2
    assert modelo.predict(mas).mean() > modelo.predict(dias).mean()
