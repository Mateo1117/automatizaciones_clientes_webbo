# Validación y corrección — creación de contactos en HubSpot

Instancia `flow.mcmasociados.tech` · Workflow producción `m9mqIWluJay9qOWs` (activo, 180 nodos)
Workflow corregido `sDZyht21H9H3w2Tl` — **"Flow Tatika, Colina del Viento - Conaring [v2 CORREGIDO]"**, 204 nodos, **inactivo**.

Esta vez sí hubo acceso a la API de n8n (el dominio ya está permitido y las variables
`N8N_BASE_URL` / `N8N_API_KEY` están cargadas), así que la revisión se hizo contra la
instancia real, con ejecuciones reales y con una prueba end-to-end.

---

## Requisitos pedidos y cómo quedaron

| # | Requisito | Antes | Ahora |
|---|---|---|---|
| 1 | Crear los contactos correctamente | Parcial: proyecto siempre `Tatika`, JSON se rompía con comillas | ✅ |
| 2 | Sin duplicados | Correcto por email, pero pisaba datos existentes | ✅ |
| 3 | Repetido → doble conversión | ❌ no existía en el workflow | ✅ |
| 4 | Registrar en notas qué pasó, en cada paso | ❌ no existía en el workflow | ✅ |

Adicionalmente se desbloqueó el envío de WhatsApp, que estaba caído en los 24 nodos por un
token sin permisos (ver más abajo). Verificado con un envío real.

---

## Cómo se conecta a HubSpot

No hace falta abrir `api.hubapi.com` en la política de red del entorno (hoy está bloqueado:
`CONNECT api.hubapi.com:443 → 403`). n8n ya tiene la credencial **`HubSpot App Token account`**
(`haT6Hrg5ZUq5fRt7`, usada en 36 nodos) y el servidor de n8n sí alcanza HubSpot.

Para consultar HubSpot desde fuera se crea un workflow auxiliar que use esa credencial, se
activa, se llama por webhook y se borra al terminar. Así se leyeron las 483 propiedades del
contacto y se verificó el resultado de la prueba.

Si aun así se quiere conexión directa: agregar `api.hubapi.com` a *Allowed domains* del
entorno (`Network access: Custom`, dejando marcado *"Also include default list of common
package managers"*) y un `HUBSPOT_TOKEN` de Private App con scopes
`crm.objects.contacts.read/write`, `crm.schemas.contacts.read`, `crm.objects.notes.write`.
Aplica sólo a **sesiones nuevas**.

---

## Hallazgo que resolvió el requisito 3

La propiedad `hs_lead_status` **ya tiene definido el valor `"Doble conversión"`** en la cuenta
de HubSpot — con tilde. Es el valor interno, no sólo la etiqueta:

```
hs_lead_status: Pendiente · Intentar de Nuevo 2 · Contactado · ilocalizable · Intento 1 ·
                Doble conversión · Nuevo lead · Agendamiento visita · Contacto Humano ·
                Descartado · Sin Numero de Telefono · Error · Agendamiento Llamada ·
                Apertura de correo reciente
```

No había que crear nada: el workflow simplemente nunca lo usaba.

## Hallazgo sobre las "notas"

**No existe una propiedad de contacto llamada `notas`** en las 483 propiedades de la cuenta.
Lo que existe es `num_notes`, `notes_last_updated`, etc., todas **de sólo lectura** (las
calcula HubSpot). La única propiedad de texto libre editable es `message`, que la llenan los
formularios de Facebook Lead Ads.

La "casilla notas" que se ve en la ficha del contacto es el objeto **Note** de HubSpot. Por eso
se implementó así: cada evento crea una nota nueva vía
`POST /crm/v3/objects/notes` asociada al contacto (`associationTypeId: 202`). Queda el
historial completo con fecha, que es lo que pedía el *"y así sucesivamente"*.

> Si en vez de esto se prefiere una propiedad custom `notas` de texto largo con todo
> concatenado, hay que crearla en HubSpot y se cambia el destino de la escritura.

---

## Rama de ingesta corregida

Entrada: `POST /webhook/conaring-lead` (nodo `Webhook Chatwoot`).

```
Webhook Chatwoot
  → Normalizar Datos3            (proyecto real, email validado, teléfono +57)
  → ¿Tiene email valido?
       ├─ no  → Respuesta Sin Email3
       └─ sí  → HubSpot Upsert Contact3      POST /crm/v3/objects/contacts/batch/upsert
                → ¿Upsert exitoso?2
                     ├─ no → Respuesta Error3
                     └─ sí → Decidir Accion (nuevo / doble conversion)
                             → Aplicar Cambios Contacto     PATCH /contacts/{id}
                             → Registrar Nota HubSpot       POST /notes
                             → Respuesta OK3
```

### Por qué no hay duplicados

El `batch/upsert` con `idProperty: "email"` resuelve el duplicado **del lado de HubSpot, de
forma atómica**. No hay ventana de carrera: si dos webhooks entran a la vez con el mismo
email, HubSpot devuelve el mismo `id` a ambos. Un `search` previo seguido de un `create`
sí tendría esa ventana (el índice de búsqueda de HubSpot tarda ~200 ms en actualizarse).

### Por qué el upsert manda sólo el email

```js
{ inputs: [ { idProperty: 'email', id: $json.email, properties: { email: $json.email } } ] }
```

Antes el upsert mandaba nombre, teléfono, `proyecto`, `lifecyclestage` y
`hs_lead_status: "Nuevo lead"` en **todas** las llamadas. Con un contacto que ya existía eso
significaba pisarle el estado que el asesor había dejado (`Contactado`, `Agendamiento visita`…)
y devolverlo a `Nuevo lead`. Ahora el upsert sólo resuelve la identidad, y el `PATCH`
posterior escribe según el caso:

| Caso | Propiedades que se escriben |
|---|---|
| Contacto **nuevo** | `firstname`, `lastname`, `phone`, `mobilephone`, `proyecto`, `fuente`, `punto_de_contacto`, `lifecyclestage=lead`, `hs_lead_status=Nuevo lead`, `automatizacion=Iniciada` |
| Contacto **existente** | sólo `hs_lead_status = "Doble conversión"` |

En el caso existente **no se sobrescribe ningún dato** que el equipo comercial haya trabajado.
El proyecto y la fuente de la nueva entrada quedan registrados en la nota.

> Supuesto aplicado. Si se prefiere que un lead repetido también refresque `proyecto` y
> `fuente`, o que rellene teléfono/nombre cuando estaban vacíos, es un cambio de dos líneas
> en el nodo `Decidir Accion`.

### Detección de "ya existía"

Se usa `results[0].new` de la respuesta del upsert, con respaldo por si HubSpot no lo envía:

```js
let esNuevo = res.new;
if (typeof esNuevo !== 'boolean') {
  esNuevo = !!(res.createdAt && res.updatedAt && res.createdAt === res.updatedAt);
}
```

---

## Prueba end-to-end ejecutada

Workflow de prueba aislado (webhook propio, misma lógica), tres llamadas reales contra la
cuenta de HubSpot de producción:

| Llamada | Payload | Respuesta |
|---|---|---|
| 1 | `name: 'Juan "Pipe" O'Brien Ñáñez'`, `proyecto: "colina del viento"` | `accion: "creado"`, id `239733337516` |
| 2 | mismo email, `proyecto: "Tatika"` | `accion: "doble_conversion"`, **mismo id** |
| 3 | sin email | rechazado, no llega a HubSpot |

Estado del contacto en HubSpot al terminar:

```
firstname       = 'Juan'
lastname        = '"Pipe" O\'Brien Ñáñez'     <- comillas y apóstrofo intactos
phone           = '+573124524776'             <- normalizado a +57
proyecto        = 'Colina Del Viento'         <- mapeado desde "colina del viento"
fuente          = 'WEB CONARING'
hs_lead_status  = 'Doble conversión'
automatizacion  = 'Iniciada'
```

Notas creadas en la ficha (2):

```
Contacto creado por la automatización | Proyecto: Colina Del Viento | Fuente: WEB CONARING |
Punto de contacto: WHATSAPP | Teléfono: +573124524776 | Estado inicial: Nuevo lead |
Fecha: 2026-08-03 22:48

Doble conversión | El contacto volvió a registrarse por el formulario web. |
Proyecto de esta entrada: Tatika | Fuente: WEB CONARING | Estado cambiado a: Doble conversión |
No se sobrescribieron los datos existentes del contacto. | Fecha: 2026-08-03 22:48
```

Al terminar se archivó el contacto de prueba (HTTP 204) y se borraron los tres workflows
auxiliares. La instancia quedó sin residuos.

---

## Fallas de producción encontradas en las ejecuciones reales

De las últimas 50 ejecuciones, **20 con error**. Las causas confirmadas:

### 1. HubSpot está devolviendo 429 (rate limit) — es lo que más rompe hoy

```
🔍 Buscar Últimos Contactos… : "You have reached your secondly limit."
HubSpot - Obtener Detalles   : "You have reached your ten_secondly_rolling limit."
```

Origen: el `Schedule Trigger` corría **cada 1 minuto** y el search no tenía filtro
incremental, así que traía los mismos 100 contactos y hacía ~100 llamadas de detalle por
minuto. Corregido: trigger a **15 minutos** y filtro `lastmodifieddate >= ahora - 20 min`.

### 2. El poller nunca buscaba Colina del Viento

El filtro decía `"values": ["Tatika"]` aunque el nodo se llama *"Tatika y Colina del Viento"*.
Toda la rama de Colina del Viento del flujo automático estaba muerta. Corregido a
`["Tatika", "Colina Del Viento"]`.

### 3. WhatsApp: al token de n8n le faltan permisos (no es el número)

```
WhatsApp Business Cloud12: Object with ID '696830786845937' does not exist,
cannot be loaded due to missing permissions, or does not support this operation.
```

El número **está bien**: `+57 302 7560683` (ConaringTatiká) aparece *Conectado* con calidad
*Alta* en el Administrador de WhatsApp. El problema es el token de la credencial
`WhatsApp conaring` (`n9u0q4bVTSFGubcI`). Consultando la Graph API a través de n8n:

```
GET /v21.0/me/permissions
{ "data": [ { "permission": "public_profile", "status": "granted" } ] }
```

Una sola permission. Faltan las dos que exige WhatsApp Cloud API:

| Permiso | Para qué | Estado |
|---|---|---|
| `whatsapp_business_messaging` | enviar mensajes | ausente |
| `whatsapp_business_management` | leer números y plantillas | ausente |

Lo demás que se comprobó con ese mismo token:

| Consulta | Resultado |
|---|---|
| `GET /me` | `122186025470899698` — "APP SOLVOT CONARING" |
| `GET /2034375463493184` (negocio) | OK — "Conaring" |
| `GET /1503335814370202` (WABA) | `GraphMethodException 100/33` — no la ve |
| `GET /1503335814370202/phone_numbers` | `#200 You do not have permission` |
| `GET /2034375463493184/owned_whatsapp_business_accounts` | `#200 Requires business_management` |

El token quedó asociado al negocio pero **la cuenta de WhatsApp nunca se le asignó como
activo**. El objeto `696830786845937` existe; el token no puede verlo.

**Resuelto.** El cliente generó un token con permisos y se validó contra la Graph API:

```
GET /v21.0/me/permissions
whatsapp_business_messaging      granted
whatsapp_business_management     granted
whatsapp_business_manage_events  granted
leads_retrieval, ads_management, pages_messaging, read_insights, ...
```

Con ese token la cuenta y el número sí son visibles:

| Consulta | Resultado |
|---|---|
| `GET /1503335814370202` | `ConaringTatiká` |
| `GET /1503335814370202/phone_numbers` | `696830786845937` — `+57 302 7560683`, calidad `GREEN`, `CLOUD_API` |
| `GET /696830786845937` | mismo número, `verified_name: ConaringTatiká` |

**El `phoneNumberId` de los 24 nodos (`696830786845937`) siempre fue el correcto.** El único
problema era el token: el anterior sólo tenía `public_profile`. No hubo que tocar ningún nodo.

Se creó la credencial **`WhatsApp Conaring (token con permisos)`** (`LbUtavO3Z1MlRmsM`,
`businessAccountId = 1503335814370202`) y los 24 nodos WhatsApp de la v2 se reapuntaron a
ella. La credencial vieja `WhatsApp conaring` (`n9u0q4bVTSFGubcI`) sigue existiendo y la usa
el workflow de producción; conviene borrarla una vez migrado.

#### Envío real verificado

Se envió la plantilla `hello_world` a `+57 310 244 8187` usando el **nodo real
`n8n-nodes-base.whatsApp` v1** con la credencial nueva, es decir la misma combinación que
usan los 24 nodos del workflow:

```json
{
  "messaging_product": "whatsapp",
  "contacts": [{ "input": "573102448187", "wa_id": "573102448187" }],
  "messages": [{ "id": "wamid.HBgMNTczMTAyNDQ4MTg3…", "message_status": "accepted" }]
}
```

Queda validada la cadena completa: credencial → `phoneNumberId 696830786845937` → envío de
plantilla. El mensaje llegó al destinatario.

#### Pendientes de WhatsApp

1. **El token es de usuario, no de usuario del sistema.** Los tokens `EAA...` de usuario
   caducan (60 días los de larga duración) y se invalidan si la persona cambia la contraseña
   o revoca la sesión. Cuando eso pase, los 24 nodos vuelven a fallar igual que hoy.
   Reemplazarlo por uno de **usuario del sistema** (Configuración del negocio → Usuarios del
   sistema → asignar la WABA como activo → generar token): esos no caducan.
2. **El token circuló por un chat.** Hay que regenerarlo por higiene.
3. **`code_verification_status: EXPIRED`** en el número. No bloquea el envío por Cloud API,
   pero conviene revalidarlo desde el Administrador de WhatsApp.
4. **Plantilla `seguimiento_conversacion` (en) está en `PENDING`**, y hay un nodo que la usa.
   Ese envío va a fallar hasta que Meta la apruebe. De las 20 plantillas de la cuenta, 18
   están `APPROVED`; las otras dos en `PENDING` son `seguimiento_conversacion` (en) y
   `bienvenida_tatika` (es_CO) — esta última no la usa ningún nodo.

### 4. Paths de webhook con espacios → 404

| Nodo | Antes | Ahora |
|---|---|---|
| `Webhook10` | `" respuesta_cliente_colina_viento_no_interesa"` (espacio inicial) | sin espacio |
| `Webhook11` | `"respuesta_cliente_colina 2"` | `respuesta_cliente_colina_2` |

El espacio inicial de `Webhook10` dejaba el botón "no me interesa" de Colina del Viento
inalcanzable.

### 5. Espacio dentro de la URL de Chatwoot

`.../contacts/ {{ id }}` → `.../contacts/ 12345`. Corregido en `Actualizar contacto` y
`Actualizar contacto2`.

### 6. Zona horaria

El workflow no fijaba `timezone`, así que los cron corrían en UTC: el *"Trigger diario 2PM
seguimiento"* disparaba a las **8:00 a.m.** hora Colombia. Se fijó `America/Bogota`.

### 7. Sin reintentos

Se puso `retryOnFail` (3 intentos, 3 s) en los 25 nodos HubSpot y en el search. Antes un
solo 429 tumbaba la ejecución completa y se perdían los items restantes del lote.

---

## Notas en cada cambio de estado

Se agregaron **21 nodos de nota**, uno colgado en paralelo de cada
`Crear y Actualizar Contacto*`. Van en rama paralela (no en serie) para que no alteren el
`$json` de la cadena original, y llevan `onError: continueRegularOutput`: **una nota que
falle nunca puede tumbar la automatización**.

Texto según el evento:

| Estado | Nota |
|---|---|
| `Iniciada` | Se envió el primer mensaje de WhatsApp al cliente |
| `En proceso` / `Seguimiento` | El cliente respondió. Pasa a seguimiento comercial |
| `Llamar` / `Seguimiento Tibio` | El cliente pidió que un asesor lo llame |
| `Agendar Cita` / `Seguimiento Tibio` | El cliente pidió agendar visita al apartamento modelo |
| `Finalizada` / `Descalificado` | El cliente respondió que no está interesado |
| `Finalizo sin Exito` / `Descalificado` | La automatización terminó sin respuesta |
| `Finalizo sin Exito` / `ilocalizable` | No se logró contactar al cliente |
| `Error` | La automatización falló. Requiere revisión manual |

---

## Lo que falta y no se tocó

Está en `docs/revision-flow-tatika-colina-conaring.md` con más detalle. Lo pendiente:

- **Token de WhatsApp**: ya funciona, pero es de usuario y caduca. Cambiarlo por uno de
  usuario del sistema antes de que expire (punto 3 arriba).
- **Plantilla `seguimiento_conversacion` (en) en PENDING** — un nodo la usa y va a fallar.
- **Tokens de Chatwoot hardcodeados en 14 nodos**, en claro dentro del workflow. Hay dos
  tokens distintos contra la misma cuenta. Deberían pasar a una credencial *Header Auth* y
  **rotarse**, porque ya circularon en exports.
- **`HubSpot Trigger` sin evento configurado** (`eventValues: [{}]`) — no está suscrito a
  nada.
- **`Switch3` / `Switch`** con `typeValidation: strict` comparando contra `"[object Object]"`.
- **Rama Chatwoot huérfana** (`Es conversation_created?` y sus 9 nodos) sin conexión de
  entrada, duplicada con la que sí funciona.
- **Etiqueta invertida** en `Switch3`: la salida "SIN CONTACTO" es la que matchea
  `hs_lead_status == "Contactado"`. Hay que confirmarlo con el equipo comercial.
- `settings.callerPolicy` se perdió al crear la v2 (la API pública de n8n no lo acepta).
  Volver a ponerlo en *Settings → Caller policy* desde la UI.

---

## Cómo pasar la v2 a producción

1. Abrir **`Flow Tatika, Colina del Viento - Conaring [v2 CORREGIDO]`** en n8n y revisarla.
2. Reponer `callerPolicy = workflowsFromSameOwner` en Settings.
3. **Desactivar** el workflow de producción `m9mqIWluJay9qOWs`. Los dos no pueden estar
   activos a la vez: comparten los paths de webhook y n8n rechaza el conflicto.
4. Activar la v2.
5. Mirar las primeras ejecuciones en *Executions*. Debe desaparecer el patrón de una
   ejecución por minuto y bajar el ruido de 429.

El workflow de producción no se modificó. Sigue activo y sirve de rollback: si algo sale
mal, se desactiva la v2 y se reactiva el original.

### Reproducir la construcción

```bash
# exportar el workflow actual
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "$N8N_BASE_URL/api/v1/workflows/m9mqIWluJay9qOWs" > wf.json

# generar la versión corregida
python3 build/construir_v2.py wf.json wf-v2.json

# crear el workflow nuevo (inactivo)
curl -s -X POST -H "X-N8N-API-KEY: $N8N_API_KEY" \
  -H "Content-Type: application/json" --data @wf-v2.json \
  "$N8N_BASE_URL/api/v1/workflows"
```


---

## Segunda ronda — errores con la v2 ya activa

La v2 se activó y producción (`m9mqIWluJay9qOWs`) quedó desactivada. Con la v2 corriendo
aparecieron 11 ejecuciones con error. Causas, todas distintas:

### Validación sistemática de las 24 plantillas

Se comparó, nodo por nodo, la plantilla configurada contra su definición real en Meta
(nombre, idioma, estado y número de variables `{{n}}` en el BODY). **22 de 24 correctos.**
Los dos que fallaban:

| Nodo | Plantilla | Params enviados | Esperados | Estado |
|---|---|---|---|---|
| `WhatsApp Business Cloud21` | `seguimiento_4_colina_del_viento` (es_CO) | 0 | **1** | APPROVED |
| `WhatsApp Business Cloud3` | `seguimiento_conversacion` (en) | 0 | 0 | **PENDING** |

**Cloud21 — corregido.** El body de la plantilla empieza con `Hola *{{1}}* 😉…` pero el nodo
tenía `components: null`. Meta respondía *"Number of parameters does not match the expected
number of params"*. Se le puso `{{ $json.nombre }}`, igual que sus plantillas hermanas
`seguimiento_1` y `seguimiento_2`. Verificado que `Separar Citas16` sí entrega `nombre`.

**Cloud3 — no se puede corregir desde n8n.** La plantilla `seguimiento_conversacion` (en)
sigue en `PENDING` en Meta, y por eso devuelve
`(#132001) Template name does not exist in the translation`. Hay que esperar la aprobación,
o apuntar el nodo a una plantilla equivalente ya aprobada.

### Email vacío tumbaba la ejecución completa — corregido

Tres ejecuciones murieron en `Crear y Actualizar Contacto4/7/14` con `404 - ""`. El webhook
llegó así:

```json
{ "hs_lead_status": "Contactado", "email": "", "phone_number": "+573157437402" }
```

Con `email` vacío, el nodo HubSpot v1 arma la URL
`/contacts/v1/contact/createOrUpdate/email//` y HubSpot devuelve 404. Como esos nodos no
tenían manejo de error, **abortaban la ejecución entera y el cliente nunca recibía su
respuesta de WhatsApp**.

Sin email no hay forma de identificar el contacto, así que lo correcto es saltarse la
actualización y dejar que el resto del flujo siga. Se puso
`onError: continueRegularOutput` en los 21 nodos `Crear y Actualizar Contacto*`.

> Esto trata el síntoma. La causa está aguas arriba: quien llama a
> `respuesta_cliente_tatika` está mandando `email` vacío. Vale la pena revisar por qué.

---

## Los errores del Chatwoot de Webbo NO son de este workflow

Se buscó en los **20 workflows** de la instancia y **ninguno contiene el texto de esos
mensajes** ni la palabra "Webbo". Salen de Chatwoot directamente (envío manual o campaña),
sobre una cuenta de WhatsApp distinta a `ConaringTatiká`. Los tres errores vistos:

| Error | Qué significa | Solución |
|---|---|---|
| `Template not found or invalid template name` | El nombre o el **idioma** de la plantilla no coincide con ninguna aprobada en esa WABA. Casi siempre es el idioma: la plantilla existe en `es_CO` y se envía como `es`. | Verificar nombre + idioma exactos en el Administrador de WhatsApp de **esa** cuenta |
| `131049: This message was not delivered to maintain healthy ecosystem engagement` | Meta **descartó** el mensaje a propósito. Es el límite por-usuario de plantillas **MARKETING**: se aplica cuando el destinatario ya recibió demasiadas, no interactúa, o la calidad del número bajó. No es un fallo técnico. | Bajar volumen de marketing, usar categoría `UTILITY` donde corresponda, y priorizar contactos que ya respondieron |
| *"Sólo puede responder usando una plantilla — ventana de 24 horas"* | Fuera de las 24 h desde el último mensaje del cliente sólo se pueden enviar plantillas aprobadas, no texto libre. | Es el comportamiento normal de la API |

El `131049` no tiene arreglo por código: es un control antispam de Meta. La vía sostenible es
que el contacto haya dado opt-in y responda —eso abre la ventana de 24 h y habilita texto
libre—, además de cuidar la calificación de calidad del número.


---

## Tercera ronda — "inicia pero no sale el mensaje"

Se analizaron 12 ejecuciones consecutivas del `Schedule Trigger` con datos completos.
**Cero items llegaron a enviar un WhatsApp.** 10 de 12 terminaron en
`No Operation, do nothing2`.

### Recorrido real de una ejecución

```
Schedule Trigger → Buscar Contactos (1) → extraer leads (3 leads)
  → Loop Over Items → Procesar Item Individual → HubSpot Obtener Detalles
  → Procesar Info Detallada → 3. Format Lead Data1
  → Switch2  (rutea por proyecto)
       ├ salida 0 "Colina Del Viento" → Loop Over Items   ← DESCARTADO
       └ salida 1 "Tatiká"            → Switch
                                          ├ salida 1 "SIN CONTACTO"  → Loop  ← descartado
                                          └ salida 4 "Aut Iniciada"  → NoOp  ← descartado
```

De 3 leads: 1 de Colina descartado, 1 ya `Contactado`, 1 ya `Iniciada`. Ninguno enviado.

### Causa raíz: `Switch3` está huérfano

`Switch3` es el **espejo exacto** de `Switch` pero para Colina del Viento — mismas 5 salidas
(`SIN NUMERO`, `SIN CONTACTO`, `NO INICIADA`, `NO INICIADA 2`, `Aut Iniciada`) — y su rama
`NO INICIADA` lleva a la cadena de envío de Colina:

```
Switch3 → Contact Exists? → HubSpot Obtener Detalles2 → Procesar Info Detallada3
        → Crear Mensaje4 → Verificar Teléfono4 → ¿Teléfono Válido?4
        → buscar contacto2 → crear contacto2 → crear conversacion2
        → Send template (bienvenida_colina_del_viento)
        → Wait2 → Crear y Actualizar Contacto12 (marca automatizacion = Iniciada)
```

Esa cadena está **completa y correcta**, incluido el marcado de `Iniciada` que evita
reenvíos. Lo único que falta es la **conexión de entrada**: `Switch2` salida 0
("Colina Del Viento") apunta hoy a `Loop Over Items` en vez de a `Switch3`.

La posición de los nodos confirma la intención: `Switch2` en `[-6304,-4704]`,
`Switch` (Tatiká) en `[-5968,-4704]` y `Switch3` en `[-5824,-4048]`, justo debajo.

**La corrección es una sola conexión: `Switch2` salida 0 → `Switch3`.**

### ⚠️ Por qué NO se aplicó todavía

Conectarla despierta una rama dormida sobre una base de datos grande. Conteo real en HubSpot:

| Segmento | Contactos |
|---|---|
| Colina Del Viento, total | 3.314 |
| Colina Del Viento **sin `automatizacion`** (entrarían al envío) | **2.960** |
| Colina Del Viento ya en `Iniciada` | 105 |
| Tatika sin `automatizacion` | 1.070 |
| Tatika ya en `Iniciada` | 5 |

Al conectarla, en el siguiente ciclo de 15 minutos entrarían **2.960 contactos** a recibir
`bienvenida_colina_del_viento`. Aunque el `Loop Over Items` los procesa por lotes, es un
envío masivo de plantillas MARKETING a una base fría — exactamente el patrón que dispara el
error `131049` de Meta y que degrada la calificación de calidad del número.

**Decisión: no se conecta sin aprobación explícita del cliente.** Antes conviene:

1. Confirmar que los 2.960 tienen opt-in y que se les quiere escribir.
2. Definir un ritmo (por ejemplo filtrar por `createdate` de los últimos N días, o subir el
   intervalo del `Schedule Trigger`) para no mandar todo de una vez.
3. Recién entonces conectar `Switch2` salida 0 → `Switch3`.

### Sobre "inicia pero no sale el mensaje"

En ambas ramas el marcado `automatizacion = Iniciada` ocurre **después** del envío
(`WhatsApp → Wait → Crear y Actualizar Contacto8` en Tatiká, `Send template → Wait2 →
Crear y Actualizar Contacto12` en Colina). Ese orden es el correcto: si el envío falla, el
contacto no queda marcado y se reintenta en el siguiente ciclo.

Por lo tanto, un contacto en `Iniciada` **sí tuvo un envío aceptado por Meta**. Si aun así el
cliente no recibió nada, la pérdida ocurre después de la API y las causas son las de la
sección de Chatwoot: `131049` (Meta descarta el mensaje), plantilla no aprobada, o ventana de
24 h. Los 105 contactos de Colina en `Iniciada` no pueden venir de esta rama —está
desconectada—, así que vienen de los webhooks o de la versión anterior del flujo.

---

## Instancia n8n distinta: "WEBBO - Bot completo CORREGIDO"

Ese workflow **no está** en `flow.mcmasociados.tech`. Se listaron los 20 workflows de la
instancia y no aparece ninguno con ese nombre. Vive en otra n8n (por la interfaz, n8n Cloud).
Para revisarlo hace falta su URL y una API key propia.


---

## Cuarta ronda — Colina del Viento fuera de los recordatorios

Instrucción del cliente: **los recordatorios y seguimientos no deben incluir Colina del
Viento.** Eso invalida la lectura hecha en la tercera ronda (se interpretó que la rama de
Colina estaba "muerta por error"); en realidad **no debe existir**.

### Por dónde entraba Colina a los recordatorios

Tres crons de seguimiento, cada uno con su buscador y su Switch por proyecto:

| Trigger | Hora (UTC) | Buscador | Switch |
|---|---|---|---|
| `Trigger diario 2PM seguimiento` | 13 | `🔍 Buscar Leads con Automatización1` | `Switch5` |
| `Trigger diario 10AM Mañana2` | 15 | `🔍 Buscar Leads con Automatización` | `Switch4` |
| `Trigger diario 10AM Mañana3` | 16 | `🔍 Buscar Leads con Automatización2` | `Switch6` |

Los tres buscadores tenían **dos `filterGroups`**, y en la API de HubSpot los grupos se
combinan con **OR**, no con AND:

```json
"filterGroups": [
  { "filters": [{ "propertyName": "automatizacion", "operator": "IN",
                  "values": ["Iniciada", "En proceso"] }] },
  { "filters": [{ "propertyName": "proyecto", "operator": "CONTAINS_TOKEN", "value": "Tatika" },
                { "propertyName": "proyecto", "operator": "CONTAINS_TOKEN", "value": "Colina Del Viento" }] }
]
```

O sea *(automatizacion Iniciada/En proceso)* **OR** *(proyecto …)*. El primer grupo por sí
solo trae leads de **cualquier proyecto**, así que Colina entraba por ahí incluso sin
mencionarlo. Y la salida 0 de cada Switch (`"Colina Del Viento"`) estaba conectada y enviaba:

- `Switch5` → `IF8` → `Cloud16` (`seguimiento_1_colina_del_viento`) / `Cloud23` (`continuar_flujo_colina`)
- `Switch4` → `IF10` → `Cloud17` (`seguimiento_2_colina_del_viento`) / `Cloud22` (`continuar_flujo_colina`)
- `Switch6` → `IF12` → `Cloud21` (`seguimiento_4_…`), `Cloud18` (`seguimiento_3_…`),
  `Cloud19` (`continuar_flujo_colina`), `Cloud20` (texto de cierre), y además escrituras en
  HubSpot: `Crear y Actualizar Contacto19` / `20` (`automatizacion = Finalizo sin Exito`,
  `gesti_n_comercial = Descalificado`) y `📝 Cambiar proyecto5` / `6`
  (`motivos_descalificaci_n`).

### Corregido

1. Los **tres buscadores** pasan a un **único `filterGroup`** (AND real) con
   `proyecto EQ "Tatika"`. Ya no traen Colina ni ningún otro proyecto.
2. Se **desconecta la salida 0 ("Colina Del Viento")** de `Switch4`, `Switch5` y `Switch6`.
   Doble seguro: aunque un lead se colara, no tiene a dónde ir.
3. Se **revierte** el cambio hecho el 18 de agosto en el poller de 15 min
   (`🔍 Buscar Últimos Contactos…1`): vuelve a `"values": ["Tatika"]`.

Verificado en vivo sobre `sDZyht21H9H3w2Tl`: ninguno de los cuatro buscadores contiene ya la
cadena "Colina", y las tres salidas 0 quedaron vacías.

> Las ramas de Colina siguen existiendo como nodos, sólo sin entrada. Reconectarlas es
> arrastrar una conexión si algún día se quiere reactivar.

### Auditoría: qué se le tocó a Colina del Viento

Consultado en HubSpot con `proyecto EQ "Colina Del Viento"`:

| Consulta | Contactos |
|---|---|
| `lastmodifieddate >= 2026-08-18` | **1.914** |
| …de esos, con `automatizacion` con valor | **242** |

Los 1.914 incluyen cualquier modificación (asesores, importaciones, otras integraciones), así
que no son atribuibles a la automatización. Los **242** con `automatizacion` poblada son los
que sí pasaron por un flujo:

| `automatizacion` | Contactos |
|---|---|
| Finalizo sin Exito | 92 |
| Iniciada | 56 |
| Finalizada | 46 |
| Agendar Cita | 27 |
| Llamar | 15 |
| Error | 6 |

Última modificación por día (hora Colombia):

```
2026-08-18:   1     2026-08-29: 172   <- concentración
2026-08-19:  13     2026-08-30:   5
2026-08-20:   4     2026-08-31:  10
2026-08-24:   1     2026-09-01:  24
2026-08-25:   1     2026-09-02:   7
2026-08-27:   1     2026-09-03:   2
2026-08-28:   1
```

`motivos_descalificaci_n` de los 242: 164 `DESINTERES O EQUIVOCADO`, 15 `UBICACIÓN`,
12 `PRECIO`, 7 `INVIRTIO OTRO PROYECTO`, 5 `NO SE LOGRO CONTACTO`, 1 `PLAZO`,
1 `SIN PRESUPUESTO`, 37 vacío. `DESINTERES O EQUIVOCADO` y `NO SE LOGRO CONTACTO` son los dos
únicos valores que escriben los nodos `📝 Cambiar proyecto3/4/5/6`; los demás (UBICACIÓN,
PRECIO, PLAZO…) no los escribe ningún nodo, así que son de captura manual.

**Lo que no se pudo determinar:** el historial de ejecuciones de n8n sólo llega al
**1 de septiembre** (la instancia purga las anteriores), así que **no hay evidencia directa
de qué disparó la concentración de 172 contactos del 29 de agosto**. Los flujos tenían la
capacidad de hacerlo, pero afirmarlo sin el log sería especular.

El listado completo de los 242 se entregó como CSV al cliente. **No se versiona** porque
lleva correos y teléfonos; `.gitignore` bloquea `leads-*.csv`.

### Nota sobre el JSON que el cliente estaba editando

El body que se estaba pegando a mano en `🔍 Buscar Leads con Automatización1` tenía además un
**error de sintaxis**: una llave `}` duplicada tras el filtro de `proyecto`, que es lo que
producía *"JSON parameter needs to be valid JSON"*. Y varias propiedades del array
`properties` no existen en la cuenta: `numero_de_telefono`, `numero_de_movil`, `vid`,
`estado_del_lead`, `presupuesto`, `tipo_inversion`, `utm_campaign`, `utm_source`, y
`gestion_comercial` — la real se llama **`gesti_n_comercial`** (con el guion bajo en lugar de
la ó). El body que quedó aplicado ya usa sólo propiedades que existen.


---

## Auditoría definitiva: qué le tocó n8n a Colina del Viento

La primera pasada usó `automatizacion` con valor como proxy, lo cual es impreciso: un asesor
también puede tocar esa propiedad. HubSpot guarda el **origen de cada cambio de propiedad**
(`propertiesWithHistory`), así que la atribución se puede hacer con certeza.

### Cómo se identificó a n8n

`POST /crm/v3/objects/contacts/batch/read` con
`propertiesWithHistory: [automatizacion, hs_lead_status, motivos_descalificaci_n, gesti_n_comercial]`
sobre los 242 candidatos (en lotes de **50** — el límite para historiales es 50, no 100).

Cada versión trae `sourceType` y `sourceId`. Orígenes encontrados en la cuenta:

| `sourceType` | Qué es | Cambios |
|---|---|---|
| `INTEGRATION` | apps vía API (n8n entre ellas) | 1.181 |
| `CRM_UI` | personas en la interfaz de HubSpot | 1.146 |
| `AUTOMATION_PLATFORM` | workflows propios de HubSpot | 69 |
| `MERGE_OBJECTS` | fusiones de contactos | 37 |
| `CRM_UI_BULK_ACTION` | acciones masivas manuales | 27 |
| `MOBILE_ANDROID` | app móvil | 9 |

Dentro de `INTEGRATION` hay dos apps: **`13577433`** y `33500359`. La primera es **n8n**: es
el único origen que escribe `automatizacion` (85 de 86 cambios; el otro es `MERGE_OBJECTS`) y
`motivos_descalificaci_n` (57). `33500359` sólo tocó `hs_lead_status` 5 veces.

### Resultado

| Universo | Contactos |
|---|---|
| Colina modificados por cualquier causa desde 18-ago | 1.914 |
| …con `automatizacion` poblada (proxy de la 1ª pasada) | 242 |
| **…modificados por n8n (`INTEGRATION 13577433`)** | **85** |

Fechas del último cambio hecho por n8n:

```
2026-08-19: 72
2026-08-20: 13
```

**Nada después del 20 de agosto.** Lo que n8n escribió:

| Cambio | Veces |
|---|---|
| `automatizacion = Finalizo sin Exito` | 84 |
| `motivos_descalificaci_n = DESINTERES O EQUIVOCADO` | 57 |
| `gesti_n_comercial = Descalificado` | 11 |
| `hs_lead_status = Contactado` | 6 |
| `automatizacion = Finalizada` | 1 |

Esos valores corresponden exactamente a `Crear y Actualizar Contacto19` / `20` y
`📝 Cambiar proyecto5` / `6`, que son los nodos de la rama Colina de `Switch6` — la que se
desconectó. Coherente: los crons de seguimiento corrieron el 19 y 20 de agosto sobre leads de
Colina y los marcaron como descalificados. Después del 20 no volvieron a aparecer porque ya no
cumplían el filtro `automatizacion IN (Iniciada, En proceso)`.

### Se resuelve la duda de la concentración del 29 de agosto

En la pasada anterior quedó sin explicar el pico de 172 contactos del 29 de agosto. **No fue
n8n:** ningún cambio atribuido a `INTEGRATION 13577433` cae en esa fecha. Fue actividad de
`CRM_UI` / `CRM_UI_BULK_ACTION` / `AUTOMATION_PLATFORM`, es decir personas o workflows de
HubSpot.

### Pendiente de decisión: revertir los 85

Los 85 quedaron marcados como `Finalizo sin Exito` + `Descalificado` +
`DESINTERES O EQUIVOCADO` por una automatización que no debía tocarlos. Si se quiere revertir,
el historial de propiedades trae el **valor anterior de cada uno**, así que se puede restaurar
contacto por contacto con precisión. Requiere confirmación del cliente: no se hizo nada.

Listado completo entregado como CSV (`leads-colina-modificados-POR-AUTOMATIZACION.csv`), con
una columna `detalle` que lista cada cambio con fecha, propiedad y valor. No se versiona por
contener correos y teléfonos.
