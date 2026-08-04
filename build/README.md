# build/

`construir_v2.py` genera la versión corregida del workflow
*Flow Tatika, Colina del Viento - Conaring* a partir del JSON exportado del que está en
producción.

```bash
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/workflows/m9mqIWluJay9qOWs" > wf.json

python3 construir_v2.py wf.json wf-v2.json

curl -s -X POST -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" --data @wf-v2.json \
  "$N8N_BASE_URL/api/v1/workflows"
```

El script es idempotente respecto a la entrada: siempre parte del workflow de producción y
aplica los cambios encima, así que se puede volver a correr cuando producción cambie.

Los `*.json` están en `.gitignore`: los exports de n8n traen los tokens de Chatwoot en
claro. Ver `docs/validacion-hubspot-contactos.md` para el detalle de qué cambia y por qué.
