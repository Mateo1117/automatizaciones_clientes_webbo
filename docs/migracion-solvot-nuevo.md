# Migración del Solvot (Chatwoot) — del viejo al nuevo

El Solvot anterior (`chat.solvot.com`, cuenta 60) se cerró. Desde entonces los nodos que lo
llaman devuelven `connection timed out` y ningún lead recibe su mensaje.

Estado medido el 13-nov 20:35 (Colombia):

| | |
|---|---|
| Workflow `sDZyht21H9H3w2Tl` | **activo**, corriendo cada 15 min con normalidad |
| Primer timeout registrado | 13-nov 17:56 en `buscar contacto` |
| Contactos de Tatiká en `automatizacion = Error`, últimos 7 días | **56** |
| …últimos 30 días | 84 |

La contención que se puso en octubre está haciendo su trabajo: los leads quedan marcados
`Error` y **visibles**, y el lote sigue procesando en vez de abortarse. Sin eso, la caída del
Solvot habría dejado los leads desapareciendo en silencio.

> El historial de ejecuciones sólo guarda ~2 días y en esa ventana ningún lead nuevo alcanzó
> la cadena de Chatwoot (los 69 extraídos se descartaron antes, en el `Switch`, por estar ya
> procesados). Así que **no hay en el historial una llamada exitosa a Solvot que copiar**. La
> especificación de abajo sale de la definición del workflow, que es la fuente autoritativa.

---

## Especificación de la integración, tal como funcionaba

Cadena viva (Tatiká). Hay 8 nodos gemelos (`…2`) para Colina del Viento, hoy deshabilitados.

### Valores fijos del Solvot viejo

| Dato | Valor |
|---|---|
| Dominio | `chat.solvot.com` |
| `account_id` | `60` |
| `inbox_id` | `105` |
| `team_id` | `18` |
| Token A (lectura) | `hwWCD8…KykN` — en `buscar contacto`, `Busca conversacion`, `Actualizar contacto` |
| Token B (escritura) | `ioGpXH…7JH9` — en `crear contacto`, `crear conversacion`, `status a pendiente` |

Los tokens van **hardcodeados en el header `api_access_token`** de cada nodo.

### Secuencia

```
¿Teléfono Válido?3
  └─> buscar contacto            GET  /accounts/60/contacts/search?q={telefono}
        └─> IF  (¿existe?)
             ├─ no ─> crear contacto       POST /accounts/60/contacts/
             │          └─> crear conversacion  POST /accounts/60/conversations/
             │                └─> WhatsApp Cloud14  (envía saludo_tatika3)
             └─ sí ─> Contact Exists?2
                        ├─> Busca conversacion   GET /accounts/60/contacts/{id}/conversations
                        │     └─> Actualizar contacto  PUT /accounts/60/contacts/{id}
                        │           └─> WhatsApp Cloud14
                        └─> crear conversacion (si no tenía conversación)

WhatsApp Cloud14 ─> Wait ─> Crear y Actualizar Contacto8 (marca Iniciada + fecha_ultimo_mensaje)
                              └─> status a pendiente   POST /accounts/60/conversations/{id}/toggle_status
```

### Cuerpos exactos

**`crear contacto`** — `POST /api/v1/accounts/60/contacts/`
```json
{
  "inbox_id": "105",
  "name": "{{ firstname }} {{ lastname }}",
  "phone_number": "{{ phone_numbers.primary }}",
  "status": "open",
  "custom_attributes": { "email": "{{ email }}", "proyecto": "{{ business_info.proyecto }}" }
}
```
Respuesta usada: `payload.contact.id`.

**`crear conversacion`** — `POST /api/v1/accounts/60/conversations/`
```json
{
  "inbox_id": "105",
  "contact_id": "{{ $json.payload?.contact?.id || $json.payload[0].id }}",
  "team_id": "18",
  "status": "open",
  "message": { "content": "{{ mensaje }}" }
}
```
El `contact_id` con doble origen cubre las dos ramas: contacto recién creado
(`payload.contact.id`) o encontrado por búsqueda (`payload[0].id`).

**`Actualizar contacto`** — `PUT /api/v1/accounts/60/contacts/{contact_id}`
```json
{ "custom_attributes": { "email": "{{ email }}", "proyecto": "{{ proyecto }}" } }
```

**`status a pendiente`** — `POST /api/v1/accounts/60/conversations/{id}/toggle_status`
```json
{ "status": "pending" }
```

---

## Dos bugs latentes encontrados al extraer la especificación — ✅ CORREGIDOS 14-nov

Se corrigieron sin esperar al Solvot nuevo, porque son independientes del dominio: el
workflow quedó en **213 nodos** (antes 212) y sigue activo.

### B1 — `status a pendiente` usa el id del asesor, no el de la conversación

```
/accounts/60/conversations/{{ $('Busca conversacion').item.json.payload[0].meta.assignee.id }}/toggle_status
```

`meta.assignee.id` es el **agente asignado**, no la conversación. La URL correcta se arma con
`payload[0].id`. Tal como está, o apunta a una conversación ajena o devuelve 404.

### B2 — `status a pendiente` falla siempre para contactos nuevos

El nodo se alimenta de `Crear y Actualizar Contacto8`, que corre en **ambas** ramas. Pero su
expresión referencia `$('Busca conversacion')`, que **sólo se ejecuta en la rama del contacto
existente**. Para un contacto nuevo ese nodo nunca corrió y la expresión revienta.

Antes de la contención de octubre esto mataba el lote completo. Hoy cae en el manejador de
error, pero el `toggle_status` no se aplica.

### Cómo quedaron corregidos

Se insertó un nodo **`🔎 Resolver id de conversacion`** entre `Crear y Actualizar Contacto8`
y `status a pendiente`. Resuelve el id de la rama que haya corrido, leyendo cada origen
dentro de un `try` (referenciar un nodo que no se ejecutó lanza excepción):

```js
let convId = '';
try { convId = String($('Busca conversacion').first().json.payload[0].id); } catch (e) {}
if (!convId) { try { convId = String($('crear conversacion').first().json.id); } catch (e) {} }
```

`status a pendiente` pasó a `…/conversations/{{ $json.conversacion_id }}/toggle_status`
(también se quitó un espacio al final de la URL, que iba al path).

### B3 — bonus: el fallo del `toggle_status` marcaba el lead como `Error`

Encontrado al revisar las conexiones. La salida de error de `status a pendiente` iba a
`⚠️ Fallo en el envio (marca Error)`. Pero ese nodo corre **después** de
`WhatsApp Cloud14 → Wait → Crear y Actualizar Contacto8`: para cuando se ejecuta, **el
mensaje ya salió y el lead ya quedó en `Iniciada`**. Si fallaba el cambio de estado en
Chatwoot —algo cosmético— se sobrescribía a `Error` un lead que sí había sido contactado.

Eso lo introduje yo en la contención de octubre, al enrutar las 22 salidas de error al mismo
manejador sin separar las que ocurren antes del envío de las que ocurren después.

Ahora esa rama va a `Finalizar Envío`: se registra y el bucle continúa, sin tocar el estado.

| | Antes | Ahora |
|---|---|---|
| Contacto nuevo | expresión reventaba, nunca se aplicaba `pending` | se aplica con el id de `crear conversacion` |
| Contacto existente | apuntaba al id del **asesor** → 404 o conversación ajena | id real de `payload[0].id` |
| Si Chatwoot falla | lead marcado `Error` pese a haber recibido el mensaje | lead queda `Iniciada`, que es la verdad |

---

## Mejora: los tokens dejan de estar hardcodeados

Hoy el token está escrito a mano en 14 nodos, en dos variantes distintas. Rotarlo obliga a
tocar los 14, y queda en claro en cada export.

En la migración se reemplaza por **una credencial Header Auth de n8n**
(`api_access_token` = token del Solvot nuevo) y los nodos pasan a
`authentication: predefinedCredentialType`. A partir de ahí, rotar el token es **un cambio en
un solo sitio**, y el token no vuelve a aparecer en el JSON del workflow.

---

## Datos que hay que pedir / crear en el tenant nuevo

Esto es el inventario completo, verificado el 14-nov contra el workflow vivo
(`sDZyht21H9H3w2Tl`). Nada de esto se puede inventar desde n8n: son datos que da el tenant.

### A. Los 5 datos que bloquean la migración

| # | Dato | Valor viejo | Dónde se ve en el tenant nuevo | Se usa en |
|---|---|---|---|---|
| 1 | **Dominio** | `chat.solvot.com` | la URL de la barra al entrar | 14 nodos |
| 2 | **`account_id`** | `60` | está en la propia URL: `/app/accounts/**60**/dashboard` | 14 nodos |
| 3 | **`inbox_id`** de Tatiká | `105` | Configuración → Bandejas → abrir la de Tatiká; sale en la URL `/settings/inboxes/**105**` | `crear contacto`, `crear conversacion` |
| 4 | **`team_id`** | `18` | Configuración → Equipos → abrir el equipo; sale en la URL | `crear conversacion` |
| 5 | **Token de acceso** | 2 tokens distintos | Perfil → *Access Token* (token de un usuario) **o** Configuración → Integraciones → API (token de bot) | header `api_access_token` |

> **Sobre el token:** hoy hay **dos** (`hwWCD8…` para leer, `ioGpXH…` para escribir). En el
> tenant nuevo alcanza con **uno solo**, siempre que el usuario dueño del token tenga rol
> **administrador** de la cuenta. Un token de agente no puede crear contactos ni cambiar el
> estado de conversaciones ajenas.
>
> **El token no se pega en el chat.** Se crea en n8n como credencial *Header Auth*
> (nombre `api_access_token`) y yo sólo uso su ID. Ver la sección de abajo.

### B. Lo que hay que configurar dentro del tenant

**1. La bandeja (inbox) y el número de WhatsApp.**
El número debe ser el mismo: **`+57 302 7560683`**, `phone_number_id` `696830786845937`.

Ojo con esto, porque es la confusión más fácil: **quien envía el WhatsApp es n8n, no
Chatwoot.** Los 7 nodos `WhatsApp Business Cloud*` llaman a Meta directo con ese
`phone_number_id` y las plantillas `saludo_tatika3`, `mensaje_lead_agente`,
`finaliza_flujo_cliente`, `finaliza_colina_viento`. El Solvot sirve para **recibir las
respuestas** y para que el asesor conteste.

Si el número cambia, hay que tocar además los 24 nodos de WhatsApp y volver a aprobar
plantillas en Meta. **Conviene conservarlo.**

**2. Confirmar con Solvot el tipo de canal de la bandeja.** `crear conversacion` manda un
`message.content` al crear la conversación. Según el tipo de canal eso se comporta distinto:

| Si la bandeja es… | Qué pasa con ese `message` | Riesgo |
|---|---|---|
| Canal **API** | queda registrado como contexto, no se envía | ninguno — es lo que se asume hoy |
| Canal **WhatsApp** | Chatwoot intenta **entregarlo** | mensaje duplicado, o error fuera de la ventana de 24 h |

No se puede determinar desde fuera porque el tenant viejo ya está caído. **Hay que
preguntarlo al crear la bandeja nueva**, y si queda como canal WhatsApp, quitar el `message`
del body.

**3. Atributos personalizados del contacto.** `crear contacto` y `Actualizar contacto` envían:

```json
"custom_attributes": { "email": "…", "proyecto": "…" }
```

Si `email` y `proyecto` no existen como **atributos personalizados de contacto** en el tenant
nuevo (Configuración → Atributos personalizados), Chatwoot acepta la petición pero
**descarta los valores en silencio** — y el asesor pierde el proyecto del lead.

**4. Los asesores y el equipo.** El `team_id` es a quien se le asigna la conversación. El
equipo tiene que existir y tener agentes dentro, o las conversaciones llegan sin asignar.

**5. El bot y sus llamadas de vuelta a n8n.** Ver la sección siguiente: resultó no ser
"automatizaciones de Chatwoot" sino flujos del constructor de bot, y el detalle importa.

### B-bis. Los 12 webhooks son del BOT, no de Chatwoot

Esto se confirmó leyendo qué espera cada webhook. Los nodos reciben un cuerpo **mínimo**:

```json
{ "nombre": "…", "email": "…", "tipo_de_compra": "…", "phone_number": "…", "Respuesta": "…" }
```

En la práctica **el único campo obligatorio es `email`** — es la llave con la que se actualiza
el contacto en HubSpot. El resto es opcional.

Ese cuerpo **no es el payload de un webhook de Chatwoot** (que manda un objeto enorme con
`event`, `conversation`, `contact`, `messages`…). Por tanto no se recrean en
*Configuración → Integraciones → Webhooks* ni en *Reglas de automatización*: son llamadas
HTTP del **constructor de bot** (el que arma los botones de respuesta), disparadas cuando el
cliente elige una opción.

**El mapa completo** — cada opción del bot, su URL y el estado que deja en HubSpot:

| Proyecto | Cuando el cliente… | URL a llamar (POST) | `hs_lead_status` | `automatizacion` | Además |
|---|---|---|---|---|---|
| Tatiká | responde / sigue conversando | `respuesta_cliente_tatika` | Contactado | En proceso | |
| Tatiká | responde (variante) | `respuesta_cliente_tatika1` | Contactado | En proceso | |
| Tatiká | indica tipo de compra | `respuesta_cliente_tatika2` | Contactado | En proceso | guarda `tipo_de_compra` |
| Tatiká | pide **llamada** | `respuesta_cliente_tatika3` | Agendamiento Llamada | Llamar | avisa al asesor (`mensaje_lead_agente`) |
| Tatiká | pide **visita** | `respuesta_cliente_tatika4` | Agendamiento visita | Agendar Cita | avisa al asesor (`mensaje_lead_agente`) |
| Tatiká | **no le interesa** | `respuesta_cliente_tatika5` | Descartado | Finalizada | |
| Tatiká | pide llamada (cierre) | `respuesta_cliente_tatika6` | Agendamiento Llamada | Llamar | cierra al cliente (`finaliza_flujo_cliente`) |
| Tatiká | pide visita (cierre) | `respuesta_cliente_tatika7` | Agendamiento visita | Agendar Cita | cierra al cliente (`finaliza_flujo_cliente`) |
| Colina | responde | `respuesta_cliente_colina` | Contactado | En proceso | |
| Colina | pide **visita** | `respuesta_cliente_colina_viento` | Agendamiento visita | Agendar Cita | `finaliza_colina_viento` |
| Colina | pide **llamada** | `respuesta_cliente_colina_viento_llamada` | Agendamiento Llamada | Llamar | `finaliza_colina_viento` |
| Colina | **no le interesa** | `respuesta_cliente_colina_viento_no_interesa` | Descartado | Finalizada | |

Prefijo de todas: `https://flow.mcmasociados.tech/webhook/`

`conaring-lead` es aparte: **no es del bot**, es la entrada de leads del formulario web.
Nada que recrear en Solvot.

> **Mínimo viable:** si no alcanza el tiempo para recrear los 12, los que de verdad mueven la
> operación son **`tatika3`, `tatika4` y `tatika5`** (llamada, visita, no interesa). Sin esos
> tres, el asesor nunca se entera de que el lead pidió cita. Los de "Contactado / En proceso"
> son los cuatro duplicados y pueden esperar.
>
> Ojo: los 4 de Colina se recrean **sólo si el cliente levanta la exclusión**. Hoy Colina no
> envía ni se le hace seguimiento, por instrucción suya.

### C. Lo que NO hace falta pedir

- **El `account_id` de Webbo (64) y su inbox 131** son de otro cliente y de otra instancia de
  n8n. No entran en esta migración.
- **Los 8 nodos gemelos de Colina del Viento** están deshabilitados y así se quedan: por
  instrucción del cliente, Colina no envía ni se le hace seguimiento.
- **Nada de HubSpot cambia.** La integración con HubSpot es independiente del Solvot y sigue
  igual.

### D. Plantilla para responder

```
Dominio:        https://________________
account_id:     ____
inbox_id:       ____   (bandeja de Tatiká)
team_id:        ____
Número WhatsApp de la bandeja:  +57 ___ _______   (¿es el mismo 302 7560683?)
Tipo de canal de la bandeja:    [ ] API    [ ] WhatsApp Cloud
Atributos "email" y "proyecto" creados:   [ ] sí  [ ] no
Token: NO escribirlo aquí — crearlo como credencial en n8n (ver abajo)
```

### Cómo entregar el token sin exponerlo

1. En n8n → **Credentials** → **New** → **Header Auth**.
2. Nombre: `Solvot nuevo — api_access_token`.
3. *Header Name*: `api_access_token` · *Header Value*: el token del tenant nuevo.
4. Guardar y **adjuntarla al nodo `buscar contacto`** del workflow.

Con eso leo el ID de la credencial y la replico en los otros 5 nodos sin ver nunca el valor.
A partir de ahí, rotar el token es un cambio en un solo sitio en vez de 14.

---

## Paso a paso para crear el tenant nuevo

Orden por dependencias: cada paso necesita el anterior. Los nombres de menú son los de
Chatwoot; Solvot es un Chatwoot con otra marca, así que pueden estar traducidos distinto,
pero la ubicación es la misma.

### Paso 0 — Antes de tocar nada: pausar el workflow

**Recomendado.** Hoy el workflow sigue corriendo cada 15 minutos contra un Solvot muerto, y
cada ciclo marca leads nuevos como `automatizacion = Error`. Un lead en `Error` **ya no vuelve
a entrar solo**: hay que recuperarlo a mano. Van 56 en 7 días y siguen subiendo.

Pausarlo no pierde ningún lead: el poller los lee de HubSpot por filtro, así que los que
entren mientras tanto quedan esperando y se procesan al reactivar. Y como ahora mismo **no se
está contactando a nadie de todos modos**, pausar no cuesta nada y evita que la lista de
recuperación siga creciendo.

> n8n → workflow `sDZyht21H9H3w2Tl` → interruptor **Active** arriba a la derecha → apagar.
> Yo puedo hacerlo por API si prefiere; dígame y lo apago.

### Paso 1 — Tener a mano las credenciales de Meta

Antes de empezar, conseguir del Administrador de WhatsApp / Meta for Developers:

- **`phone_number_id`**: `696830786845937` (el del número `+57 302 7560683`)
- **WABA ID** (id de la cuenta de WhatsApp Business)
- Un **token de acceso permanente** con permiso `whatsapp_business_messaging`

> ⚠️ El token de Meta que se pegó en el chat hace semanas **hay que regenerarlo**. Quedó en
> el historial de la conversación. Genere uno nuevo y úselo para este paso.

**Decisión:** ¿se conserva el número `+57 302 7560683`? Si se cambia, además de esto hay que
tocar los 24 nodos de WhatsApp en n8n y volver a aprobar las 5 plantillas en Meta
(`saludo_tatika3`, `mensaje_lead_agente`, `finaliza_flujo_cliente`, `finaliza_colina_viento`).
**Conviene conservarlo.**

### Paso 2 — Crear la cuenta (el tenant)

En el Solvot nuevo, crear la cuenta de Conaring. Al entrar, la URL queda así:

```
https://EL-DOMINIO-NUEVO/app/accounts/123/dashboard
                                      ^^^
                                      este es el account_id  → ANOTARLO
```

→ **Dato 1: dominio.  Dato 2: `account_id`.**

### Paso 3 — Crear los asesores y el equipo

1. **Configuración → Agentes → Agregar agente.** Cargar a los asesores de Conaring.
   Al menos uno debe quedar con rol **Administrador** (lo necesita el Paso 6).
2. **Configuración → Equipos → Crear equipo.** Nombre a conveniencia; agregar dentro a los
   asesores.
3. Abrir el equipo recién creado y mirar la URL: `…/settings/teams/45/edit`

→ **Dato 3: `team_id`.**

Si el equipo no existe o está vacío, las conversaciones llegan **sin asignar** y nadie las ve.

### Paso 4 — Crear los atributos personalizados

**Configuración → Atributos personalizados → Atributos de contacto.** Crear dos, de tipo texto:

| Clave (exacta, en minúscula) | Para qué |
|---|---|
| `email` | correo del lead |
| `proyecto` | Tatiká / Colina del Viento / Guayacán … |

**La clave tiene que escribirse exactamente así.** Si no existen, Chatwoot acepta la petición
de n8n con `200` y **descarta los valores en silencio**: el asesor abre el chat y no ve ni el
correo ni el proyecto, sin ningún error en ningún lado.

### Paso 5 — Crear la bandeja de WhatsApp

**Configuración → Bandejas de entrada → Agregar bandeja → WhatsApp → WhatsApp Cloud.**
Cargar el `phone_number_id`, el WABA ID y el token del Paso 1.

Luego, en la misma bandeja: **Colaboradores / Equipos** → asignar el equipo del Paso 3.

Abrir la bandeja y mirar la URL: `…/settings/inboxes/789`

→ **Dato 4: `inbox_id`.**

**Y lo que más se olvida:** Chatwoot muestra una **URL de callback** y un **token de
verificación**. Hay que pegarlos en Meta:

> Meta for Developers → la app → **WhatsApp → Configuración → Webhooks → Editar** →
> pegar la URL de callback y el token → **Verificar y guardar** → suscribir el campo
> **`messages`**.

Sin esto el bot manda el primer mensaje pero **las respuestas del cliente nunca llegan al
Solvot**. Es el fallo más común de una migración así, y es silencioso.

### Paso 6 — Crear el token de API

Opción simple: **Perfil (abajo a la izquierda) → Configuración del perfil → Token de acceso**,
del usuario **administrador** del Paso 3.

> Un token de **agente** no sirve: no puede crear contactos ni cambiar el estado de
> conversaciones ajenas. Tiene que ser de administrador.

En el Solvot viejo había dos tokens (uno para leer, otro para escribir). **Con uno de
administrador alcanza.**

**No me lo mande por chat.** En n8n:

1. **Credentials → New → Header Auth**
2. Nombre: `Solvot nuevo — api_access_token`
3. *Header Name*: `api_access_token` · *Header Value*: el token
4. Guardar, y **adjuntarla al nodo `buscar contacto`** del workflow `sDZyht21H9H3w2Tl`

Así yo leo sólo el ID de la credencial y la replico en los otros 5 nodos sin ver el valor.

### Paso 7 — Recrear los flujos del bot

En el constructor de bot del Solvot nuevo, rearmar el flujo de Tatiká. Cada botón que el
cliente pueda tocar hace un **POST** a su URL con el cuerpo:

```json
{ "email": "{{ email del contacto }}" }
```

El `email` sale del atributo personalizado del Paso 4. La tabla completa de qué URL va en
cada botón está en la sección **B-bis** de este documento.

Si el tiempo aprieta, los tres que de verdad importan son **`tatika3`** (llamada),
**`tatika4`** (visita) y **`tatika5`** (no interesa). Sin esos, el asesor nunca se entera de
que el lead pidió cita.

### Paso 8 — Pasarme los datos

```
Dominio:        https://________________
account_id:     ____
inbox_id:       ____   (bandeja de Tatiká)
team_id:        ____
Número de la bandeja:  +57 ___ _______    (¿es el mismo 302 7560683?)
Tipo de canal:  [ ] WhatsApp Cloud   [ ] API
Atributos "email" y "proyecto" creados:   [ ] sí  [ ] no
Webhook de Meta repuntado al Solvot nuevo: [ ] sí  [ ] no
Credencial Header Auth creada en n8n y pegada en "buscar contacto": [ ] sí
```

### Paso 9 — Yo repunto n8n

Con eso cambio los 6 nodos vivos (y los 8 gemelos de Colina, por consistencia): dominio,
`account_id`, `inbox_id`, `team_id`, y la credencial en vez del token a mano. Son unos
minutos.

Quedará pendiente una sola cosa de la sección B: si la bandeja es **canal WhatsApp** en vez de
canal API, hay que quitar el `message.content` del body de `crear conversacion`, porque si no
Chatwoot intenta entregar ese texto y sale duplicado o da error fuera de la ventana de 24 h.
Por eso el checklist pregunta el tipo de canal.

### Paso 10 — Probar con UN lead antes de soltar

Crear un contacto de prueba en HubSpot con `fuente = FACEBOOK ADS`, `proyecto = Tatiká`,
teléfono real suyo, y reactivar el workflow. Verificar la cadena completa:

1. Llega el WhatsApp al teléfono
2. Aparece el contacto y la conversación en el Solvot nuevo, **con el proyecto y el correo**
3. La conversación queda en **Pendiente** (esto es lo que arreglamos hoy)
4. Al responder desde el teléfono, la respuesta **llega al Solvot** (valida el Paso 5)
5. Al tocar "agendar visita", el contacto en HubSpot pasa a `Agendamiento visita` / `Agendar Cita`

Si los 5 pasan, está migrado.

### Paso 11 — Recuperar los leads represados

Sólo después de que el Paso 10 pase. Son los **56 en `automatizacion = Error`** más los que se
acumulen durante la migración. Hay que tocarlos para que vuelvan a entrar al flujo.

**Por tandas de 30–40 al día, no todos de golpe.** Son plantillas MARKETING: 56 envíos en un
ciclo es justo lo que dispara el `131049` de Meta y se pierden igual. Eso lo hago yo cuando
dé la orden.

---

## Plan de corte

1. Crear la credencial Header Auth en n8n con el token del Solvot nuevo.
2. Reapuntar los 6 nodos vivos (y los 8 gemelos de Colina, por consistencia): dominio,
   `account_id`, `inbox_id`, `team_id`, y la credencial en lugar del header a mano.
3. ~~Corregir B1 y B2.~~ ✅ hecho el 14-nov, ya está en producción.
4. Probar con un contacto de prueba antes de dar por buena la migración.
5. Recuperar los 56 leads en `Error`: tocarlos para que vuelvan a entrar, **por tandas** —
   de golpe serían 56 plantillas MARKETING en un ciclo, con el riesgo de `131049` de Meta.
