from typing import Any
from flask import session
from services.supabase_service import get_supabase_admin


def _table():
    return "hc_evolucion_medicamentos"


def _sb():
    return get_supabase_admin()


def _empresa_id():
    return session.get("empresa_id")


def _normalize(row: dict[str, Any] | None):

    if not row:
        return None

    return {
        "id": row.get("id"),
        "evolucion_id": row.get("evolucion_id"),
        "medicamento_id": row.get("medicamento_id"),
        "medicamento_nombre": row.get("medicamento_nombre"),
        "dosis": row.get("dosis"),
        "frecuencia": row.get("frecuencia"),
        "duracion": row.get("duracion"),
        "via_administracion": row.get("via_administracion"),
        "observaciones": row.get("observaciones"),
    }


# ======================
# LISTAR POR EVOLUCION
# ======================

def listar_por_evolucion(evolucion_id: int):

    empresa_id = _empresa_id()

    if not empresa_id:
        return []

    res = (
        _sb()
        .table(_table())
        .select("""
            *,
            evolucion:hc_evoluciones!hc_evolucion_medicamentos_evolucion_id_fkey(empresa_id)
        """)
        .eq("evolucion_id", evolucion_id)
        .eq("evolucion.empresa_id", empresa_id)  # 🔥 SEGURIDAD
        .execute()
    )

    return [_normalize(x) for x in (res.data or [])]


# ======================
# CREAR
# ======================

def crear(data: dict):

    empresa_id = _empresa_id()

    if not empresa_id:
        return None

    # 🔒 VALIDAR QUE LA EVOLUCIÓN ES DE LA EMPRESA
    valid = (
        _sb()
        .table("hc_evoluciones")
        .select("id")
        .eq("id", data.get("evolucion_id"))
        .eq("empresa_id", empresa_id)
        .limit(1)
        .execute()
    )

    if not valid.data:
        return None  # 🚫 intento inválido

    res = (
        _sb()
        .table(_table())
        .insert(data)
        .execute()
    )

    return _normalize(res.data[0]) if res.data else None