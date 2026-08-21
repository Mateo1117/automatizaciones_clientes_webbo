# GoIP `190.24.47.209` — habilitación de la cuenta 101

**Para:** ingeniero a cargo del gateway
**De:** MCM Salud · central `pbx.mcmsolutions.com.co` · FreePBX 17 / Asterisk 22
**Fecha:** 21/8/2026 · Contacto: gerencia@mcmasociados.com

---

## Resumen en tres líneas

La central ya está configurada y probada del lado nuestro: la troncal SIP hacia el gateway
existe, y el gateway **ya responde a nuestros SIP OPTIONS con 101 ms de latencia**, así que
hay camino de red en ambos sentidos y el 5060/UDP está abierto entre las dos puntas.

Lo que falta es autorizar la cuenta para que acepte llamadas.

---

## QUÉ NECESITAMOS QUE HAGA

### 1. Autorizar nuestra IP pública — el punto principal

```
157.245.244.48        (pbx.mcmsolutions.com.co)
```

Nuestra central está configurada **sin registro**: no va a llegarle ningún `REGISTER`. Nos
identificamos por IP y autenticamos con la clave de la cuenta `101` cuando el gateway nos
desafía (autenticación saliente).

Si su plataforma **exige** registro en lugar de autorización por IP, díganoslo y lo cambiamos
a registro saliente en cinco minutos. Solo necesitamos saberlo.

### 2. Abrir el rango RTP

```
10000-20000 / UDP    desde y hacia 157.245.244.48
```

Es el rango de audio estándar de Asterisk, confirmado en nuestra central. **Este es el punto
que más problemas causa y el más fácil de pasar por alto**: si el RTP está bloqueado, la
llamada conecta y el registro de llamadas dice `ANSWERED`, pero no hay audio o solo se oye
en un sentido. Parece un fallo de la central cuando en realidad es un puerto cerrado.

### 3. Confirmarnos el CallerID que espera

Hoy la llamada sale con el número de la extensión interna como origen. Muchos gateways
rechazan un CLI que no sea un número válido de la línea.

Podemos fijar el DID del hospital: **`6013288948`**. Díganos cuál espera y lo configuramos.

### 4. Confirmarnos el formato de marcación

Enviamos el número **completo, de 10 dígitos, sin prefijos**: por ejemplo `3001234567` para
celular y `6012345678` para fijo.

Si el equipo espera un prefijo (`0`, `09`, código de operador…), díganoslo y lo anteponemos
en la ruta de salida.

### 5. Decirnos cuántas llamadas simultáneas admite la línea

Necesitamos el número para topar la troncal. Sin tope, un envío de recordatorios a pacientes
puede saturar el equipo y las llamadas empiezan a fallar sin causa aparente.

### 6. Confirmar códecs y DTMF

Trabajamos con **ulaw / alaw** y DTMF en **RFC 4733**. El DTMF nos importa de forma concreta:
los recordatorios piden al paciente marcar 1, 2 o 3 para confirmar o cancelar su cita.

### 7. ¿Puede el GoIP tener una IP pública propia?

**Pregunta importante, aunque no bloquea la puesta en marcha.**

El GoIP sale a internet por la misma IP pública que las oficinas: `190.24.47.209`. Eso nos
obligó a montar la troncal de una forma particular, porque la configuración estándar hacía
que nuestra central confundiera el tráfico de los teléfonos del personal con el del gateway.

Lo tenemos resuelto **para llamadas salientes**, que es lo que necesitamos ahora. Pero
mientras compartan IP, **no podremos recibir llamadas entrantes por el GoIP** sin volver a
romper los teléfonos de la sede.

Si el equipo puede salir por una IP distinta a la de la oficina, el problema desaparece de
raíz y queda abierta la posibilidad de usarlo también para entrantes. Si no puede, seguimos
adelante igual: las salientes funcionan.

---

## Datos técnicos de nuestra central (referencia)

| Parámetro | Valor |
|---|---|
| IP pública a autorizar | `157.245.244.48` |
| Nombre DNS | `pbx.mcmsolutions.com.co` |
| Destino configurado | `190.24.47.209` puerto `5060/UDP` |
| Cuenta / usuario | `101` |
| Autenticación | Saliente (respondemos al desafío) |
| Registro | Ninguno — identificación por IP |
| Transporte | UDP |
| Códecs | ulaw, alaw |
| DTMF | RFC 4733 |
| Rango RTP | `10000-20000/UDP` |
| Monitoreo | SIP OPTIONS cada 60 s |
| Números que enviaremos | Los que empiezan por **3** (celulares) y por **6** (fijos), 10 dígitos completos |

---

## Cómo sabremos que quedó habilitado

Basta una llamada de prueba a un celular. Miramos tres cosas:

1. Que el `INVITE` hacia `190.24.47.209:5060` reciba **`200 OK`**.
2. Un **`401`** o **`403`** significa que la cuenta o la IP no están autorizadas, o que el
   CallerID no le sirve (punto 3). Un **`404`** o **`503`**, que no reconoce el formato del
   número (punto 4).
3. Que haya **audio en los dos sentidos**, no solo que la llamada figure como contestada.
   Audio mudo o en un solo sentido apunta al punto 2 (RTP).

En cuanto nos confirme los puntos 1 y 2, hacemos la prueba y le decimos el resultado.
