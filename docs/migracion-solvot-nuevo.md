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

## Dos bugs latentes encontrados al extraer la especificación

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

**Ambos se corrigen en la migración**, tomando el id de la conversación de la respuesta de
`crear conversacion` o de `Busca conversacion` según la rama.

---

## Mejora: los tokens dejan de estar hardcodeados

Hoy el token está escrito a mano en 14 nodos, en dos variantes distintas. Rotarlo obliga a
tocar los 14, y queda en claro en cada export.

En la migración se reemplaza por **una credencial Header Auth de n8n**
(`api_access_token` = token del Solvot nuevo) y los nodos pasan a
`authentication: predefinedCredentialType`. A partir de ahí, rotar el token es **un cambio en
un solo sitio**, y el token no vuelve a aparecer en el JSON del workflow.

---

## Qué hace falta del Solvot nuevo

| Dato | Viejo | Nuevo |
|---|---|---|
| Dominio | `chat.solvot.com` | ? |
| `account_id` | `60` | ? |
| `inbox_id` de Tatiká | `105` | ? |
| `team_id` | `18` | ? |
| Token | 2 hardcodeados | se crea como credencial en n8n |

### Del lado del Solvot nuevo (no se puede hacer desde n8n)

1. **El inbox debe estar conectado al mismo número de WhatsApp**: `+57 302 7560683`
   (`phone_number_id 696830786845937`). Si cambia el número, también hay que actualizar los
   24 nodos de WhatsApp y volver a aprobar plantillas.
2. **Recrear las automatizaciones que llamaban a n8n.** Estos webhooks siguen activos y
   esperando:

   ```
   respuesta_cliente_tatika      respuesta_cliente_tatika1     respuesta_cliente_tatika2
   respuesta_cliente_tatika3     respuesta_cliente_tatika4     respuesta_cliente_tatika5
   respuesta_cliente_tatika6     respuesta_cliente_tatika7
   conaring-lead
   respuesta_cliente_colina      respuesta_cliente_colina_viento
   respuesta_cliente_colina_viento_llamada
   respuesta_cliente_colina_viento_no_interesa
   ```

   URL completa: `https://flow.mcmasociados.tech/webhook/<path>`

---

## Plan de corte

1. Crear la credencial Header Auth en n8n con el token del Solvot nuevo.
2. Reapuntar los 6 nodos vivos (y los 8 gemelos de Colina, por consistencia): dominio,
   `account_id`, `inbox_id`, `team_id`, y la credencial en lugar del header a mano.
3. Corregir B1 y B2.
4. Probar con un contacto de prueba antes de dar por buena la migración.
5. Recuperar los 56 leads en `Error`: tocarlos para que vuelvan a entrar, **por tandas** —
   de golpe serían 56 plantillas MARKETING en un ciclo, con el riesgo de `131049` de Meta.
