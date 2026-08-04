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

> ⚠️ **La configuración de entornos NO está en Settings.** No existe página de ajustes ni
> URL directa para el selector — hay que abrirlo desde la pantalla de Claude Code.
> (Documentación: *"There's no settings page or direct URL for the selector."*)

1. Abrir **https://claude.ai/code**.
2. **Justo encima de la caja de mensajes** hay una fila con un **ícono de nube ☁️ que
   muestra el nombre del entorno actual** (normalmente `Default`). Hacer clic ahí.
3. Se abre un menú con secciones *Local*, *Cloud* y *Remote Control*. En **Cloud**:
   - **Recomendado:** **Add cloud environment** — crea uno nuevo y deja intacto el `Default`.
   - O bien: pasar el mouse sobre el entorno existente → **ícono de engranaje ⚙️** a la derecha.
4. En el diálogo (campos: *Name*, *Network access*, *Environment variables*, *Setup script*):

   | Campo | Valor |
   |---|---|
   | **Name** | `n8n-webbo` |
   | **Network access** | cambiar de `Trusted` a **`Custom`** |
   | **Allowed domains** | `flow.mcmasociados.tech` (uno por línea) |

   Si la instancia usa un puerto distinto de 443, incluirlo: `flow.mcmasociados.tech:5678`.
   Un `*.` inicial hace match con todos los subdominios.

5. ✅ **Marcar "Also include default list of common package managers"**. Sin esa casilla
   queda permitido *sólo* el dominio de la lista y se rompe todo lo demás (npm, apt,
   GitHub, PyPI…).
6. **Create environment** / **Save**.

Los cuatro niveles de `Network access` son:

| Nivel | Salida permitida |
|---|---|
| `None` | Nada por la red de la sesión |
| `Trusted` | *(default)* Sólo la lista de dominios de Anthropic (registries, GitHub, SDKs) |
| `Full` | Cualquier dominio |
| `Custom` | Lista propia, con o sin los defaults |

Referencia oficial: https://code.claude.com/docs/en/cloud-environments

> El cambio aplica a **sesiones nuevas**. La sesión en curso sigue con la política vieja.
> Además, al cambiar los hosts permitidos se invalida la caché del entorno y el setup
> script vuelve a correr en la siguiente sesión.

### 3. Pasar la key como variable de entorno

En el mismo diálogo, campo **Environment variables**, en formato `.env` (un `KEY=value`
por línea):

```
N8N_BASE_URL=https://flow.mcmasociados.tech
N8N_API_KEY=<la key nueva del paso 1>
```

> ⚠️ **Advertencia de la documentación:** los entornos cloud **no tienen almacén de
> secretos**. Cualquiera que use el entorno puede leer las variables en claro
> (*"don't add API keys or other credentials"*).
>
> En un entorno **personal** el riesgo práctico es bajo. En un entorno **compartido de
> organización**, cualquier miembro la lee. Mitigación: usar la key con **expiración de 7
> días y scopes mínimos** (paso 1) y borrarla al terminar.
>
> La alternativa es no guardarla y pegarla en cada sesión — pero entonces vuelve a quedar
> en el historial del chat. Elegir según quién más tenga acceso al entorno.

### 3b. Seleccionar el entorno al abrir la sesión

Si se creó un entorno nuevo en vez de editar el `Default`, hay que **elegirlo en el mismo
ícono de nube antes de mandar el primer mensaje** de la sesión. Si no, la sesión arranca en
`Default` y el dominio sigue bloqueado.

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

## Si no aparece la opción

- **No se ve el ícono de nube:** requiere haber pasado por el onboarding web de Claude Code.
  La función está en *research preview* para planes **Pro, Max y Team**, y para **Enterprise**
  con asientos premium o Chat + Claude Code.
- **El entorno es compartido de la organización:** los entornos creados por un admin se
  editan desde **Cloud environments** en https://claude.ai/admin-settings — hace falta rol
  de Owner o Admin. Si no se tiene, hay que pedírselo al administrador.

## Si no se puede cambiar la política del entorno

Alternativa sin API, ya validada: exportar el workflow desde la UI de n8n
(`⋯` → **Download**) y subir el `.json` al chat. Es como se hizo esta revisión. Lo único que
se pierde es el historial de ejecuciones — que se puede exportar aparte desde
**Executions** → abrir una fallida → `⋯` → **Download**.
