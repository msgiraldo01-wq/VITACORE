from typing import Optional
from services.supabase_service import get_supabase_admin


def _table_name():
    return "rda_catalogos"


def _sb():
    return get_supabase_admin()


def _normalize(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "tipo": row.get("tipo"),
        "codigo": row.get("codigo"),
        "nombre": row.get("nombre"),
        "activo": bool(row.get("activo", True)),
        "orden": row.get("orden") or 0,
    }


# =========================
# LISTAR POR TIPO (para los selectores)
# =========================

def listar(tipo: str, solo_activos: bool = True) -> list:
    """Lista las opciones de un catálogo (p.ej. 'causa_externa'),
    por defecto solo las activas, ordenadas."""
    try:
        q = (
            _sb()
            .table(_table_name())
            .select("*")
            .eq("tipo", tipo)
            .order("orden")
        )
        if solo_activos:
            q = q.eq("activo", True)

        r = q.execute()
        if not r or not hasattr(r, "data") or not r.data:
            return []
        return [_normalize(row) for row in r.data if row]

    except Exception as e:
        print(f"Error listando catálogo RDA '{tipo}': {e}")
        return []


# =========================
# OBTENER UN CÓDIGO (para el nombre oficial)
# =========================

def obtener(tipo: str, codigo: str) -> Optional[dict]:
    """Devuelve una opción por tipo+código (activa o no)."""
    if not tipo or not codigo:
        return None
    try:
        r = (
            _sb()
            .table(_table_name())
            .select("*")
            .eq("tipo", tipo)
            .eq("codigo", str(codigo))
            .limit(1)
            .execute()
        )
        if not r or not hasattr(r, "data") or not r.data:
            return None
        return _normalize(r.data[0])
    except Exception as e:
        print(f"Error obteniendo catálogo RDA '{tipo}/{codigo}': {e}")
        return None


# =========================
# CAMBIAR ESTADO (activar/desactivar)
# =========================

def cambiar_estado(catalogo_id: int, activo: bool) -> Optional[dict]:
    """Activa o desactiva una opción del catálogo."""
    if not catalogo_id:
        return None
    try:
        r = (
            _sb()
            .table(_table_name())
            .update({"activo": bool(activo)})
            .eq("id", catalogo_id)
            .execute()
        )
        if not r or not hasattr(r, "data") or not r.data:
            return None
        return _normalize(r.data[0])
    except Exception as e:
        print(f"Error cambiando estado de catálogo RDA {catalogo_id}: {e}")
        return None