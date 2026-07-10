"""
Normalizador de recursos FHIR del visor.

Convierte cada recurso crudo que devuelve el Ministerio en un diccionario
plano con solo los campos que el visor muestra. Así el frontend no tiene que
entender FHIR: recibe datos ya listos para pintar.

Cada función es defensiva: si un campo falta, devuelve "" o [] en vez de
reventar. Los recursos del Ministerio pueden venir incompletos.
"""


# ---------- helpers de extracción ----------

def _coding(concepto):
    """Primer coding de un CodeableConcept -> (code, display)."""
    if not isinstance(concepto, dict):
        return "", ""
    for c in concepto.get("coding", []) or []:
        return c.get("code", ""), c.get("display", "") or concepto.get("text", "")
    return "", concepto.get("text", "")


def _texto(concepto):
    """Texto legible de un CodeableConcept."""
    if not isinstance(concepto, dict):
        return ""
    _, disp = _coding(concepto)
    return disp or concepto.get("text", "")


def _nombre(recurso):
    """Nombre humano de un Patient/Practitioner."""
    nombres = recurso.get("name") or []
    if not nombres:
        return recurso.get("id", "")
    n = nombres[0]
    if n.get("text"):
        return n["text"]
    dado = " ".join(n.get("given", []) or [])
    return f"{dado} {n.get('family', '')}".strip()


def _fecha(*valores):
    """Primer valor de fecha no vacío, recortado a AAAA-MM-DD HH:MM."""
    for v in valores:
        if v:
            return str(v).replace("T", " ")[:16]
    return ""


def _identificador(recurso):
    ids = recurso.get("identifier") or []
    if ids:
        return ids[0].get("value", "")
    return ""


# ---------- normalizadores por tipo ----------

def patient(r):
    return {
        "nombre": _nombre(r),
        "documento": _identificador(r),
        "sexo": r.get("gender", ""),
        "nacimiento": r.get("birthDate", ""),
        "telefono": next((t.get("value", "") for t in r.get("telecom", []) or []), ""),
    }


def practitioner(r):
    return {
        "nombre": _nombre(r),
        "documento": _identificador(r),
    }


def organization(r):
    return {
        "nombre": r.get("name", ""),
        "identificador": _identificador(r),
    }


def encounter(r):
    clase = r.get("class") or {}
    # referencia al médico que atendió (participant)
    medico_ref = ""
    for p in r.get("participant", []) or []:
        ind = p.get("individual") or {}
        ref = ind.get("reference", "")
        if isinstance(ref, str) and "Practitioner" in ref:
            medico_ref = ref
            break
    diags = []
    for d in r.get("diagnosis", []) or []:
        cond = d.get("condition", {}) or {}
        diags.append(cond.get("reference", "") or cond.get("display", ""))
    tipos = [_texto(t) for t in r.get("type", []) or []]
    return {
        "clase": clase.get("display", "") or clase.get("code", ""),
        "estado": r.get("status", ""),
        "inicio": _fecha((r.get("period") or {}).get("start")),
        "fin": _fecha((r.get("period") or {}).get("end")),
        "tipos": [t for t in tipos if t],
        "motivo": ", ".join(_texto(rc) for rc in r.get("reasonCode", []) or [] if _texto(rc)),
        "num_diagnosticos": len(diags),
        "medico_ref": medico_ref,
    }


def condition(r):
    code, disp = _coding(r.get("code", {}))
    return {
        "codigo": code,
        "descripcion": disp,
        "estado_clinico": _texto(r.get("clinicalStatus", {})),
        "verificacion": _texto(r.get("verificationStatus", {})),
        "inicio": _fecha(r.get("onsetDateTime"), r.get("recordedDate")),
    }


def allergy(r):
    code, disp = _coding(r.get("code", {}))
    reacciones = []
    for reac in r.get("reaction", []) or []:
        for m in reac.get("manifestation", []) or []:
            t = _texto(m)
            if t:
                reacciones.append(t)
    return {
        "sustancia": disp or code,
        "criticidad": r.get("criticality", ""),
        "estado_clinico": _texto(r.get("clinicalStatus", {})),
        "reacciones": reacciones,
    }


def _medication_nombre(r):
    cc = r.get("medicationCodeableConcept")
    if cc:
        return _texto(cc)
    ref = r.get("medicationReference") or {}
    return ref.get("display", "")


def medication_statement(r):
    dosis = ""
    for d in r.get("dosage", []) or []:
        if d.get("text"):
            dosis = d["text"]; break
    return {
        "medicamento": _medication_nombre(r),
        "estado": r.get("status", ""),
        "dosis": dosis,
        "periodo": _fecha((r.get("effectivePeriod") or {}).get("start"), r.get("effectiveDateTime")),
    }


def medication_request(r):
    dosis = ""
    for d in r.get("dosageInstruction", []) or []:
        if d.get("text"):
            dosis = d["text"]; break
    return {
        "medicamento": _medication_nombre(r),
        "estado": r.get("status", ""),
        "dosis": dosis,
        "fecha": _fecha(r.get("authoredOn")),
    }


def medication_administration(r):
    return {
        "medicamento": _medication_nombre(r),
        "estado": r.get("status", ""),
        "fecha": _fecha(r.get("effectiveDateTime"), (r.get("effectivePeriod") or {}).get("start")),
    }


def procedure(r):
    code, disp = _coding(r.get("code", {}))
    return {
        "codigo": code,
        "procedimiento": disp,
        "estado": r.get("status", ""),
        "fecha": _fecha(r.get("performedDateTime"), (r.get("performedPeriod") or {}).get("start")),
    }


def observation(r):
    code, disp = _coding(r.get("code", {}))
    valor = ""
    if "valueQuantity" in r:
        q = r["valueQuantity"]
        valor = f"{q.get('value', '')} {q.get('unit', '')}".strip()
    elif "valueString" in r:
        valor = r["valueString"]
    elif "valueCodeableConcept" in r:
        valor = _texto(r["valueCodeableConcept"])
    return {
        "codigo": code,
        "observacion": disp,
        "valor": valor,
        "estado": r.get("status", ""),
        "fecha": _fecha(r.get("effectiveDateTime")),
    }


def risk_assessment(r):
    preds = []
    for p in r.get("prediction", []) or []:
        preds.append(_texto(p.get("outcome", {})))
    return {
        "estado": r.get("status", ""),
        "codigo": _texto(r.get("code", {})),
        "predicciones": [p for p in preds if p],
        "fecha": _fecha(r.get("occurrenceDateTime")),
    }


def service_request(r):
    code, disp = _coding(r.get("code", {}))
    return {
        "codigo": code,
        "servicio": disp,
        "estado": r.get("status", ""),
        "intencion": r.get("intent", ""),
        "fecha": _fecha(r.get("authoredOn")),
    }


def family_history(r):
    condiciones = []
    for c in r.get("condition", []) or []:
        t = _texto(c.get("code", {}))
        if t:
            condiciones.append(t)
    return {
        "parentesco": _texto(r.get("relationship", {})),
        "condiciones": condiciones,
    }


def document_reference(r):
    code, disp = _coding(r.get("type", {}))
    tiene_pdf = any(
        (c.get("attachment") or {}).get("data") or (c.get("attachment") or {}).get("url")
        for c in r.get("content", []) or []
    )
    return {
        "id": r.get("id", ""),
        "tipo": disp or r.get("description", "") or "Documento",
        "fecha": _fecha(r.get("date"))[:10],
        "estado": r.get("status", ""),
        "tiene_pdf": bool(tiene_pdf),
    }


# Mapa de tipo FHIR -> (clave de salida, función normalizadora)
NORMALIZADORES = {
    "Patient": ("pacientes", patient),
    "Practitioner": ("profesionales", practitioner),
    "Organization": ("organizaciones", organization),
    "Encounter": ("encuentros", encounter),
    "Condition": ("diagnosticos", condition),
    "AllergyIntolerance": ("alergias", allergy),
    "MedicationStatement": ("medicamentos", medication_statement),
    "MedicationRequest": ("prescripciones", medication_request),
    "MedicationAdministration": ("administraciones", medication_administration),
    "Procedure": ("procedimientos", procedure),
    "Observation": ("observaciones", observation),
    "RiskAssessment": ("factores_riesgo", risk_assessment),
    "ServiceRequest": ("ordenes", service_request),
    "FamilyMemberHistory": ("antecedentes_familiares", family_history),
    "DocumentReference": ("documentos", document_reference),
}


def normalizar(tipo, recurso):
    """Devuelve (clave, dict_normalizado) o (None, None) si el tipo no se maneja."""
    entrada = NORMALIZADORES.get(tipo)
    if not entrada:
        return None, None
    clave, fn = entrada
    try:
        return clave, fn(recurso)
    except Exception:
        return clave, None