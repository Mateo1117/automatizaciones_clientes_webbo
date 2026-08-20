# MCM — Extensión 610, troncal PJSIP al gateway y ruta de salida

**Estado: NO APLICADO.** Esta configuración está pendiente de ejecutarse contra el PBX
`157.245.244.48`. Ver "Por qué no se aplicó" al final. Nada de lo descrito aquí ha sido
verificado contra el servidor.

Proyecto: `solvot_mcm_salud` · PBX: FreePBX sobre Asterisk 22 (solo PJSIP, `chan_sip` no existe).

---

## 1. Extensión 610 «Supervisión»

Crear desde la GUI: **Applications → Extensions → Add New → Add New PJSIP Extension**.

| Campo | Valor |
|---|---|
| User Extension | `610` |
| Display Name | `Supervisión` |
| Secret | ver abajo |
| Outbound CID | (vacío / heredar) |

**Secret propuesto** (32 chars, generado aleatoriamente — cámbialo si prefieres, o genera
otro en el servidor con `openssl rand -base64 24`):

```
CGdD24JoJY7NlFg3xvDP5UllPZj6fnPI
```

> Este secret es una *propuesta*. Hasta que la extensión no se cree realmente, no son
> credenciales válidas. Las credenciales reales son las que queden guardadas en el PBX.

### No debe pertenecer a ninguna cola

La 610 **no** se agrega a ninguna cola. La cola `701` debe seguir conteniendo únicamente
`601, 602, 603, 604`.

Verificación (la 610 no debe aparecer):

```bash
sudo asterisk -rx "queue show 701"
```

Y en la GUI: **Applications → Queues → 701 → Static Agents** debe listar solo 601-604.

### Consumo por la función de escucha

La función de escucha ya desplegada espera la extensión en `PBX_EXTENSIONS_SUPERVISION`.
Una vez creada, esa variable debe quedar en `610` y el servicio debe autenticarse con el
secret real registrado en el PBX.

---

## 2. Troncal PJSIP al gateway

**Connectivity → Trunks → Add Trunk → Add SIP (chan_pjsip) Trunk**

Pestaña **General**:

| Campo | Valor |
|---|---|
| Trunk Name | `gateway_mcm` |
| Outbound CallerID | (según lo que acepte el gateway) |

Pestaña **pjsip Settings → General**:

| Campo | Valor |
|---|---|
| Username | `101` |
| Secret | `73942850d11564862de74cddace36452` |
| Authentication | `Outbound` |
| Registration | `None` |
| SIP Server | `190.24.47.209` |
| SIP Server Port | `5060` |

`Registration: None` asume que el gateway identifica por IP. **Si el gateway exige
registro**, cambiar Registration a `Outbound` y volver a aplicar.

### Cómo saber cuál de los dos aplica

Con `Registration: None` **no existe registro que consultar**. Conviene tenerlo claro
antes de verificar:

- `pjsip show endpoints` → muestra el *endpoint* y su estado de alcanzabilidad
  (`Avail`/`Unavail`), que depende de que Qualify esté activo. No dice nada sobre registro.
- `pjsip show registrations` → esta es la que muestra registros salientes, y con
  `Registration: None` aparecerá **vacía**. Eso es lo esperado, no un fallo.

```bash
sudo asterisk -rx "pjsip show endpoints"
sudo asterisk -rx "pjsip show registrations"
sudo asterisk -rx "pjsip show endpoint gateway_mcm"
```

Criterio: si con `None` las llamadas salen y el endpoint queda `Avail`, está correcto.
Si el gateway responde `401/403` a los INVITE salientes, entonces exige registro → pasar a
`Outbound` y confirmar con `pjsip show registrations` que el estado es `Registered`.

---

## 3. Ruta de salida

**Connectivity → Outbound Routes → Add Outbound Route**

Pestaña **Route Settings**:

| Campo | Valor |
|---|---|
| Route Name | `salientes_co` |
| Trunk Sequence | `gateway_mcm` |

Pestaña **Dial Patterns**:

| prepend | prefix | match pattern |
|---|---|---|
| | | `3.` |
| | | `6.` |

`3.` cubre celulares de Colombia (10 dígitos, empiezan por 3) y `6.` los fijos bajo la
numeración de 10 dígitos.

### Nota sobre el solape con las extensiones 6xx

Las extensiones internas (601-604, 610) también empiezan por 6, pero **no hay conflicto**:
en Asterisk una coincidencia literal de extensión gana sobre un patrón, y además el match
es sobre la cadena completa — marcar `601` no coincide con un fijo de 10 dígitos como
`6012345678`. La marcación interna sigue funcionando igual.

---

## 4. Aplicar y verificar

```bash
sudo fwconsole reload
```

Verificación de la troncal (ver la nota de §2 sobre cuál comando aplica):

```bash
sudo asterisk -rx "pjsip show endpoints"
sudo asterisk -rx "pjsip show registrations"
```

Verificación de la ruta — que el patrón exista y apunte a la troncal:

```bash
sudo asterisk -rx "dialplan show outbound-allroutes" | head -40
```

Llamada de prueba a un celular, observando por dónde sale:

```bash
sudo asterisk -rvvv
# en otra sesión, o marcando desde la 610:
core set verbose 5
pjsip set logger on
# marcar el celular y confirmar en el log que el INVITE va a 190.24.47.209:5060
```

Confirmar en el CDR que la llamada salió por `gateway_mcm` y que hubo audio en ambos
sentidos (no solo `ANSWERED`).

---

## Por qué no se aplicó

El entorno remoto donde se ejecutó esta sesión no tiene forma de llegar al PBX:

- No hay cliente SSH instalado (`ssh`, `scp`, `sftp`, `ssh-keygen` no existen).
- La llave `~/.ssh/solvot-plataforma.key` no está presente; `~/.ssh/` está vacío.
- El puerto 22 de `157.245.244.48` no es alcanzable (timeout, sin ruta).
- La salida a internet pasa por un proxy HTTPS con allowlist: incluso `https://example.com`
  y el panel web del PBX devuelven `403 CONNECT tunnel failed`.

Por tanto ninguna de las tres tareas pudo ejecutarse ni verificarse. Este documento es la
configuración a aplicar, no un registro de cambios realizados.
