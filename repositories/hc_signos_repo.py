from typing import Any
from services.supabase_service import get_supabase_admin


def _table():
    return "hc_evolucion_signos"


def _sb():
    return get_supabase_admin()


def listar_por_paciente(paciente_id: int):

    r = (
        _sb()
        .table(_table())
        .select("*")
        .eq("paciente_id", paciente_id)
        .order("fecha", desc=True)
        .execute()
    )

    return r.data or []


def crear(data: dict):

    r = (
        _sb()
        .table(_table())
        .insert(data)
        .execute()
    )

    return r.data
