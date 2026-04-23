from services.supabase_service import get_supabase_admin


def _table():
    return "hc_rec_procedimientos"


def _sb():
    return get_supabase_admin()


def listar_por_recurso(recurso_id: int):
    r = (
        _sb()
        .table(_table())
        .select("*, hc_cups(id, codigo, descripcion)")
        .eq("recurso_id", recurso_id)
        .order("id")
        .execute()
    )
    return r.data or []


def agregar(recurso_id: int, cups_id: int, duracion_min: int = 20):
    r = (
        _sb()
        .table(_table())
        .insert({
            "recurso_id":   recurso_id,
            "cups_id":      cups_id,
            "duracion_min": duracion_min,
        })
        .execute()
    )
    return r.data


def actualizar_duracion(id: int, duracion_min: int):
    r = (
        _sb()
        .table(_table())
        .update({"duracion_min": duracion_min})
        .eq("id", id)
        .execute()
    )
    return r.data


def eliminar(id: int):
    r = (
        _sb()
        .table(_table())
        .delete()
        .eq("id", id)
        .execute()
    )
    return r.data