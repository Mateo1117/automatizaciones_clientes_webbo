# MCM — Extensión 610, troncal PJSIP al gateway y ruta de salida

**Estado: puntos 1, 2 y 3 aplicados el 21/8/2026.** Falta únicamente la llamada de prueba
que confirme audio en ambos sentidos. Detalle de lo aplicado y verificado al final de cada
sección. Referencia del PBX:
`pbx.mcmsolutions.com.co` (`157.245.244.48`).

Proyecto: `solvot_mcm_salud` · FreePBX 17 / Asterisk 22 (solo PJSIP, `chan_sip` no existe).

> **La fuente de verdad de la extensión 610 es
> `apps/bot/deploy/pbx/EXTENSION_610.md` en el repo `solvot_mcm_salud`.** Este documento
> se alinea con ella y añade lo que allí no está: la troncal al gateway y la ruta de
> salida. Si algo discrepa, manda la del repo del proyecto.

---

## 1. Extensión 610 «Supervisión»

### La 610 YA EXISTE — verificada y corregida el 21/8/2026

`pjsip show endpoint 610` en el PBX devuelve el endpoint, así que **no hay que
crearla**: recrearla por la GUI le cambiaría el secret y dejaría muda la escucha de Funza.
Lo que queda es cerrar tres desviaciones respecto a esta misma spec.

Correcto en la central: `webrtc: yes` (con `media_encryption: dtls`, `use_avpf: true`,
`rtcp_mux: true`, `ice_support: true`), `language: es_419`,
`callerid: "Supervision Funza" <610>`, `context: from-internal`.

| # | Observado | Esperado | Veredicto |
|---|---|---|---|
| 1 | `max_contacts: 1` + `remove_existing: true` | Max Contacts `2` | **CORREGIDA 21/8.** Los dos juntos hacen que un segundo registro no falle sino que **expulse al primero en silencio**: el supervisor abre el softphone del portal y la sesión anterior se cae sin aviso. Subir a `2` |
| 2 | `mailboxes: 610@device` | Voicemail `No` | **Descartada.** La 601 sale igual (`mailboxes: 601@device`), así que es del molde con que FreePBX genera estas extensiones, no señal de voicemail activo. Para cerrarlo del todo: `voicemail show users \| grep 610`, sin resultado = no hay buzón |
| 3 | `direct_media: true` | `false` | **CORREGIDA 21/8.** La 601 tiene `direct_media: false`: no es el estándar de la central, la 610 es la excepción. En WebRTC el navegador negocia DTLS-SRTP y no puede hacer media directa con un endpoint que no lo hable, así que el reinvite es candidato a audio en un solo sentido. Ponerla en `No` (Advanced → Direct Media) |

Contrastado contra la 601 el 21/8/2026 — un agente que funciona hoy. Es lo que permitió
descartar la #2 y confirmar la #3: sin ese contraste, las dos parecían igual de sospechosas.

`Unavailable` y `0 of inf`, sin línea `Contact`, **no es un fallo**: no hay nada registrado en
ese momento. Es lo esperado si nadie tiene abierto el softphone del portal.

**Aislamiento verificado el 21/8/2026**: `asterisk -rx "queue show" | grep -c 610` devuelve
`0`. La 610 no es miembro de ninguna cola —ni la 700, ni la 701, ni la 702—, que es el
requisito de seguridad del que depende todo lo demás: no le van a entrar llamadas de
pacientes.

Las dos correcciones se aplicaron por base de datos, que es la fuente de verdad de las
extensiones en FreePBX (los `.conf` de pjsip se regeneran en cada reload):

```bash
mysql asterisk -e "UPDATE sip SET data='2'  WHERE id='610' AND keyword='max_contacts';"
mysql asterisk -e "UPDATE sip SET data='no' WHERE id='610' AND keyword='direct_media';"
fwconsole reload
```

Verificado después del reload: `max_contacts : 2` y `direct_media : false`. Valores
anteriores, por si hiciera falta volver: `1` y `yes`.

**PUNTO 1 CERRADO (21/8/2026)**, de las dos puntas: central y bot. La variable
`PBX_EXTENSIONS_SUPERVISION={"610":"<secret>"}` quedó guardada y desplegada en el servicio
del bot de Funza (EasyPanel → Environment, no por `docker service update`).

Va **solo** en el bot de Funza. Una por hospital: 610 Funza, 410 La Mesa, 510 Madrid. Si se
declarara la 610 en los tres, cualquier administrador del portal de otro hospital podría
pedirle a su propio portal el secret de la 610 —`adminSoftphone.js` fusiona
`PBX_EXTENSIONS` y `PBX_EXTENSIONS_SUPERVISION` y los entrega por
`/admin/softphone/config`— y registrarse con él en la central compartida.

> Matiz sobre el aislamiento, porque `EXTENSION_610.md` lo simplifica: declarar la 610 en
> otro tenant **no** permitiría oír llamadas de Funza desde la app. Eso lo corta
> `PBX_EXTENSIONS`, ya que `escuchaLlamadas.js:249` comprueba que el canal esté entre las
> llamadas activas de ese hospital antes de pinchar nada. La variable de supervisión
> gobierna qué extensión sirve de oreja y a quién se le entrega su clave.

Verificación pendiente de la escucha: que en el arranque del bot ya no salga «sin extensión
de supervisión», y la prueba de punta a punta de `EXTENSION_610.md` (agente en llamada →
Cola en vivo → Escuchar → audio en ambos sentidos → Terminar escucha corta solo la pata del
supervisor).

Para sacar el secret de **Applications → Extensions → 610 → Secret** para
`PBX_EXTENSIONS_SUPERVISION` en EasyPanel. No hace falta que salga de la central ni del
panel.

<details>
<summary>Los pasos de creación, por si hiciera falta rehacerla (o para la 410 y la 510)</summary>

**Applications → Extensions → Add Extension → Add New SIP (chan_pjsip)**

| Pestaña | Campo | Valor |
|---|---|---|
| General | User Extension | `610` |
| General | Display Name | `Supervisión Funza` |
| General | Secret | ver abajo |
| General | Language | `es_419` (igual que 601-604) |
| Advanced | **Enable WebRTC** | **Yes** |
| Advanced | Max Contacts | `2` |
| Voicemail | Enabled | **No** |

### La convención completa (los tres hospitales)

La central es **compartida**. Cada hospital tiene su propia extensión de supervisión, y es
justo eso lo que impide que un supervisor oiga a los pacientes de otro:

| Hospital | Agentes | Cola | Supervisión |
|---|---|---|---|
| Madrid | 501–508 | 700 | `510` (pendiente) |
| Funza | 601–604 | 701 | `610` |
| La Mesa | 401–404 | 702 | `410` (pendiente) |

Fuente: tabla de `IVR_LA_MESA.md` (líneas 10-11). Ojo: la tabla de convención de
`EXTENSION_610.md` está **incompleta** — omite La Mesa y nombra a Madrid solo como «el del
rango 500». Este documento trata la de `IVR_LA_MESA.md` como la buena.


**WebRTC es obligatorio**, no opcional: el softphone del portal se registra por
`wss://pbx.mcmsolutions.com.co:8089/ws`, y ese interruptor es el que activa DTLS,
transporte `wss`, cifrado de medios, AVPF, ICE y `rtcp_mux`. Sin él la 610 se crea pero el
portal no puede registrarla. (Esto no estaba en la primera versión de este documento.)

Luego **Submit → Apply Config**.

</details>

**Secret propuesto** (32 chars, aleatorio — o genera otro con `openssl rand -base64 24`):

```
CGdD24JoJY7NlFg3xvDP5UllPZj6fnPI
```

> Es una *propuesta*, no una credencial válida: hasta que la extensión no exista en el PBX
> no autentica nada. La credencial real es la que quede guardada en la central.

### No debe pertenecer a ninguna cola

Es el punto entero de la extensión: los agentes 601-604 son miembros **estáticos** de la
cola 701, así que si un supervisor registrara una de ellas, la cola empezaría a repartirle
llamadas de pacientes. El backend rechaza cualquier extensión que esté en la cola
(`escuchaLlamadas.js → iniciar`).

Tampoco: ningún Ring Group, ningún destino de ruta entrante, ningún Follow Me de un agente.

Verificación — debe imprimir `0`:

```bash
asterisk -rx "queue show" | grep -c 610
```

Comprueba **todas** las colas, no solo la 701; si imprime otra cosa, la 610 quedó dentro de
alguna y hay que sacarla antes de entregarla. Y que la 701 siga con solo 601-604:

```bash
asterisk -rx "queue show 701"
```

> **No lo verifiques por la GUI.** Las colas de esta central **no están en FreePBX**: viven
> en `/etc/asterisk/queues_custom.conf`, igual la 700 que la 701 y la 702
> (`IVR_LA_MESA.md` §3). Applications → Queues no las muestra, así que `queue show` por
> consola es la única comprobación válida. Una versión anterior de este documento mandaba
> mirar Static Agents en la GUI: era incorrecto.

### Declararla en el bot

En el entorno del servicio `bot` del tenant:

```
PBX_EXTENSIONS_SUPERVISION={"610":"<el secret de la 610>"}
```

> **Ojo con EasyPanel**: desplegar desde su interfaz reescribe las variables del servicio.
> Añádela en el panel, no con `docker service update`, o se pierde en el siguiente
> despliegue.

---

## 2. Troncal PJSIP al gateway

**Connectivity → Trunks → Add Trunk → Add SIP (chan_pjsip) Trunk**

| Pestaña | Campo | Valor |
|---|---|---|
| General | Trunk Name | `gw_co_out` |
| pjsip Settings → General | Username | `101` |
| pjsip Settings → General | Secret | `73942850d11564862de74cddace36452` |
| pjsip Settings → General | Authentication | `Outbound` |
| pjsip Settings → General | Registration | `None` |
| pjsip Settings → General | SIP Server | `190.24.47.209` |
| pjsip Settings → General | SIP Server Port | `5060` |

### Por qué `gw_co_out` y no `goip`

El troncal `goip` que aparece en la documentación **no es este gateway**: vive en el
**Issabel** (CentOS 7, `chan_sip`) del hospital del rango 500 —el ejemplo de click-to-call
de `README_DESPLIEGUE.md` usa la extensión `501`—, es una GSM box local y la propia doc lo
marca como **temporal** a la espera de `LIWA_OUT`. Este otro es un gateway SIP en IP
pública con cuenta `101` y secret, sobre el FreePBX 17 de Funza.

Reutilizar el nombre dejaría dos troncales homónimas en dos servidores distintos apuntando
a hardware distinto, y eso se paga al leer CDRs. `gw_co_out` dice qué es (gateway, Colombia,
salida), no asume un proveedor que no está confirmado, no choca con `goip` ni con el
reservado `LIWA_OUT`, y no queda obsoleto si cambia la IP.

Consecuencia operativa: `TRUNK_OUT` de `telefonia-service` **se queda como está** (`goip`).
Ese servicio sigue marcando por su Issabel; no se toca nada suyo con este cambio.

### Registro: None vs Outbound

`Registration: None` asume que el gateway identifica por IP. **Si el gateway exige
registro**, cambiar a `Outbound` y volver a aplicar.

Conviene tener claro qué comando mira qué, porque no son intercambiables:

- `pjsip show endpoints` → muestra el *endpoint* y su alcanzabilidad (`Avail`/`Unavail`),
  y solo si Qualify está activo. **No dice nada sobre registro.**
- `pjsip show registrations` → esta es la de registros salientes. Con `Registration: None`
  saldrá **vacía**, y eso es lo correcto, no un fallo.

```bash
asterisk -rx "pjsip show endpoints"
asterisk -rx "pjsip show registrations"
```

Criterio para decidir: si con `None` las llamadas salen, está bien. Si el gateway responde
`401`/`403` a los INVITE salientes, exige registro → pasar a `Outbound` y confirmar que
`pjsip show registrations` marca `Registered`.

---

## 3. Ruta de salida

**Connectivity → Outbound Routes → Add Outbound Route**

| Campo | Valor |
|---|---|
| Route Name | `salientes_co` |
| Trunk Sequence | `gw_co_out` |

Dial Patterns (match pattern, sin prepend ni prefix):

| match pattern | cubre |
|---|---|
| `3.` | celulares de Colombia (10 dígitos, empiezan por 3) |
| `6.` | fijos bajo la numeración de 10 dígitos |

### El solape con las extensiones 6xx no es problema

Las extensiones internas (601-604, 610) también empiezan por 6, pero no hay conflicto: en
Asterisk una coincidencia literal de extensión gana sobre un patrón, y el match es sobre la
cadena completa — marcar `601` no coincide con un fijo de 10 dígitos como `6012345678`. La
marcación interna sigue igual.

---

## 4. Aplicar y verificar

```bash
fwconsole reload
```

Que la ruta exista (hoy este comando devuelve vacío — es justo lo que se está arreglando):

```bash
asterisk -rx "dialplan show outbound-allroutes" | head -40
```

Llamada de prueba a un celular, mirando por dónde sale:

```bash
asterisk -rvvv
pjsip set logger on
# marcar y confirmar en el log que el INVITE va a 190.24.47.209:5060
```

Confirmar en el CDR que salió por la troncal nueva y que hubo audio en **ambos** sentidos,
no solo estado `ANSWERED`.

Cierre del círculo: con la ruta de salida viva, deja de ser cierto que "no hay alternativa
por celular" — el supuesto que `EXTENSION_610.md` da como razón para que la escucha tenga
que ir por la 610. La 610 sigue siendo la vía correcta (la escucha no debe salir de la
central), pero conviene actualizar esa frase en el repo del proyecto cuando esto quede
aplicado, o quedará contradiciendo la realidad.

---

## Por qué no se aplicó

El entorno remoto de esta sesión no puede llegar al PBX. Comprobado:

- No hay cliente SSH instalado (`ssh`, `scp`, `sftp`, `ssh-keygen` no existen).
- La llave `~/.ssh/solvot-plataforma.key` no está; `~/.ssh/` está vacío.
- El repo `solvot_mcm_salud` **tampoco** contiene material de llave privada (se buscó
  `BEGIN OPENSSH/RSA/EC PRIVATE KEY` en todo el árbol: cero resultados). Sus `.env.example`
  son plantillas con los valores en blanco y advierten de no commitear el `.env` real.
- `pbx.mcmsolutions.com.co` resuelve a `157.245.244.48`, pero el puerto 22 da timeout.
- La salida a internet pasa por un proxy HTTPS con allowlist: `https://example.com` y el
  panel web del PBX devuelven ambos `403 CONNECT tunnel failed`.

Es decir: el bloqueo no es la llave. Aunque estuviera, no hay cliente SSH ni ruta de red.
Este documento es la configuración a aplicar, no un registro de cambios realizados.


---

## Resultado de la aplicación — 21/8/2026

Aplicado por el GUI de FreePBX (`https://pbx.mcmsolutions.com.co/admin`) y verificado por
consola.

### Troncal `gw_co_out` — APLICADA y alcanzable

```
Endpoint:  gw_co_out                              Not in use    0 of inf
   OutAuth:  gw_co_out/101
  Contact:  gw_co_out/sip:101@190.24.47.209:5060  Avail  107.215
  Identify:  gw_co_out/gw_co_out
```

`Avail` con 107 ms de RTT: el gateway responde a los OPTIONS. **`Registration: None` es la
opción correcta** —identificación por IP, visible en la línea `Identify`— y no hizo falta
pasar a `Outbound`. `pjsip show registrations` devuelve `No objects found.`, que con `None`
es lo esperado.

Un campo se apartó de la primera versión de este documento: **Language Code = `es_419`**, no
`Default`. `IVR_LA_MESA.md` lo deja anotado («le pasó a Funza») y aquí pesa porque el
`Context` de la troncal es `from-pstn`: si algún día entran llamadas por ella, los anuncios
saldrían en inglés.

### Ruta `salientes_co` — APLICADA

`outbound-allroutes` incluye `outrt-1`, que contiene los dos patrones:

```
'_3.' => ... Set(_ROUTENAME=salientes_co) ... Gosub(macro-dialout-trunk,s,1(1,${EXTEN},,off))
'_6.' => ... Set(_ROUTENAME=salientes_co) ... Gosub(macro-dialout-trunk,s,1(1,${EXTEN},,off))
```

Verificado que pasa `${EXTEN}` **entero** y no `${EXTEN:1}`: los patrones quedaron en la
columna *match pattern* y no en *prefix*, que era el error a evitar —habría mandado al
gateway el número sin el primer dígito, fallando de forma confusa porque la llamada sí sale.

### Observación: esta central no tenía ninguna troncal en el GUI

`gw_co_out` es la única fila de Connectivity → Trunks. Pero la central sí recibe llamadas
hoy (los DID de Funza), así que **el camino de entrada está configurado fuera del GUI**,
igual que las colas viven en `queues_custom.conf`. Es el patrón de esta máquina: al depurar
llamadas entrantes, no buscar en Connectivity → Trunks.

### Pendiente

- **Llamada de prueba a un celular**, confirmando audio en **ambos** sentidos y no solo
  estado `ANSWERED` en el CDR.
- **Outbound CallerID** de la troncal quedó vacío a propósito, para no meter variables en la
  primera prueba. Si el gateway responde `401`/`403` al INVITE, el sospechoso principal no
  es la autenticación sino el CLI: la llamada sale con `<610>` como origen y muchos gateways
  rechazan un CLI que no sea un número válido de la línea. Solución: poner el DID de Funza
  (`6013288948`).
- **Maximum Channels** también vacío (sin tope). Si el gateway es una caja GSM con un número
  fijo de canales, conviene ponerle ese número: sin tope, una tanda de recordatorios lo
  satura y las llamadas fallan sin motivo aparente.


---

## INCIDENTE 21/8/2026 — la troncal tumbó los registros de toda la oficina

**Causa raíz: el GoIP y la oficina comparten la misma IP pública, `190.24.47.209`.** El
gateway es un aparato físico en la sede, detrás de la misma conexión a internet que los
puestos de trabajo.

Al crear la troncal, FreePBX generó automáticamente un objeto *identify*:

```
Identify:  gw_co_out/gw_co_out
     Match: 190.24.47.209/32
```

Asterisk identifica endpoints **por IP antes que por usuario** (orden por defecto
`ip,username,anonymous`). Así que cualquier `REGISTER` salido de la oficina se atribuía a la
troncal: el softphone mandaba `To: sip:507@...`, Asterisk decidía «esto es `gw_co_out`»,
buscaba un AOR llamado `507` entre los de esa troncal —que solo tiene `gw_co_out`— y
respondía **`404 Not Found`**.

De ahí las tres pistas que parecían contradictorias:

- Fallaban **todas** las extensiones de la sede, no una: el choque es por IP.
- **Desde fuera funcionaba**: sin coincidencia de IP, Asterisk identifica por usuario y
  encuentra el endpoint correcto.
- La extensión existía y estaba **idéntica a una que sí registraba** (507 vs 502): el
  problema nunca estuvo en la extensión.

Mitigación inmediata aplicada: **Disable Trunk = Yes**. Los registros volvieron al instante.

### Arreglo definitivo

Quitar el *identify* por IP de `gw_co_out`, **no** cambiar el orden global de identificación.

La troncal es solo de salida: para sacar llamadas, Asterisk manda el INVITE y se autentica
al ser desafiado, sin que el *identify* intervenga. El *identify* solo sirve para reconocer
**entrantes**, y las entrantes llegan por `provetel` (tres IP propias, sin choque). Se
estaban pagando los softphones de una sede entera por una función que no se usa.

Tocar `endpoint_identifier_order` global también funcionaría, pero afectaría a `provetel`,
que sostiene el tráfico real de la central (se le vieron 13 llamadas simultáneas). No es
sitio para experimentar.

### Restricción permanente, a tener presente

**El GoIP y la oficina van a seguir compartiendo IP pública.** Si en el futuro hace falta
que el gateway envíe llamadas **entrantes**, no se podrá resolver por IP sin volver a romper
los registros de la sede. Habría que pedir al proveedor una IP distinta para el equipo, o
recibir esas entrantes por otro camino.

### Lección para la próxima troncal

Antes de crear una troncal identificada por IP, comprobar si esa IP coincide con la red
desde la que se registran teléfonos. Es un dato que no aparece en ningún formulario y que
convierte un cambio rutinario en una caída de sede.


## Solución definitiva: troncal a mano + troncal Custom (21/8/2026)

`identify_by = Username` (etiqueta **Match Inbound Authentication** en el GUI) **no sirve**:
se guarda en la base, pero FreePBX genera el `identify` a partir del campo `sip_server`
igualmente. Comprobado encendiendo la troncal con ese valor puesto — el `Match:
190.24.47.209/32` volvió a aparecer.

Tampoco se tocó `endpoint_identifier_order` global: habría funcionado, pero afecta a
`provetel`, que sostiene el tráfico real de la central. Demasiado alcance para el problema.

La solución adoptada sigue **el patrón que ya usaba esta máquina para `provetel`**: definir la
troncal a mano en `/etc/asterisk/pjsip_custom.conf`, omitiendo a propósito la sección
`type=identify`, y exponerla a FreePBX como una troncal **Custom**.

1. **Borrada** la troncal PJSIP del GUI (era la que generaba el `identify`).
2. **Añadido** a `pjsip_custom.conf` el bloque `gw_co_out` con tres secciones —`endpoint`,
   `auth`, `aor`— y **ninguna** `identify`. Lleva un comentario explicando por qué, para que
   nadie la "complete" en el futuro.
3. **Creada** una troncal **Custom** en el GUI llamada `gw_co_out`, con dial string
   `PJSIP/$OUTNUM$@gw_co_out`. Las Custom solo generan dialplan, no configuración PJSIP: por
   eso no puede volver a crear el `identify`.
4. **Reapuntada** la ruta `salientes_co` a esa troncal.

Estado verificado tras el reload:

```
Identify:  provetel/provetel        <- solo provetel, gw_co_out ya no aparece
Endpoint:  gw_co_out                                     Not in use   0 of inf
   OutAuth:  gw_co_out/101
     Contact:  gw_co_out/sip:190.24.47.209:5060          Avail   101.237
OUT_1 = AMP:PJSIP/$OUTNUM$@gw_co_out
trunkid 1 | gw_co_out | custom
```

La troncal Custom reutilizó el `trunkid 1`, que es el índice que la ruta ya llamaba en
`macro-dialout-trunk`, así que la ruta quedó bien enganchada sin tocar los patrones.

### Detalle que confunde al verificar

`NonQual` e `Invalid` justo después de un reload **no son un fallo**: el qualify corre cada
60 s y aún no ha hecho su primer ciclo. A los pocos minutos el contacto pasó a `Avail` con
101 ms y el endpoint a `Not in use`. Comprobar antes de ese primer ciclo lleva a diagnosticar
un problema que no existe.

Lo mismo con el GUI: verificar **después** de pulsar Apply Config, no antes. Una comprobación
temprana mostró un `identify` que ya se había quitado, porque Asterisk seguía con la
configuración anterior.

### Copia de seguridad

Antes de tocar `pjsip_custom.conf` se guardó copia en `/root/pjsip_custom.conf.bak-<epoch>`.
Ese archivo contiene la troncal `provetel` de producción: **hacer copia siempre antes de
editarlo**. Vuelta atrás: restaurar la copia y `fwconsole reload`.
