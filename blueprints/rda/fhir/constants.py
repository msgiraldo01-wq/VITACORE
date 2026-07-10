"""
Constantes del RDA (perfiles, sistemas de codificación y endpoints).
Aislar aquí estos valores permite actualizarlos en un solo punto si el
Ministerio cambia la guía de implementación.
"""

FHIR_BASE = "https://fhir.minsalud.gov.co/rda"

# --- Perfiles (meta.profile de cada recurso) ---
PROFILE = {
    "Bundle":         f"{FHIR_BASE}/StructureDefinition/BundleAmbulatoryRDA",
    "Composition":    f"{FHIR_BASE}/StructureDefinition/CompositionAmbulatoryRDA",
    "Patient":        f"{FHIR_BASE}/StructureDefinition/PatientRDA",
    "OrgIPS":         f"{FHIR_BASE}/StructureDefinition/CareDeliveryOrganizationRDA",
    "OrgEAPB":        f"{FHIR_BASE}/StructureDefinition/HealthBenefitPlanAdminOrganizationRDA",
    "Practitioner":   f"{FHIR_BASE}/StructureDefinition/PractitionerRDA",
    "Encounter":      f"{FHIR_BASE}/StructureDefinition/EncounterAmbulatoryRDA",
    "Condition":      f"{FHIR_BASE}/StructureDefinition/ConditionRDA",
    "DocumentRef":    f"{FHIR_BASE}/StructureDefinition/DocumentReferenceEPIRDA",
}

# --- Sistemas de codificación ---
SYS = {
    "LOINC":          "http://loinc.org",
    "ICD10":          "http://hl7.org/fhir/sid/icd-10",   # el slice del Condition usa el internacional
    "IDENTIFIER_RDA": f"{FHIR_BASE}/NamingSystem/identifier-RDA",
    "V3_CONF":        "http://terminology.hl7.org/CodeSystem/v3-Confidentiality",
    "BCP13":          "urn:ietf:bcp:13",
    "LIST_EMPTY":     "http://terminology.hl7.org/CodeSystem/list-empty-reason",
}

# --- Endpoint de la operación de envío de consulta externa ---
OP_ENVIAR_CONSULTA = "Composition/$enviar-rda-consulta"
OP_CONSULTAR_ENCUENTROS = "Composition/$consultar-rda-encuentros-clinicos"
OP_CONSULTAR_PACIENTE = "Composition/$consultar-rda-paciente"

# --- Secciones obligatorias del Composition (código LOINC, display, título) ---
# display y title son valores FIJOS del perfil del Ministerio: deben coincidir
# EXACTAMENTE (extraídos de un Bundle con acuse 200).
SECCIONES_OBLIGATORIAS = [
    ('48768-6',
     'Payment sources Document',
     'Entidad(es) responsable(s) por el plan de beneficios en salud (consulta)'),
    ('74208-0',
     'Demographic information + History of occupation Document',
     'Otros datos demográficos'),
    ('105583-9',
     'Worker Sick leave form',
     'Datos incapacidad (SIPE – Sistema de Incapacidades y Prestaciones Economicas)'),
    ('10160-0',
     'History of Medication use Narrative',
     'Historial de medicamentos'),
    ('48765-2',
     'Allergies and adverse reactions Document',
     'Historial de alergias, intolerancias y reacciones adversas'),
    ('11450-4',
     'Problem list - Reported',
     'Historial de diagnósticos de problemas de salud'),
    ('75492-9',
     'Risk assessment and screening note',
     'Factores de riesgo'),
    ('61146-1',
     'Orders for services Document',
     'Órdenes, prescripciones o solicitudes de servicio'),
    ('55107-7',
     'Addendum Document',
     'Documentos de soporte'),
]

# Display fijo del tipo de documento del Composition
COMPOSITION_TYPE_DISPLAY = 'Outpatient Consult note'