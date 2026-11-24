#!/usr/bin/env bash
# Genera .env_encoded para Kestra OSS: cada variable de .env se expone como SECRET_<NOMBRE>
# codificada en base64, y la llave privada de Snowflake como SECRET_SNOWFLAKE_PRIVATE_KEY.
# En los flujos se leen con {{ secret('NOMBRE') }}.
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env"
KEY_FILE="secrets/rsa_key.p8"
OUT=".env_encoded"

[[ -f "$ENV_FILE" ]] || { echo "Falta $ENV_FILE (copia .env.example)"; exit 1; }
[[ -f "$KEY_FILE" ]] || { echo "Falta $KEY_FILE (ver scripts/snowflake_setup.sql)"; exit 1; }

b64() { base64 | tr -d '\n'; }

: > "$OUT"
while IFS='=' read -r key value; do
  [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
  key="$(echo "$key" | xargs)"
  echo "SECRET_${key}=$(printf '%s' "$value" | b64)" >> "$OUT"
done < "$ENV_FILE"

echo "SECRET_SNOWFLAKE_PRIVATE_KEY=$(b64 < "$KEY_FILE")" >> "$OUT"
echo "Generado $OUT con $(wc -l < "$OUT") secretos."
