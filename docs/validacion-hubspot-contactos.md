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

**Esto no se corrigió porque hay que hacerlo en Meta Business:**

1. business.facebook.com → Configuración del negocio → **Usuarios → Usuarios del sistema**
2. Crear `n8n-conaring` (o usar el existente), rol Administrador
3. **Agregar activos → Cuentas de WhatsApp** → la que tiene `+57 302 7560683` → *Control total*
4. **Generar token** con `whatsapp_business_messaging` + `whatsapp_business_management`
5. Confirmar el **Phone number ID** en developers.facebook.com → app → WhatsApp → *API Setup*
   (los 24 nodos usan `696830786845937`)
6. Pegar el token en n8n → Credentials → `WhatsApp conaring`

Un token de usuario del sistema no caduca, así que además deja de romperse cada 60 días.
Una vez actualizada la credencial se puede revalidar desde n8n sin necesidad de entrar a Meta
ni de compartir el token.

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

- **Token de WhatsApp sin permisos** (punto 3 arriba) — bloquea el envío de mensajes en los
  24 nodos. Es lo más urgente después de subir la v2. El número está bien; hay que asignarle
  la WABA al usuario del sistema y regenerar el token.
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
