from typing import Any
from services.supabase_service import get_supabase_admin


def _table():
    return "hc_municipios"


def _sb():
    return get_supabase_admin()


def _normalize(row: dict[str, Any] | None):

    if not row:
        return None

    dep = row.get("hc_departamentos") or {}

    return {
        "id": row.get("id"),
        "departamento_id": row.get("departamento_id"),
        "departamento": dep.get("nombre"),
        "departamento_nombre": dep.get("nombre"),

        "codigo": row.get("codigo") or "",
        "nombre": row.get("nombre") or "",

        "estado": row.get("estado") or "ACTIVO",
        "created_at": row.get("created_at"),
    }


# ========================
# LISTAR
# ========================

def listar():

    res = (
        _sb()
        .table(_table())
        .select("*, hc_departamentos(nombre)")
        .order("nombre")
        .execute()
    )

    return [_normalize(x) for x in (res.data or [])]


# ========================
# LISTAR POR DEPARTAMENTO
# ========================

def listar_por_departamento(dep_id):

    res = (
        _sb()
        .table(_table())
        .select("*, hc_departamentos(nombre)")
        .eq("departamento_id", dep_id)
        .order("nombre")
        .execute()
    )

    return [_normalize(x) for x in (res.data or [])]


# ========================
# OBTENER
# ========================

def obtener(item_id: int):

    res = (
        _sb()
        .table(_table())
        .select("*, hc_departamentos(nombre)")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )

    data = res.data or []

    return _normalize(data[0]) if data else None


# ========================
# CREAR
# ========================

def crear(data: dict):

    payload = {
        "departamento_id": data.get("departamento_id"),
        "codigo": (data.get("codigo") or "").strip(),
        "nombre": (data.get("nombre") or "").strip(),
        "estado": "ACTIVO",
    }

    res = _sb().table(_table()).insert(payload).execute()

    return _normalize(res.data[0]) if res.data else None


# ========================
# ACTUALIZAR
# ========================

def actualizar(item_id: int, data: dict):

    payload = {
        "departamento_id": data.get("departamento_id"),
        "codigo": (data.get("codigo") or "").strip(),
        "nombre": (data.get("nombre") or "").strip(),
    }

    res = (
        _sb()
        .table(_table())
        .update(payload)
        .eq("id", item_id)
        .execute()
    )

    rows = res.data or []

    return _normalize(rows[0]) if rows else obtener(item_id)


# ========================
# TOGGLE ESTADO
# ========================

def cambiar_estado(item_id: int, nuevo_estado: str):

    res = (
        _sb()
        .table(_table())
        .update({"estado": nuevo_estado})
        .eq("id", item_id)
        .execute()
    )

    rows = res.data or []

    return _normalize(rows[0]) if rows else obtener(item_id)