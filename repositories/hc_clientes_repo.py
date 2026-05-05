from services.supabase_service import get_supabase_public

TABLE = "hc_clientes"


def _sb():
    return get_supabase_public()


def listar():
    res = (
        _sb()
        .table(TABLE)
        .select("*")
        .order("nombre")
        .execute()
    )
    return res.data or []


def obtener(cliente_id):
    res = (
        _sb()
        .table(TABLE)
        .select("*")
        .eq("id", cliente_id)
        .single()
        .execute()
    )
    return res.data


def crear(data: dict):
    res = _sb().table(TABLE).insert(data).execute()
    return res.data


def actualizar(cliente_id, data: dict):
    res = (
        _sb()
        .table(TABLE)
        .update(data)
        .eq("id", cliente_id)
        .execute()
    )
    return res.data


def cambiar_estado(cliente_id, nuevo_estado: str):
    _sb().table(TABLE).update({"estado": nuevo_estado}).eq("id", cliente_id).execute()


def existe_codigo(codigo: str, exclude_id=None):
    q = _sb().table(TABLE).select("id").eq("codigo", codigo.strip().upper())
    if exclude_id:
        q = q.neq("id", exclude_id)
    res = q.execute()
    return bool(res.data)