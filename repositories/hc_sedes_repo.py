from typing import Any
from flask import current_app  # type: ignore

from services.supabase_service import get_supabase_admin


def _table_name() -> str:
    return current_app.config.get("SUPABASE_TABLE_HC_SEDES", "hc_sedes")


def _sb():
    return get_supabase_admin()


def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None

    return {
        "id": row.get("id"),
        "codigo": row.get("codigo") or "",
        "nombre": row.get("nombre") or "",
        "ciudad": row.get("ciudad") or "",
        "direccion": row.get("direccion") or "",
        "telefono": row.get("telefono") or "",
        "estado": row.get("estado") or "ACTIVA",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def listar():
    response = (
        _sb()
        .table(_table_name())
        .select("*")
        .order("estado", desc=False)
        .order("nombre", desc=False)
        .execute()
    )

    items = response.data or []
    return [_normalize_row(x) for x in items]


def obtener(sede_id: int):
    response = (
        _sb()
        .table(_table_name())
        .select("*")
        .eq("id", sede_id)
        .limit(1)
        .execute()
    )

    data = response.data or []
    return _normalize_row(data[0]) if data else None


def existe_codigo(codigo: str, exclude_id: int | None = None):
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return False

    query = (
        _sb()
        .table(_table_name())
        .select("id")
        .eq("codigo", codigo)
    )

    if exclude_id is not None:
        query = query.neq("id", exclude_id)

    response = query.limit(1).execute()
    data = response.data or []
    return len(data) > 0


def crear(data: dict):
    payload = {
        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "ciudad": (data.get("ciudad") or "").strip(),
        "direccion": (data.get("direccion") or "").strip(),
        "telefono": (data.get("telefono") or "").strip(),
        "estado": ((data.get("estado") or "ACTIVA").strip().upper()),
    }

    response = (
        _sb()
        .table(_table_name())
        .insert(payload)
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else None


def actualizar(sede_id: int, data: dict):
    payload = {
        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "ciudad": (data.get("ciudad") or "").strip(),
        "direccion": (data.get("direccion") or "").strip(),
        "telefono": (data.get("telefono") or "").strip(),
        "estado": ((data.get("estado") or "ACTIVA").strip().upper()),
    }

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", sede_id)
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else obtener(sede_id)


def cambiar_estado(sede_id: int, nuevo_estado: str):
    payload = {
        "estado": (nuevo_estado or "").strip().upper()
    }

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", sede_id)
        .execute()
    )
def listar_select():
    """
    Versión ligera para dropdowns — solo id y nombre, solo ACTIVAS.
    """
    response = (
        _sb()
        .table(_table_name())
        .select("id, nombre")
        .eq("estado", "ACTIVA")
        .order("nombre")
        .execute()
    )
    return response.data or []
    rows = response.data or []
    return _normalize_row(rows[0]) if rows else obtener(sede_id)