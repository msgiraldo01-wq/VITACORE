from typing import Any
from flask import current_app  # type: ignore

from services.supabase_service import get_supabase_admin


def _table_name() -> str:
    return current_app.config.get(
        "SUPABASE_TABLE_HC_TIPOS_DOCUMENTO",
        "hc_tipos_documento"
    )


def _sb():
    return get_supabase_admin()


def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None

    return {
        "id": row.get("id"),
        "codigo": row.get("codigo") or "",
        "nombre": row.get("nombre") or "",
        "descripcion": row.get("descripcion") or "",
        "estado": row.get("estado") or "ACTIVO",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def listar():
    response = (
        _sb()
        .table(_table_name())
        .select("*")
        .order("estado", desc=False)
        .order("codigo", desc=False)
        .execute()
    )

    items = response.data or []
    return [_normalize_row(x) for x in items]


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


def existe_codigo(codigo: str, exclude_id: int | None = None):
    codigo = (codigo or "").strip()
    if not codigo:
        return False

    query = (
        _sb()
        .table(_table_name())
        .select("id")
        .ilike("codigo", codigo)
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
        "descripcion": (data.get("descripcion") or "").strip(),
        "estado": ((data.get("estado") or "ACTIVO").strip().upper()),
    }

    response = (
        _sb()
        .table(_table_name())
        .insert(payload)
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else None


def actualizar(item_id: int, data: dict):
    payload = {
        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "descripcion": (data.get("descripcion") or "").strip(),
        "estado": ((data.get("estado") or "ACTIVO").strip().upper()),
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


def cambiar_estado(item_id: int, nuevo_estado: str):
    response = (
        _sb()
        .table(_table_name())
        .update({"estado": (nuevo_estado or "").strip().upper()})
        .eq("id", item_id)
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else obtener(item_id)