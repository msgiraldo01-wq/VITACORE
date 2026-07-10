"""
Constructores de recursos FHIR (diccionarios puros, sin dependencias externas).
Cada función devuelve el dict del recurso, con la estructura EXACTA que el
sandbox del Ministerio aceptó (acuse 200) en el prototipo.
"""

from . import constants as C
from .cie10_co import normalizar_codigo, display_oficial

FB = C.FHIR_BASE


# =========================
# NARRATIVE (para secciones)
# =========================

def _narrative_datos():
    return {
        "status": "generated",
        "div": '<div xmlns="http://www.w3.org/1999/xhtml"><p>Seccion del RDA.</p></div>',
    }


def _narrative_vacia():
    return {
        "status": "generated",
        "div": ('<div xmlns="http://www.w3.org/1999/xhtml">No existen elementos '
                'conocidos para esta lista y/o el paciente no declara información</div>'),
    }


# =========================
# PATIENT
# =========================

def build_patient(*, fhir_id, tipo_doc, num_doc, primer_nombre, segundo_nombre,
                  primer_apellido, segundo_apellido, sexo, fecha_nacimiento,
                  nacionalidad_cod="170", nacionalidad_nombre="Colombia",
                  etnia_cod="6", etnia_nombre="Otras etnias",
                  discapacidad_cod="08", discapacidad_nombre="Sin discapacidad",
                  zona_cod="01", zona_nombre="Urbana",
                  municipio_cod="", municipio_nombre="",
                  # NOTA: etnia, discapacidad y zona siguen teniendo un valor por
                  # defecto porque el paciente aún no tiene esas columnas. Ese
                  # default es un dato inventado — ver sql/02_campos_rda.sql.
                  pais_nombre="Colombia"):
    given = [primer_nombre]
    if segundo_nombre:
        given.append(segundo_nombre)

    fam_ext = [{
        "url": f"{FB}/StructureDefinition/ExtensionFathersFamilyName",
        "valueString": primer_apellido,
    }]
    if segundo_apellido:
        fam_ext.append({
            "url": f"{FB}/StructureDefinition/ExtensionMothersFamilyName",
            "valueString": segundo_apellido,
        })

    # Detección robusta del sexo biológico (soporta M/Masculino/H/Hombre/1, etc.)
    s = str(sexo).strip().upper()
    if s in ("M", "MASCULINO", "H", "HOMBRE", "1", "01"):
        es_hombre = True
    elif s in ("F", "FEMENINO", "MUJER", "2", "02"):
        es_hombre = False
    else:
        es_hombre = s.startswith("M") or s.startswith("H")

    # --- address (solo si hay municipio) ---
    address = {
        "id": "HomeAddress-0",
        "extension": [{
            "url": f"{FB}/StructureDefinition/ExtensionResidenceZone",
            "valueCoding": {
                "system": f"{FB}/CodeSystem/ColombianResidenceZone",
                "code": zona_cod, "display": zona_nombre,
            },
        }],
        "use": "home",
        "type": "physical",
        "country": pais_nombre,
        "_country": {"extension": [{
            "url": f"{FB}/StructureDefinition/ExtensionCountryCode",
            "valueCoding": {"system": f"{FB}/CodeSystem/ISO31661",
                            "code": nacionalidad_cod},
        }]},
    }
    # city es obligatorio (cardinalidad 1..1) en el perfil del Ministerio.
    # Si el paciente no tiene municipio, el Bundle no debe construirse:
    # el servicio lo valida antes de llamar aquí.
    address["city"] = municipio_nombre
    if municipio_cod:
        address["_city"] = {"extension": [{
            "url": f"{FB}/StructureDefinition/ExtensionDivipolaMunicipality",
            "valueCoding": {"system": f"{FB}/CodeSystem/DIVIPOLA", "code": municipio_cod},
        }]}

    return {
        "resourceType": "Patient",
        "id": fhir_id,
        "meta": {"profile": [C.PROFILE["Patient"]]},
        "extension": [
            {
                "url": f"{FB}/StructureDefinition/ExtensionPatientNationality",
                "valueCoding": {"system": f"{FB}/CodeSystem/ISO31661",
                                "code": nacionalidad_cod, "display": nacionalidad_nombre},
            },
            {
                "url": f"{FB}/StructureDefinition/ExtensionPatientEthnicity",
                "valueCoding": {"system": f"{FB}/CodeSystem/ColombianEthnicGroup",
                                "code": etnia_cod, "display": etnia_nombre},
            },
            {
                "url": f"{FB}/StructureDefinition/ExtensionPatientDisability",
                "valueCoding": {"system": f"{FB}/CodeSystem/ColombianDisabilityClassification",
                                "code": discapacidad_cod, "display": discapacidad_nombre},
            },
        ],
        "identifier": [{
            "id": "NationalPersonIdentifier-0",
            "use": "official",
            "type": {"coding": [
                {"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                 "code": "PN", "display": "Person number"},
                {"system": f"{FB}/CodeSystem/ColombianPersonIdentifier",
                 "code": tipo_doc, "display": "Cédula ciudadanía"},
            ]},
            "system": f"{FB}/NamingSystem/RNEC",
            "value": str(num_doc),
        }],
        "active": True,
        "name": [{
            "use": "official",
            "family": primer_apellido,
            "_family": {"extension": fam_ext},
            "given": given,
        }],
        "gender": "male" if es_hombre else "female",
        "_gender": {"extension": [{
            "url": f"{FB}/StructureDefinition/ExtensionBiologicalGender",
            "valueCoding": {
                "system": f"{FB}/CodeSystem/ColombianGenderGroup",
                "code": "01" if es_hombre else "02",
                "display": "Hombre" if es_hombre else "Mujer",
            },
        }]},
        "birthDate": fecha_nacimiento,
        "deceasedBoolean": False,
        "address": [address],
    }


# =========================
# ORGANIZATION IPS (prestador / custodian)
# =========================

def build_organization_ips(*, fhir_id, cod_habilitacion, nombre, nit="900000000",
                           ciudad="", municipio_cod="66001", pais="Colombia"):
    return {
        "resourceType": "Organization",
        "id": fhir_id,
        "meta": {"profile": [C.PROFILE["OrgIPS"]]},
        "identifier": [
            {
                "id": "TaxIdentifier-0",
                "use": "official",
                "type": {"coding": [
                    {"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                     "code": "TAX", "display": "Tax ID number"},
                    {"system": f"{FB}/CodeSystem/ColombianOrganizationIdentifiers",
                     "code": "NIT", "display": "Número de Identificación Tributaria"},
                ]},
                "system": f"{FB}/NamingSystem/DIAN",
                "value": str(nit),
            },
            {
                "id": "HealthcareProviderIdentifier-0",
                "use": "official",
                "type": {"coding": [
                    {"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                     "code": "PRN", "display": "Provider number"},
                    {"system": f"{FB}/CodeSystem/ColombianOrganizationIdentifiers",
                     "code": "CodigoPrestador",
                     "display": "Código de habilitación de prestador de servicios de salud"},
                ]},
                "system": f"{FB}/NamingSystem/REPS",
                "value": str(cod_habilitacion),
            },
        ],
        "active": True,
        "type": [{"coding": [{
            "system": f"{FB}/CodeSystem/ProviderClass", "code": "IPS",
            "display": "Institución Prestadora de Servicios de Salud",
        }]}],
        "name": nombre,
        "address": [{
            "use": "work",
            "type": "physical",
            "city": ciudad,
            "_city": {"extension": [{
                "url": f"{FB}/StructureDefinition/ExtensionDivipolaMunicipality",
                "valueCoding": {"system": f"{FB}/CodeSystem/DIVIPOLA", "code": municipio_cod},
            }]},
            "country": pais,
        }],
    }


# =========================
# ORGANIZATION PAYOR (EPS / EAPB)
# =========================

def build_organization_payor(*, codigo_eapb, nombre):
    # El slice PayorResources la distingue de la IPS por su meta.profile.
    # id = código EAPB (mínima, como el molde oficial).
    return {
        "resourceType": "Organization",
        "id": str(codigo_eapb),
        "meta": {"profile": [C.PROFILE["OrgEAPB"]]},
        "name": nombre,
    }


# =========================
# PRACTITIONER
# =========================

def build_practitioner(*, fhir_id, tipo_doc, num_doc, primer_nombre, segundo_nombre,
                       primer_apellido, segundo_apellido, tipo_profesional="MED",
                       tipo_profesional_nombre="Médico"):
    given = [primer_nombre]
    if segundo_nombre:
        given.append(segundo_nombre)

    fam_ext = [{
        "url": f"{FB}/StructureDefinition/ExtensionFathersFamilyName",
        "valueString": primer_apellido,
    }]
    if segundo_apellido:
        fam_ext.append({
            "url": f"{FB}/StructureDefinition/ExtensionMothersFamilyName",
            "valueString": segundo_apellido,
        })

    return {
        "resourceType": "Practitioner",
        "id": fhir_id,
        "meta": {"profile": [C.PROFILE["Practitioner"]]},
        "identifier": [{
            "id": "NationalPersonIdentifier-0",
            "use": "official",
            "type": {"coding": [
                {"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
                 "code": "PN", "display": "Person number"},
                {"system": f"{FB}/CodeSystem/ColombianPersonIdentifier",
                 "code": tipo_doc, "display": "Cédula ciudadanía"},
            ]},
            "system": f"{FB}/NamingSystem/RNEC",
            "value": str(num_doc),
        }],
        "active": True,
        "name": [{
            "use": "official",
            "family": primer_apellido,
            "_family": {"extension": fam_ext},
            "given": given,
        }],
        "qualification": [{
            "code": {"coding": [{
                "system": f"{FB}/CodeSystem/TipoProfesional",
                "code": tipo_profesional, "display": tipo_profesional_nombre,
            }]},
        }],
    }


# =========================
# ENCOUNTER
# =========================

def build_encounter(*, fhir_id, patient_ref, practitioner_ref, condition_ref,
                    inicio, fin, cups_codigo="890201",
                    cups_nombre="CONSULTA DE PRIMERA VEZ POR MEDICINA GENERAL",
                    servicio_cod="328", servicio_nombre="MEDICINA GENERAL",
                    tipo_dx_cod="02", tipo_dx_nombre="Confirmado Nuevo",
                    causa_externa_cod="22", causa_externa_nombre="ACCIDENTE EN EL HOGAR"):
    return {
        "resourceType": "Encounter",
        "id": fhir_id,
        "meta": {"profile": [C.PROFILE["Encounter"]]},
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB", "display": "ambulatory",
        },
        "type": [
            {"coding": [{"system": f"{FB}/CodeSystem/ColombianTechModality",
                         "code": "01", "display": "Intramural"}]},
            {"coding": [{"system": f"{FB}/CodeSystem/GrupoServicios",
                         "code": "01", "display": "Consulta externa"}]},
            {"coding": [{"system": f"{FB}/CodeSystem/REPShealthcareServices",
                         "code": servicio_cod, "display": servicio_nombre}]},
            {"coding": [{"system": f"{FB}/CodeSystem/EntornoAtencion",
                         "code": "05", "display": "Institucional"}]},
        ],
        "serviceType": {"coding": [{
            "system": f"{FB}/CodeSystem/CUPS",
            "code": cups_codigo, "display": cups_nombre,
        }]},
        "subject": {"reference": patient_ref},
        "participant": [{
            "id": "AttenderPhysician",
            "type": [{"coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationType",
                "code": "ATND", "display": "attender",
            }]}],
            "individual": {"reference": practitioner_ref},
        }],
        "period": {"start": inicio, "end": fin},
        # Causa externa de la atención (obligatoria en el perfil del Ministerio)
        "reasonCode": [{"coding": [{
            "system": f"{FB}/CodeSystem/RIPSCausaExternaVersion2",
            "code": causa_externa_cod, "display": causa_externa_nombre,
        }]}],
        "diagnosis": [{
            "id": "MainDiagnosis",
            "extension": [{
                "url": f"{FB}/StructureDefinition/ExtensionDiagnosisType",
                "valueCoding": {
                    "system": f"{FB}/CodeSystem/RIPSTipoDiagnosticoPrincipalVersion2",
                    "code": tipo_dx_cod, "display": tipo_dx_nombre,
                },
            }],
            "condition": {"reference": condition_ref},
            "use": {"coding": [{
                "system": f"{FB}/CodeSystem/ColombianDiagnosisRole",
                "code": "8319008", "display": "diagnóstico primario",
            }]},
            "rank": 1,
        }],
    }


# =========================
# CONDITION (diagnóstico)
# =========================

def build_condition(*, fhir_id, patient_ref, cod_cie10, nombre_dx=""):
    codigo = normalizar_codigo(cod_cie10)
    display = display_oficial(cod_cie10, fallback=nombre_dx)
    return {
        "resourceType": "Condition",
        "id": fhir_id,
        "meta": {"profile": [C.PROFILE["Condition"]]},
        "code": {
            "coding": [{
                "system": C.SYS["ICD10"],
                "code": codigo,
                "display": display,
            }],
            "text": nombre_dx or display,
        },
        "subject": {"reference": patient_ref},
    }


# =========================
# DOCUMENT REFERENCE (epicrisis)
# =========================

def build_document_reference(*, fhir_id, patient_ref, author_ref, fecha,
                             pdf_base64="JVBERi0xLjQKJUVPRgo="):
    # PDF mínimo por defecto (mismo del prototipo que dio 200).
    return {
        "resourceType": "DocumentReference",
        "id": fhir_id,
        "meta": {"profile": [C.PROFILE["DocumentRef"]]},
        "status": "current",
        "type": {"coding": [
            {"system": C.SYS["LOINC"], "code": "18842-5", "display": "Discharge summary"},
            {"system": f"{FB}/CodeSystem/ColombianDocumentTypes", "code": "EPI",
             "display": "Epicrisis"},
        ]},
        "category": [{"coding": [
            {"system": C.SYS["LOINC"], "code": "55108-5",
             "display": "Clinical presentation Document"},
        ]}],
        "subject": {"reference": patient_ref},
        "date": fecha,
        "author": [{"reference": author_ref}],
        "custodian": {"reference": "Organization/MinSalud"},
        "description": "Epicrisis del encuentro de atención en salud - RDA",
        "securityLabel": [{"coding": [
            {"system": C.SYS["V3_CONF"], "code": "R", "display": "restricted"},
        ]}],
        "content": [{
            "attachment": {
                "data": pdf_base64,
                "title": "Soporte de la atención",
            },
            "format": {"system": C.SYS["BCP13"], "code": "application/pdf",
                       "display": "PDF"},
        }],
    }


# =========================
# SECTION (del Composition)
# =========================

def build_section(code, display, title, entries=None):
    sec = {
        "title": title,
        "code": {"coding": [{"system": C.SYS["LOINC"], "code": code, "display": display}]},
    }
    if entries:
        sec["entry"] = entries
        sec["text"] = _narrative_datos()
    else:
        sec["emptyReason"] = {"coding": [{
            "system": C.SYS["LIST_EMPTY"], "code": "nilknown", "display": "Nil Known",
        }]}
        sec["text"] = _narrative_vacia()
    return sec