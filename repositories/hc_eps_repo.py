from typing import Any
from flask import current_app  # type: ignore

from services.supabase_service import get_supabase_admin
from flask import session 


# =========================
# CONFIG
# =========================

def _table_name() -> str:
    return current_app.config.get("SUPABASE_TABLE_HC_EPS", "hc_eps")


def _sb():
    return get_supabase_admin()

def _empresa_id():
    return session.get("empresa_id")


# =========================
# NORMALIZAR
# =========================

def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None

    return {
        "id": row.get("id"),
        "codigo": row.get("codigo") or "",
        "nombre": row.get("nombre") or "",
        "nit": row.get("nit") or "",
        "regimen": row.get("regimen") or "",
        "estado": row.get("estado") or "ACTIVO",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# =========================
# LISTAR
# =========================

def listar():

    empresa_id = _empresa_id()

    if not empresa_id:
        return []

    response = (
        _sb()
        .table(_table_name())
        .select("*")
        .eq("empresa_id", empresa_id)
        .order("estado", desc=False)
        .order("nombre", desc=False)
        .execute()
    )

    items = response.data or []
    return [_normalize_row(x) for x in items]


# =========================
# OBTENER
# =========================

def obtener(item_id: int):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    response = (
        _sb()
        .table(_table_name())
        .select("*")
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)
        .limit(1)
        .execute()
    )

    data = response.data or []
    return _normalize_row(data[0]) if data else None


# =========================
# VALIDAR CÓDIGO
# =========================

def existe_codigo(codigo: str, exclude_id: int | None = None):

    empresa_id = _empresa_id()

    if not empresa_id:
        return False

    codigo = (codigo or "").strip().upper()

    if not codigo:
        return False

    query = (
        _sb()
        .table(_table_name())
        .select("id")
        .eq("codigo", codigo)
        .eq("empresa_id", empresa_id)
    )

    if exclude_id is not None:
        query = query.neq("id", exclude_id)

    response = query.limit(1).execute()

    data = response.data or []
    return len(data) > 0


# =========================
# CREAR
# =========================

def crear(data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    payload = {
        "empresa_id": empresa_id,
        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "nit": (data.get("nit") or "").strip(),
        "regimen": (data.get("regimen") or "").strip().upper(),
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


# =========================
# ACTUALIZAR
# =========================

def actualizar(item_id: int, data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    payload = {
        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "nit": (data.get("nit") or "").strip(),
        "regimen": (data.get("regimen") or "").strip().upper(),
    }

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else obtener(item_id)


# =========================
# CAMBIAR ESTADO
# =========================

def cambiar_estado(item_id: int, nuevo_estado: str):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    payload = {
        "estado": (nuevo_estado or "").strip().upper()
    }

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else obtener(item_id)

# =========================
# BUSCAR
# =========================

def buscar(q: str = ""):

    empresa_id = _empresa_id()

    if not empresa_id:
        return []

    q = (q or "").strip().lower()

    if not q:
        return listar()

    todos = listar()

    filtrados = [
        item for item in todos
        if q in (item.get("codigo") or "").lower()
        or q in (item.get("nombre") or "").lower()
        or q in (item.get("nit") or "").lower()
    ]

    return filtrados