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
2. Pasa el ratón por encima del calendario que se llama **comercialwebbo2@gmail.com** (es el
   principal, el que lleva el nombre de la cuenta).
3. Aparecen tres puntos verticales **⋮** a la derecha. Haz clic.
4. Elige **"Configuración y uso compartido"**.

### Paso 1.3 — Compartir con permiso de escritura

1. Baja hasta la sección **"Compartir con determinadas personas o grupos"**.
2. Haz clic en **"Añadir personas y grupos"**.
3. Escribe: `webbo.meetings@gmail.com`
4. **Este es el paso crítico:** a la derecha hay un desplegable de permisos. Por defecto viene en
   *"Ver todos los detalles del evento"*. **Cámbialo a "Hacer cambios en los eventos".**

   | Permiso | ¿Sirve? |
   |---|---|
   | Ver solo libre/ocupado | ❌ no |
   | Ver todos los detalles del evento | ❌ no — puede leer pero no crear |
   | **Hacer cambios en los eventos** | ✅ **este** |
   | Hacer cambios y gestionar el uso compartido | ✅ también, pero da más permiso del necesario |

5. Haz clic en **"Enviar"**.

### Paso 1.4 — Aceptar la invitación desde la otra cuenta

Google manda un correo a `webbo.meetings@gmail.com`. **Hay que aceptarlo o el permiso no se
activa.**

1. Entra al correo de `webbo.meetings@gmail.com`.
2. Busca el mensaje de Google Calendar (asunto parecido a *"comercialwebbo2 te ha invitado a
   consultar un calendario"*).
3. Haz clic en el enlace **"Añadir este calendario"**.
4. Se abre Google Calendar y el calendario de `comercialwebbo2` aparece en la columna izquierda,
   bajo **"Otros calendarios"**.

### Paso 1.5 — Comprobar que funcionó (importante)

No te fíes de que "parece que sí". Hay una forma de verificarlo que no deja dudas:

1. Entra a n8n: **https://n8n-n8n.qhwbfx.easypanel.host**
2. Abre el workflow **WEBBO - Bot completo CORREGIDO (audio+imagen+texto)**.
3. Busca el nodo **`Agendar cita`** y haz doble clic.
4. En el campo **Calendar** despliega la lista.
5. **Si en la lista aparece `comercialwebbo2@gmail.com`, el permiso quedó bien.** Si solo sale
   `webbo.meetings@gmail.com`, algo falló — revisa el paso 1.3 (el desplegable de permisos) y el
   1.4 (aceptar el correo).

> Cierra el nodo **sin guardar** (tecla `Esc` o la X). Solo estabas mirando.

---

## Parte 2 — Cuatro decisiones

Te propongo una respuesta por defecto para cada una. Si te parecen bien, con que me digas
**"todas OK"** es suficiente.

**1. ¿Qué pasa si al asesor que le toca no tiene hueco?**
*Por defecto:* se alterna uno y uno, pero si al que le toca no le queda nada libre ese día, la
cita pasa al otro. Alternar de forma rígida hace que se pierdan citas por insistir en un asesor
que está lleno.

**2. ¿Un cliente que vuelve a escribir cae con el mismo asesor?**
*Por defecto:* sí. Si reagenda o pide una segunda reunión, le toca la misma persona. Lo
contrario es que el cliente se encuentre con alguien que no sabe nada de la conversación
anterior.

**3. ¿Los dos atienden en el mismo horario?**
*Por defecto:* sí — lunes a viernes, 9:30 a 13:00 y 14:00 a 17:00, citas de 30 minutos, nunca el
mismo día. Es lo que ya tiene configurado el bot.

**4. ¿A quién se invita a la reunión?**
*Por defecto:* al cliente y al asesor que le tocó, nada más. Hoy se invita siempre a
`webbo.meetings`, incluso cuando no va a atender.

### Y un dato que sí necesito

**¿Cómo se llama la persona detrás de cada correo?**

```
webbo.meetings@gmail.com   →  ¿nombre?
comercialwebbo2@gmail.com  →  ¿nombre?
```

Lo uso para que Sofía pueda decir *"quedaste agendado el martes a las 10:00 con Pedro"* en vez
de un genérico *"con nuestro equipo"*. Si prefieres que no mencione nombres, dímelo y lo dejo
genérico.

---

## Parte 3 — Lo que hago yo en n8n

Para que sepas qué va a cambiar, no para que lo hagas tú.

1. **Un nodo nuevo antes del agente** que decide a quién le toca y deja el correo y el nombre
   del asesor listos para el resto del flujo.
2. **`Agendar cita`**: el calendario deja de ser un texto fijo y pasa a ser el del asesor
   asignado. Los invitados pasan a ser cliente + asesor asignado.
3. **`Consultar disponibilidad`**: el mismo cambio de calendario. Este es el que normalmente se
   olvida — si se crea la cita en el calendario de uno pero se consulta la agenda del otro, se
   agendan reuniones encima de las que ya tenía.
4. **El prompt de Sofía**: una línea para que nombre al asesor asignado.
5. **De paso, un arreglo:** hoy `Consultar disponibilidad` pide el calendario **entero**, sin
   filtro de fechas. Le está pasando a la IA todos los eventos que existan desde el principio de
   los tiempos. Le pongo un filtro a la ventana de días que se está ofreciendo. Con dos
   calendarios esto se duplicaría.

### Cómo se decide el turno

Empiezo por la opción que **no necesita infraestructura nueva**: el reparto sale del número de
contacto del cliente (par → asesor A, impar → asesor B). Ventajas: el mismo cliente siempre cae
con el mismo asesor (decisión 2 resuelta sola), reparte mitad y mitad sobre volumen, y no hay
ningún contador que se pueda perder o descuadrar.

Lo que **no** te da es un 1-2-1-2 exacto: en un día con pocas citas puede salir 3 y 1. Si
necesitas que sea literalmente en orden, hay que guardar un contador en el CRM de Supabase —
dímelo y lo montamos así, pero implica tocar la función `solvot-inbound`.

### Cómo lo verifico

No lo doy por bueno hasta tener una cita de prueba real creada en el calendario de
`comercialwebbo2`, con su enlace de Meet y su invitación enviada. Si algo del permiso quedó a
medias, aparece justo ahí.

---

## Resumen

| Quién | Qué | Tiempo |
|---|---|---|
| **Tú** | Parte 1: compartir el calendario y comprobarlo en el nodo `Agendar cita` | ~15 min |
| **Tú** | Parte 2: "todas OK" + los dos nombres | 1 min |
| **Yo** | Parte 3: cambios en n8n y prueba real | — |
