# repositories/hc_cita_procedimientos_repo.py

from services.supabase_service import get_supabase_admin


def _table():
    return "hc_cita_procedimientos"


def _sb():
    return get_supabase_admin()


def listar_por_cita(cita_id: int):
    """Devuelve los procedimientos de una cita con datos del CUPS."""
    r = (
        _sb()
        .table(_table())
        .select("*, hc_cups(id, codigo, descripcion)")
        .eq("cita_id", cita_id)
        .order("orden")
        .execute()
    )
    return r.data or []


def crear_bulk(cita_id: int, procedimientos: list[dict]) -> list:
    """
    Inserta múltiples procedimientos para una cita.

    procedimientos: lista de dicts con claves:
        - cups_id   (int)
        - duracion_min (int)
        - orden     (int, opcional)
    """
    if not procedimientos:
        return []

    rows = [
        {
            "cita_id":      cita_id,
            "cups_id":      p["cups_id"],
            "duracion_min": p.get("duracion_min", 20),
            "orden":        p.get("orden", i + 1),
        }
        for i, p in enumerate(procedimientos)
    ]

    r = _sb().table(_table()).insert(rows).execute()
    return r.data or []


def eliminar_por_cita(cita_id: int):
    """Elimina todos los procedimientos de una cita (útil para re-guardar)."""
    r = (
        _sb()
        .table(_table())
        .delete()
        .eq("cita_id", cita_id)
        .execute()
    )
    return r.data