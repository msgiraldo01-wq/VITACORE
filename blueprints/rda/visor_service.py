"""
Servicio del visor de RDA — carga en dos fases.

Fase 1 (rápida)  · listar_atenciones(): hace solo las dos consultas al
    Ministerio y devuelve una lista de atenciones con lo que viene en el
    propio Composition (fecha, título, tipo, conteos). No baja recursos.

Fase 2 (bajo demanda) · detallar_atenciones(): recibe las referencias de
    unas pocas atenciones (las visibles) y baja + normaliza su contenido.

Así el usuario ve la lista en ~2-3 s y el detalle se completa por página,
sin bajar decenas de recursos de golpe.

Las credenciales salen del .env, nunca del cliente.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from .fhir import client as ihce
from . import visor_normalizer as norm


# Tipos de recurso que cuelgan de una atención (para la fase 2).
CLAVES_ATENCION = [
    "profesionales", "organizaciones", "diagnosticos", "alergias",
    "medicamentos", "prescripciones", "administraciones", "procedimientos",
    "observaciones", "factores_riesgo", "ordenes", "antecedentes_familiares",
    "documentos",
]


# ---------------------------------------------------------------------------
# Utilidades de referencias
# ---------------------------------------------------------------------------

def _ref_de(valor):
    """Extrae 'Tipo/id' de un objeto reference FHIR (ignora refs internas #id)."""
    if isinstance(valor, dict):
        r = valor.get("reference", "")
        if isinstance(r, str) and "/" in r and not r.startswith("#"):
            return r
    return None


def _referencias_de_composition(comp):
    """Todas las referencias externas que cuelgan de un Composition."""
    refs = set()

    for campo in ("encounter", "subject", "custodian"):
        r = _ref_de(comp.get(campo))
        if r:
            refs.add(r)

    for a in comp.get("author", []) or []:
        r = _ref_de(a)
        if r:
            refs.add(r)

    def _mirar(sec):
        for e in sec.get("entry", []) or []:
            r = _ref_de(e)
            if r:
                refs.add(r)
        for sub in sec.get("section", []) or []:
            _mirar(sub)

    for sec in comp.get("section", []) or []:
        _mirar(sec)

    return refs


def _conteos_de_composition(comp):
    """Cuenta entries por sección SIN bajar recursos, para los badges.
    Devuelve un dict aproximado por categoría."""
    # Mapa de código LOINC de sección -> categoría de badge
    seccion_a_badge = {
        "11450-4": "diagnosticos",
        "10160-0": "medicamentos",
        "48765-2": "alergias",
        "61146-1": "ordenes",
        "55107-7": "documentos",
    }
    conteo = {}
    for sec in comp.get("section", []) or []:
        code = ((sec.get("code") or {}).get("coding") or [{}])[0].get("code", "")
        n = len(sec.get("entry", []) or [])
        if n and code in seccion_a_badge:
            conteo[seccion_a_badge[code]] = conteo.get(seccion_a_badge[code], 0) + n
    return conteo


# ---------------------------------------------------------------------------
# Descarga y normalización de recursos
# ---------------------------------------------------------------------------

def _bajar_y_normalizar(referencias, token, max_paralelo=10):
    """Descarga en paralelo un conjunto de referencias y las normaliza.
    Devuelve {'Tipo/id': (clave, dato)}."""
    resultado = {}
    if not referencias:
        return resultado

    def _uno(ref):
        try:
            tipo, rid = ref.split("/", 1)
        except ValueError:
            return ref, None, None
        if tipo not in norm.NORMALIZADORES:
            return ref, None, None
        try:
            crudo = ihce.obtener_recurso(tipo, rid, token=token)
        except Exception:
            return ref, None, None
        if not crudo:
            return ref, None, None
        clave, dato = norm.normalizar(tipo, crudo)
        return ref, clave, dato

    with ThreadPoolExecutor(max_workers=max_paralelo) as ex:
        for fut in as_completed([ex.submit(_uno, r) for r in referencias]):
            ref, clave, dato = fut.result()
            if clave and dato:
                resultado[ref] = (clave, dato)
    return resultado


# ---------------------------------------------------------------------------
# FASE 1 — listar atenciones (rápido)
# ---------------------------------------------------------------------------

def listar_atenciones(tipo_doc, num_doc):
    """
    Consulta las dos operaciones del Ministerio y devuelve la lista de
    atenciones con lo que trae el propio Composition. No baja recursos.

    Cada atención incluye 'refs': las referencias que la fase 2 debe resolver.
    """
    resultados, _ = ihce.consultar_rda_completo(tipo_doc, num_doc)

    etiquetas = {
        "paciente": "Antecedentes manifestados por el paciente",
        "encuentros": "Encuentro clínico",
    }

    atenciones = []
    errores = {}
    paciente_ref = None

    for origen, res in resultados.items():
        if not res["ok"]:
            errores[origen] = res["error"]
            continue
        for e in (res["data"] or {}).get("entry", []) or []:
            comp = e.get("resource") or {}
            if comp.get("resourceType") != "Composition":
                continue

            if paciente_ref is None:
                paciente_ref = _ref_de(comp.get("subject"))

            fecha = (comp.get("date") or "").replace("T", " ")[:16]
            tipo = ((comp.get("type") or {}).get("coding") or [{}])[0].get("display", "")

            atenciones.append({
                "id": comp.get("id", ""),
                "tipo": etiquetas.get(origen, "Atención"),
                "titulo": comp.get("title") or tipo or "Resumen de atención",
                "subtipo": tipo,
                "fecha": fecha,
                "conteo": _conteos_de_composition(comp),
                "refs": sorted(_referencias_de_composition(comp)),
            })

    atenciones.sort(key=lambda a: a["fecha"], reverse=True)

    return {
        "paciente_ref": paciente_ref,
        "atenciones": atenciones,
        "errores": errores,
        "total": len(atenciones),
    }


# ---------------------------------------------------------------------------
# FASE 2 — detallar atenciones visibles (bajo demanda)
# ---------------------------------------------------------------------------

def detallar_atenciones(lista_refs, paciente_ref=None):
    """
    Recibe una lista de conjuntos de referencias (uno por atención visible)
    y devuelve el contenido normalizado de cada una, agrupado por atención.

    lista_refs: [{"id": "...", "refs": ["Encounter/x", "Condition/y", ...]}, ...]
    """
    # token único para todas las descargas de esta página
    token = ihce.obtener_token_actual()

    # juntar todas las referencias de la página (incluida la del paciente) y
    # bajarlas una sola vez, aunque se repitan entre atenciones
    todas = set()
    for a in lista_refs:
        todas |= set(a.get("refs") or [])
    if paciente_ref:
        todas.add(paciente_ref)

    cache = _bajar_y_normalizar(todas, token)

    # paciente (si se pidió)
    paciente = None
    if paciente_ref and paciente_ref in cache and cache[paciente_ref][0] == "pacientes":
        paciente = cache[paciente_ref][1]

    # armar el detalle de cada atención
    detalles = {}
    for a in lista_refs:
        contenido = {k: [] for k in CLAVES_ATENCION}
        encuentro = None
        medico = None

        for ref in a.get("refs") or []:
            if ref not in cache:
                continue
            clave, dato = cache[ref]
            if clave == "encuentros":
                encuentro = dato
            elif clave == "profesionales":
                if medico is None:
                    medico = dato
                contenido["profesionales"].append(dato)
            elif clave in contenido:
                contenido[clave].append(dato)

        # el médico puede venir del Encounter.participant
        if encuentro and encuentro.get("medico_ref") and medico is None:
            mref = encuentro["medico_ref"]
            if mref in cache and cache[mref][0] == "profesionales":
                medico = cache[mref][1]
            else:
                extra = _bajar_y_normalizar({mref}, token)
                if mref in extra and extra[mref][0] == "profesionales":
                    medico = extra[mref][1]

        detalles[a["id"]] = {
            "encuentro": encuentro,
            "medico": medico,
            "contenido": contenido,
        }

    return {"paciente": paciente, "detalles": detalles}


# ---------------------------------------------------------------------------
# Descarga de epicrisis (PDF)
# ---------------------------------------------------------------------------

def descargar_epicrisis(doc_ref_id):
    """Devuelve (bytes_pdf, nombre) de la epicrisis de un DocumentReference."""
    import base64

    doc = ihce.obtener_recurso("DocumentReference", doc_ref_id)
    if not doc:
        raise ValueError("Documento no encontrado en el Ministerio")

    for c in doc.get("content", []) or []:
        att = c.get("attachment") or {}
        if att.get("data"):
            try:
                return base64.b64decode(att["data"]), (att.get("title") or "epicrisis") + ".pdf"
            except Exception as e:
                raise ValueError(f"El adjunto no es un PDF válido: {e}")
    raise ValueError("El documento no tiene un PDF adjunto")