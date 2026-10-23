# Leads de TikTok — cómo llegan y qué falta

Workflow `TX3A1wgpXHiLKwID` · revisado 2026-10-23

---

## La ruta real

```
TikTok (formulario instantáneo)
      ↓  (integración externa, NO es n8n)
Google Sheet "Tiktok" · doc 1ms_tigWxFqX1bjGix0TFW9BjsynC_aORy_Ee5eoX9wk · Hoja 1
      ↓  Google Sheets Trigger1  (rowAdded, poll cada minuto)
Normalizar TikTok → Datos lead1 → CRM: crear lead → Crear contacto1
      → Crear conversacion1 → CRM: vincular Solvot1 → Enviar plantilla1
```

n8n **solo lee** esa hoja. Ningún workflow de la instancia escribe en ella: la llena la
integración de TikTok. Por eso, para que lleguen leads de una campaña nueva **no hay que tocar
n8n** — basta con que esa campaña entregue al mismo Sheet.

> **El webhook `POST /lead-tiktok` se borró el 2026-10-23.** Nunca se había usado y, tal como
> estaba, no habría funcionado: `Normalizar TikTok` lee `$json.Name`, `$json.Whatsapp`, etc.,
> que son nombres de columna del Sheet. Por webhook el cuerpo llega bajo `$json.body`, así que
> nombre, teléfono y email habrían salido vacíos. Se eliminó para que nadie lo conectara
> creyendo que servía. `Normalizar TikTok` ahora solo lo alimenta `Google Sheets Trigger1`.

### Verificado en producción

La noche del 2026-10-23 entraron 6 leads entre las 02:24 y las 03:45 UTC, todos completos hasta
el envío de la plantilla de bienvenida, sin errores.

---

## Lo que falta: atribución de campaña

La hoja trae solo 6 columnas:

```
TikTok Lead ID · TikTok Lead Status · Name · Whatsapp · Email · Company
```

No hay nada de campaña, anuncio, grupo de anuncios ni formulario. Con una sola campaña activa
daba igual; con varias no se puede saber cuál trae cada lead.

**El flujo ya está preparado para recibirlos.** `Normalizar TikTok` busca estos campos y hoy
llegan vacíos solo porque las columnas no existen:

| Campo que llega al CRM | Columna que n8n espera en la hoja |
|---|---|
| `campania` | `Campaign Name` |
| `ad_name` | `Ad Name` |
| `adgroup_name` | `Adgroup Name` |
| `formulario` | `Form Id` |

### Las columnas ya están creadas (2026-10-23)

Se añadieron a la hoja en `G1:J1`, que estaban libres:

```
A: TikTok Lead ID   B: TikTok Lead Status   C: Name   D: Whatsapp   E: Email   F: Company
G: Campaign Name    H: Ad Name              I: Adgroup Name         J: Form Id
```

**Pero crear la columna no hace que se llene.** La hoja la escribe una integración externa a
n8n, y hasta que esa integración no mapee esos cuatro campos de TikTok a las columnas nuevas,
seguirán llegando vacíos. Esa parte se configura donde esté montado el envío de leads, no en la
hoja ni en n8n.

#### Cómo averiguar qué integración llena la hoja

Por orden de rapidez:

1. **En la propia hoja:** *Archivo → Historial de versiones → Ver historial de versiones*. El
   panel derecho dice quién escribió las últimas filas.
2. **En TikTok Ads Manager:** *Herramientas → Generación de clientes potenciales* (o
   *Formularios instantáneos*). Abriendo el formulario de la campaña se ve si tiene un destino
   de entrega conectado.
3. **Si se usa Zapier o Make:** buscar el Zap o escenario cuyo disparador sea *TikTok Lead Ads*
   y cuya acción escriba en esta hoja.

#### Qué mapear una vez identificada

| Campo de TikTok | Columna destino |
|---|---|
| Campaign name | `Campaign Name` |
| Ad name | `Ad Name` |
| Ad group name | `Adgroup Name` |
| Form ID | `Form Id` |

n8n no necesita ningún cambio: `Normalizar TikTok` ya busca esos nombres.

---

## Limpieza del campo `empresa` (aplicado 2026-10-23)

### El problema

En 4 de los 6 leads de esa noche, la columna `Company` del formulario no traía una empresa:

| Lead | `Company` recibido | Qué era |
|---|---|---|
| María del Pilar | `mariadelpilarcertuche@gmail.com` | su correo |
| Elba Judith Vega | `vegaelva713@gmail.com` | su correo |
| Jhonny | `Jhonny` | su propio nombre |
| Gladys Yáñez | `Gladys yanez ` | su propio nombre |

Solo María Islebia (*Nequi*) y Francisco Javier (*Café El Mirador*) traían empresa real. Esa
basura entraba tal cual al campo `empresa` del CRM.

Son dos defectos distintos: el formulario de TikTok pide mal el dato, y el flujo no lo filtraba.
Esto corrige lo segundo.

### La corrección

El campo `empresa` de `Normalizar TikTok` pasó de

```
={{ $json.Company || $json.empresa || '' }}
```

a una expresión que descarta lo que claramente no es una empresa:

```js
const emp = ($json.Company || $json.empresa || '').toString().trim();
if (!emp) return '';
const nom = ($json.Name || $json['Full Name'] || $json.nombre || '').toString().trim();
const norm = s => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'')
                   .replace(/\s+/g,' ').trim();
if (/[\w.+-]+@[\w-]+\.[\w.-]+/.test(emp)) return '';   // es un correo
if (/^\+?\d[\d\s()-]{5,}$/.test(emp)) return '';       // es un telefono
if (nom && norm(emp) === norm(nom)) return '';          // repite el nombre de la persona
return emp;
```

Es la misma lógica que `Analizar interaccion` ya aplicaba en la rama del chat, más el caso del
correo.

**Vacío significa "no lo sabemos todavía"**, que es lo correcto: el agente pregunta la empresa
durante la conversación. No se pone `Independiente` porque eso significa otra cosa — que se
confirmó que no tiene empresa.

### Comprobación

La expresión exacta del nodo se ejecutó contra los 6 leads reales más 4 casos límite:

| Nombre | `Company` | Resultado |
|---|---|---|
| María del pilar | `mariadelpilarcertuche@gmail.com` | descartado |
| María islebia Marín galavis | `Nequi ` | **Nequi** |
| Elba Judith Vega cantillo | `vegaelva713@gmail.com` | descartado |
| Jhonny | `Jhonny` | descartado |
| Gladys yanez | `Gladys yanez ` | descartado |
| Francisco Javier Poveda | `Café El Mirador` | **Café El Mirador** |
| Ana Lopez | `ANA  LÓPEZ` | descartado (ignora tildes, mayúsculas y espacios dobles) |
| Carlos Ruiz | `+57 310 5130868` | descartado |
| Luis Mora | `3M` | **3M** (no confunde nombres cortos con teléfonos) |
| *(sin nombre)* | `Servikorea` | **Servikorea** |

Aplicado con `PUT`, HTTP 200, workflow activo, `settings` intactos.

---

## Pendiente

- **Las cuatro columnas de atribución** en el Sheet (ver arriba). Es lo único que impide medir
  campaña por campaña.
- **El formulario de TikTok**: mientras siga pidiendo la empresa de forma que la gente escriba
  su correo o su nombre, el dato se seguirá perdiendo. La limpieza evita que ensucie el CRM,
  pero no inventa el dato que no llega.
- **El webhook `/lead-tiktok`**: o se arreglan sus expresiones o se borra, para que nadie lo
  conecte creyendo que funciona.

---

## 🔴 Hallazgo nuevo: un formulario web sin teléfono puede tocar el contacto de otro cliente

Descubierto el 2026-10-23 al probar que el webhook borrado ya no respondía: un `POST` vacío a
`/webhook/lead-web` produjo esta cadena.

```
Normalizar Web1        telefono = ''   (no cumple el formato, se descarta)
CRM: crear lead        400  "telefono invalido o ausente"        ← el CRM sí valida ✅
Crear contacto1        422  "Phone number should be in e164 format" → salida de ERROR
Buscar contacto3       q = "+"   →  devuelve 15 contactos cualesquiera
Datos (existente)3     contact_id = 384506   ← un contacto REAL que no tiene nada que ver
Crear conversacion1    falla, "Resource could not be found"
```

Esta vez no pasó nada porque la creación de la conversación falló. Pero el mecanismo es claro:
**con el teléfono vacío, `Buscar contacto3` busca `"+"`, Solvot devuelve contactos al azar y el
flujo se queda con el primero.** Si esa última llamada hubiera funcionado, se habría abierto una
conversación y enviado la plantilla de bienvenida de Webbo a un cliente que no la pidió.

Es el hallazgo A2 de `docs/revision-bot-webbo.md`, ahora con evidencia de hasta dónde llega.

**Corrección:** un `Filter` justo después de `Normalizar Web1` / `Normalizar Meta1` /
`Normalizar TikTok` que descarte los items con `telefono` vacío, antes de que lleguen a
`Datos lead1`. Dos nodos y el problema desaparece de las tres ramas de entrada.
