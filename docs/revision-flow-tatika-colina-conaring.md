# Revisión — "Flow Tatika, Colina del Viento - Conaring"

Instancia: `flow.mcmasociados.tech` · Workflow ID `m9mqIWiuJay9qOws` · Estado: **Active**
Alcance: revisión estática del JSON exportado (192 nodos, 162 conexiones, 20 triggers).

> No se pudo consultar la API pública de n8n desde esta sesión: la política de red del
> entorno bloquea el dominio (`CONNECT flow.mcmasociados.tech:443 → 403`). Ver
> `docs/conectar-n8n-api.md` para habilitarlo.

---

## Resumen

| Severidad | Cantidad |
|---|---|
| 🔴 Bloqueante (rompe ejecución o dispara duplicados) | 6 |
| 🟠 Alto (rama muerta / lógica invertida / seguridad) | 7 |
| 🟡 Medio (robustez, mantenimiento) | 5 |

Nodos por tipo: 27 IF · 26 HTTP Request · 25 HubSpot · 24 WhatsApp · 17 Split In Batches ·
15 Webhook · 12 Code · 11 Function (deprecado) · 8 Respond to Webhook · 6 Switch.

---

## 🔴 Bloqueantes

### B1 — `Schedule Trigger` cada 1 minuto sin filtro incremental

`Schedule Trigger` → `🔍 Buscar Últimos Contactos Tatika y Colina del Viento1`

```json
{ "rule": { "interval": [{ "field": "minutes", "minutesInterval": 1 }] } }
```

El search de HubSpot que dispara no tiene filtro de fecha ni de "ya procesado":

```json
"filterGroups": [{ "filters": [{ "propertyName": "proyecto", "operator": "IN", "values": ["Tatika"] }] }],
"sorts": [{ "propertyName": "createdate", "direction": "DESCENDING" }],
"limit": 100
```

Cada minuto se traen **los mismos 100 contactos** y cada uno entra al `Loop Over Items`,
que hace un `HubSpot - Obtener Detalles` por item. Eso son ~100 llamadas/minuto
(144.000/día) sólo en el detalle, más el search. HubSpot corta en 100–190 req/10s por
app token: la automatización se va a auto-limitar (429) y las ramas sin manejo de error
van a fallar en silencio.

**Corrección:** añadir un segundo filtro al `filterGroups` sobre `lastmodifieddate`
(u otra marca de agua) y bajar el trigger a 5–15 minutos:

```json
"filterGroups": [{
  "filters": [
    { "propertyName": "proyecto", "operator": "IN", "values": ["Tatika", "Colina Del Viento"] },
    { "propertyName": "lastmodifieddate", "operator": "GTE", "value": "{{ $now.minus(15,'minutes').toMillis() }}" }
  ]
}]
```

### B2 — El poller busca sólo `Tatika`, nunca `Colina Del Viento`

El nodo se llama "Buscar Últimos Contactos **Tatika y Colina del Viento**", el código de
`extraer leads` clasifica `categoria: "colina_del_viento"` y `Switch2` tiene una salida
`Colina Del Viento`… pero el filtro del search es `"values": ["Tatika"]`. **La rama de
Colina del Viento del flujo automático nunca recibe datos.** Corregir el array de `values`
(ver B1) usando el valor exacto de la propiedad `proyecto` en HubSpot.

### B3 — `HubSpot Trigger` sin evento configurado

```json
{ "eventsUi": { "eventValues": [{}] }, "additionalFields": {} }
```

`eventValues` trae un objeto vacío: no hay evento suscrito. El trigger no se registra
correctamente en HubSpot y el flujo de 63 nodos que cuelga de él nunca arranca por esa vía.
Seleccionar el evento (`contact.creation` / `contact.propertyChange`) o eliminar el nodo.

### B4 — URL malformada en `Actualizar contacto` y `Actualizar contacto2`

```
=https://chat.solvot.com/api/v1/accounts/60/contacts/ {{ $('buscar contacto').item.json.payload[0].id }}
```

Hay un **espacio** entre `contacts/` y la expresión. La URL resultante queda
`.../contacts/ 12345` → Chatwoot responde 404/400. Quitar el espacio en ambos nodos.

### B5 — Paths de webhook con espacios

| Nodo | Path actual | Problema |
|---|---|---|
| `Webhook10` | `" respuesta_cliente_colina_viento_no_interesa"` | **espacio inicial** |
| `Webhook11` | `"respuesta_cliente_colina 2"` | espacio interno (nodo desactivado) |

El espacio inicial de `Webhook10` hace que la URL real sea
`/webhook/%20respuesta_cliente_colina_viento_no_interesa`. Cualquier sistema externo que
llame a la URL "limpia" recibe **404**. Este webhook alimenta
`Crear y Actualizar Contacto1 → 📝 Cambiar proyecto`, o sea que el botón "no me interesa"
está muerto. Hacer trim al path.

### B6 — `typeValidation: strict` comparando un objeto contra string

`Switch3` y `Switch` (v3.2) evalúan `{{ $json.automation }}` con operador `string` y
`typeValidation: "strict"`. Hay una regla que compara literalmente contra `"[object Object]"`:

```json
{ "leftValue": "={{ $json.automation }}", "rightValue": "[object Object]", "operator": { "type": "string", "operation": "equals" } }
```

Ese valor sólo aparece cuando `automation` llega como **objeto**, no como string. En modo
strict n8n lanza error de tipo en vez de evaluar, y el item revienta el switch. El origen
está en `3. Format Lead Data1`, que asigna `automation = {{ $json.automation.value }}`
sobre un `automation` que a veces ya es primitivo. Normalizar en el Code node previo
(`String(automation?.value ?? automation ?? '')`) y borrar la regla `"[object Object]"`.

---

## 🟠 Altos

### A1 — Sub-flujo de Chatwoot completo huérfano

`Es conversation_created?` **no tiene conexión de entrada**. Con él queda inalcanzable toda
su rama: `Detectar Canal1 → Es canal Web? → Tiene email? → HubSpot Upsert Contact2 →
Upsert exitoso? → Respuesta OK2 / Respuesta Error2 / Respuesta Ignorado2 / Respuesta Canal No Web1 /
Respuesta Sin Email2`.

Parece una versión anterior del flujo `Webhook Chatwoot → Normalizar Datos3 → ¿Tiene email
valido? → HubSpot Upsert Contact3 → ¿Upsert exitoso?2 → Respuesta OK3/Error3`, que sí está
conectado. Decidir cuál se queda y **borrar la otra** — mantener las dos confunde el
mantenimiento y duplica los `respondToWebhook`.

### A2 — Nodo `Envia mensaje` huérfano

`Envia mensaje` (HTTP a Chatwoot) no tiene entrada, pero sí salida hacia
`WhatsApp Business Cloud14`. Su gemelo `Envia mensaje2` sí está cableado. Conectarlo o
eliminarlo junto con su cadena.

### A3 — Tokens de Chatwoot hardcodeados en 14 nodos

Los nodos `buscar contacto`, `crear contacto`, `Actualizar contacto`, `Busca conversacion`,
`Envia mensaje`, `status a pendiente`, `crear conversacion` (y sus versiones `2`) llevan
`authentication: "none"` y mandan el header a mano:

```json
{ "name": "api_access_token", "value": "hwWCD8Nu…" }
```

Son **dos tokens distintos** repartidos sin criterio entre nodos que pegan a la misma
cuenta (`accounts/60`). Problemas: quedan en claro en cada export del workflow, rotar uno
obliga a tocar 14 nodos, y no hay forma de saber cuál token tiene qué permisos.

**Corrección:** crear una credencial *Header Auth* en n8n (`api_access_token` = token) y
poner los 14 nodos en `authentication: predefinedCredentialType`. **Además, rotar ambos
tokens en Chatwoot** — ya circularon en un archivo exportado.

### A4 — Etiqueta invertida en `Switch3` / `Switch`

```json
{ "leftValue": "={{ $json.hs_lead_status }}", "rightValue": "Contactado",
  "operator": { "operation": "equals" }, "outputKey": "SIN CONTACTO" }
```

La salida que se llama **"SIN CONTACTO"** es exactamente la que matchea
`hs_lead_status == "Contactado"`. O el nombre está mal, o la condición debería ser
`notEquals`. Hoy esa salida va a `Loop Over Items` (se descarta el lead), así que si la
intención era "aún no contactado → mandarle mensaje", **nunca se le manda a nadie**.
Verificar contra el proceso comercial real.

### A5 — Campo sin nombre en `3. Format Lead Data1`

```json
{ "value": "={{ $json.business_info.fuente }}" }
```

Entrada sin `name` dentro de `values.string`. Con `keepOnlySet: true` produce una clave
vacía o se descarta silenciosamente; el dato `fuente` se pierde. Ponerle nombre
(`"name": "fuente"`) o quitar la entrada.

### A6 — 9 webhooks comparten el mismo `webhookId`

`Webhook`, `Webhook1`, `Webhook2`, `Webhook3`, `Webhook5`, `Webhook6`, `Webhook7`,
`Webhook8`, `Webhook11` tienen todos `webhookId: 076bbfcf-a095-4f14-9fd1-1949038a35fa`
(resultado de duplicar el nodo con copiar/pegar). Los paths de producción sí difieren, pero
las **URL de test comparten id**, así que probar uno desde el editor puede activar el
listener equivocado. Regenerar borrando y recreando los nodos, o dejar constancia de que
las pruebas se hacen sólo en producción.

### A7 — 59 de 76 nodos de API sin manejo de error

Sólo 17 nodos (de HTTP/HubSpot/WhatsApp/Postgres) tienen `continueOnFail`, `onError` o
`retryOnFail`. Con el workflow **activo**, un 429 de HubSpot o un fallo de WhatsApp corta
la ejecución completa y los items restantes del lote se pierden sin traza. Como mínimo
poner `retryOnFail: true` (con `maxTries: 3`) en los HubSpot y WhatsApp que están dentro de
los bucles `Separar Citas*`.

---

## 🟡 Medios

### M1 — Horarios de los cron inconsistentes

| Nodo | Hora configurada (UTC) | Hora en Colombia (UTC-5) | Nombre |
|---|---|---|---|
| `Trigger diario 10AM Mañana2` | 15 | 10:00 ✅ | coincide |
| `Trigger diario 10AM Mañana3` | 16 | 11:00 ❌ | dice 10AM |
| `Trigger diario 2PM seguimiento` | 13 | **08:00** ❌ | dice 2PM |

El workflow no fija `timezone` en `settings`, así que hereda el default de la instancia. Si
el default es UTC, "2PM seguimiento" está mandando WhatsApps a las **8 de la mañana**.
Fijar `settings.timezone = "America/Bogota"` y reescribir las horas en local.

### M2 — 11 nodos `n8n-nodes-base.function` (deprecado)

`extraer leads`, `Procesar Item Individual`, `Procesar Info Detallada`, `Process Lead Data`
… siguen en el nodo `Function` v1, retirado de la UI hace varias versiones. Migrar a `Code`
antes de la próxima actualización mayor de n8n.

### M3 — `3. Format Lead Data1` es un Set v1 con `keepOnlySet`

Tipo antiguo y destructivo: descarta todo lo que no esté listado explícitamente. Combinado
con A5, cualquier campo nuevo que agreguen aguas arriba se pierde sin aviso. Migrar a Set v3
(`Edit Fields`) con "Include Other Input Fields".

### M4 — Nodo Postgres desactivado, huérfano y sin credencial

`Insert or update rows in a table`: `disabled: true`, sin entradas, sin salidas y sin
credencial asignada. Borrarlo.

### M5 — Nodos desactivados que quedaron colgando

`When clicking 'Execute workflow'`, `Webhook11` (+ `Crear y Actualizar Contacto21`),
`Webhook12` (`tiktok-leads`, sin nada conectado detrás). `Webhook12` en particular sugiere
una integración de TikTok Leads a medio hacer. Limpiar o terminar.

---

## Lo que sí está bien

- Los 16 bucles `Separar Citas*` (splitInBatches v1) **tienen el ciclo correctamente
  cerrado** — cada cadena retorna al nodo de batch. No hay bucles rotos.
- No hay nombres de nodo duplicados.
- No hay expresiones `$('Nodo')` ni `$node["Nodo"]` apuntando a nodos inexistentes (se
  revisaron los 192).
- Ningún IF/Switch tiene ramas vacías.
- Todas las conexiones apuntan a nodos que existen.
- `callerPolicy: workflowsFromSameOwner` y `executionOrder: v1` están correctos.

---

## Orden sugerido de corrección

1. **B5** (trim de paths) y **B4** (espacio en URL) — 4 ediciones, arreglan endpoints caídos.
2. **B1 + B2** — filtro incremental + incluir Colina del Viento; baja el consumo de API y
   activa la rama muerta.
3. **A3** — credencial Header Auth y rotación de los tokens de Chatwoot.
4. **B6 + A5** — normalizar `automation` y nombrar el campo suelto.
5. **A4** — confirmar con el equipo comercial la lógica de `hs_lead_status`.
6. **A1 + A2 + M4 + M5** — borrar ramas huérfanas y nodos desactivados.
7. **M1** — fijar `America/Bogota` y recalcular horas.
8. **A7** — `retryOnFail` en los nodos de API dentro de bucles.
