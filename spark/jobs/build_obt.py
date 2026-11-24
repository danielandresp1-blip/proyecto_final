"""
Construye la One Big Table (OBT) de ventas Rossmann a partir del star schema de GOLD.

GRANO de la OBT: una fila por tienda y dia observado (igual que GOLD.FCT_SALES_DAILY).
Si algun join cambia el numero de filas, crea duplicados o deja claves sin pareja, el job falla
ANTES de escribir, y la OBT anterior queda intacta.

Salidas en Snowflake:
  OBT.OBT_SALES_DAILY       tabla desnormalizada + variables de serie de tiempo por tienda
  OBT.OBT_VALIDATION_LOG    resultado de cada validacion por ejecucion
"""

import os
import sys
import uuid
from datetime import datetime, timezone

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

GOLD_SCHEMA = "GOLD"
OBT_SCHEMA = "OBT"
OBT_TABLE = "OBT_SALES_DAILY"
LOG_TABLE = "OBT_VALIDATION_LOG"
GRAIN = ["store_id", "sales_date"]
WRITE_PARTITIONS = int(os.environ.get("OBT_WRITE_PARTITIONS", "64"))


# --------------------------------------------------------------------------- conexion
def _key_variants() -> list:
    """Dos formatos posibles de la llave para el conector: segun la version, acepta el PEM
    completo o solo el cuerpo base64 sin encabezados. Se prueban ambos (ver resolve_key)."""
    key = os.environ["SNOWFLAKE_PRIVATE_KEY"].replace("\r", "").strip()
    body = "".join(line.strip() for line in key.splitlines() if line.strip() and "-----" not in line)
    return [body, key]


PEM_KEY = None  # se fija en resolve_key()


def snowflake_options(schema: str) -> dict:
    return {
        "sfURL": f"{os.environ['SNOWFLAKE_ACCOUNT']}.snowflakecomputing.com",
        "sfUser": os.environ["SNOWFLAKE_USER"],
        "sfRole": os.environ["SNOWFLAKE_ROLE"],
        "sfWarehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "sfDatabase": os.environ["SNOWFLAKE_DATABASE"],
        "sfSchema": schema,
        "pem_private_key": PEM_KEY,
    }


def resolve_key(spark: SparkSession) -> None:
    """Prueba la conexion con cada formato de llave y se queda con el que funciona."""
    global PEM_KEY
    last_error = None
    for candidate in _key_variants():
        PEM_KEY = candidate
        try:
            (spark.read.format("snowflake").options(**snowflake_options(GOLD_SCHEMA))
             .option("query", "select 1 as ok").load().collect())
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"No se pudo autenticar en Snowflake con la llave privada: {last_error}")


def read_table(spark: SparkSession, table: str) -> DataFrame:
    df = (
        spark.read.format("snowflake")
        .options(**snowflake_options(GOLD_SCHEMA))
        .option("dbtable", table)
        .load()
    )
    return df.toDF(*[c.lower() for c in df.columns])


def write_table(df: DataFrame, table: str, mode: str) -> None:
    (
        df.write.format("snowflake")
        .options(**snowflake_options(OBT_SCHEMA))
        .option("dbtable", table)
        .mode(mode)
        .save()
    )


# --------------------------------------------------------------------------- construccion
def build_obt(fct: DataFrame, dim_store: DataFrame, dim_date: DataFrame, dim_holiday: DataFrame) -> DataFrame:
    store_cols = dim_store.select(
        "store_key",
        "store_id",
        "store_type",
        "assortment",
        "assortment_label",
        "competition_distance_m",
        "has_competition_distance",
        "competition_open_since_date",
        "participates_promo2",
        "promo2_since_date",
        "promo2_interval_months",
        F.col("coverage_ratio").alias("store_coverage_ratio"),
        F.col("has_data_gap").alias("store_has_data_gap"),
    )
    date_cols = dim_date.select(
        "date_key",
        F.col("calendar_date").alias("sales_date"),
        "year", "quarter", "month", "iso_week", "day_of_month", "day_of_year",
        "day_of_week_iso", "is_weekend", "is_month_start", "is_month_end", "day_index",
    )
    holiday_cols = dim_holiday.select(
        "holiday_key", "state_holiday_code", "state_holiday_type",
        "is_state_holiday", "is_school_holiday", "is_any_holiday",
    )

    # Joins N:1 desde el hecho. LEFT para que un fallo de integridad se detecte en la validacion
    # (atributos nulos) en lugar de perder filas silenciosamente como haria un INNER.
    # Las dimensiones son pequenas (1.115 / ~990 / 8 filas): broadcast evita shuffles.
    return (
        fct.drop("_batch_id")
        .join(F.broadcast(store_cols), "store_key", "left")
        .join(F.broadcast(date_cols), "date_key", "left")
        .join(F.broadcast(holiday_cols), "holiday_key", "left")
    )


def add_time_features(obt: DataFrame) -> DataFrame:
    """Variables por tienda con ventanas por FECHA (rangeBetween sobre day_index), no por fila:
    asi el hueco de 2014-S2 no hace que 'el dia anterior' sea en realidad meses atras.
    Las estadisticas de ventas solo miran dias pasados (-N..-1) para no filtrar el objetivo."""
    by_store = Window.partitionBy("store_id").orderBy("day_index")
    w_prev_1 = by_store.rangeBetween(-1, -1)
    w_next_1 = by_store.rangeBetween(1, 1)
    w_prev_7 = by_store.rangeBetween(-7, -1)
    w_prev_28 = by_store.rangeBetween(-28, -1)

    eligible_sales = F.when(F.col("is_model_eligible"), F.col("sales"))
    eligible_customers = F.when(F.col("is_model_eligible"), F.col("customers"))
    as_int = lambda c: F.col(c).cast("int")  # noqa: E731

    return (
        obt
        .withColumn("sales_mean_prev_7d", F.round(F.avg(eligible_sales).over(w_prev_7), 2))
        .withColumn("sales_mean_prev_28d", F.round(F.avg(eligible_sales).over(w_prev_28), 2))
        .withColumn("customers_mean_prev_28d", F.round(F.avg(eligible_customers).over(w_prev_28), 2))
        .withColumn("n_days_observed_prev_28d", F.count(F.lit(1)).over(w_prev_28))
        # Calendario conocido de antemano (aperturas, promos y feriados se planifican): dia anterior y siguiente
        .withColumn("was_open_prev_day", F.max(as_int("is_open")).over(w_prev_1).cast("boolean"))
        .withColumn("is_open_next_day", F.max(as_int("is_open")).over(w_next_1).cast("boolean"))
        .withColumn("was_promo_prev_day", F.max(as_int("is_promo")).over(w_prev_1).cast("boolean"))
        .withColumn("is_state_holiday_prev_day", F.max(as_int("is_state_holiday")).over(w_prev_1).cast("boolean"))
        .withColumn("is_state_holiday_next_day", F.max(as_int("is_state_holiday")).over(w_next_1).cast("boolean"))
    )


# --------------------------------------------------------------------------- validacion
def validate(fct: DataFrame, obt: DataFrame, stage: str) -> list:
    n_fct = fct.count()
    n_obt = obt.count()
    duplicates = obt.groupBy(*GRAIN).count().filter("count > 1").count()
    unmatched_store = obt.filter(F.col("store_type").isNull()).count()
    unmatched_date = obt.filter(F.col("sales_date").isNull()).count()
    unmatched_holiday = obt.filter(F.col("state_holiday_type").isNull()).count()
    sales_fct = fct.agg(F.sum("sales")).first()[0]
    sales_obt = obt.agg(F.sum("sales")).first()[0]

    checks = [
        ("row_count_preserved", n_obt == n_fct, f"fct={n_fct} obt={n_obt}"),
        ("no_duplicates_on_grain", duplicates == 0, f"claves (store_id, sales_date) duplicadas={duplicates}"),
        ("all_stores_matched", unmatched_store == 0, f"filas sin dim_store={unmatched_store}"),
        ("all_dates_matched", unmatched_date == 0, f"filas sin dim_date={unmatched_date}"),
        ("all_holidays_matched", unmatched_holiday == 0, f"filas sin dim_holiday={unmatched_holiday}"),
        ("sales_total_preserved", sales_fct == sales_obt, f"fct={sales_fct} obt={sales_obt}"),
    ]
    return [(stage, name, bool(ok), detail) for name, ok, detail in checks]


def main() -> int:
    run_id = os.environ.get("OBT_RUN_ID") or str(uuid.uuid4())
    spark = SparkSession.builder.appName("pset2_build_obt").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    resolve_key(spark)

    fct = read_table(spark, "FCT_SALES_DAILY").cache()
    dim_store = read_table(spark, "DIM_STORE")
    dim_date = read_table(spark, "DIM_DATE")
    dim_holiday = read_table(spark, "DIM_HOLIDAY")

    obt_joined = build_obt(fct, dim_store, dim_date, dim_holiday).cache()
    results = validate(fct, obt_joined, "after_joins")

    obt = (
        add_time_features(obt_joined)
        .withColumn("obt_run_id", F.lit(run_id))
        .withColumn("obt_built_at", F.current_timestamp())
        .cache()
    )
    results += validate(fct, obt, "after_features")

    for stage, name, ok, detail in results:
        print(f"[{'OK' if ok else 'FAIL'}] {stage}.{name}: {detail}")

    failed = [r for r in results if not r[2]]
    if not failed:
        expected = fct.count()
        # Liberar memoria antes de escribir: el conector arma cada particion en memoria antes de
        # subirla a Snowflake, asi que se usan muchas particiones pequenas (sin ordenar: ordenar
        # obliga a mover todos los datos y no aporta nada a la tabla).
        obt_joined.unpersist()
        fct.unpersist()
        write_table(obt.repartition(WRITE_PARTITIONS), OBT_TABLE, "overwrite")
        # Validacion posterior a la escritura: lo que quedo en Snowflake tiene el mismo numero de filas
        written = (
            spark.read.format("snowflake")
            .options(**snowflake_options(OBT_SCHEMA))
            .option("query", f"select count(*) as n from {OBT_SCHEMA}.{OBT_TABLE}")
            .load()
            .first()[0]
        )
        results.append(("after_write", "snowflake_row_count", int(written) == expected,
                        f"esperado={expected} escrito={written}"))
        print(f"[{'OK' if int(written) == expected else 'FAIL'}] after_write.snowflake_row_count: "
              f"esperado={expected} escrito={written}")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    log_df = spark.createDataFrame(
        [(run_id, now, stage, name, ok, detail) for stage, name, ok, detail in results],
        "RUN_ID string, CHECKED_AT timestamp, STAGE string, CHECK_NAME string, PASSED boolean, DETAIL string",
    )
    write_table(log_df, LOG_TABLE, "append")

    failed = [r for r in results if not r[2]]
    spark.stop()
    if failed:
        print(f"{len(failed)} validacion(es) fallaron; la OBT no se actualizo (o no coincide tras escribir).")
        return 1
    print("OBT construida y validada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
