# Revisión — "WEBBO - Bot completo CORREGIDO (audio+imagen+texto)"

Instancia `n8n-n8n.qhwbfx.easypanel.host` · Workflow `TX3A1wgpXHiLKwID` · **activo** · 215 nodos
Chatwoot: `chat.solvot.com` cuenta **64**, inbox **131** ("WPP WEBBO", `+57 321 340 9983`)

Revisión hecha con acceso a la API: workflow real, ejecuciones reales y las plantillas
reales de la cuenta de WhatsApp.

---

## Punto de partida

**29 de las últimas 50 ejecuciones con error (58%).** Repartidas así:

| Nodo | Errores | Mensaje |
|---|---|---|
| `Google Sheets Trigger1` | 23 | `Service unavailable` |
| `Google Sheets Trigger1` | 4 | `The service was not able to process your request` |
| `Google Sheets Trigger1` | 1 | `Bad gateway` |
| `Crear conversacion1` | 1 | `The value in the "JSON Body" field is not valid JSON` |

---

## 1. `Template not found or invalid template name` — CORREGIDO

Es el error que aparecía en Chatwoot al enviar. La causa es una discrepancia de **categoría**.

Plantillas reales del inbox 131, leídas de la cuenta:

| Plantilla | Categoría | Idioma | Estado | Variables |
|---|---|---|---|---|
| `remarketing_webbo` | **MARKETING** | es_CO | APPROVED | 1 |
| `seguimiento_24h_webbo` | MARKETING | es_CO | APPROVED | 1 |
| `cierre_48h_webbo` | MARKETING | es_CO | APPROVED | 1 |

Y lo que mandaban los nodos:

| Nodo | Plantilla | Categoría enviada | Vivo | Veredicto |
|---|---|---|---|---|
| `Enviar plantilla1` | remarketing_webbo | **UTILITY** | sí | ❌ → corregido |
| `Enviar mensaje2` | remarketing_webbo | **UTILITY** | sí | ❌ → corregido |
| `Enviar plantilla`, `Enviar plantilla3`, `Enviar plantilla4`, `Enviar mensaje` | remarketing_webbo | UTILITY | no | copias muertas |
| `Reintento 24h (plantilla)1` | seguimiento_24h_webbo | MARKETING | sí | ✅ |
| `Reintento 48h (plantilla)1` | cierre_48h_webbo | MARKETING | sí | ✅ |

Chatwoot busca la plantilla por **nombre + categoría + idioma**. Con `UTILITY` no encuentra
ninguna y responde *"Template not found or invalid template name"*. Los nodos de reintento
sí traían la categoría correcta, y por eso esos sí funcionaban — eso confirma el
diagnóstico.

**Corregido** en los 2 nodos vivos: `UTILITY` → `MARKETING`.

> Ojo: cambiar la categoría en el nodo **no** cambia la categoría en Meta. La plantilla
> sigue siendo MARKETING, con los límites de MARKETING (ver el `131049` más abajo). Si se
> quiere que sea realmente UTILITY hay que recrearla en Meta como UTILITY — y sólo aplica
> si el contenido de verdad es transaccional, no promocional.

---

## 2. Contacto duplicado que tumbaba la ejecución — CORREGIDO

La ejecución `24037295` muestra la cadena completa:

```
Formulario Web3 → Normalizar Web1 → Datos lead1 → CRM: crear lead
  → Crear contacto1   422 "Email has already been taken"
  → Buscar contacto3  q = "+573003331886"  →  { count: 0, payload: [] }
  → Datos (existente)3  contact_id = null
  → Crear conversacion1  ERROR: JSON Body no es JSON válido
```

Tres bugs encadenados:

1. **`Crear contacto1` crea primero y pregunta después.** Chatwoot rechaza con 422 porque el
   **email** ya existe.
2. **`Buscar contacto3` busca por la llave equivocada.** El conflicto fue por email, pero la
   búsqueda de respaldo consulta por **teléfono** (`q = +573003331886`). El contacto
   existente tiene ese email con otro teléfono, así que devuelve 0 resultados.
3. **`contact_id` queda `null` y rompe el JSON.** `Datos (existente)3` hace
   `{{ $json.payload[0].id }}` sobre un array vacío. Luego `Crear conversacion1` interpola
   `"contact_id": {{ $json.contact_id }}` sin comillas: n8n renderiza `null` como cadena
   vacía y queda `"contact_id": ,` — JSON inválido, y la ejecución muere.

**Corregido:**

- `Buscar contacto3` ahora busca por email cuando el 422 fue por email, y por teléfono en
  cualquier otro caso:
  ```js
  {{ (($json.error?.message || '').includes('Email') && $('Datos lead1').item.json.email)
     ? $('Datos lead1').item.json.email
     : '+' + $('Datos lead1').item.json.telefono }}
  ```
- `Datos (existente)3` → `{{ $json.payload?.[0]?.id ?? null }}`, sin reventar con payload vacío.
- 4 nodos vivos pasan a `JSON.stringify(... ?? null)` en los valores sin comillas, así un
  valor faltante ya no invalida el JSON: `Crear conversacion1`, `Crear conversacion2`,
  `CRM: vincular Solvot1`, `CRM: actualizar fase`.

---

## 3. `Google Sheets Trigger1` — CORREGIDO (parcialmente)

28 de los 29 errores. El nodo hace polling **cada minuto** contra la hoja `Tiktok`
(`1ms_tigWxFqX...`) y **no tenía reintentos**. Google devuelve 502/503 intermitentes y cada
uno queda como ejecución fallida.

**Corregido:** `retryOnFail` con 3 intentos y 5 s de espera.

> **Pendiente de decisión:** bajar el polling de `everyMinute` a cada 5 minutos. Reduce
> mucho el ruido y la probabilidad de 5xx, a cambio de hasta 5 minutos de latencia en los
> leads de TikTok. No se cambió porque afecta el comportamiento del negocio.

---

## 4. El `131049` no se arregla por código

`131049: This message was not delivered to maintain healthy ecosystem engagement`

Meta **descarta el mensaje a propósito**. Es su límite por-usuario de plantillas
**MARKETING**, y las tres plantillas de la cuenta son MARKETING. Se dispara cuando el
destinatario ya recibió demasiadas, no interactúa, o la calidad del número bajó.

No hay parámetro ni reintento que lo evite. Lo que sí funciona:

- Priorizar contactos que **ya respondieron** — al responder se abre la ventana de 24 h y se
  puede mandar texto libre sin plantilla ni límite de categoría.
- Reducir el volumen de envíos en frío.
- Si algún mensaje es genuinamente transaccional (confirmación, recordatorio de cita),
  recrearlo en Meta como plantilla **UTILITY**: no comparte el límite de MARKETING.
- Vigilar la calificación de calidad del número en el Administrador de WhatsApp.

---

## 5. Lo que NO se tocó

### El workflow tiene 145 nodos muertos de 215

Sólo **70 nodos son alcanzables** desde un trigger activo. El resto son copias completas del
mismo flujo que quedaron deshabilitadas:

| Path | Nodos con ese path | Activos |
|---|---|---|
| `lead-web` | 4 (`Formulario Web`, `1`, `2`, `3`) | 1 |
| `lead-tiktok` | 2 | 1 |
| `webbot-solvot` | 2 | 1 |
| `bdwebboclientes` | 2 | **0** |

**No hay envíos duplicados**: las copias están deshabilitadas y sólo una de cada path
responde. Pero 145 nodos muertos hacen que cualquier cambio futuro sea confuso y propenso a
tocar la copia equivocada — de hecho hay 4 nodos `Enviar plantilla*` muertos con la
categoría mal que nadie notó. Conviene borrarlas.

Ojo: `bdwebboclientes` no tiene ningún nodo activo, así que **ese webhook está caído**. Si
algo externo lo llama, recibe 404.

### Tokens de Chatwoot en claro

| Token | Nodos |
|---|---|
| `hwWCD8…KykN` | **56** |
| `ioGpXH…7JH9` | 6 |

Son los **mismos tokens** que están hardcodeados en el flujo de Conaring, en otra instancia
de n8n. Están en claro en cada export. Deberían pasar a una credencial *Header Auth* y
**rotarse**.

---

## Resumen

| # | Hallazgo | Estado |
|---|---|---|
| 1 | Categoría `UTILITY` vs `MARKETING` → *Template not found* | ✅ corregido (2 nodos vivos) |
| 2 | Búsqueda por teléfono cuando el duplicado es por email | ✅ corregido |
| 3 | `contact_id` nulo → JSON inválido → ejecución muerta | ✅ corregido (4 nodos) |
| 4 | `Google Sheets Trigger1` sin reintentos | ✅ corregido |
| 5 | Polling cada minuto | ⏸ decisión del negocio |
| 6 | `131049` de Meta | ⛔ no tiene arreglo técnico |
| 7 | 145 nodos muertos / webhook `bdwebboclientes` caído | ⏸ limpieza pendiente |
| 8 | Tokens de Chatwoot en claro en 62 nodos | ⏸ rotar y mover a credencial |

Respaldo del workflow previo a los cambios: se guardó en el scratchpad de la sesión antes
del `PUT`. Las conexiones y el número de nodos no cambiaron — sólo los parámetros de 9 nodos.
