#!/usr/bin/env python3
"""
Construye la version corregida del workflow "Flow Tatika, Colina del Viento - Conaring".

Entrada : JSON exportado del workflow en produccion (id m9mqIWluJay9qOWs)
Salida  : JSON listo para crear como workflow nuevo e inactivo en n8n

Objetivos (pedido del cliente):
  1. Crear los contactos correctamente en HubSpot
  2. No generar duplicados
  3. Si el contacto ya existe -> hs_lead_status = "Doble conversión"
  4. Registrar en las notas del contacto que paso, en cada paso
"""
import json, sys, copy

CRED_HS = {"hubspotAppToken": {"id": "haT6Hrg5ZUq5fRt7", "name": "HubSpot App Token account"}}

# Valores validos leidos de /crm/v3/properties/contacts en la cuenta real
PROYECTOS = ['PuertoViento', 'Colina Del Viento', 'Terrarium', 'Guayacán', 'Park200',
             'Tatika', 'Terrazul', 'Cesantías', 'Contempo', 'Embajador', 'Gualanday']

# ---------------------------------------------------------------- helpers

def node(wf, name):
    for n in wf['nodes']:
        if n['name'] == name:
            return n
    raise KeyError(name)

def add_note_node(wf, source_name, titulo, detalle, dx=0, dy=170):
    """Cuelga un nodo de nota en paralelo a source_name. No altera la cadena original."""
    src = node(wf, source_name)
    nn = f"Nota - {titulo}"
    body = (
        "={{ JSON.stringify({\n"
        "  properties: {\n"
        "    hs_timestamp: $now.toMillis(),\n"
        f"    hs_note_body: {json.dumps(titulo, ensure_ascii=False)} + ' - ' + {json.dumps(detalle, ensure_ascii=False)}\n"
        "      + '<br>Fecha: ' + $now.setZone('America/Bogota').toFormat('yyyy-LL-dd HH:mm')\n"
        "      + '<br>Origen: n8n / " + source_name.replace("'", "") + "'\n"
        "  },\n"
        "  associations: [{\n"
        "    to: { id: String($json.vid || $json.id || $json.properties?.hs_object_id || '') },\n"
        "    types: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 202 }]\n"
        "  }]\n"
        "}) }}"
    )
    wf['nodes'].append({
        "parameters": {
            "method": "POST",
            "url": "https://api.hubapi.com/crm/v3/objects/notes",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "hubspotAppToken",
            "sendBody": True, "specifyBody": "json", "jsonBody": body,
            "options": {"response": {"response": {"neverError": True}}},
        },
        "id": f"n0tec{abs(hash(nn)) % 10**8:08d}-0000-4000-8000-{abs(hash(source_name)) % 10**12:012d}",
        "name": nn,
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "position": [src['position'][0] + dx, src['position'][1] + dy],
        "credentials": CRED_HS,
        # una nota nunca debe tumbar la automatizacion
        "onError": "continueRegularOutput",
        "retryOnFail": True, "maxTries": 2, "waitBetweenTries": 2000,
    })
    # rama paralela: se agrega a la salida 0 sin quitar las conexiones existentes
    conns = wf['connections'].setdefault(source_name, {}).setdefault('main', [])
    while len(conns) < 1:
        conns.append([])
    if conns[0] is None:
        conns[0] = []
    conns[0].append({"node": nn, "type": "main", "index": 0})
    return nn


def main(src_path, out_path):
    wf = json.load(open(src_path))
    cambios = []

    # =========================================================
    # A. RAMA DE INGESTA: crear / deduplicar / doble conversion / nota
    # =========================================================

    # A1 -- Normalizacion: proyecto real (ya no fijo en "Tatika") y saneo de datos
    n = node(wf, 'Normalizar Datos3')
    n['parameters']['jsCode'] = r'''
// Normaliza el payload del formulario web / Chatwoot de Conaring.
// Salida: un unico item listo para el upsert en HubSpot.

const body = $input.first().json.body || {};

const txt = (v) => String(v ?? '').trim();

const nombre     = txt(body.name || body.nombre || body.fullName);
const email      = txt(body.email).toLowerCase();
const telefonoRaw= txt(body.phone_number || body.phoneNumber || body.celular || body.telefono);
const proyectoIn = txt(body.proyecto || body.project);

// --- validacion de email (unica llave de deduplicacion) -------------------
const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email);
if (!emailOk) {
  return { json: { _skip: true, _reason: 'Email ausente o invalido: no se puede deduplicar el contacto', _raw_body: body } };
}

// --- proyecto: se mapea contra los valores validos de HubSpot -------------
// Ojo: son los "value" internos exactos de la propiedad, con tildes incluidas.
const PROYECTOS = ['PuertoViento','Colina Del Viento','Terrarium','Guayacán','Park200',
                   'Tatika','Terrazul','Cesantías','Contempo','Embajador','Gualanday'];
const norm = (s) => String(s).toLowerCase().normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/g, '');
const proyecto = PROYECTOS.find(p => norm(p) === norm(proyectoIn)) || 'Tatika';

// --- nombre / apellido ----------------------------------------------------
// Si el formulario mando el email en el campo nombre, no lo copiamos.
let firstname = nombre, lastname = '';
if (nombre.includes('@')) {
  firstname = ''; lastname = '';
} else if (nombre.includes(' ')) {
  const parts = nombre.split(/\s+/);
  firstname = parts[0];
  lastname  = parts.slice(1).join(' ');
}

// --- telefono colombiano --------------------------------------------------
const normalizePhone = (phone) => {
  const str = txt(phone);
  if (!str) return '';
  if (str.startsWith('+')) return str.replace(/\s/g, '');
  const clean = str.replace(/\D/g, '');
  if (clean.length === 10 && clean.startsWith('3')) return '+57' + clean;
  if (clean.length === 12 && clean.startsWith('57')) return '+' + clean;
  return clean ? '+' + clean : '';
};
const mobilephone = normalizePhone(telefonoRaw);

return {
  json: {
    _skip: false,
    email, firstname, lastname,
    mobilephone, phone: mobilephone,
    proyecto,
    fuente: 'WEB CONARING',
    punto_de_contacto: 'WHATSAPP',
    _origen: 'Chat Web Conaring',
  }
};
'''.strip()
    cambios.append("Normalizar Datos3: proyecto real (no fijo en Tatika), email validado con regex, nombre no se llena con el email")

    # A2 -- Upsert: SOLO la llave. Nada mas se escribe aqui, para no pisar datos
    #       de un contacto que ya existe. HubSpot resuelve el duplicado del lado
    #       del servidor (atomico), asi que dos webhooks simultaneos no crean dos
    #       contactos.
    n = node(wf, 'HubSpot Upsert Contact3')
    n['parameters']['jsonBody'] = (
        "={{ JSON.stringify({ inputs: [ { idProperty: 'email', id: $json.email, "
        "properties: { email: $json.email } } ] }) }}"
    )
    n['retryOnFail'] = True; n['maxTries'] = 3; n['waitBetweenTries'] = 3000
    n['name'] = 'HubSpot Upsert Contact3'
    cambios.append("HubSpot Upsert Contact3: body con JSON.stringify (comillas en el nombre ya no rompen el JSON); "
                   "solo manda el email para no sobrescribir datos de contactos existentes; retry x3 ante 429")

    # A3 -- Decide que hacer segun si el contacto ya existia
    dec = {
        "parameters": {"jsCode": r'''
// Decide la accion a partir de la respuesta del upsert.
// HubSpot devuelve results[0].new = true cuando acaba de crear el contacto.

const up   = $input.first().json;
const res  = (up.results && up.results[0]) || {};
const lead = $('Normalizar Datos3').first().json;

const contactId = String(res.id || '');
if (!contactId) {
  throw new Error('El upsert no devolvio id de contacto: ' + JSON.stringify(up).slice(0, 400));
}

// respaldo por si la respuesta no trae "new": si createdAt == updatedAt es nuevo
let esNuevo = res.new;
if (typeof esNuevo !== 'boolean') {
  esNuevo = !!(res.createdAt && res.updatedAt && res.createdAt === res.updatedAt);
}

const fecha = $now.setZone('America/Bogota').toFormat('yyyy-LL-dd HH:mm');

// --- propiedades a escribir ----------------------------------------------
let props, nota;

if (esNuevo) {
  // Contacto nuevo: se completa toda la ficha.
  props = {
    firstname: lead.firstname,
    lastname: lead.lastname,
    phone: lead.phone,
    mobilephone: lead.mobilephone,
    proyecto: lead.proyecto,
    fuente: lead.fuente,
    punto_de_contacto: lead.punto_de_contacto,
    lifecyclestage: 'lead',
    hs_lead_status: 'Nuevo lead',
    automatizacion: 'Iniciada',
  };
  nota = '<b>Contacto creado por la automatización</b>'
       + '<br>Proyecto: ' + lead.proyecto
       + '<br>Fuente: ' + lead.fuente
       + '<br>Punto de contacto: ' + lead.punto_de_contacto
       + '<br>Teléfono: ' + (lead.mobilephone || 'no suministrado')
       + '<br>Estado inicial: Nuevo lead';
} else {
  // Ya existia: DOBLE CONVERSION. No se pisa ningun dato que el asesor
  // haya trabajado; solo se cambia el estado y se deja constancia.
  props = {
    hs_lead_status: 'Doble conversión',
  };
  nota = '<b>Doble conversión</b>'
       + '<br>El contacto volvió a registrarse por el formulario web.'
       + '<br>Proyecto de esta entrada: ' + lead.proyecto
       + '<br>Fuente: ' + lead.fuente
       + '<br>Estado cambiado a: Doble conversión'
       + '<br>No se sobrescribieron los datos existentes del contacto.';
}

// Solo se mandan propiedades con valor, para no borrar campos con cadenas vacias.
const limpias = {};
for (const [k, v] of Object.entries(props)) {
  if (v !== undefined && v !== null && v !== '') limpias[k] = v;
}

return {
  json: {
    contact_id: contactId,
    es_nuevo: esNuevo,
    es_doble_conversion: !esNuevo,
    email: lead.email,
    proyecto: lead.proyecto,
    props_patch: limpias,
    nota_html: nota + '<br>Fecha: ' + fecha,
  }
};
'''.strip()},
        "id": "dec15100-0000-4000-8000-000000000001",
        "name": "Decidir Accion (nuevo / doble conversion)",
        "type": "n8n-nodes-base.code", "typeVersion": 2,
        "position": [-5728, -7584],
    }

    # A4 -- Aplica las propiedades decididas
    patch = {
        "parameters": {
            "method": "PATCH",
            "url": "=https://api.hubapi.com/crm/v3/objects/contacts/{{ $json.contact_id }}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "hubspotAppToken",
            "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ properties: $json.props_patch }) }}",
            "options": {"response": {"response": {"neverError": True}}},
        },
        "id": "dec15100-0000-4000-8000-000000000002",
        "name": "Aplicar Cambios Contacto",
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "position": [-5504, -7584], "credentials": CRED_HS,
        "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 3000,
    }

    # A5 -- Nota en la ficha del contacto
    nota = {
        "parameters": {
            "method": "POST",
            "url": "https://api.hubapi.com/crm/v3/objects/notes",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "hubspotAppToken",
            "sendBody": True, "specifyBody": "json",
            "jsonBody": (
                "={{ JSON.stringify({\n"
                "  properties: {\n"
                "    hs_timestamp: $now.toMillis(),\n"
                "    hs_note_body: $('Decidir Accion (nuevo / doble conversion)').item.json.nota_html\n"
                "  },\n"
                "  associations: [{\n"
                "    to: { id: $('Decidir Accion (nuevo / doble conversion)').item.json.contact_id },\n"
                "    types: [{ associationCategory: 'HUBSPOT_DEFINED', associationTypeId: 202 }]\n"
                "  }]\n"
                "}) }}"
            ),
            "options": {"response": {"response": {"neverError": True}}},
        },
        "id": "dec15100-0000-4000-8000-000000000003",
        "name": "Registrar Nota HubSpot",
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "position": [-5280, -7584], "credentials": CRED_HS,
        "onError": "continueRegularOutput",
        "retryOnFail": True, "maxTries": 2, "waitBetweenTries": 2000,
    }

    wf['nodes'].extend([dec, patch, nota])

    # Respuesta OK con el detalle real de lo que paso
    n = node(wf, 'Respuesta OK3')
    n['parameters']['responseBody'] = (
        "={{ JSON.stringify({\n"
        "  success: true,\n"
        "  accion: $('Decidir Accion (nuevo / doble conversion)').item.json.es_nuevo ? 'creado' : 'doble_conversion',\n"
        "  hubspot_contact_id: $('Decidir Accion (nuevo / doble conversion)').item.json.contact_id,\n"
        "  email: $('Decidir Accion (nuevo / doble conversion)').item.json.email,\n"
        "  proyecto: $('Decidir Accion (nuevo / doble conversion)').item.json.proyecto,\n"
        "  nota_registrada: true\n"
        "}) }}"
    )
    n['position'] = [-5056, -7664]

    # recableado: upsert-ok -> decidir -> patch -> nota -> respuesta
    wf['connections']['¿Upsert exitoso?2'] = {"main": [
        [{"node": "Decidir Accion (nuevo / doble conversion)", "type": "main", "index": 0}],
        [{"node": "Respuesta Error3", "type": "main", "index": 0}],
    ]}
    wf['connections']['Decidir Accion (nuevo / doble conversion)'] = {
        "main": [[{"node": "Aplicar Cambios Contacto", "type": "main", "index": 0}]]}
    wf['connections']['Aplicar Cambios Contacto'] = {
        "main": [[{"node": "Registrar Nota HubSpot", "type": "main", "index": 0}]]}
    wf['connections']['Registrar Nota HubSpot'] = {
        "main": [[{"node": "Respuesta OK3", "type": "main", "index": 0}]]}
    cambios.append("Rama de ingesta: upsert -> Decidir Accion -> Aplicar Cambios -> Registrar Nota -> Respuesta OK")
    cambios.append("Contacto repetido: hs_lead_status = 'Doble conversion' (valor que ya existe en HubSpot) sin pisar datos")
    cambios.append("Contacto nuevo y repetido: se crea una nota en la ficha describiendo que paso")

    # =========================================================
    # B. NOTAS EN CADA CAMBIO DE ESTADO ("y asi sucesivamente")
    # =========================================================
    EVENTOS = {
        'En proceso|Seguimiento|Contactado':          ("Cliente respondio", "El cliente respondio al mensaje de WhatsApp. Pasa a seguimiento comercial."),
        'En proceso||Contactado':                     ("Cliente respondio", "El cliente respondio e indico su tipo de compra."),
        'Finalizada|Descalificado|Contactado':        ("Cliente no interesado", "El cliente respondio que no esta interesado. Queda descalificado."),
        'Iniciada||':                                 ("Automatizacion iniciada", "Se envio el primer mensaje de WhatsApp al cliente."),
        'Finalizo sin Exito|Descalificado|Contactado':("Sin respuesta", "La automatizacion termino sin respuesta del cliente."),
        'Finalizo sin Exito|Descalificado|ilocalizable':("Ilocalizable", "No se logro contactar al cliente por WhatsApp."),
        'Llamar|Seguimiento Tibio|Contactado':        ("Solicita llamada", "El cliente pidio que un asesor lo llame."),
        'Agendar Cita|Seguimiento Tibio|Contactado':  ("Solicita cita", "El cliente pidio agendar una visita al apartamento modelo."),
        'Error||':                                    ("Error en la automatizacion", "La automatizacion fallo al procesar a este contacto. Requiere revision manual."),
    }
    notas_agregadas = 0
    for nd in list(wf['nodes']):
        if not nd['name'].startswith('Crear y Actualizar Contacto'):
            continue
        if nd.get('disabled'):
            continue
        af = nd['parameters'].get('additionalFields', {})
        cps = {x['property']: x['value'] for x in af.get('customPropertiesUi', {}).get('customPropertiesValues', [])}
        clave = '|'.join([
            cps.get('automatizacion', '').lstrip('='),
            cps.get('gesti_n_comercial', '').lstrip('='),
            af.get('leadStatus', '').lstrip('='),
        ])
        titulo, detalle = EVENTOS.get(clave, ("Actualizacion de la automatizacion", "Estado: " + clave.replace('|', ' / ')))
        add_note_node(wf, nd['name'], f"{titulo} ({nd['name'].replace('Crear y Actualizar Contacto', 'CyA')})", detalle)
        notas_agregadas += 1
    cambios.append(f"Se agregaron {notas_agregadas} nodos de nota en paralelo, uno por cada cambio de estado del contacto")

    # =========================================================
    # C. FALLAS DE PRODUCCION CONFIRMADAS EN LAS EJECUCIONES
    # =========================================================

    # C1 -- Schedule cada 1 min => 429 de HubSpot (confirmado en ejecuciones reales)
    n = node(wf, 'Schedule Trigger')
    n['parameters'] = {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}
    cambios.append("Schedule Trigger: de 1 min a 15 min (los 429 de HubSpot vienen de aqui)")

    # C2 -- El poller solo buscaba Tatika, y sin marca de agua
    n = node(wf, '🔍 Buscar Últimos Contactos Tatika y Colina del Viento1')
    n['parameters']['jsonBody'] = json.dumps({
        "filterGroups": [{"filters": [
            {"propertyName": "proyecto", "operator": "IN", "values": ["Tatika", "Colina Del Viento"]},
            {"propertyName": "lastmodifieddate", "operator": "GTE",
             "value": "{{ $now.minus(20, 'minutes').toMillis() }}"},
        ]}],
        "properties": ["firstname", "lastname", "email", "phone", "proyecto",
                       "hs_object_id", "createdate", "lastmodifieddate", "automatizacion", "hs_lead_status"],
        "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
        "limit": 100,
    }, ensure_ascii=False, indent=2)
    n['parameters']['jsonBody'] = '=' + n['parameters']['jsonBody']
    n['retryOnFail'] = True; n['maxTries'] = 3; n['waitBetweenTries'] = 5000
    cambios.append("Buscador: incluye 'Colina Del Viento' (antes esa rama nunca recibia datos) "
                   "y filtra por lastmodifieddate de los ultimos 20 min en vez de traer los mismos 100 contactos cada vez")

    # C3 -- Paths de webhook con espacios => 404 en produccion
    for wn in ['Webhook10', 'Webhook11']:
        n = node(wf, wn)
        viejo = n['parameters'].get('path', '')
        nuevo = viejo.strip().replace(' ', '_')
        if viejo != nuevo:
            n['parameters']['path'] = nuevo
            cambios.append(f"{wn}: path {viejo!r} -> {nuevo!r} (el espacio hacia que la URL respondiera 404)")

    # C4 -- Espacio dentro de la URL de Chatwoot
    for cn in ['Actualizar contacto', 'Actualizar contacto2']:
        n = node(wf, cn)
        u = n['parameters']['url']
        if 'contacts/ {{' in u:
            n['parameters']['url'] = u.replace('contacts/ {{', 'contacts/{{')
            cambios.append(f"{cn}: se quito el espacio en la URL (.../contacts/ 123 -> .../contacts/123)")

    # C5 -- Zona horaria: sin esto los cron corren en UTC
    wf.setdefault('settings', {})['timezone'] = 'America/Bogota'
    cambios.append("settings.timezone = America/Bogota (los cron corrian en UTC: el de las 2PM disparaba a las 8AM)")

    # C6 -- Reintentos en el resto de llamadas a HubSpot dentro de bucles
    reint = 0
    for nd in wf['nodes']:
        if nd['type'] in ('n8n-nodes-base.hubspot',) and not nd.get('retryOnFail'):
            nd['retryOnFail'] = True; nd['maxTries'] = 3; nd['waitBetweenTries'] = 3000
            reint += 1
    cambios.append(f"retryOnFail x3 en {reint} nodos HubSpot (un 429 ya no tumba la ejecucion completa)")

    # -------- salida
    # La API publica de n8n solo acepta este subconjunto de settings.
    PERMITIDOS = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution',
                  'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow',
                  'timezone', 'executionOrder'}
    descartados = sorted(set(wf['settings']) - PERMITIDOS)
    wf['settings'] = {k: v for k, v in wf['settings'].items() if k in PERMITIDOS}
    if descartados:
        cambios.append(f"settings no soportados por la API publica omitidos: {descartados} "
                       "(hay que volver a fijarlos desde la UI de n8n)")

    salida = {
        "name": "Flow Tatika, Colina del Viento - Conaring [v2 CORREGIDO]",
        "nodes": wf['nodes'],
        "connections": wf['connections'],
        "settings": wf['settings'],
    }
    json.dump(salida, open(out_path, 'w'), ensure_ascii=False, indent=1)

    print(f"Nodos: {len(wf['nodes'])}  (originales 180)")
    print(f"Escrito: {out_path}\n")
    print("CAMBIOS APLICADOS")
    for i, c in enumerate(cambios, 1):
        print(f" {i:>2}. {c}")


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
