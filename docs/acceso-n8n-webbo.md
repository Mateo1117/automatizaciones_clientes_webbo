# Acceso a la segunda instancia de n8n (bot de Webbo)

El workflow **"WEBBO - Bot completo CORREGIDO (audio+imagen+texto)"** no está en
`flow.mcmasociados.tech`. Vive en otra instancia, sobre Easypanel:

| Dato | Valor |
|---|---|
| Instancia | `https://n8n-n8n.qhwbfx.easypanel.host` |
| Workflow ID | `TX3A1wgpXHiLKwID` |
| URL directa | https://n8n-n8n.qhwbfx.easypanel.host/workflow/TX3A1wgpXHiLKwID |

Estado verificado desde la sesión: **dominio bloqueado**.

```
CONNECT n8n-n8n.qhwbfx.easypanel.host:443 → 403
{ "kind": "connect_rejected",
  "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)" }
```

No es la instancia ni la API key: es la política de egreso del entorno, igual que pasó con
`flow.mcmasociados.tech`. **No se puede sortear desde dentro de la sesión.**

---

## Pasos

### 1. Agregar el dominio al entorno

1. Abrir **https://claude.ai/code**.
2. Ícono de nube ☁️ **justo encima de la caja de mensajes** (muestra el nombre del entorno
   actual) → clic.
3. Sobre el entorno que ya se usa para este proyecto → **ícono de engranaje ⚙️**.
4. **Network access** debe estar en **`Custom`**. En **Allowed domains**, dejar el que ya
   está y agregar el nuevo, uno por línea:

   ```
   flow.mcmasociados.tech
   n8n-n8n.qhwbfx.easypanel.host
   ```

5. ✅ Mantener marcado **"Also include default list of common package managers"**. Sin esa
   casilla se rompe npm, apt, GitHub, PyPI y todo lo demás.
6. **Save**.

### 2. Crear la API key en esa n8n

1. Entrar a `https://n8n-n8n.qhwbfx.easypanel.host`.
2. Menú de usuario (abajo a la izquierda) → **Settings** → **n8n API**.
3. **Create an API key**. Nombre reconocible (`claude-code-webbo`) y **expiración de 7 días**.
4. Copiarla. Sólo se muestra una vez.

### 3. Guardarla como variable de entorno

En el mismo diálogo del entorno, campo **Environment variables**, formato `.env`:

```
N8N_BASE_URL=https://flow.mcmasociados.tech
N8N_API_KEY=<la que ya está>
N8N_WEBBO_BASE_URL=https://n8n-n8n.qhwbfx.easypanel.host
N8N_WEBBO_API_KEY=<la key nueva del paso 2>
```

> ⚠️ Los entornos cloud **no cifran las variables**: cualquiera con acceso al entorno las lee
> en claro. Por eso la expiración de 7 días del paso 2, y borrar la key al terminar.
>
> La alternativa es pegarla en el chat, pero entonces queda en el historial de la
> conversación — que es lo que pasó con el token de Meta y por eso hay que regenerarlo.

### 4. Abrir una sesión NUEVA

El cambio de red **no aplica a la sesión en curso**. Hay que abrir una sesión nueva sobre
este mismo repo. Si se creó un entorno distinto en vez de editar el existente, hay que
**elegirlo en el ícono de nube antes de mandar el primer mensaje**.

### 5. Verificar

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-N8N-API-KEY: $N8N_WEBBO_API_KEY" \
  "$N8N_WEBBO_BASE_URL/api/v1/workflows?limit=1"
```

- `200` → conectado.
- `401` → la key no es válida o no se cargó la variable.
- `000` + `CONNECT tunnel failed, response 403` → el dominio sigue bloqueado; revisar el
  paso 1 y confirmar que la sesión sea nueva.

Y traer el workflow:

```bash
curl -s -H "X-N8N-API-KEY: $N8N_WEBBO_API_KEY" \
  "$N8N_WEBBO_BASE_URL/api/v1/workflows/TX3A1wgpXHiLKwID" > webbo-bot.json
```

---

## Alternativa sin accesos

Si no se puede cambiar la política del entorno: exportar el workflow desde la UI
(`⋯` → **Download**) y subir el `.json` al chat. Se pierde el historial de ejecuciones, que
se puede exportar aparte desde **Executions** → abrir una fallida → `⋯` → **Download**.

Para una revisión estática alcanza. Para aplicar correcciones directamente sobre la
instancia hace falta la API.

---

## Qué revisar cuando haya acceso

De la captura, el workflow tiene 4 flujos y ~45 nodos:

**Flujo 1 — bot conversacional (audio + imagen + texto)**
`Webhook Typebot → Obtener mensajes Solvot → Detectar tipo de mensaje → Que tipo es`
con ramas a descarga de imagen (con reintentos: *intento 1*, *Esperar 3s*, *intento 2*,
*Imagen se descargó?*), `Analizar imagen`, y luego
`Obtener contacto → Combinar contacto y mensaje → AI Agent → Responder a Typebot →
Analizar interacción → Tiene teléfono? → CRM: actualizar fase`.
El `AI Agent` cuelga de `OpenAI Chat Model`, `Memoria por conversación`,
`Consultar disponibilidad` y `Agendar cita`.

**Flujo 2 — ingesta de leads (4 orígenes)**
`Nuevo Lead (Meta)`, `Formulario Web`, `Lead TikTok`, `Google Sheets Trigger` → cada uno con
su `Normalizar *` → `Datos lead` → `CRM: crear lead` → `Crear contacto` →
`Buscar contacto` → `Datos (nuevo)` / `Datos (existente)` → `Crear conversación` →
`CRM: vincular Solvot` → `Enviar plantilla`.

Puntos a verificar (son los que dieron problemas en el flujo de Conaring):

1. **Duplicados**: `Crear contacto` antes de `Buscar contacto` sugiere que se crea primero y
   se busca después. Si es así, hay riesgo de duplicados y de condición de carrera.
2. **`Enviar plantilla`**: nombre + idioma exactos contra las plantillas aprobadas de **esa**
   WABA, y que el número de variables `{{n}}` coincida. Es el origen de los errores
   `Template not found or invalid template name` y
   `Number of parameters does not match` vistos en Chatwoot.
3. **Errores `131049`** en los envíos: es Meta descartando plantillas MARKETING por límite de
   engagement. No se arregla por código.
4. **Manejo de error** en los nodos HTTP y de WhatsApp: sin `onError`/`retryOnFail`, un 429 o
   un 404 corta la ejecución completa.
5. **Los 4 orígenes de lead** deben converger en la misma lógica de deduplicación.
6. **`Google Sheets Trigger`**: revisar el intervalo de polling, por el mismo motivo que el
   `Schedule Trigger` de cada minuto en Conaring generaba 429.
