#!/usr/bin/env bash
# Envoltorio de dbt: carga la llave privada desde archivo si no llego como variable y ejecuta dbt.
set -euo pipefail

if [[ -z "${SNOWFLAKE_PRIVATE_KEY:-}" && -n "${SNOWFLAKE_PRIVATE_KEY_PATH:-}" ]]; then
  export SNOWFLAKE_PRIVATE_KEY="$(cat "${SNOWFLAKE_PRIVATE_KEY_PATH}")"
fi

cd /usr/app/dbt
exec dbt "$@"
