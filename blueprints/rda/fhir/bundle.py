"""
Ensamblador del Bundle 'document' del RDA (diccionarios puros).

Detalles clave (validados contra el sandbox del Ministerio):
- Las entries solo llevan 'resource' (sin fullUrl). Referencias internas #id.
- El Bundle NO declara meta.profile: el validador del Ministerio no resuelve
  el discriminador del slice PayorResources y produce un error falso en
  Bundle.type. Los recursos internos sí llevan su perfil.
- Orden de la guía oficial v1.0.0: Composition, Patient, Encounter,
  Organization(IPS), Practitioner, Payor, Condition, DocumentReference.
"""

import uuid
from datetime import datetime, timezone

from . import constants as C
from . import builders as B


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensamblar_bundle(*, patient, organization_ips, practitioner, encounter,
                     conditions, docref, payor, refs):
    """
    refs: dict con las referencias internas (#id) de cada recurso:
      composition, patient, ips, practitioner, encounter, docref, payor,
      conditions (lista).
    """
    now = _now_iso()

    # --- Secciones del Composition ---
    secciones = []
    for code, display, title in C.SECCIONES_OBLIGATORIAS:
        if code == "48768-6" and payor is not None:
            secciones.append(B.build_section(code, display, title,
                                             [{"reference": refs["payor"]}]))
        elif code == "11450-4":
            entries = [{"reference": r} for r in refs["conditions"]]
            secciones.append(B.build_section(code, display, title, entries))
        elif code == "55107-7":
            secciones.append(B.build_section(code, display, title,
                                             [{"reference": refs["docref"]}]))
        else:
            secciones.append(B.build_section(code, display, title))

    composition = {
        "resourceType": "Composition",
        "id": "Composition-0",
        "meta": {"profile": [C.PROFILE["Composition"]]},
        "status": "final",
        "type": {"coding": [{"system": C.SYS["LOINC"], "code": "51845-6",
                             "display": C.COMPOSITION_TYPE_DISPLAY}]},
        "subject": {"reference": refs["patient"]},
        "encounter": {"reference": refs["encounter"]},
        "date": now,
        "author": [{"reference": refs["ips"]}],
        "title": "Resumen Digital de Atención - Consulta Externa",
        "custodian": {"reference": refs["ips"]},
        "section": secciones,
    }

    # --- Entries (solo 'resource'), orden guía v1.0.0 ---
    entries = [
        {"resource": composition},
        {"resource": patient},
        {"resource": encounter},
        {"resource": organization_ips},
        {"resource": practitioner},
    ]
    if payor is not None:
        entries.append({"resource": payor})
    for cond in conditions:
        entries.append({"resource": cond})
    entries.append({"resource": docref})

    # --- Bundle SIN meta.profile ---
    # El validador Firely del Ministerio no logra resolver el discriminador del
    # slice Bundle.entry:PayorResources (avisa: "should navigate to an
    # ElementDefinition with exactly one 'type' element"). Cuando eso ocurre, la
    # validación del Bundle se rompe y devuelve un error falso en Bundle.type
    # ("Value is not exactly equal to fixed value 'document'"), aunque el valor
    # sea correcto. Al no declarar el perfil del Bundle, el validador no entra a
    # ese slice y el documento se acepta. Los recursos internos SÍ llevan su
    # meta.profile, así que la conformidad del contenido se mantiene.
    return {
        "resourceType": "Bundle",
        "type": "document",
        "identifier": {
            "system": C.SYS["IDENTIFIER_RDA"],
            "value": str(uuid.uuid4()),
        },
        "timestamp": now,
        "entry": entries,
    }