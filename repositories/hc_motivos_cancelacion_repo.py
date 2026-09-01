# repositories/hc_motivos_cancelacion_repo.py
"""
Maestra de motivos de cancelación de citas. Usada por:
  - la página de administración en Configuración (agregar/desactivar motivos)
  - el modal de cancelar cita en la agenda (selección obligatoria del motivo)
  - el reporte "Citas canceladas" en Reportes

Los motivos no se eliminan físicamente: se desactivan. Un motivo ya usado
en citas canceladas debe seguir existiendo para que el histórico y los
reportes no queden con una referencia rota; "desactivar" solo lo saca
de la lista que se ofrece al cancelar una cita nueva.
"""

from services.supabase_service import get_supabase_public


def _sb():
    return get_supabase_public()


def _table():
    return "hc_motivos_cancelacion"


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
    """Solo los motivos activos, para ofrecer al cancelar una cita."""
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


def obtener_o_crear_por_nombre(nombre: str) -> dict:
    """
    Busca un motivo por nombre (sin importar mayúsculas/espacios) entre
    TODOS los motivos (activos e inactivos, vía listar()); si existe pero
    está desactivado lo reactiva, y si no existe lo crea. Pensado para
    que una funcionalidad nueva (p.ej. "marcar inasistencia" en
    Admisiones) pueda garantizar que su motivo reservado exista, sin
    depender de que un administrador lo haya creado a mano primero en
    Configuración → Motivos de cancelación.
    """
    nombre_norm = (nombre or "").strip()
    if not nombre_norm:
        raise ValueError("nombre es requerido")

    existentes = listar()
    for m in existentes:
        if (m.get("nombre") or "").strip().lower() == nombre_norm.lower():
            if not m.get("activo", True):
                cambiar_estado(m["id"], True)
                m["activo"] = True
            return m

    return crear(nombre_norm)
