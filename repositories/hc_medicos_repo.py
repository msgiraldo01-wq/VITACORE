from services.supabase_service import get_supabase_admin


def _sb():
    return get_supabase_admin()


def _normalize_row(row: dict) -> dict:
    if not row:
        return None

    especialidad = row.get("hc_especialidades") or {}

    return {
        "id"              : row.get("id"),
        "nombre"          : row.get("nombre") or "",
        "especialidad_id" : row.get("especialidad_id"),
        "especialidad"    : especialidad.get("nombre") or "",
        "numero_documento": row.get("numero_documento") or "",
        "telefono"        : row.get("telefono") or "",
        "email"           : row.get("email") or "",
        "estado"          : row.get("estado") or "ACTIVO",
    }


def listar(especialidad_id: int = None):
    q = (
        _sb()
        .table("hc_medicos")
        .select("*, hc_especialidades(nombre)")
        .eq("estado", "ACTIVO")
        .order("nombre")
    )

    if especialidad_id:
        q = q.eq("especialidad_id", especialidad_id)

    res = q.execute()
    return [_normalize_row(r) for r in (res.data or [])]


def obtener(item_id: int):
    res = (
        _sb()
        .table("hc_medicos")
        .select("*, hc_especialidades(nombre)")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )
    data = res.data or []                        # ← faltaba esto
    return _normalize_row(data[0]) if data else None  # ← y esto


def listar_select(especialidad_id: int = None):
    q = (
        _sb()
        .table("hc_medicos")
        .select("id, nombre")
        .eq("estado", "ACTIVO")
        .order("nombre")
    )

    if especialidad_id:
        q = q.eq("especialidad_id", especialidad_id)

    res = q.execute()
    return res.data or []                        # ← solo un return aquí