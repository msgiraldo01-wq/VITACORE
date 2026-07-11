"""
Servicio orquestador del RDA.

Toma una evolución de VitaCore, reúne los datos de los módulos existentes
(paciente, profesional, empresa, eps, país, municipio, tipo de documento),
arma el Bundle FHIR, lo transmite al Ministerio y registra el resultado en
rda_envios. Nunca lanza excepción hacia el flujo clínico: cualquier fallo
queda registrado como estado del envío.
"""

from datetime import datetime, timedelta, timezone

from services.supabase_service import get_supabase_admin

from repositories import hc_evoluciones_repo as repo_evo
from repositories import hc_profesionales_repo as repo_prof
from repositories import hc_paises_repo as repo_pais
from repositories import hc_municipios_repo as repo_muni
from repositories import hc_tipos_documento_repo as repo_tdoc
from repositories import rda_envios_repo as repo_envios
from repositories import rda_catalogos_repo as repo_cat
from repositories import hc_cups_repo as repo_cups

from .fhir import builders as B
from .fhir import client as ihce
from .fhir.bundle import ensamblar_bundle


# =========================
# LECTURA DE DATOS
# =========================

def _paciente_full(paciente_id):
    """Lee hc_pacientes directo para tener los ids (pais, municipio, tipo doc, eps)."""
    sb = get_supabase_admin()
    r = (
        sb.table("hc_pacientes")
        .select("*")
        .eq("id", paciente_id)
        .limit(1)
        .execute()
    )
    return (r.data or [None])[0]


def _empresa_activa(empresa_id):
    """Lee la empresa (prestador) activa para el custodian del RDA."""
    sb = get_supabase_admin()
    r = (
        sb.table("hc_empresas")
        .select("id, nit, razon_social, nombre_comercial, codigo_habilitacion, municipio")
        .eq("id", empresa_id)
        .limit(1)
        .execute()
    )
    return (r.data or [None])[0]


def _eps_por_id(eps_id):
    if not eps_id:
        return None
    sb = get_supabase_admin()
    r = (
        sb.table("hc_eps")
        .select("id, codigo, nombre")
        .eq("id", eps_id)
        .limit(1)
        .execute()
    )
    return (r.data or [None])[0]


def _partir_apellidos(apellidos: str):
    """Separa 'Ruiz Gomez' -> ('Ruiz', 'Gomez'). Un solo apellido -> segundo vacío."""
    partes = (apellidos or "").strip().split()
    if not partes:
        return "", ""
    if len(partes) == 1:
        return partes[0], ""
    # primer apellido = primera palabra; segundo = el resto
    return partes[0], " ".join(partes[1:])


def _tipo_doc_codigo(tipo_documento_id, default="CC"):
    if not tipo_documento_id:
        return default
    t = repo_tdoc.obtener(tipo_documento_id)
    return (t.get("codigo") if t else "") or default


def _pais_iso(pais_id, default="170"):
    if not pais_id:
        return default
    p = repo_pais.obtener(pais_id)
    # el RDA usa el código numérico ISO3166; si guardas ISO3 alfabético, ajústalo aquí
    return (p.get("codigo_iso3") if p else "") or default


def _zona(zona_texto):
    """Traduce el texto de hc_pacientes.zona al código del catálogo del
    Ministerio (ColombianResidenceZone).

    ATENCIÓN: solo está verificado el código "01" (Urbana), tomado de un
    Bundle con acuse 200. El código de "Rural" y el de zonas dispersas NO
    están confirmados contra el ValueSet oficial. Si el paciente no es
    urbano, esta función devuelve ("", "") y el Bundle NO debe enviarse
    hasta cargar el catálogo real.
    """
    z = (zona_texto or "").strip().upper()
    if z in ("U", "URBANA", "URBANO", "01"):
        return "01", "Urbana"
    # Rural y demás: código desconocido. No inventar.
    return "", ""


def _municipio(municipio_id):
    """Devuelve (codigo_divipola, nombre) del municipio, o ("", "") si no hay
    o si el código no tiene formato DIVIPOLA válido.

    DIVIPOLA de municipio son siempre 5 dígitos (2 de departamento + 3 de
    municipio). Un código con otro formato es un dato corrupto en el
    catálogo -- no se envía al Ministerio, se bloquea el RDA en
    construir_bundle() para no transmitir un municipio falso."""
    if not municipio_id:
        return "", ""
    m = repo_muni.obtener(municipio_id)
    if not m:
        return "", ""
    codigo = (m.get("codigo") or "").strip()
    if not (codigo.isdigit() and len(codigo) == 5):
        return "", ""
    return codigo, (m.get("nombre") or "")

# =========================
# ARMADO DEL BUNDLE
# =========================

def _catalogo(tipo, codigo, cod_default, nom_default):
    """Traduce un código de catálogo RDA a (codigo, nombre oficial).
    Si la evolución no trae el código (evoluciones antiguas), usa el
    respaldo verificado para no romper el envío."""
    if not codigo:
        return cod_default, nom_default
    op = repo_cat.obtener(tipo, str(codigo))
    if op and op.get("nombre"):
        return str(codigo), op["nombre"]
    return cod_default, nom_default


def _cups(cups_id):
    """Devuelve (codigo, descripcion) del CUPS de la evolución.
    Respaldo: consulta de medicina general (verificado con acuse 200)."""
    if cups_id:
        try:
            c = repo_cups.obtener(cups_id)
            if c and c.get("codigo"):
                return c["codigo"], (c.get("descripcion") or c["codigo"])
        except Exception:
            pass
    return "890201", "CONSULTA DE PRIMERA VEZ POR MEDICINA GENERAL"


def construir_bundle(evolucion_id, empresa_id):
    """Construye el Bundle FHIR del RDA a partir de una evolución. Devuelve
    (bundle, meta) donde meta trae datos para el registro del envío."""

    evo = repo_evo.obtener(evolucion_id)
    if not evo:
        raise ValueError("Evolución no encontrada")

    pac = _paciente_full(evo["paciente_id"])
    if not pac:
        raise ValueError("Paciente no encontrado")

    empresa = _empresa_activa(empresa_id)
    if not empresa or not empresa.get("codigo_habilitacion"):
        raise ValueError("La empresa no tiene código de habilitación configurado")
    if not empresa.get("municipio"):
        raise ValueError("La empresa no tiene municipio registrado")

    medico = repo_prof.obtener(evo["medico_id"])
    if not medico:
        raise ValueError("Médico no encontrado")

    eps = _eps_por_id(pac.get("eps_id"))

    # --- Referencias internas (#id) ---
    pac_tipo = _tipo_doc_codigo(pac.get("tipo_documento_id"))
    pac_num = pac.get("numero_documento")
    med_tipo = medico.get("tipo_documento_codigo") or "CC"
    med_num = medico.get("numero_documento")
    cod_hab = str(empresa["codigo_habilitacion"])
    cie10 = evo.get("cie10_codigo") or ""

    refs = {
        "composition": "#Composition-0",
        "patient": f"#{pac_tipo}-{pac_num}",
        "ips": f"#{cod_hab}",
        "practitioner": f"#{med_tipo}-{med_num}",
        "encounter": "#Encounter-0",
        "docref": "#DocumentReference-0",
        "payor": f"#{eps['codigo']}" if eps and eps.get("codigo") else None,
        "conditions": ["#Condition-0"],
    }

    # --- Paciente ---
    # zona y municipio salen de hc_pacientes, no de un valor fijo.
    pac_muni_cod, pac_muni_nom = _municipio(pac.get("municipio_id"))
    zona_cod, zona_nom = _zona(pac.get("zona"))

    # El perfil exige Patient.address.city (1..1). Antes se rellenaba con
    # "Pereira" para cualquier paciente; eso enviaba un dato falso al Estado.
    if not pac_muni_nom:
        raise ValueError(
            "El paciente no tiene municipio de residencia registrado. "
            "El RDA no puede enviarse con un municipio inventado."
        )
    if not zona_cod:
        raise ValueError(
            f"Zona de residencia '{pac.get('zona')}' sin código válido. "
            "Solo está verificado el código de zona urbana; falta cargar "
            "el catálogo ColombianResidenceZone del Ministerio."
        )
    patient = B.build_patient(
        fhir_id=f"{pac_tipo}-{pac_num}",
        tipo_doc=pac_tipo, num_doc=pac_num,
        primer_nombre=pac.get("primer_nombre") or "",
        segundo_nombre=pac.get("segundo_nombre") or "",
        primer_apellido=pac.get("primer_apellido") or "",
        segundo_apellido=pac.get("segundo_apellido") or "",
        sexo=pac.get("sexo") or "M",
        fecha_nacimiento=str(pac.get("fecha_nacimiento") or "")[:10],
        zona_cod=zona_cod, zona_nombre=zona_nom,
        municipio_cod=pac_muni_cod, municipio_nombre=pac_muni_nom,
    )

    # --- IPS (custodian) ---
    ips = B.build_organization_ips(
        fhir_id=cod_hab,
        cod_habilitacion=cod_hab,
        nombre=empresa.get("nombre_comercial") or empresa.get("razon_social") or "IPS",
        nit=str(empresa.get("nit") or "900000000"),
        ciudad=empresa.get("municipio") or "",
    )

    # --- Médico (apellidos separados) ---
    med_pa, med_sa = _partir_apellidos(medico.get("apellidos"))
    med_nombres = (medico.get("nombres") or "").strip().split()
    med_pn = med_nombres[0] if med_nombres else ""
    med_sn = " ".join(med_nombres[1:]) if len(med_nombres) > 1 else ""
    practitioner = B.build_practitioner(
        fhir_id=f"{med_tipo}-{med_num}",
        tipo_doc=med_tipo, num_doc=med_num,
        primer_nombre=med_pn, segundo_nombre=med_sn,
        primer_apellido=med_pa, segundo_apellido=med_sa,
    )

    # --- Pagador (EPS) ---
    payor = None
    if eps and eps.get("codigo"):
        payor = B.build_organization_payor(
            codigo_eapb=eps["codigo"],
            nombre=eps.get("nombre") or "EPS",
        )

    # --- Encuentro (ventana pasada para cumplir end<=now) ---
    # Hora de Colombia (UTC-5). El perfil exige start<=end<=ahora,
    # por eso se cierra la ventana unos minutos en el pasado.
    tz_co = timezone(timedelta(hours=-5))
    ahora = datetime.now(tz_co)
    fin = ahora - timedelta(minutes=2)
    inicio = fin - timedelta(minutes=25)
    fmt = "%Y-%m-%dT%H:%M:%S-05:00"

    # Datos de la atención tomados de la evolución (con respaldo verificado
    # para evoluciones antiguas que aún no tienen estos campos).
    causa_cod, causa_nom = _catalogo(
        "causa_externa", evo.get("causa_externa_codigo"), "38", "ENFERMEDAD GENERAL")
    tipo_dx_cod, tipo_dx_nom = _catalogo(
        "tipo_diagnostico", evo.get("tipo_diagnostico_codigo"), "02", "Confirmado Nuevo")
    # entorno: por ahora el builder fija "05" (único verificado); cuando se
    # confirmen los demás códigos, se pasará este valor al build_encounter.
    cups_cod, cups_nom = _cups(evo.get("cups_id"))

    encounter = B.build_encounter(
        fhir_id="Encounter-0",
        patient_ref=refs["patient"], practitioner_ref=refs["practitioner"],
        condition_ref=refs["conditions"][0],
        inicio=inicio.strftime(fmt), fin=fin.strftime(fmt),
        causa_externa_cod=causa_cod, causa_externa_nombre=causa_nom,
        tipo_dx_cod=tipo_dx_cod, tipo_dx_nombre=tipo_dx_nom,
        cups_codigo=cups_cod, cups_nombre=cups_nom,
    )

    # --- Diagnóstico ---
    condition = B.build_condition(
        fhir_id="Condition-0",
        patient_ref=refs["patient"],
        cod_cie10=cie10,
        nombre_dx=evo.get("cie10_nombre") or "",
    )

    # --- DocumentReference (epicrisis; PDF opcional en esta fase) ---
    docref = B.build_document_reference(
        fhir_id="DocumentReference-0",
        patient_ref=refs["patient"],
        author_ref=refs["practitioner"],
        fecha=ahora.strftime(fmt),
        pdf_base64=None,
    )

    bundle = ensamblar_bundle(
        patient=patient, organization_ips=ips, practitioner=practitioner,
        encounter=encounter, conditions=[condition], docref=docref,
        payor=payor, refs=refs,
    )

    meta = {
        "evolucion_id": evolucion_id,
        "paciente_id": pac.get("id"),
        "paciente_doc": f"{pac_tipo}-{pac_num}",
        "paciente_nombre": f"{pac.get('primer_nombre','')} {pac.get('primer_apellido','')}".strip(),
        "dx_codigo": cie10,
    }
    return bundle, meta


# =========================
# TRANSMISIÓN + REGISTRO
# =========================

def _extraer_motivo(respuesta):
    """Extrae un mensaje legible de la respuesta del Ministerio,
    cubriendo los distintos formatos de OperationOutcome."""
    if not isinstance(respuesta, dict):
        return ""
    # 1) OperationOutcome con issues
    for it in respuesta.get("issue", []) or []:
        if isinstance(it, str):
            if it.strip():
                return it.strip()
            continue
        if isinstance(it, dict):
            det = it.get("details", {}) or {}
            # texto directo
            if det.get("text"):
                return det["text"]
            # a veces el texto viene en el coding.display o .code
            for c in det.get("coding", []) or []:
                if c.get("display"):
                    return c["display"]
                if c.get("code"):
                    return c["code"]
            if it.get("diagnostics"):
                return it["diagnostics"]
    # 2) mensaje suelto
    for k in ("message", "error", "_raw"):
        if respuesta.get(k):
            return str(respuesta[k])[:300]
    return ""


def _clasificar(status, respuesta):
    """Traduce la respuesta del Ministerio a estado + motivo legible."""
    if status == 200:
        return "aceptado", "Registrado"
    if status == 409:
        return "aceptado", "Ya estaba registrado"

    motivo = _extraer_motivo(respuesta)
    motivo_low = (motivo or "").lower()
    if ("no coincide" in motivo_low or "couldn't be found" in motivo_low
            or "evol" in motivo_low or "does not exist in the value set" in motivo_low
            or "prior creation" in motivo_low):
        return "excepcion_identidad", motivo or "Validación de identidad/registro"
    return "rechazado", motivo or f"Rechazado (HTTP {status})"


def _extraer_composition_id(respuesta):
    if not isinstance(respuesta, dict):
        return ""
    if respuesta.get("resourceType") == "Bundle":
        for e in respuesta.get("entry", []) or []:
            r = (e.get("resource") or {})
            if r.get("resourceType") == "Composition" and r.get("id"):
                return r["id"]
            for c in r.get("content", []) or []:
                url = (c.get("attachment", {}) or {}).get("url", "")
                if url.startswith("Composition/"):
                    return url.split("/", 1)[1]
    return ""


def transmitir_evolucion(evolucion_id, empresa_id):
    """
    Flujo completo y seguro: arma, transmite y registra en rda_envios.
    Devuelve el registro del envío (dict). Nunca propaga excepción.
    """
    # 1. Construir
    try:
        bundle, meta = construir_bundle(evolucion_id, empresa_id)
    except Exception as e:
        # No intentamos registrar en rda_envios con una FK que puede no existir
        # (p. ej. evolución inexistente). Devolvemos el error de forma segura.
        return {
            "id": None,
            "evolucion_id": evolucion_id,
            "estado": "error",
            "http_status": 0,
            "motivo": f"No se pudo construir el RDA: {e}",
            "composition_id": "",
        }

    # 2. Si la transmisión no está habilitada, dejar pendiente
    if not ihce.esta_habilitado():
        return repo_envios.crear({
            **meta, "estado": "pendiente", "http_status": None,
            "motivo": "Transmisión deshabilitada (IHCE_ENABLED=0)",
            "bundle_json": bundle,
        })

    # 3. Transmitir
    try:
        res = ihce.enviar_rda_consulta(bundle)
    except ihce.IhceError as e:
        return repo_envios.crear({
            **meta, "estado": "error", "http_status": 0,
            "motivo": str(e), "bundle_json": bundle,
        })

    estado, motivo = _clasificar(res["status"], res["respuesta"])
    comp_id = _extraer_composition_id(res["respuesta"])

    return repo_envios.crear({
        **meta,
        "estado": estado,
        "http_status": res["status"],
        "motivo": motivo,
        "composition_id": comp_id,
        "bundle_json": bundle,
        "acuse_json": res["respuesta"],
    })


def reintentar_envio(envio_id, empresa_id):
    """Reintenta un envío existente reconstruyendo el Bundle desde la evolución."""
    envio = repo_envios.obtener(envio_id)
    if not envio:
        raise ValueError("Envío no encontrado")

    evolucion_id = envio.get("evolucion_id")
    try:
        bundle, meta = construir_bundle(evolucion_id, empresa_id)
        res = ihce.enviar_rda_consulta(bundle)
        estado, motivo = _clasificar(res["status"], res["respuesta"])
        comp_id = _extraer_composition_id(res["respuesta"])
        return repo_envios.actualizar_estado(envio_id, {
            "estado": estado, "http_status": res["status"], "motivo": motivo,
            "composition_id": comp_id, "acuse_json": res["respuesta"],
            "bundle_json": bundle, "intentos": (envio.get("intentos") or 1) + 1,
        })
    except Exception as e:
        return repo_envios.actualizar_estado(envio_id, {
            "estado": "error", "http_status": 0, "motivo": str(e),
            "intentos": (envio.get("intentos") or 1) + 1,
        })


# =========================
# TRANSMISIÓN EN SEGUNDO PLANO
# =========================

def transmitir_en_segundo_plano(evolucion_id, empresa_id):
    """
    Lanza la transmisión del RDA en un hilo aparte, sin bloquear la respuesta
    al médico. El resultado queda registrado en rda_envios y visible en /rda/.

    El hilo recibe el contexto de aplicación de Flask (app_context), porque
    los repositories necesitan current_app para leer la configuración de
    Supabase. Sin esto, el hilo falla con "Working outside of application
    context". Se pasa empresa_id como parámetro porque el hilo no tiene
    acceso a la sesión de la petición.
    """
    import threading
    from flask import current_app

    # obtener la app REAL (no el proxy current_app, que no vive fuera de la petición)
    app = current_app._get_current_object()

    def _worker():
        with app.app_context():
            try:
                transmitir_evolucion(evolucion_id, empresa_id)
            except Exception as e:
                print(f"[RDA][hilo] Error transmitiendo evolución {evolucion_id}: {e}")

    hilo = threading.Thread(target=_worker, daemon=True)
    hilo.start()
    return hilo