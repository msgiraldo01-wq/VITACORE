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


def listar_modulos():
    supabase = get_supabase_admin()
    res = (
        supabase
        .table("modulos")
        .select("""
            id,
            code,
            name,
            endpoint,
            icon,
            section,
            visible_in_sidebar,
            is_active,
            sort_order
        """)
        .eq("is_active", True)
        .order("section")
        .order("sort_order")
        .order("name")
        .execute()
    )
    return res.data or []


def listar_permisos_de_rol(role_id: int):
    supabase = get_supabase_admin()
    res = (
        supabase
        .table("roles_modulos")
        .select("""
            id,
            role_id,
            modulo_id,
            can_view,
            can_create,
            can_edit,
            can_delete
        """)
        .eq("role_id", role_id)
        .execute()
    )
    return res.data or []


def guardar_permisos_rol(role_id: int, permisos: list[dict]):
    supabase = get_supabase_admin()

    # borra matriz actual
    (
        supabase
        .table("roles_modulos")
        .delete()
        .eq("role_id", role_id)
        .execute()
    )

    if not permisos:
        return []

    # inserta nueva matriz
    res = (
        supabase
        .table("roles_modulos")
        .insert(permisos)
        .execute()
    )
    return res.data or []


def construir_matriz_roles(role_id: int):
    modulos = listar_modulos()
    permisos = listar_permisos_de_rol(role_id)

    permisos_map = {p["modulo_id"]: p for p in permisos}
    secciones = {}

    for modulo in modulos:
        section = modulo.get("section") or "OTROS"
        permiso = permisos_map.get(modulo["id"], {})

        item = {
            "id": modulo["id"],
            "code": modulo.get("code"),
            "name": modulo.get("name"),
            "endpoint": modulo.get("endpoint"),
            "icon": modulo.get("icon") or "fa-solid fa-circle",
            "visible_in_sidebar": bool(modulo.get("visible_in_sidebar", True)),
            "can_view": bool(permiso.get("can_view", False)),
            "can_create": bool(permiso.get("can_create", False)),
            "can_edit": bool(permiso.get("can_edit", False)),
            "can_delete": bool(permiso.get("can_delete", False)),
        }

        secciones.setdefault(section, []).append(item)

    return secciones


def crear_rol(code: str, name: str):
    supabase = get_supabase_admin()

    payload = {
        "code": (code or "").strip().lower(),
        "name": (name or "").strip(),
        "is_active": True,
    }

    res = (
        supabase
        .table("roles")
        .insert(payload)
        .execute()
    )

    data = res.data or []
    return data[0] if data else None