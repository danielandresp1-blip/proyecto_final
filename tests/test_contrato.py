"""Contrato de la API y respaldo (secciones 3.1 y 3.4)."""
import copy

import main

DECISIONES = {"reforzar_turnos", "mantener_plan", "reducir_turnos"}


def predecir(cliente, registro):
    return cliente.post("/predecir", json={"registros": [registro]})


def campos_fallidos(respuesta) -> list[str]:
    return [c["campo"] for c in respuesta.json()["campos"]]


def test_entrada_valida_devuelve_200_con_el_esquema_esperado(cliente, registro_valido):
    r = predecir(cliente, registro_valido)
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) >= {"predicciones", "modelo", "version_modelo", "respaldo", "latencia_ms"}
    p = cuerpo["predicciones"][0]
    assert set(p) >= {"id_prediccion", "ventas_pronosticadas", "ventas_regla_actual",
                      "ajuste_dotacion_pct", "decision", "version_modelo"}
    assert p["decision"] in DECISIONES
    assert p["ventas_pronosticadas"] >= 0
    assert cuerpo["respaldo"] is False


def test_campo_faltante_devuelve_422(cliente, registro_valido):
    registro = copy.deepcopy(registro_valido)
    del registro["is_promo"]
    r = predecir(cliente, registro)
    assert r.status_code == 422
    assert "registros.0.is_promo" in campos_fallidos(r)


def test_tipo_incorrecto_devuelve_422(cliente, registro_valido):
    registro = copy.deepcopy(registro_valido)
    registro["sales_mean_lag42_dow"] = "mucho"
    r = predecir(cliente, registro)
    assert r.status_code == 422
    assert "registros.0.sales_mean_lag42_dow" in campos_fallidos(r)


def test_categoria_desconocida_devuelve_422(cliente, registro_valido):
    registro = copy.deepcopy(registro_valido)
    registro["store_type"] = "z"
    r = predecir(cliente, registro)
    assert r.status_code == 422
    assert "registros.0.store_type" in campos_fallidos(r)


def test_respaldo_si_el_modelo_no_carga(cliente, registro_valido, monkeypatch):
    """Si el modelo no carga, la API responde con la regla del gerente (PSet 1) y lo indica."""
    monkeypatch.setattr(main, "MODELO_RUTA", "/ruta/que/no/existe")
    main.cargar_modelo()
    try:
        r = predecir(cliente, registro_valido)
        assert r.status_code == 200
        cuerpo = r.json()
        p = cuerpo["predicciones"][0]
        assert cuerpo["respaldo"] is True
        assert cuerpo["modelo"] == "regla_gerente"
        assert p["ventas_pronosticadas"] == registro_valido["sales_mean_lag42_dow"]
        assert p["decision"] == "mantener_plan"
    finally:
        monkeypatch.undo()
        main.cargar_modelo()
    assert main.estado["modelo"] is not None
