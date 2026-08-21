# Datos para el ingeniero del GoIP — habilitación de la línea 101

Central: **MCM Salud** · FreePBX 17 / Asterisk 22 · `pbx.mcmsolutions.com.co`
Fecha: 21/8/2026

Del lado de la central **ya está todo configurado y probado hasta donde depende de
nosotros**. Falta que del lado del gateway se autorice la cuenta. Abajo, primero lo que
hicimos, después lo que necesitamos de ustedes.

---

## 1. Lo que ya está configurado en nuestra central

### Troncal SIP hacia el gateway

| Parámetro | Valor |
|---|---|
| Nombre de la troncal | `gw_co_out` |
| Tecnología | **PJSIP** (Asterisk 22 no tiene `chan_sip`; el equivalente de `type=friend` es endpoint + AOR + auth + identify, que es lo que está creado) |
| Destino | `190.24.47.209` puerto **5060/UDP** |
| Usuario / cuenta | `101` |
| Autenticación | **Outbound** — respondemos al desafío con la clave de la cuenta 101 |
| Registro | **Ninguno.** No enviamos `REGISTER`; nos identificamos por IP |
| Transporte | UDP |
| Qualify | cada 60 s (OPTIONS) |

### IP pública de nuestra central — la que hay que autorizar

```
157.245.244.48        (pbx.mcmsolutions.com.co)
```

**Este es el dato clave.** Como no enviamos registro, el gateway debe reconocer nuestra IP
para aceptar los INVITE.

### Estado actual de la señalización

El gateway **ya responde** a nuestros OPTIONS:

```
Contact: gw_co_out/sip:101@190.24.47.209:5060   Avail   107.215 ms
```

O sea que hay camino de red en ambos sentidos y el puerto 5060/UDP está abierto entre las
dos puntas. Lo que falta es que acepte las llamadas.

### Marcación que vamos a enviar

- Reglas de salida: todo lo que empiece por **3** (celulares) o por **6** (fijos).
- Se envía el número **completo, tal cual se marca, sin prefijos ni recortes**: por ejemplo
  `3001234567`. Verificado en el dialplan (pasa `${EXTEN}` entero).

---

## 2. Lo que necesitamos del ingeniero del gateway

1. **Autorizar la IP `157.245.244.48`** para la cuenta `101`. No va a llegar ningún
   `REGISTER` desde nuestro lado: la identificación es por IP. Si su plataforma exige
   registro, avísenos y lo cambiamos a registro saliente.

2. **¿Qué CallerID (CLI) debemos enviar?** Hoy la llamada sale con el número de la extensión
   interna como origen, y muchos gateways rechazan un CLI que no sea un número válido de la
   línea. Si hace falta, podemos fijar el DID del hospital: **`6013288948`**. Confírmenos
   cuál esperan.

3. **¿Formato de marcación?** Enviamos 10 dígitos tal cual (`3001234567`). Si el equipo
   espera un prefijo (`0`, `09`, código de operador…) díganoslo y lo anteponemos en la ruta.

4. **¿Cuántas llamadas simultáneas admite la línea?** Necesitamos el número para topar la
   troncal. Sin tope, un envío masivo de recordatorios puede saturar el equipo y las
   llamadas empiezan a fallar sin causa aparente.

5. **Códecs y DTMF.** Trabajamos con **ulaw/alaw** y DTMF en **RFC 4733** (negociado).
   Confírmenos que el equipo los soporta; el DTMF nos importa porque los recordatorios piden
   al paciente marcar 1, 2 o 3.

6. **Rango de puertos RTP.** El audio va por el rango RTP estándar de Asterisk
   (**10000-20000/UDP**) desde `157.245.244.48`. Si hay firewall del lado de ustedes, debe
   permitirlo, o el resultado típico es llamada que conecta pero **sin audio o con audio en
   un solo sentido**.

---

## 3. Cómo sabremos que quedó habilitado

Del lado nuestro basta una llamada de prueba a un celular. Lo que miramos:

- El `INVITE` sale hacia `190.24.47.209:5060` y el gateway responde **`200 OK`**.
- Un `401`/`403` significa que la cuenta o la IP no están autorizadas, o que el CLI no le
  sirve (punto 2).
- Que haya **audio en los dos sentidos**, no solo que el CDR diga `ANSWERED`. Audio mudo o
  en un solo sentido apunta al punto 6 (RTP/firewall).

Contacto por nuestro lado: gerencia@mcmasociados.com
