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

**5. Las automatizaciones que llaman de vuelta a n8n.** Estos 13 webhooks **siguen activos y
esperando** en `https://flow.mcmasociados.tech/webhook/<path>`:

```
respuesta_cliente_tatika      respuesta_cliente_tatika1     respuesta_cliente_tatika2
respuesta_cliente_tatika3     respuesta_cliente_tatika4     respuesta_cliente_tatika5
respuesta_cliente_tatika6     respuesta_cliente_tatika7
conaring-lead
respuesta_cliente_colina      respuesta_cliente_colina_viento
respuesta_cliente_colina_viento_llamada
respuesta_cliente_colina_viento_no_interesa
```

Sin recrearlas, el flujo manda el primer mensaje pero **nunca se entera de que el cliente
respondió**: el lead se queda en `Iniciada` para siempre y entra en recordatorios que no
corresponden.

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

## Plan de corte

1. Crear la credencial Header Auth en n8n con el token del Solvot nuevo.
2. Reapuntar los 6 nodos vivos (y los 8 gemelos de Colina, por consistencia): dominio,
   `account_id`, `inbox_id`, `team_id`, y la credencial en lugar del header a mano.
3. ~~Corregir B1 y B2.~~ ✅ hecho el 14-nov, ya está en producción.
4. Probar con un contacto de prueba antes de dar por buena la migración.
5. Recuperar los 56 leads en `Error`: tocarlos para que vuelvan a entrar, **por tandas** —
   de golpe serían 56 plantillas MARKETING en un ciclo, con el riesgo de `131049` de Meta.
