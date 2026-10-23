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

> El webhook `POST /lead-tiktok` existe y está activo, pero **nunca se ha usado**. Además, tal
> como está hoy no funcionaría: `Normalizar TikTok` lee `$json.Name`, `$json.Whatsapp`, etc.,
> que son nombres de columna del Sheet. Por webhook el cuerpo llega bajo `$json.body`, así que
> nombre, teléfono y email saldrían vacíos — y con el teléfono vacío la cadena revienta más
> adelante en `Datos (existente)3` (`payload[0].id`). Si alguna vez se quiere usar esa vía, hay
> que arreglar las expresiones primero.

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

Añadir esas cuatro columnas **con esos nombres exactos** en la integración que alimenta el Sheet
activa la atribución sin cambiar nada en n8n.

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
