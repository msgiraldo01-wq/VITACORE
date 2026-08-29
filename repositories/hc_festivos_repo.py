"""
Repositorio: hc_festivos_repo.py
Maestra de días festivos (Colombia). Usada por:
  - la página de administración en Configuración (agregar/quitar festivos)
  - hc_prof_programacion_repo.py, para no ofrecer disponibilidad en un
    festivo a los profesionales que no lo tengan marcado (trabaja_festivos).
"""

from services.supabase_service import get_supabase_public


def _sb():
    return get_supabase_public()


def _table():
    return "hc_festivos"


def listar() -> list:
    """Todos los festivos, ordenados por fecha."""
    res = (
        _sb()
        .table(_table())
        .select("*")
        .order("fecha")
        .execute()
    )
    return res.data or []


def crear(fecha: str, nombre: str) -> dict:
    payload = {
        "fecha": fecha,
        "nombre": (nombre or "").strip(),
    }
    res = _sb().table(_table()).insert(payload).execute()
    return res.data[0] if res.data else {}


def eliminar(festivo_id: int):
    _sb().table(_table()).delete().eq("id", festivo_id).execute()


def es_festivo(fecha: str) -> str | None:
    """Si `fecha` (YYYY-MM-DD) es festivo, retorna su nombre; si no, None."""
    res = (
        _sb()
        .table(_table())
        .select("nombre")
        .eq("fecha", fecha)
        .limit(1)
        .execute()
    )
    return res.data[0]["nombre"] if res.data else None


def listar_rango(fecha_desde: str, fecha_hasta: str) -> dict:
    """
    Festivos dentro de [fecha_desde, fecha_hasta], como {fecha: nombre}.
    Pensado para traer de una sola vez los festivos de toda una ventana
    (ej. los 90 días de "buscar siguiente disponible") en vez de consultar
    día por día.
    """
    res = (
        _sb()
        .table(_table())
        .select("fecha, nombre")
        .gte("fecha", fecha_desde)
        .lte("fecha", fecha_hasta)
        .execute()
    )
    return {r["fecha"]: r["nombre"] for r in (res.data or [])}
