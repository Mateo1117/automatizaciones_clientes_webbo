# Corrección — "los mensajes no llegan a los clientes" (bot de Webbo)

Workflow `TX3A1wgpXHiLKwID` · instancia `n8n-n8n.qhwbfx.easypanel.host` · 2026-08-19

---

## El motivo

Los mensajes de seguimiento **sí se crean en Solvot pero WhatsApp los rechaza**. El error, leído
del historial real de las conversaciones:

```
status: failed
content_attributes.external_error: "Template not found or invalid template name"
```

### Evidencia — conversación 1032 (Héctor Castro)

| Hora UTC | Mensaje | Nodo que lo envió | Estado |
|---|---|---|---|
| 01:36:27 | `"Hola Héctor"` | `Enviar plantilla1` (con `template_params`) | ✅ `read` |
| 01:42:11 | `"Héctor, para aterrizarlo rápido…"` | `Enviar mensaje contextual` (texto libre) | ❌ **`failed`** — `Template not found or invalid template name` |
| 01:58:27 | `"Sí, quiero saber más"` (entrante del cliente) | — | — |

Mismo patrón en la conversación 1027 (David), 23:54 → `failed` con el mismo error. Otras 19
salidas del bot quedaron en `progress` (nunca confirmadas por el proveedor), todas del mismo nodo.

En contraste, la conversación 1026 (Deisy, que **escribió primero**) tiene sus 10 respuestas en
`read`. Y las plantillas de bienvenida, que sí llevan `template_params`, también llegan.

### La causa

`Enviar mensaje contextual` publica el texto generado por la IA sin declarar plantilla:

```json
{ "content": "<texto de la IA>", "message_type": "outgoing" }
```

La **ventana de servicio de 24 h de WhatsApp solo la abre un mensaje entrante del cliente** —
enviar una plantilla no la abre. Con la ventana cerrada, Chatwoot no puede mandar texto libre:
intenta enviarlo como plantilla, busca una aprobada que coincida con el contenido, y como el
texto lo genera la IA distinto cada vez no existe ninguna. De ahí
`Template not found or invalid template name`.

Y por definición **todo lead que está en la cola de seguimiento en las etapas `reintento_5m`,
`reintento_30m` y `reintento_12h` es un lead que todavía no ha respondido** → la ventana siempre
está cerrada → **ninguno de esos mensajes llega nunca**.

n8n no se entera porque Chatwoot devuelve **HTTP 200** al crear el mensaje; el fallo ocurre
después, de forma asíncrona, en el proveedor. El nodo tiene `onError: continueRegularOutput` y
pasa directo a `CRM: avanzar etapa`, así que el CRM registra el seguimiento como hecho.

---

## La corrección

### Fix 1 — Respetar la ventana de 24 h (3 nodos nuevos + 1 reconexión)

```
Que reintento[contextual]
  └─▶ Mensajes de la conversacion   (GET .../conversations/{id}/messages)
        └─▶ Calcular ventana 24h    (Code)
              └─▶ Ventana 24h abierta?  (IF)
                    ├─ true  ─▶ Generar mensaje contextual ─▶ Enviar mensaje contextual
                    └─ false ─▶ Enviar plantilla (ventana cerrada) ─▶ CRM: avanzar etapa
```

`Calcular ventana 24h` busca el último mensaje **entrante** (`message_type === 0`) y considera la
ventana abierta si tiene menos de 24 h:

```js
const ahora = Math.floor(Date.now() / 1000);
let ultimoEntrante = 0;
for (const m of msgs) {
  if (m && m.message_type === 0 && Number(m.created_at) > ultimoEntrante) {
    ultimoEntrante = Number(m.created_at);
  }
}
const ventana_abierta = ultimoEntrante > 0 && (ahora - ultimoEntrante) < 24 * 60 * 60;
```

El mismo nodo resuelve qué plantilla usar cuando la ventana está cerrada, en un mapa editable
arriba del código:

```js
const PLANTILLA_POR_ETAPA = {
  reintento_5m:  'seguimiento_24h_webbo',
  reintento_30m: 'seguimiento_24h_webbo',
  reintento_12h: 'seguimiento_24h_webbo',
};
```

> ⚠️ **Pendiente de confirmar:** la única plantilla verificada como aprobada y entregada es
> `remarketing_webbo` (las bienvenidas llegan en estado `read`). `seguimiento_24h_webbo` y
> `cierre_48h_webbo` están en el flujo desde antes pero **no hay ninguna entrega confirmada** con
> ellas. Si no existen en Meta, los envíos fallarán con el mismo error. Verificar en
> Solvot → Inbox 131 → plantillas, y ajustar el mapa de arriba.

### Fix 2 — Reconectar los fallbacks de audio/imagen y romper el bucle infinito

Antes, cuando fallaba la descarga del adjunto:

```
Audio se descargo?[false] ─▶ Obtener mensajes Solvot9 ─▶ audio ─▶ Descargar (1) ─▶ … ─▶ Audio se descargo?
```

Un ciclo cerrado sin contador ni salida. Como el webhook está en `responseMode: responseNode`,
**Typebot se quedaba colgado y el cliente no recibía nada**. Los nodos de rescate
`Mensaje final (audio fallo)` y `Mensaje final (imagen fallo)` ya existían con el texto escrito,
pero estaban sueltos, sin entrada ni salida.

Ahora:

```
Audio se descargo?[false]  ─▶ Mensaje final (audio fallo)  ─▶ Obtener contacto
Imagen se descargo?[false] ─▶ Mensaje final (imagen fallo) ─▶ Obtener contacto
```

`Combinar contacto y mensaje` ya contemplaba ambos nodos en su cadena de fallback, así que no
hizo falta tocar código.

---

## Verificación del parche antes de aplicar

| Comprobación | Resultado |
|---|---|
| Conexiones a nodos inexistentes | 0 |
| Ciclo en la rama de audio | eliminado |
| Ciclo en la rama de imagen | eliminado |
| Nodos alcanzables desde triggers activos | 74 → 79 |
| Nodos que quedan huérfanos | 1 (`Obtener mensajes Solvot10`, solo lo alimentaba el bucle) |

---

## Aplicación — notas sobre el API pública de n8n

El parche se aplicó con `PUT /api/v1/workflows/TX3A1wgpXHiLKwID` (HTTP 200, workflow activo,
219 nodos). Dos cosas que conviene saber para la próxima vez:

**El `settings` completo es rechazado.** Mandar el objeto tal como lo devuelve `GET` produce:

```
HTTP 400 — request/body/settings must NOT have additional properties
```

El esquema de la API pública solo admite `executionOrder`, `timezone`, `errorWorkflow`,
`executionTimeout`, `saveExecutionProgress`, `saveManualExecutions`, `saveDataErrorExecution` y
`saveDataSuccessExecution`. El workflow tiene además `binaryMode`, `timeSavedMode`, `callerPolicy`
y `availableInMCP`.

**Pero n8n no los borra.** Se envió `settings` solo con `executionOrder` y `timezone`, y al releer
el workflow los cuatro siguen ahí, `availableInMCP: true` incluido — el servidor hace merge, no
reemplazo. No hubo que reactivar nada en *Settings → Instance-level MCP*.

## ⚠️ Segunda causa, independiente: Meta está bloqueando las plantillas (error 131049)

Después de aplicar el parche apareció un error **distinto** en los envíos, y es el que ahora
impide que lleguen los mensajes a los leads nuevos:

```
131049: This message was not delivered to maintain healthy ecosystem engagement.
```

Inventario de todos los envíos fallidos observados:

| Hora UTC | Conv. | Mensaje | Error |
|---|---|---|---|
| 08-18 23:54 | 1027 | seguimiento (texto libre) | `Template not found` |
| 08-19 01:42 | 1032 | seguimiento (texto libre) | `Template not found` |
| 08-19 02:46 | 1033 | **`"Hola Ramiro"` — plantilla de bienvenida** | **`131049`** |
| 08-19 02:51 | 1033 | seguimiento (texto libre) | `Template not found` |
| 08-19 03:25 | 1035 | **`"Hola Jhon"` — plantilla de bienvenida** | **`131049`** |

Los tres `Template not found` son la causa que corrige este parche. Los dos `131049` son otra
cosa: **Meta está descartando las plantillas de bienvenida**, que hasta las 01:36 sí se
entregaban (`"Hola Héctor"` quedó en `read`). Y son los dos casos más recientes.

`131049` es el tope de frecuencia por usuario que Meta aplica a las plantillas de *marketing*.
Salta cuando el destinatario ya recibió demasiados mensajes de marketing o cuando la calidad del
número se degrada. Aunque el flujo declara `"category": "UTILITY"` en `remarketing_webbo`, la
categoría real la asigna Meta del lado del servidor.

**Esto no se arregla en n8n.** Y la causa de fondo es justamente lo que hacía el flujo: mandar
seguimientos a los 5 y 30 minutos a leads que nunca abrieron la conversación. Aunque esos
mensajes fallaran, los intentos cuentan para la reputación del número.

Qué revisar, en orden:

1. **Calidad del número** en WhatsApp Manager → *Insights* → estado de calidad y límite de
   mensajería. Si está en amarillo o rojo, hay que bajar el volumen y esperar a que se recupere.
2. **Categoría real de `remarketing_webbo`** en WhatsApp Manager → *Plantillas*. Si Meta la
   clasificó como MARKETING, está sujeta al tope por usuario.
3. **Espaciar la secuencia.** Un seguimiento a los 5 minutos de una plantilla que el lead ni
   siquiera ha abierto es justo el patrón que dispara el 131049.

## Lo que este parche **no** arregla

Sigue pendiente de la revisión general (`docs/revision-bot-webbo.md`):

- **B2** — el seguimiento reencola leads que ya respondieron (Héctor recibió `reintento_5m` dos
  veces). Se arregla en la función `leads-seguimiento` de Supabase.
- **A8** — `CRM: avanzar etapa` marca la etapa como hecha aunque el envío falle. La ventana de 24 h
  era la causa de fondo, pero el patrón de "HTTP 200 ≠ entregado" sigue ahí: conviene releer el
  estado del mensaje antes de avanzar.
- **B3/B4** — tokens en claro y webhooks sin autenticación.
- **B5** — los 141 nodos muertos y los paths de webhook duplicados.
