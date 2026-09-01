# repositories/hc_motivos_reprogramacion_repo.py
"""
Maestra de motivos de reprogramación de citas. Usada por:
  - la página de administración en Configuración (agregar/desactivar motivos)
  - el modal de reprogramar cita en la agenda (selección obligatoria del motivo)

Los motivos no se eliminan físicamente: se desactivan. Un motivo ya usado
en citas reprogramadas debe seguir existiendo para que el histórico no
quede con una referencia rota; "desactivar" solo lo saca de la lista que
se ofrece al reprogramar una cita nueva.
"""

from services.supabase_service import get_supabase_public


def _sb():
    return get_supabase_public()


def _table():
    return "hc_motivos_reprogramacion"


def listar() -> list:
    """Todos los motivos (activos e inactivos), para la página de administración."""
    res = (
        _sb()
        .table(_table())
        .select("*")
        .order("nombre")
        .execute()
    )
    return res.data or []


def listar_activos() -> list:
    """Solo los motivos activos, para ofrecer al reprogramar una cita."""
    res = (
        _sb()
        .table(_table())
        .select("id, nombre")
        .eq("activo", True)
        .order("nombre")
        .execute()
    )
    return res.data or []


def crear(nombre: str) -> dict:
    payload = {"nombre": (nombre or "").strip(), "activo": True}
    res = _sb().table(_table()).insert(payload).execute()
    return res.data[0] if res.data else {}


def cambiar_estado(motivo_id: int, activo: bool):
    _sb().table(_table()).update({"activo": activo}).eq("id", motivo_id).execute()
