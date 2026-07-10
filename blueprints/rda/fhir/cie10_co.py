"""
CIE-10 Colombia: normalización de código y displays OFICIALES.

El Ministerio valida que Condition.code.coding.display coincida EXACTAMENTE
con el texto del catálogo (mayúsculas, sin tildes, con corchetes donde aplica).
Los códigos de categoría de 3 caracteres se rellenan con 'X' (J00 -> J00X).

Cuando un código no está en esta tabla, el servicio usa como respaldo el
'cie10_nombre' de la evolución. Para producción, lo ideal es cargar el
catálogo CIE-10 completo del Ministerio con sus displays oficiales.
"""

CIE10_CO = {
    "J00X": "RINOFARINGITIS AGUDA [RESFRIADO COMUN]",
    "J029": "FARINGITIS AGUDA, NO ESPECIFICADA",
    "J020": "FARINGITIS ESTREPTOCOCICA",
    "J039": "AMIGDALITIS AGUDA, NO ESPECIFICADA",
    "J030": "AMIGDALITIS ESTREPTOCOCICA",
    "J069": "INFECCION AGUDA DE LAS VIAS RESPIRATORIAS SUPERIORES, NO ESPECIFICADA",
    "J019": "SINUSITIS AGUDA, NO ESPECIFICADA",
    "J304": "RINITIS ALERGICA, NO ESPECIFICADA",
    "A09X": "DIARREA Y GASTROENTERITIS DE PRESUNTO ORIGEN INFECCIOSO",
    "K30X": "DISPEPSIA",
    "N390": "INFECCION DE VIAS URINARIAS, SITIO NO ESPECIFICADO",
    "I10X": "HIPERTENSION ESENCIAL (PRIMARIA)",
    "E119": "DIABETES MELLITUS NO INSULINODEPENDIENTE SIN MENCION DE COMPLICACION",
    "R51X": "CEFALEA",
    "R509": "FIEBRE, NO ESPECIFICADA",
    "R688": "OTROS SINTOMAS Y SIGNOS GENERALES ESPECIFICADOS",
    "M545": "LUMBAGO NO ESPECIFICADO",
    "Z000": "EXAMEN MEDICO GENERAL",
}


def normalizar_codigo(cod: str) -> str:
    """Mayúsculas + relleno con X para códigos de 3 caracteres (J00 -> J00X)."""
    c = (cod or "").strip().upper().replace(".", "")
    if len(c) == 3:
        c = c + "X"
    return c


def display_oficial(cod: str, fallback: str = "") -> str:
    """Display oficial del código; si no está en la tabla, usa el fallback."""
    c = normalizar_codigo(cod)
    return CIE10_CO.get(c, (fallback or c).strip())