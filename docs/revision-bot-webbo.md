# Revisión — "WEBBO - Bot completo CORREGIDO (audio+imagen+texto)"

Instancia: `n8n-n8n.qhwbfx.easypanel.host` · Workflow ID `TX3A1wgpXHiLKwID` · Estado: **Active**
Alcance: revisión del JSON en vivo vía API (215 nodos, 199 orígenes de conexión, 23 triggers)
**más las últimas 50 ejecuciones con datos** (`GET /executions?includeData=true`).

> A diferencia de la revisión de Tatika, aquí sí hubo acceso a la API: los hallazgos marcados
> con 🔬 están confirmados con datos de ejecuciones reales de producción, no inferidos del JSON.

---

## Resumen

| Severidad | Cantidad |
|---|---|
| 🔴 Bloqueante (cuelga el bot, escribe mal al cliente o expone credenciales) | 5 |
| 🟠 Alto (rama que revienta, lógica inconsistente, sin manejo de error) | 8 |
| 🟡 Medio (coste, mantenimiento, observabilidad) | 8 |

**El dato que resume el estado del workflow: sólo 74 de los 215 nodos son alcanzables desde
los triggers activos. Los otros 141 son una copia muerta del flujo.**

Nodos por tipo: 72 HTTP Request · 36 Set · 14 Code · 10 Webhook · 10 IF · 8 Wait · 8 NoOp ·
6 Google Sheets · 6 Filter · 6 OpenAI · 4 Schedule · 4 Switch · 4 Split In Batches ·
4 Meta Lead Ads · 4 Google Calendar Tool · 2 AI Agent · 2 Function (deprecado).

### Los cuatro flujos vivos

| Trigger activo | Qué hace |
|---|---|
| `Webhook Typebot` (`POST /webbot-solvot`) | Conversación con el cliente: detecta texto/audio/imagen → transcribe o describe → `AI Agent` (Sofía) → responde a Typebot → actualiza CRM |
| `Cada 3 minutos` | Lee la cola de seguimiento del CRM (Supabase) y manda reintentos 5m/30m/12h (IA) o 24h/48h (plantilla) |
| `Nuevo Lead (Meta)3` · `Formulario Web3` · `Lead TikTok` · `Google Sheets Trigger1` | Entrada de leads → normaliza → CRM → crea contacto y conversación en Solvot → plantilla de bienvenida |
| `When clicking 'Execute workflow'` (manual) | Campaña en frío desde la hoja `WEBBO BG` |

---

## 🔴 Bloqueantes

### B1 — Bucle infinito en las ramas de audio y de imagen; el nodo de rescate está desconectado

La rama de audio está cableada así:

```
Audio se descargo?1 ── false ──▶ Obtener mensajes Solvot9 ──▶ audio
                                        ▲                       │
                                        └───────────────────────┴─▶ Descargar audio (intento 1)1
                                                                    └─▶ Esperar 3s ─▶ intento 2 ─▶ Audio se descargo?1
```

Es un ciclo cerrado **sin contador y sin salida**. Idéntico en imagen
(`Imagen se descargo?1 → Obtener mensajes Solvot10 → Descargar imagen (intento 1)1 → …`).

Lo grave es que la salida correcta **ya existe y está escrita**: los nodos
`Mensaje final (audio fallo)` y `Mensaje final (imagen fallo)` contienen exactamente el texto
de rescate previsto…

```
"[Nota de voz recibida, pero no pude acceder al audio despues de varios intentos.
  Cuentame por escrito en que te puedo ayudar.]"
```

…pero **no tienen conexión de entrada**. Alguien escribió el fallback y nunca lo cableó; en su
lugar la rama `false` se realimentó al principio.

Consecuencias cuando el `data_url` de Chatwoot falla (que es justo el caso para el que se
construyó el reintento):

1. El `Webhook Typebot` está en `responseMode: responseNode`. Como nunca llega a
   `Responder a Typebot`, **Typebot se queda esperando hasta su timeout** y el cliente no
   recibe nada.
2. La ejecución sigue girando indefinidamente, con una llamada a la API de Solvot y dos
   descargas cada 3 segundos.

**Corrección:** borrar las conexiones `false → Obtener mensajes Solvot9/10` y conectar
`Audio se descargo?1[false] → Mensaje final (audio fallo)` e
`Imagen se descargo?1[false] → Mensaje final (imagen fallo)`. Ambos ya apuntan a
`Obtener contacto` aguas abajo, así que el flujo se cierra solo.

### B2 — 🔬 El seguimiento automático le escribe a clientes que **ya respondieron**

Reconstruido de las ejecuciones reales de la conversación `1032` (Héctor Castro, `+573158405069`):

| Hora (UTC) | Ejecución | Qué pasó |
|---|---|---|
| 01:42 | `24044704` | Cron manda `reintento_5m`: *"Héctor, para aterrizarlo rápido…"* |
| 01:58 | `24044713` | **El cliente responde "Sí, quiero saber más"** y el `AI Agent` le contesta con la propuesta completa |
| 02:06 | `24044718` | El cron lo devuelve en la cola **otra vez con `etapa_nueva: reintento_5m`** y le manda *"Para ubicarte sin venderte humo… ¿Cuál es el nombre…"* |

O sea: 8 minutos después de una respuesta activa del cliente, el bot le manda un mensaje de
"te perdí". Dos defectos superpuestos:

- **La etapa no avanza.** `CRM: avanzar etapa` reenvía `follow_up_stage = {{ etapa_nueva }}`,
  es decir la etapa que *acaba de ejecutar*, no la siguiente. Héctor recibió `reintento_5m` dos
  veces. (Wilson Herrera sí pasó de `5m` a `30m`, así que el CRM avanza a veces — lo que apunta
  a que el mensaje entrante **reinicia** el reloj de seguimiento en vez de cancelarlo.)
- **n8n no tiene ninguna guarda.** El payload de `leads-seguimiento` ya trae
  `ultimo_mensaje_usuario` (en el caso de Héctor venía con `"Sí, quiero saber más"`), pero
  nadie lo mira antes de enviar.

**Corrección (dos lados):**
1. En la función `leads-seguimiento` de Supabase: excluir leads cuyo último evento sea un
   `mensaje_recibido` posterior al último mensaje del bot. Un cliente que responde sale de la
   secuencia, no la reinicia.
2. En n8n, como red de seguridad inmediata: que el CRM devuelva
   `ultimo_mensaje_usuario_at` y `ultima_respuesta_bot_at`, y meter un `Filter` entre
   `Separar leads` y `Uno a uno1` que descarte todo lead con
   `ultimo_mensaje_usuario_at > ultima_respuesta_bot_at`.

Mientras esto siga así, cada cliente que conteste recibe mensajes de seguimiento encima de la
conversación real. Es el hallazgo con más impacto comercial de la lista.

### B3 — Tres credenciales en claro repartidas en 62 nodos, una compartida con otro cliente

| Secreto | Dónde | Nodos |
|---|---|---|
| Token Chatwoot `hwWCD8Nu…` | header `api_access_token`, cuenta **64** (Webbo) | 56 |
| Token Chatwoot `ioGpXHKQ…` | header `api_access_token`, cuenta **60** | 6 |
| Bearer Supabase `a933e0c5…` | header `Authorization` a `…supabase.co/functions/v1/…` | 5 |

Tres cosas:

1. **El token `hwWCD8Nu…` es el mismo que aparece en el workflow de Tatika/Colina del Viento**
   (ver `docs/revision-flow-tatika-colina-conaring.md`, hallazgo A3), donde se usa contra la
   cuenta `60`. Un único token cruzando cuentas de clientes distintos: quien tenga acceso al
   export de un cliente puede operar sobre el Chatwoot del otro.
2. El bearer de Supabase da acceso a las *edge functions* `solvot-inbound` y
   `leads-seguimiento` del CRM, con el `empresa_id` en la query string. Con ese token se puede
   leer la cola de leads y escribir eventos en el CRM.
3. Todos viajan en claro en cada export del workflow y en cada backup.

**Corrección:** crear credenciales *Header Auth* en n8n (una para Chatwoot, una para Supabase),
pasar los 62 nodos a `authentication: predefinedCredentialType`, y **rotar los tres secretos** —
ya circularon en archivos exportados. Además separar el token de la cuenta 60 del de la 64.

### B4 — Los tres webhooks de entrada son públicos y sin autenticación

`Formulario Web3` (`POST /lead-web`), `Lead TikTok` (`POST /lead-tiktok`) y
`Webhook Typebot` (`POST /webbot-solvot`) tienen `options: {}` — sin *Header Auth*, sin *Basic
Auth*, sin secreto compartido.

Cualquiera que conozca (o adivine) la URL puede, con un `curl`:

- crear contactos y conversaciones en el Solvot de Webbo,
- **disparar el envío de la plantilla `remarketing_webbo` a cualquier número móvil colombiano**
  (el normalizador sólo valida el formato `57[36]` + 12 dígitos, no de dónde viene),
- e inyectar mensajes falsos al `AI Agent` con un `contact_id` arbitrario.

Coste directo en plantillas de Meta y riesgo de que la calidad del número WhatsApp caiga por
reportes de spam.

**Corrección:** activar *Header Auth* en los tres webhooks (n8n → nodo Webhook →
*Authentication*) y configurar el secreto en Typebot, en el formulario web y en el conector de
TikTok. Como mínimo, un header compartido validado en un `IF` inmediatamente después.

### B5 — 141 de 215 nodos son una copia muerta del flujo

De los 91 nombres base del workflow, **88 tienen 2 o más copias** (6 nombres llegan a 6 copias).
Sólo 74 nodos son alcanzables desde los triggers activos. El resto es una versión anterior
completa, con sus triggers desactivados.

Lo que esto rompe hoy:

| Path | Nodos que lo declaran |
|---|---|
| `POST /lead-web` | `Formulario Web`, `Formulario Web1`, `Formulario Web2` (desactivados) + `Formulario Web3` (activo) |
| `POST /lead-tiktok` | `Lead TikTok1` (desactivado) + `Lead TikTok` (activo) |
| `POST /webbot-solvot` | `Webhook Typebot2` (desactivado) + `Webhook Typebot` (activo) |
| `GET /bdwebboclientes` | `Webhook`, `Webhook1` (ambos desactivados) |

**Reactivar cualquiera de esos nodos impide activar el workflow entero** (n8n rechaza dos
webhooks activos con el mismo método y path). El bot completo se cae por reactivar un nodo
"para probar".

Y los `webhookId` también están duplicados por copiar/pegar: los 4 `Nuevo Lead (Meta)*`
comparten `fb-lead-webbot`, los 4 `Formulario Web*` comparten `lead-web-webbot`, y los pares de
`Wait` comparten `wait-webhook-001`, `wait-seg-v2`, `wait-audio-retry`, `wait-img-retry` — o sea
que las URL de reanudación de los Wait colisionan entre copias.

**Corrección:** exportar una copia de respaldo, borrar los 141 nodos muertos y volver a
generar los `webhookId` de los que queden (borrando y recreando el nodo). Es la limpieza que
más reduce el riesgo por unidad de esfuerzo.

---

## 🟠 Altos

### A1 — El "intento 1" de audio/imagen nunca sirve para nada

La cadena es lineal, no condicional:

```
Descargar audio (intento 1)1 ─▶ Esperar 3s ─▶ Descargar audio (intento 2)1 ─▶ Audio se descargo?1
```

No hay IF entre el intento 1 y el intento 2, así que **el intento 2 siempre se ejecuta y el
resultado del intento 1 siempre se descarta**. En la práctica no es un reintento: es descargar
el mismo archivo dos veces con 3 segundos de pausa forzada en medio.

Coste: +3 s de latencia y una descarga extra en **cada** nota de voz e imagen, incluso cuando la
primera funcionó a la primera. Sobre un webhook síncrono con Typebot esperando al otro lado.

**Corrección:** meter un `IF` después del intento 1 (`$json.error` no existe → seguir directo a
`Transcribir audio`; existe → esperar y reintentar).

### A2 — Un teléfono inválido en el formulario web tumba la ejecución

`Normalizar Web1` devuelve `telefono: ''` cuando el número no cumple `57[36]` + 12 dígitos.
Nadie filtra ese caso, y la cadena sigue:

```
CRM: crear lead        →  {"telefono": "+"}
Crear contacto1        →  phone_number "+"  →  422 de Chatwoot  →  salida de error
Buscar contacto3       →  q="+"             →  payload: []
Datos (existente)3     →  {{ $json.payload[0].id }}  →  💥 error, ejecución abortada
```

`Datos (existente)3`, `Datos (existente)1` y `Datos (existente)5` leen `payload[0]` sin
comprobar que el array tenga elementos. Mismo problema si la búsqueda simplemente no encuentra
al contacto.

**Corrección:** un `Filter` después de `Normalizar *` que descarte `telefono` vacío, y cambiar
las expresiones a `{{ $json.payload?.[0]?.id ?? null }}` con un `IF` que corte si es nulo.

### A3 — `Que reintento` sin salida por defecto corta la cola de seguimiento

El `Switch` tiene `options.fallbackOutput: "none"` y cuatro reglas
(`contextual`, `24h`, `48h`, `pausar`). Está **dentro** del bucle `Uno a uno1`
(`splitInBatches`), y todas las salidas terminan en `CRM: avanzar etapa → Esperar 10s1 →
Uno a uno1`.

Si llega un lead con un `etapa_nueva` que no matchea ninguna regla (un valor nuevo del CRM, un
`null`, un typo), el item se descarta **y nadie vuelve al nodo de batch**: el bucle se detiene y
los leads restantes de esa tanda (hasta 50) no se procesan en ese ciclo.

**Corrección:** poner `fallbackOutput` en una salida "extra" conectada a `CRM: avanzar etapa`
(o a un `NoOp` que retorne al bucle) para que el loop siempre cierre.

### A4 — 17 de los 35 nodos de API vivos no tienen `onError` ni `retryOnFail`

Los críticos, por lo que rompen:

| Nodo | Qué pasa si falla |
|---|---|
| `AI Agent`, `OpenAI Chat Model` | La ejecución muere **antes** de `Responder a Typebot` → Typebot cuelga hasta timeout |
| `Transcribir audio`, `Analizar imagen` | Igual: el cliente mandó una nota de voz y no recibe nada |
| `Generar mensaje contextual` | Muere el bucle de seguimiento completo, no sólo ese lead |
| `CRM: cola de seguimiento` | Un 5xx de Supabase pierde el ciclo entero de 3 minutos |
| `Buscar contacto1/3`, `Crear conversacion1/2` | Cortan la creación del lead a medio camino (contacto creado, conversación no) |

**Corrección:** `retryOnFail: true` con `maxTries: 3` en todos los de red, y para la rama de
Typebot un camino de error que llegue igual a `Responder a Typebot` con un mensaje genérico —
que el cliente reciba "dame un segundo, ya te respondo" es infinitamente mejor que el silencio.

### A5 — La misma plantilla `remarketing_webbo` se manda con dos textos distintos

| Nodo | `content` enviado a Chatwoot |
|---|---|
| `Enviar plantilla1` (leads Meta/Web/TikTok) | `"Hola Juan"` |
| `Enviar mensaje2` (campaña en frío) | `"Hola Juan 👋 Te saludamos de WEBBO, tu agencia de automatizacion, marketing y desarrollo web. …"` |

Ambos declaran `template_params.name = "remarketing_webbo"` con un único parámetro `{{1}}` =
nombre. Lo que Meta entrega es el cuerpo aprobado de la plantilla; el `content` es lo que queda
registrado en Solvot. Con dos valores distintos, **la bandeja del agente muestra un texto que no
es el que recibió el cliente** en al menos uno de los dos casos.

**Corrección:** decidir cuál es el cuerpo real de la plantilla aprobada y usar exactamente ese
texto como `content` en los dos nodos.

### A6 — La validación de teléfono es más estricta al final que a la entrada

- `Normalizar Meta1` / `Normalizar Web1` / `Normalizar TikTok`: aceptan `/^57[36]/` (móvil **y
  fijo**), 12 dígitos.
- `Analizar interaccion` (Code, paso 5): `const telefono = (num.length === 12 && num.startsWith('573')) ? '+' + num : '';`
  → **sólo móviles**.

Un lead con fijo (`5760…`, `5761…`) entra bien, crea contacto y conversación, conversa con el
agente… y al llegar a `Analizar interaccion` sale con `telefono: ''` → `tiene_telefono: false` →
el `Filter` "Tiene telefono?" lo descarta → **`CRM: actualizar fase` nunca corre y la
conversación no queda registrada en el CRM**.

**Corrección:** unificar en `/^57[36]/` (o en lo que defina el negocio) en los cuatro sitios.

### A7 — 🔬 29 ejecuciones en error, todas del `Google Sheets Trigger1`

Todas las ejecuciones fallidas del workflow son del mismo nodo, con el mismo error:

```
NodeApiError: Service unavailable - try again later or consider setting this node to retry
automatically (in the node settings)
```

Racha del 2026-08-18 entre 11:16 y 11:30 UTC, una por minuto. El trigger está en
`pollTimes: everyMinute` sobre la hoja `Tiktok`, y no tiene `retryOnFail`. Cada 503 de Google es
una ejecución fallida y **una ventana de un minuto en la que un lead nuevo puede perderse**.

**Corrección:** bajar el poll a `everyX / 5 minutos` y activar `retryOnFail` con `maxTries: 3`.

### A8 — El seguimiento avanza de etapa aunque el envío haya fallado

`Enviar mensaje contextual` tiene `onError: continueRegularOutput` y su salida va directo a
`CRM: avanzar etapa`. Si Chatwoot responde 4xx/5xx (ventana de 24h cerrada, conversación
archivada, token caducado), el error se traga y **el CRM registra la etapa como completada**.
El lead avanza a la siguiente fase sin haber recibido nada, y ese mensaje no se reintenta nunca.

**Corrección:** un `IF` entre ambos que compruebe que la respuesta trae `id` de mensaje, y sólo
entonces avanzar la etapa.

---

## 🟡 Medios

### M1 — `Esperar 40s` espera 1 segundo

`Esperar 40s` y `Esperar 40s2` tienen `parameters: {}`, es decir toman el valor por defecto del
nodo Wait (`amount: 1`). Que la unidad efectiva sea *segundos* está verificado: `Esperar 10s1`
con `{"amount": 10}` midió **10001 ms** en la ejecución `24044716`.

O sea que el nodo que separa los envíos de la campaña en frío **espera ~1 s, no 40 s**: 50
mensajes de WhatsApp en menos de dos minutos. Como está en la rama del trigger manual todavía no
ha hecho daño, pero el día que se lance la campaña es un patrón de envío que Meta penaliza.

**Corrección:** poner `amount: 40` explícito (o el intervalo que se quiera) en ambos nodos.

### M2 — El system prompt de Sofía son 30.328 caracteres, y va en cada turno

~8.000 tokens de instrucciones **por mensaje**, más una memoria de 20 turnos
(`Memoria por conversacion`, `contextWindowLength: 20`), sobre `gpt-5.5`. Una conversación
larga multiplica ese coste en cada intercambio.

El prompt está bien escrito (rol, catálogo, planes con precios, manejo de objeciones, reglas de
agenda) — el problema es sólo de coste. Vale la pena medir cuánto del catálogo y del tarifario
se usa realmente y mover lo que casi nunca aplica a una herramienta consultable bajo demanda.

### M3 — La respuesta al cliente depende de que la IA ponga bien los backticks

`Responder a Typebot` hace `$json.output.split('```')[0].trim()` y `Analizar interaccion` toma el
*último* bloque con fence. El prompt exige el bloque JSON al final de cada respuesta, pero si el
modelo lo emite sin fences o lo pone primero, **el cliente ve el JSON del CRM en WhatsApp**.

**Corrección:** usar salida estructurada del agente, o limpiar con un regex que quite cualquier
`{ … "lead_state" … }` suelto además del bloque con fence.

### M4 — Sin workflow de error y sin alertas

`settings` no define `errorWorkflow`. Con `continueRegularOutput` en 16 de los nodos vivos, muchos fallos ni
siquiera marcan la ejecución como fallida (las 50 últimas figuran todas como `success` aunque
dentro haya nodos que se tragaron errores). Hoy nadie se entera de nada salvo que entre a mirar.

**Corrección:** crear un workflow de error que notifique a Slack/correo y asignarlo en
*Settings → Error Workflow*.

### M5 — Restos del workflow de otro cliente

`status a pendiente` y `status a pendiente2` (huérfanos, sin entrada) apuntan a
`chat.solvot.com/api/v1/accounts/**60**/…` con el token `ioGpXHKQ…` — la cuenta de otro cliente,
no la 64 de Webbo. Además la URL termina con un **espacio** después de `toggle_status`. Son
sobras de un copiar/pegar entre workflows. Borrar con el resto de B5.

### M6 — 2 nodos `n8n-nodes-base.function` (deprecado)

`Procesar Info Detallada` y `Procesar Info Detallada3` siguen en el nodo `Function` v1, retirado
de la UI. Ambos están en la parte muerta, así que se van con la limpieza de B5.

### M7 — Se crea una conversación nueva sin comprobar si ya hay una abierta

`Crear conversacion1` / `Crear conversacion2` hacen `POST /conversations` directo. Si el contacto
ya tiene una conversación abierta en el inbox 131 (por ejemplo, un lead que llega por Meta y por
el formulario web), se crea una segunda y el historial del cliente queda partido en dos hilos.

**Corrección:** `GET /contacts/{id}/conversations` antes y reutilizar la abierta si existe.

### M8 — `availableInMCP: true`

El workflow está expuesto como herramienta MCP. Si no es intencional, conviene apagarlo: es una
vía más para dispararlo desde fuera.

---

## Lo que sí está bien

- **`settings.timezone = "America/Bogota"`** correctamente fijado (el workflow de Tatika no lo
  tenía y por eso los cron estaban corridos 5 horas). Y el `AI Agent` recibe la fecha ya
  convertida con `$now.setZone('America/Bogota')`.
- **El patrón "crear o buscar contacto" está bien resuelto**: `Crear contacto*` usa
  `onError: continueErrorOutput` y la salida de error va a `Buscar contacto*`. Es la forma
  idiomática de hacer un upsert contra Chatwoot en n8n.
- **Los normalizadores de Meta / Web / TikTok son sólidos**: buscan el campo por varios alias,
  limpian no-dígitos, quitan ceros a la izquierda, anteponen `57` y validan longitud.
- Los cuatro bucles `splitInBatches` tienen el ciclo cerrado correctamente.
- No hay nombres de nodo duplicados, ni conexiones a nodos inexistentes, ni expresiones
  `$('Nodo')` apuntando a nodos que no existen (se revisaron los 215).
- La estrategia de canal es correcta: texto libre en los reintentos cortos (dentro de la ventana
  de 24 h de WhatsApp) y plantillas aprobadas en los de 24 h y 48 h.
- `Analizar interaccion` tiene defensas reales y bien pensadas: no acepta el nombre de la
  persona como nombre de empresa, descarta el teléfono cuando Solvot lo mete en el campo
  `name`, y detecta el `STOP` de opt-out.
- El system prompt de Sofía está bien estructurado (rol, orden obligatorio de captura de datos,
  catálogo, planes, objeciones, reglas de agenda) y prohíbe confirmar una cita que el
  calendario no haya creado.

---

## Orden sugerido de corrección

1. **B1** — reconectar los dos `Mensaje final (… fallo)` y borrar el ciclo. Son 4 cambios de
   conexión y quitan el único caso en que el bot deja al cliente sin respuesta.
2. **B2** — guarda contra escribirle a quien ya respondió. Es el que más cuesta comercialmente y
   está pasando ahora mismo en producción.
3. **B4 + B3** — autenticar los tres webhooks y rotar los tres secretos a credenciales de n8n.
4. **B5** — respaldar y borrar los 141 nodos muertos, regenerar `webhookId`.
5. **A2 + A3 + A6** — las tres ramas que revientan o descartan datos en silencio.
6. **A4 + A8** — `retryOnFail` en los nodos de red y no avanzar etapa si el envío falló.
7. **A1 + A7 + M1** — latencia del reintento, poll del Sheet, `amount` de los Wait.
8. **A5 + M3 + M4** — coherencia de plantillas, limpieza de la salida de la IA, workflow de error.
