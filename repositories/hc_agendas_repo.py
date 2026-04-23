from typing import Any
from services.supabase_service import get_supabase_admin
from flask import session


def _sb():
    return get_supabase_admin()


def _table():
    return "hc_agendas"

def _empresa_id():
    return session.get("empresa_id")


def _normalize(row: dict[str, Any] | None):

    if not row:
        return None

    return {
        "id": row.get("id"),
        "tipo": row.get("tipo"),
        "profesional_id": row.get("profesional_id"),
        "recurso_id": row.get("recurso_id"),
        "dia_semana": row.get("dia_semana"),
        "hora_inicio": row.get("hora_inicio"),
        "hora_fin": row.get("hora_fin"),
        "duracion_min": row.get("duracion_min"),
        "estado": row.get("estado"),
    }


def listar():

    empresa_id = _empresa_id()

    if not empresa_id:
        return []  

    res = (
        _sb()
        .table(_table())
        .select("*")
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .order("id")
        .execute()
    )

    return [_normalize(x) for x in (res.data or [])]