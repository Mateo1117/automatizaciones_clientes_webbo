# Repartir las citas entre dos asesores — paso a paso

Objetivo: que las citas que agenda el bot se repartan entre
`webbo.meetings@gmail.com` y `comercialwebbo2@gmail.com` en vez de caer todas en el primero.

Workflow: `WEBBO - Bot completo CORREGIDO (audio+imagen+texto)` (`TX3A1wgpXHiLKwID`).

> **Reparto del trabajo:** la **Parte 1** solo la puedes hacer tú, porque hay que entrar a las
> cuentas de Google. La **Parte 3** la hago yo en n8n. La Parte 2 son cuatro respuestas de una
> palabra.

---

## Parte 1 — Dar acceso al segundo calendario (15 minutos)

### Por qué hace falta

n8n entra a Google Calendar con **una sola conexión**, que hoy es la de
`webbo.meetings@gmail.com`. Esa conexión puede escribir en su propio calendario, pero **no en el
de `comercialwebbo2@gmail.com`**, porque son dos cuentas de Google distintas y ninguna conoce a
la otra.

La solución no es conectar una segunda cuenta a n8n (eso obliga a duplicar nodos y complica el
flujo). Es más simple: que `comercialwebbo2` le **dé permiso** a `webbo.meetings` para crear
eventos en su calendario. A partir de ahí, la conexión que ya existe sirve para los dos.

### Paso 1.1 — Entrar como `comercialwebbo2@gmail.com`

1. Abre **https://calendar.google.com**.
2. Arriba a la derecha, haz clic en la foto de perfil y comprueba que dice
   **comercialwebbo2@gmail.com**. Si dice otra cosa, usa *Añadir otra cuenta* e inicia sesión con
   esa.

> ⚠️ Este paso se hace **desde la cuenta que da el permiso**, no desde la que lo recibe. Es el
> error más común: hacerlo al revés no da ningún error, simplemente no funciona.

### Paso 1.2 — Abrir la configuración del calendario

1. En la columna de la izquierda busca la sección **"Mis calendarios"**.
2. Pasa el ratón por encima del calendario de esa cuenta. **Ojo: se llama "Comercial Webbo2", no
   `comercialwebbo2@gmail.com`** — Google muestra el nombre que tenga puesto el calendario, no el
   correo.
3. Aparecen tres puntos verticales **⋮** a la derecha. Haz clic.
4. Elige **"Configuración y uso compartido"**.

> Si ya estás en la pantalla de *Configuración* (barra lateral con "Configuración de mis
> calendarios" → el calendario desplegado), no hace falta nada de lo anterior: ya llegaste. Puedes
> ir directo a **"Compartido con"** en esa barra lateral.

### Paso 1.3 — Compartir con permiso de escritura

1. Baja hasta la sección **"Compartido con"** (en otras versiones de la interfaz se llama
   *"Compartir con determinadas personas o grupos"* — es la misma).
2. Haz clic en **"➕ Añadir personas y grupos"**.
3. Escribe: `webbo.meetings@gmail.com`
4. **Este es el paso crítico:** a la derecha hay un desplegable de permisos. Por defecto viene en
   *"Ver detalles de los eventos"*. **Cámbialo a "Hacer cambios y ver todos los detalles del
   evento"** (la cuarta de la lista). Si lo dejas como viene, el bot podrá leer la agenda pero no
   crear citas, y fallará sin dar un error claro.

   | Permiso | ¿Sirve? |
   |---|---|
   | Ver solo libre/ocupado (ocultar detalles) | ❌ no |
   | Ver detalles de los eventos | ❌ no — es la que viene puesta; solo lee |
   | Hacer cambios (ver eventos privados como libre/ocupados) | ⚠️ crea citas, pero le oculta los detalles de los eventos privados al consultar la agenda |
   | **Hacer cambios y ver todos los detalles del evento** | ✅ **esta** |
   | Hacer cambios y gestionar el uso compartido | ⚠️ también sirve, pero además permite cambiar quién más tiene acceso — más de lo necesario |

   > Los nombres cambian según la versión de Google Calendar. En versiones anteriores esta opción
   > se llamaba *"Hacer cambios en los eventos"*. Lo que importa es que empiece por **"Hacer
   > cambios"** y que **no** sea la de *"gestionar el uso compartido"*.

5. Haz clic en **"Enviar"**.

> Mientras estás ahí, comprueba que la **zona horaria** del calendario sea
> *(GMT-05:00) Hora estándar de Colombia*. El workflow trabaja en `America/Bogota`; si el segundo
> calendario estuviera en otra zona, las citas saldrían corridas.

### Paso 1.4 — Aceptar la invitación desde la otra cuenta

Google manda un correo a `webbo.meetings@gmail.com`. **Hay que aceptarlo o el permiso no se
activa.**

1. Entra al correo de `webbo.meetings@gmail.com`.
2. Busca el mensaje de Google Calendar (asunto parecido a *"comercialwebbo2 te ha invitado a
   consultar un calendario"*).
3. Haz clic en el enlace **"Añadir este calendario"**.
4. Se abre Google Calendar y el calendario de `comercialwebbo2` aparece en la columna izquierda,
   bajo **"Otros calendarios"**.

#### Si el correo no llega (camino alternativo, suele ser más rápido)

No hace falta el correo. Desde Google Calendar con la cuenta `webbo.meetings@gmail.com`:

1. Barra lateral izquierda → **"Agregar calendario"** (tiene una flecha ⌄).
2. Elige **"Suscribirme a un calendario"** (en otras versiones, *"Suscribirse al calendario"*).
3. En el campo **"Agregar calendario"** escribe `comercialwebbo2@gmail.com` y pulsa **Enter**.

Si se añade, aparece en la barra lateral bajo **"Otros calendarios"**. Si en vez de añadirlo
Google ofrece un botón de **"Solicitar acceso"**, el permiso del paso 1.3 no llegó a guardarse.

> Los nombres de los calendarios no coinciden con los correos: en una cuenta el calendario se
> llama **"Webbo IA"** y en la otra **"Comercial Webbo2"**. Google muestra el nombre, no la
> dirección, y eso hace difícil encontrarlos buscando por el correo.

### Paso 1.5 — Comprobar que el permiso es de ESCRITURA

> ⚠️ **Cuidado con el falso positivo.** Que el calendario aparezca en la lista de
> `webbo.meetings` — o en el desplegable de n8n — **no prueba que se pueda escribir en él**. Con
> permiso de solo lectura se añade exactamente igual. La única comprobación válida es intentar
> crear un evento.

En Google Calendar, con la cuenta **`webbo.meetings@gmail.com`**:

1. Pulsa **"Crear"** → **"Evento"**.
2. Busca el **desplegable del calendario** dentro del formulario (el que indica dónde se guarda;
   por defecto marcará el calendario propio de la cuenta).
3. Despliégalo y mira la lista.

- **Aparece "Comercial Webbo2"** → hay permiso de escritura ✅
- **No aparece** → el permiso quedó en solo lectura ❌ Vuelve al paso 1.3 y asegúrate de elegir
  *"Hacer cambios y ver todos los detalles del evento"* antes de pulsar **Enviar**.

Cierra el evento **sin guardar**. Solo estabas comprobando.

> La prueba definitiva es la cita de prueba real que se crea al final, en la Parte 3. Esta
> comprobación solo sirve para detectar el problema antes de tocar el workflow.

---

## Parte 2 — Lo que quedó decidido

| | Decisión |
|---|---|
| Asesores | `webbo.meetings@gmail.com` → **Pedro Casallas**<br>`comercialwebbo2@gmail.com` → **Katherine Cipagauta** |
| Criterio de reparto | Por número de contacto de Solvot: par → Pedro, impar → Katherine |
| Cliente que vuelve | Cae **siempre con el mismo asesor**, también si reagenda meses después |
| Si el asesor no tiene hueco | Se le ofrece **otra hora del mismo asesor** dentro de 21 días (ver nota abajo) |
| Horario | El mismo para los dos: L-V, 9:30-13:00 y 14:00-17:00, citas de 30 min, nunca el mismo día |
| Invitados al evento | Cliente + asesor asignado |

> **Matiz importante sobre "si no tiene hueco".** La idea inicial era pasar la cita al otro asesor.
> No se implementó así porque choca con la regla de *mismo cliente, mismo asesor*: el asesor va
> atado al contacto desde el primer mensaje, antes de saber qué día pedirá. Si no hay hueco, el
> bot ofrece otra hora de esa misma persona. Un cliente solo se quedaría sin cita si su asesor
> estuviera lleno 21 días seguidos.
>
> Las dos reglas son incompatibles: o el cliente conserva asesor, o la cita salta al que esté
> libre. Si se prefiere lo segundo, hay que rehacer el reparto con un contador en el CRM y una
> segunda herramienta de disponibilidad para que el agente vea las dos agendas.

## Parte 3 — Cambios aplicados en n8n

Aplicados el 2026-10-05 sobre el workflow en vivo (67 nodos, activo). Respaldo del estado previo
guardado antes de escribir.

| Nodo | Antes | Ahora |
|---|---|---|
| `Combinar contacto y mensaje` | — | Calcula `asesor_email` y `asesor_nombre` |
| `Agendar cita` → calendario | fijo, `webbo.meetings@gmail.com` | el del asesor asignado |
| `Agendar cita` → invitados | cliente + `webbo.meetings` siempre | cliente + asesor asignado |
| `Consultar disponibilidad` → calendario | fijo, `webbo.meetings@gmail.com` | el del asesor asignado |
| `Consultar disponibilidad` → ventana | **la agenda entera, sin filtro de fechas** | de hoy a 21 días |
| `AI Agent` → prompt | — | Recibe el nombre del asesor para nombrarlo al confirmar |

### Cómo se decide el asesor

En el nodo `Combinar contacto y mensaje`, antes de que el agente vea nada:

```js
const ASESORES = [
  { email: 'webbo.meetings@gmail.com',  nombre: 'Pedro Casallas' },
  { email: 'comercialwebbo2@gmail.com', nombre: 'Katherine Cipagauta' },
];

const idDigitos = String(msgFinal.contact_id || '').replace(/\D/g, '');
const asesor = idDigitos
  ? ASESORES[Number(idDigitos.slice(-6)) % ASESORES.length]
  : ASESORES[0];
```

**Para cambiar asesores, correos o nombres solo se toca esa lista.** Nada más del flujo los
menciona: el resto los lee de `asesor_email` y `asesor_nombre`.

El reparto se simuló antes de aplicarlo: sobre 1.000 contactos correlativos sale **500 / 500**.
Lo que no da es un 1-2-1-2 estricto — en un día de pocas citas puede salir 3 y 1. A cambio, el
mismo cliente conserva asesor y no hay contador que se pueda perder o descuadrar.

### Las dos expresiones que hacen el trabajo

Tanto el calendario de `Agendar cita` como el de `Consultar disponibilidad` pasaron de texto fijo
a:

```
={{ $('Combinar contacto y mensaje').first().json.asesor_email }}
```

El de disponibilidad es el que se suele olvidar. Si se crea la cita en el calendario de uno pero
se consulta la agenda del otro, se agendan reuniones encima de las que ya existían.

### Verificación

- ✅ Sintaxis del nodo Code comprobada con `node --check` antes de subir.
- ✅ Reparto simulado: 500/500 sobre 1.000 contactos.
- ✅ `PUT` devuelto con HTTP 200, workflow activo, `settings` intactos.
- ⏳ **Pendiente: una cita de prueba real.** Las expresiones del calendario viven dentro de
  herramientas del agente y solo se evalúan cuando alguien pide cita de verdad, así que hasta
  que no se agende una no está probado de punta a punta. Lo que hay que mirar en esa prueba:
  que el evento aparezca en el calendario del asesor que tocaba, que llegue la invitación al
  cliente, y que el enlace de Meet se haya creado.

## Resumen

| Estado | |
|---|---|
| ✅ | Calendario de Katherine compartido con permiso de escritura y añadido |
| ✅ | Decisiones tomadas y asesores definidos |
| ✅ | Cambios aplicados en n8n, workflow activo |
| ⏳ | Cita de prueba real que confirme el circuito completo |
