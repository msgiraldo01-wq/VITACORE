from typing import Any
from services.supabase_service import get_supabase_admin


def _table_name():
    return "hc_paises"


def _sb():
    return get_supabase_admin()


def _normalize_row(row: dict[str, Any] | None):

    if not row:
        return None

    return {
        "id": row.get("id"),
        "codigo_iso2": row.get("codigo_iso2") or "",
        "codigo_iso3": row.get("codigo_iso3") or "",
        "nombre": row.get("nombre") or "",
        "estado": row.get("estado") or "ACTIVO",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# ========================
# LISTAR
# ========================

def listar():

    response = (
        _sb()
        .table(_table_name())
        .select("*")
        .order("nombre")
        .execute()
    )

    return [_normalize_row(x) for x in (response.data or [])]


# ========================
# OBTENER
# ========================

def obtener(item_id: int):

    response = (
        _sb()
        .table(_table_name())
        .select("*")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )

    data = response.data or []

    return _normalize_row(data[0]) if data else None


# ========================
# CREAR
# ========================

def crear(data: dict):

    payload = {
        "codigo_iso2": (data.get("codigo_iso2") or "").upper().strip(),
        "codigo_iso3": (data.get("codigo_iso3") or "").upper().strip(),
        "nombre": (data.get("nombre") or "").strip(),
        "estado": "ACTIVO"
    }

    response = (
        _sb()
        .table(_table_name())
        .insert(payload)
        .execute()
    )

    rows = response.data or []

    return _normalize_row(rows[0]) if rows else None


# ========================
# ACTUALIZAR
# ========================

def actualizar(item_id: int, data: dict):

    payload = {
        "codigo_iso2": (data.get("codigo_iso2") or "").upper().strip(),
        "codigo_iso3": (data.get("codigo_iso3") or "").upper().strip(),
        "nombre": (data.get("nombre") or "").strip(),
    }

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", item_id)
        .execute()
    )

    rows = response.data or []

    return _normalize_row(rows[0]) if rows else obtener(item_id)


# ========================
# CAMBIAR ESTADO
# ========================

def cambiar_estado(item_id: int, nuevo_estado: str):

    response = (
        _sb()
        .table(_table_name())
        .update({"estado": nuevo_estado})
        .eq("id", item_id)
        .execute()
    )

    rows = response.data or []

    return _normalize_row(rows[0]) if rows else obtener(item_id)


def obtener_por_iso2(codigo_iso2):

    res = (
        _sb()
        .table("hc_paises")
        .select("*")
        .eq("codigo_iso2", codigo_iso2)
        .limit(1)
        .execute()
    )

    return res.data[0] if res.data else None