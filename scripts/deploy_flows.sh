#!/usr/bin/env bash
# Alternativa a la sincronizacion automatica: publica los flujos de kestra/flows via API.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
KESTRA_URL="${KESTRA_URL:-http://localhost:8080}"

for f in kestra/flows/*.yml; do
  echo "Publicando $f"
  curl -sS -u "${KESTRA_ADMIN_USER}:${KESTRA_ADMIN_PASSWORD}" \
       -X POST "${KESTRA_URL}/api/v1/main/flows/import" \
       -F fileUpload=@"$f" > /dev/null
done
echo "Listo."
