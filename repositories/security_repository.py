from services.supabase_service import get_supabase_admin


def listar_roles():
    supabase = get_supabase_admin()
    res = (
        supabase
        .table("roles")
        .select("id, code, name, is_active")
        .eq("is_active", True)
        .order("name")
        .execute()
    )
    return res.data or []


def obtener_rol_por_id(role_id: int):
    supabase = get_supabase_admin()
    res = (
        supabase
        .table("roles")
        .select("id, code, name, is_active")
        .eq("id", role_id)
        .limit(1)
        .execute()
    )
    data = res.data or []
    return data[0] if data else None


def listar_rutas():
    supabase = get_supabase_admin()
    res = (
        supabase
        .table("rutas")
        .select("id, endpoint, ruta, metodos")
        .order("ruta")
        .execute()
    )
    return res.data or []


def listar_rutas_permitidas_por_rol(role_id: int):
    supabase = get_supabase_admin()
    res = (
        supabase
        .table("roles_rutas")
        .select("id, role_id, ruta_id")
        .eq("role_id", role_id)
        .execute()
    )
    return res.data or []


def guardar_permisos_rutas(role_id: int, ruta_ids: list[int]):
    supabase = get_supabase_admin()

    (
        supabase
        .table("roles_rutas")
        .delete()
        .eq("role_id", role_id)
        .execute()
    )

    if not ruta_ids:
        return []

    payload = [{"role_id": role_id, "ruta_id": rid} for rid in ruta_ids]

    res = (
        supabase
        .table("roles_rutas")
        .insert(payload)
        .execute()
    )
    return res.data or []


def construir_matriz_rutas(role_id: int):
    rutas = listar_rutas()
    permitidas = listar_rutas_permitidas_por_rol(role_id)
    permitidas_ids = {x["ruta_id"] for x in permitidas}

    for ruta in rutas:
        ruta["permitida"] = ruta["id"] in permitidas_ids

    return rutas


def tiene_permiso_endpoint(role_id: int, endpoint: str) -> bool:
    supabase = get_supabase_admin()

    res = (
        supabase
        .table("roles_rutas")
        .select("id, rutas!inner(id, endpoint)")
        .eq("role_id", role_id)
        .eq("rutas.endpoint", endpoint)
        .limit(1)
        .execute()
    )

    data = res.data or []
    return len(data) > 0