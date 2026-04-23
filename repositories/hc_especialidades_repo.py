from typing import Any
from flask import session  # 🔥 CLAVE
from services.supabase_service import get_supabase_admin


def _table_name() -> str:
    return "hc_especialidades"


def _sb():
    return get_supabase_admin()


def _empresa_id():
    return session.get("empresa_id")


def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None

    return {
        "id": row.get("id"),
        "codigo": row.get("codigo") or "",
        "nombre": row.get("nombre") or "",
        "descripcion": row.get("descripcion") or "",
        "estado": row.get("estado") or "ACTIVA",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


# ================================
# LISTAR
# ================================
def listar():

    empresa_id = _empresa_id()

    if not empresa_id:
        return []

    response = (
        _sb()
        .table(_table_name())
        .select("*")
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .order("estado", desc=False)
        .order("nombre", desc=False)
        .execute()
    )

    return [_normalize_row(x) for x in (response.data or [])]


# ================================
# OBTENER
# ================================
def obtener(item_id: int):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    response = (
        _sb()
        .table(_table_name())
        .select("*")
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)  # 🔥 SEGURIDAD
        .limit(1)
        .execute()
    )

    data = response.data or []
    return _normalize_row(data[0]) if data else None


# ================================
# VALIDAR CÓDIGO
# ================================
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
        .ilike("codigo", codigo)
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
    )

    if exclude_id is not None:
        query = query.neq("id", exclude_id)

    response = query.limit(1).execute()

    return len(response.data or []) > 0


# ================================
# CREAR
# ================================
def crear(data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    payload = {
        "empresa_id": empresa_id,  # 🔥 CLAVE

        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "descripcion": (data.get("descripcion") or "").strip(),
        "estado": (data.get("estado") or "ACTIVA").strip().upper(),
    }

    response = (
        _sb()
        .table(_table_name())
        .insert(payload)
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else None


# ================================
# ACTUALIZAR
# ================================
def actualizar(item_id: int, data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    payload = {
        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "descripcion": (data.get("descripcion") or "").strip(),
        "estado": (data.get("estado") or "ACTIVA").strip().upper(),
    }

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)  # 🔥 SEGURIDAD
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else obtener(item_id)


# ================================
# CAMBIAR ESTADO
# ================================
def cambiar_estado(item_id: int, nuevo_estado: str):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    response = (
        _sb()
        .table(_table_name())
        .update({
            "estado": (nuevo_estado or "").strip().upper()
        })
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else obtener(item_id)


# ================================
# SELECT (DROPDOWN)
# ================================
def listar_select():

    empresa_id = _empresa_id()

    if not empresa_id:
        return []

    response = (
        _sb()
        .table(_table_name())
        .select("id, nombre")
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .eq("estado", "ACTIVA")
        .order("nombre")
        .execute()
    )

    return response.data or []