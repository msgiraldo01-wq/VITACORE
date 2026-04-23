from typing import Any
from flask import current_app, session  # 🔥 agregar session

from services.supabase_service import get_supabase_admin


def _table_name() -> str:
    return current_app.config.get("SUPABASE_TABLE_HC_CONSULTORIOS", "hc_consultorios")


def _sb():
    return get_supabase_admin()


def _empresa_id():
    return session.get("empresa_id")


def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None

    sede_rel = row.get("sede") if isinstance(row.get("sede"), dict) else None

    return {
        "id": row.get("id"),
        "sede_id": row.get("sede_id"),
        "sede_nombre": (sede_rel.get("nombre") if sede_rel else row.get("sede_nombre")) or "",
        "codigo": row.get("codigo") or "",
        "nombre": row.get("nombre") or "",
        "piso": row.get("piso") or "",
        "descripcion": row.get("descripcion") or "",
        "estado": row.get("estado") or "ACTIVO",
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
        .select("*, sede:hc_sedes!hc_consultorios_sede_id_fkey(id,nombre)")
        .eq("empresa_id", empresa_id)  
        .order("estado", desc=False)
        .order("nombre", desc=False)
        .execute()
    )

    items = response.data or []
    return [_normalize_row(x) for x in items]


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
        .select("*, sede:hc_sedes!hc_consultorios_sede_id_fkey(id,nombre)")
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)  
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
        .eq("codigo", codigo)
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
    )

    if exclude_id is not None:
        query = query.neq("id", exclude_id)

    response = query.limit(1).execute()
    data = response.data or []

    return len(data) > 0


# ================================
# CREAR
# ================================
def crear(data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    sede_id = data.get("sede_id")
    sede_id = int(sede_id) if sede_id not in (None, "", 0, "0") else None

    payload = {
        "empresa_id": empresa_id,  # 🔥 CLAVE

        "sede_id": sede_id,
        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "piso": (data.get("piso") or "").strip(),
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


# ================================
# ACTUALIZAR
# ================================
def actualizar(item_id: int, data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    sede_id = data.get("sede_id")
    sede_id = int(sede_id) if sede_id not in (None, "", 0, "0") else None

    payload = {
        "sede_id": sede_id,
        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "piso": (data.get("piso") or "").strip(),
        "descripcion": (data.get("descripcion") or "").strip(),
        "estado": ((data.get("estado") or "ACTIVO").strip().upper()),
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

    payload = {
        "estado": (nuevo_estado or "").strip().upper()
    }

    response = (
        _sb()
        .table(_table_name())
        .update(payload)
        .eq("id", item_id)
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .execute()
    )

    rows = response.data or []
    return _normalize_row(rows[0]) if rows else obtener(item_id)