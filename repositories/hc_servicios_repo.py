from services.supabase_service import get_supabase_admin


def listar_servicios():

    sb = get_supabase_admin()

    res = (
        sb.table("hc_servicios")
        .select("*, hc_especialidades(nombre)")
        .order("nombre")
        .execute()
    )

    return res.data


def obtener_servicio(servicio_id):

    sb = get_supabase_admin()

    res = (
        sb.table("hc_servicios")
        .select("*")
        .eq("id", servicio_id)
        .single()
        .execute()
    )

    return res.data


def crear_servicio(data):

    sb = get_supabase_admin()

    res = (
        sb.table("hc_servicios")
        .insert(data)
        .execute()
    )

    return res.data


def actualizar_servicio(servicio_id, data):

    sb = get_supabase_admin()

    res = (
        sb.table("hc_servicios")
        .update(data)
        .eq("id", servicio_id)
        .execute()
    )

    return res.data


def cambiar_estado(item_id: int, nuevo_estado: str):
    
    sb = get_supabase_admin

    response = (
        sb()
        .table("hc_servicios")
        .update({"estado": nuevo_estado})
        .eq("id", item_id)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None