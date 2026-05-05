from services.supabase_service import get_supabase_public

TABLE = "hc_contratos"


def _sb():
    return get_supabase_public()


def listar_por_cliente(cliente_id):
    res = (
        _sb()
        .table(TABLE)
        .select("*, hc_sedes(nombre)")
        .eq("cliente_id", cliente_id)
        .order("nro_contrato")
        .execute()
    )
    data = res.data or []
    # Aplanar sede_nombre para que el template/JS lo use directamente
    for c in data:
        sede = c.pop("hc_sedes", None)
        c["sede_nombre"] = sede["nombre"] if sede else None
    return data


def obtener(contrato_id):
    res = (
        _sb()
        .table(TABLE)
        .select("*")
        .eq("id", contrato_id)
        .single()
        .execute()
    )
    return res.data


def crear(data: dict):
    res = _sb().table(TABLE).insert(data).execute()
    return res.data


def actualizar(contrato_id, data: dict):
    res = (
        _sb()
        .table(TABLE)
        .update(data)
        .eq("id", contrato_id)
        .execute()
    )
    return res.data


def cambiar_estado(contrato_id, nuevo_estado: str):
    _sb().table(TABLE).update({"estado": nuevo_estado}).eq("id", contrato_id).execute()


def existe_nro(nro_contrato: str, exclude_id=None):
    q = _sb().table(TABLE).select("id").eq("nro_contrato", nro_contrato.strip())
    if exclude_id:
        q = q.neq("id", exclude_id)
    res = q.execute()
    return bool(res.data)