from services.supabase_service import get_supabase_admin


def listar_roles_activos():
    supabase = get_supabase_admin()
    res = (
        supabase
        .table("roles")
        .select("id, code, name")
        .eq("is_active", True)
        .order("name")
        .execute()
    )
    return res.data or []


def listar_usuarios():
    supabase = get_supabase_admin()
    res = (
        supabase
        .table("profiles")
        .select("""
            id,
            username,
            full_name,
            email,
            role_id,
            is_active,
            roles:role_id (
                id,
                code,
                name
            )
        """)
        .order("username")
        .execute()
    )
    return res.data or []


def obtener_usuario(user_id: str):
    supabase = get_supabase_admin()
    res = (
        supabase
        .table("profiles")
        .select("""
            id,
            username,
            full_name,
            email,
            role_id,
            is_active,
            roles:role_id (
                id,
                code,
                name
            )
        """)
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    data = res.data or []
    return data[0] if data else None


def crear_usuario_con_perfil(username: str, full_name: str, email: str, password: str, role_id: int):
    supabase = get_supabase_admin()

    auth_res = supabase.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": True,
    })

    user = getattr(auth_res, "user", None)
    if not user:
        raise ValueError("No fue posible crear el usuario en Supabase Auth.")

    profile_payload = {
        "id": user.id,
        "username": username.strip().lower(),
        "full_name": full_name.strip(),
        "email": email.strip().lower(),
        "role_id": role_id,
        "is_active": True,
    }

    profile_res = (
        supabase
        .table("profiles")
        .insert(profile_payload)
        .execute()
    )

    return {
        "auth_user": user,
        "profile": (profile_res.data or [None])[0]
    }


def actualizar_usuario(user_id: str, username: str, full_name: str, email: str, role_id: int, is_active: bool):
    supabase = get_supabase_admin()

    # actualiza email en auth.users
    supabase.auth.admin.update_user_by_id(
        user_id,
        {
            "email": email.strip().lower(),
            "user_metadata": {
                "full_name": full_name.strip()
            }
        }
    )

    # actualiza perfil en profiles
    payload = {
        "username": username.strip().lower(),
        "full_name": full_name.strip(),
        "email": email.strip().lower(),
        "role_id": role_id,
        "is_active": is_active,
    }

    res = (
        supabase
        .table("profiles")
        .update(payload)
        .eq("id", user_id)
        .execute()
    )

    data = res.data or []
    return data[0] if data else None


def cambiar_estado_usuario(user_id: str, is_active: bool):
    supabase = get_supabase_admin()

    res = (
        supabase
        .table("profiles")
        .update({"is_active": is_active})
        .eq("id", user_id)
        .execute()
    )

    data = res.data or []
    return data[0] if data else None