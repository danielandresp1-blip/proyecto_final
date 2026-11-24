#!/usr/bin/env bash
# Envia el job de la OBT al cluster standalone. Este contenedor actua como driver (modo client).
set -euo pipefail

if [[ -z "${SNOWFLAKE_PRIVATE_KEY:-}" && -n "${SNOWFLAKE_PRIVATE_KEY_PATH:-}" ]]; then
  export SNOWFLAKE_PRIVATE_KEY="$(cat "${SNOWFLAKE_PRIVATE_KEY_PATH}")"
fi

DRIVER_IP="$(hostname -i | awk '{print $1}')"

exec spark-submit \
  --master "${SPARK_MASTER_URL:-spark://spark-master:7077}" \
  --deploy-mode client \
  --name pset2_build_obt \
  --packages "${SPARK_SNOWFLAKE_PACKAGES}" \
  --conf spark.jars.ivy="${SPARK_IVY_DIR:-/opt/ivy}" \
  --conf spark.driver.host="${DRIVER_IP}" \
  --conf spark.driver.bindAddress=0.0.0.0 \
  --conf spark.executor.memory="${SPARK_EXECUTOR_MEMORY:-2g}" \
  --conf spark.sql.shuffle.partitions="${SPARK_SHUFFLE_PARTITIONS:-16}" \
  --conf spark.sql.session.timeZone=UTC \
  /opt/spark-apps/build_obt.py
