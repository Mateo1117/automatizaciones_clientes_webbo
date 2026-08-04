# Habilitar el acceso a la API de n8n desde Claude Code

## El problema

Claude Code corre en un contenedor aislado en la nube. Todo el tráfico saliente pasa por un
proxy que aplica la **política de red del entorno**. Ese proxy rechaza los dominios que no
estén en la lista de permitidos:

```
CONNECT flow.mcmasociados.tech:443 HTTP/1.1
< HTTP/1.1 403 Forbidden
```

Confirmado desde el propio proxy:

```json
{
  "recentRelayFailures": [
    { "kind": "connect_rejected",
      "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
      "host": "flow.mcmasociados.tech:443" }
  ]
}
```

No es la API key ni la instancia de n8n: es la política de egreso del entorno. No se puede
sortear desde dentro de la sesión — hay que cambiarla desde la configuración del entorno.

---

## Paso a paso

### 1. Rotar la API key de n8n (hacer esto primero)

La key que se compartió en el chat quedó en el historial de la conversación, y su JWT no
tiene claim `exp` — **no caduca nunca**.

1. Entrar a `https://flow.mcmasociados.tech`.
2. Menú de usuario (abajo a la izquierda) → **Settings**.
3. **n8n API**.
4. En la key existente → **Delete**.
5. **Create an API key**. Ponerle un nombre reconocible (`claude-code-review`) y, si la
   versión lo permite, **fecha de expiración a 7 días** y scopes mínimos:
   `workflow:read`, `workflow:update`, `execution:read`.
6. Copiar la key. Sólo se muestra una vez.

### 2. Permitir el dominio en el entorno de Claude Code

1. Abrir **https://claude.ai/code**.
2. Ícono de engranaje / **Settings** → **Environments**.
3. Seleccionar el entorno que usa este repo (`automatizaciones_clientes_webbo`) → **Edit**.
4. En **Network access**, cambiar de la política restringida a la opción que permite lista
   propia de dominios (*custom / additional allowed domains*).
5. Agregar el host, sin `https://` ni ruta:

   ```
   flow.mcmasociados.tech
   ```

   Si la instancia usa un puerto distinto de 443, incluirlo: `flow.mcmasociados.tech:5678`.
6. **Save**.

Referencia oficial: https://code.claude.com/docs/en/claude-code-on-the-web

> El cambio de política aplica a **entornos nuevos o reiniciados**. La sesión actual sigue
> con la política vieja: hay que abrir una sesión nueva después de guardar.

### 3. Pasar la key como variable de entorno (no por el chat)

En la misma pantalla del entorno, sección **Environment variables**:

| Nombre | Valor |
|---|---|
| `N8N_API_KEY` | *(la key nueva del paso 1)* |
| `N8N_BASE_URL` | `https://flow.mcmasociados.tech` |

Así la key no vuelve a quedar escrita en el historial del chat.

### 4. Abrir sesión nueva y verificar

Iniciar una sesión nueva de Claude Code sobre este repo y pedir que corra:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/workflows?limit=1"
```

- `200` → conectado, listo.
- `401` → la key no es válida o no se cargó la variable.
- `000` + `CONNECT tunnel failed, response 403` → el dominio sigue bloqueado; revisar el
  paso 2 y confirmar que la sesión sea nueva.

### 5. Qué se puede hacer ya con la API

```bash
# Traer el workflow completo
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/workflows/m9mqIWiuJay9qOws" > workflow.json

# Ejecuciones con error (para ver qué está fallando de verdad)
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/executions?status=error&workflowId=m9mqIWiuJay9qOws&limit=20"

# Detalle de una ejecución, con los datos de cada nodo
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/executions/<ID>?includeData=true"

# Aplicar correcciones
curl -s -X PUT -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" \
  --data @workflow-corregido.json \
  "$N8N_BASE_URL/api/v1/workflows/m9mqIWiuJay9qOws"
```

Ojo con `PUT /workflows/{id}`: **reemplaza** el workflow entero. Antes de escribir,
desactivarlo (`POST /workflows/{id}/deactivate`) y guardar una copia del JSON actual.

---

## Si no se puede cambiar la política del entorno

Alternativa sin API, ya validada: exportar el workflow desde la UI de n8n
(`⋯` → **Download**) y subir el `.json` al chat. Es como se hizo esta revisión. Lo único que
se pierde es el historial de ejecuciones — que se puede exportar aparte desde
**Executions** → abrir una fallida → `⋯` → **Download**.
