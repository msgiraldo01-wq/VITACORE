from typing import Any
from services.supabase_service import get_supabase_admin


def _table():
    return "hc_cups"


def _sb():
    return get_supabase_admin()


def listar():

    r = (
        _sb()
        .table(_table())
        .select("*")
        .order("codigo")
        .range(0, 200)
        .execute()
    )

    return r.data or []


def buscar(q):

    r = (
        _sb()
        .table(_table())
        .select("*")
        .or_(f"codigo.ilike.%{q}%,descripcion.ilike.%{q}%")
        .order("codigo")
        .limit(30)
        .execute()
    )

    return r.data or []


def obtener(item_id: int):

    r = (
        _sb()
        .table(_table())
        .select("*")
        .eq("id", item_id)
        .limit(1)
        .execute()
    )

    d = r.data or []

    return d[0] if d else None


def crear(data: dict):

    r = (
        _sb()
        .table(_table())
        .insert(data)
        .execute()
    )

    return r.data


def actualizar(item_id: int, data: dict):

    r = (
        _sb()
        .table(_table())
        .update(data)
        .eq("id", item_id)
        .execute()
    )

    return r.data


def cambiar_estado(item_id: int, estado: str):

    r = (
        _sb()
        .table(_table())
        .update({"estado": estado})
        .eq("id", item_id)
        .execute()
    )

    return r.data


def importar_lote(registros: list):
    """
    Inserta una lista de dicts en bloque.
    Si el codigo ya existe, hace upsert por la columna 'codigo'.
    """

    r = (
        _sb()
        .table(_table())
        .upsert(registros, on_conflict="codigo")
        .execute()
    )

    return r.data or []


def listar_todos_exportar():
    """Devuelve todos los registros sin límite para exportación."""

    r = (
        _sb()
        .table(_table())
        .select("id,codigo,descripcion,estado")
        .order("codigo")
        .execute()
    )

    return r.data or []