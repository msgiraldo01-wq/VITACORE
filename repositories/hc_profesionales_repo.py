from typing import Any

from services.supabase_service import get_supabase_admin


# ---------------------------------------------------------
# Config
# ---------------------------------------------------------

def _table_name() -> str:
    return "hc_profesionales"


def _sb():
    return get_supabase_admin()


# ---------------------------------------------------------
# Normalización
# ---------------------------------------------------------

def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:

    if not row:
        return None

    tipo_doc_rel = row.get("tipo_documento") if isinstance(row.get("tipo_documento"), dict) else None
    esp_rel = row.get("especialidad") if isinstance(row.get("especialidad"), dict) else None
    sede_rel = row.get("sede") if isinstance(row.get("sede"), dict) else None
    cons_rel = row.get("consultorio") if isinstance(row.get("consultorio"), dict) else None

    return {
        "id": row.get("id"),

        "tipo_documento_id": row.get("tipo_documento_id"),
        "tipo_documento_codigo": (
            tipo_doc_rel.get("codigo") if tipo_doc_rel else row.get("tipo_documento_codigo")
        ) or "",

        "numero_documento": row.get("numero_documento") or "",

        "nombres": row.get("nombres") or "",
        "apellidos": row.get("apellidos") or "",
        "nombre_completo": row.get("nombre_completo") or "",

        "especialidad_id": row.get("especialidad_id"),
        "especialidad_nombre": (
            esp_rel.get("nombre") if esp_rel else row.get("especialidad_nombre")
        ) or "",

        "sede_id": row.get("sede_id"),
        "sede_nombre": (
            sede_rel.get("nombre") if sede_rel else row.get("sede_nombre")
        ) or "",

        "consultorio_id": row.get("consultorio_id"),
        "consultorio_nombre": (
            cons_rel.get("nombre") if cons_rel else row.get("consultorio_nombre")
        ) or "",

        "registro_profesional": row.get("registro_profesional") or "",
        "correo": row.get("correo") or "",
        "telefono": row.get("telefono") or "",

        "estado": row.get("estado") or "ACTIVO",

        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# ---------------------------------------------------------
# Queries
# ---------------------------------------------------------

def listar():

    response = (
        _sb()
        .table(_table_name())
        .select("""
            *,
            tipo_documento:hc_tipos_documento(id,codigo,nombre),
            especialidad:hc_especialidades(id,nombre),
            sede:hc_sedes(id,nombre),
            consultorio:hc_consultorios(id,nombre)
        """)
        .order("estado", desc=False)
        .order("apellidos", desc=False)
        .order("nombres", desc=False)
        .execute()
    )

    return [_normalize_row(x) for x in (response.data or [])]


def obtener(item_id: int):

    response = (
        _sb()
        .table(_table_name())
        .select("""
            *,
            tipo_documento:hc_tipos_documento(id,codigo,nombre),
            especialidad:hc_especialidades(id,nombre),
            sede:hc_sedes(id,nombre),
            consultorio:hc_consultorios(id,nombre)
        """)
        .eq("id", item_id)
        .limit(1)
        .execute()
    )

    data = response.data or []
    return _normalize_row(data[0]) if data else None


# ---------------------------------------------------------
# 🔥 NUEVA FUNCIÓN (FIX ERROR)
# ---------------------------------------------------------

def obtener_medico(medico_id: int):
    return obtener(medico_id)


# ---------------------------------------------------------
# Validaciones
# ---------------------------------------------------------

def existe_documento(
    tipo_documento_id: int | None,
    numero_documento: str,
    exclude_id: int | None = None
) -> bool:

    numero_documento = (numero_documento or "").strip()

    if not tipo_documento_id or not numero_documento:
        return False

    query = (
        _sb()
        .table(_table_name())
        .select("id")
        .eq("tipo_documento_id", int(tipo_documento_id))
        .ilike("numero_documento", numero_documento)
    )

    if exclude_id is not None:
        query = query.neq("id", exclude_id)

    response = query.limit(1).execute()

    return len(response.data or []) > 0


# ---------------------------------------------------------
# Payload helper
# ---------------------------------------------------------

def _build_payload(data: dict[str, Any]) -> dict[str, Any]:

    nombres = (data.get("nombres") or "").strip()
    apellidos = (data.get("apellidos") or "").strip()

    return {
        "tipo_documento_id": int(data.get("tipo_documento_id")) if data.get("tipo_documento_id") else None,
        "numero_documento": (data.get("numero_documento") or "").strip(),

        "nombres": nombres,
        "apellidos": apellidos,
        "nombre_completo": f"{nombres} {apellidos}".strip(),

        "especialidad_id": int(data.get("especialidad_id")) if data.get("especialidad_id") else None,
        "sede_id": int(data.get("sede_id")) if data.get("sede_id") else None,
        "consultorio_id": int(data.get("consultorio_id")) if data.get("consultorio_id") else None,

        "registro_profesional": (data.get("registro_profesional") or "").strip(),
        "correo": (data.get("correo") or "").strip(),
        "telefono": (data.get("telefono") or "").strip(),

        "estado": ((data.get("estado") or "ACTIVO").strip().upper()),
    }


# ---------------------------------------------------------
# CRUD
# ---------------------------------------------------------

def crear(data: dict):

    payload = _build_payload(data)

    response = (
        _sb()
        .table(_table_name())
        .insert(payload)
        .execute()
    )

    rows = response.data or []

    return _normalize_row(rows[0]) if rows else None


def actualizar(item_id: int, data: dict):

    payload = _build_payload(data)

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", item_id)
        .execute()
    )

    rows = response.data or []

    return _normalize_row(rows[0]) if rows else obtener(item_id)


def cambiar_estado(item_id: int, nuevo_estado: str):

    response = (
        _sb()
        .table(_table_name())
        .update({
            "estado": (nuevo_estado or "").strip().upper()
        })
        .eq("id", item_id)
        .execute()
    )

    rows = response.data or []

    return _normalize_row(rows[0]) if rows else obtener(item_id)