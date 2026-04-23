from functools import wraps
from flask import session, redirect, url_for, request, jsonify, render_template
from repositories.security_repository import tiene_permiso_endpoint


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        user = session.get("user")

        if not user:
            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({
                    "error": "No has iniciado sesión.",
                    "redirect": url_for("auth.login")
                }), 401
            return redirect(url_for("auth.login"))

        return view_func(*args, **kwargs)
    return wrapped_view


def rol_required(*roles_permitidos, usar_matriz=True):
    """
    Control de acceso por rol y/o por matriz de rutas.

    Ejemplos:
        @rol_requerido("admin")
        @rol_requerido("admin", "medico")
        @rol_requerido(usar_matriz=True)
    """
    def wrapper(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            user = session.get("user")

            if not user:
                if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({
                        "error": "No has iniciado sesión.",
                        "redirect": url_for("auth.login")
                    }), 401
                return redirect(url_for("auth.login"))

            role_actual = (user.get("role") or "").strip().lower()
            role_id = user.get("role_id")
            autorizado = False

            # 1. lógica estática por nombre de rol
            if roles_permitidos:
                roles_norm = {str(r).strip().lower() for r in roles_permitidos}
                if role_actual in roles_norm:
                    autorizado = True

            # 2. lógica dinámica por matriz
            if not autorizado and usar_matriz and role_id:
                endpoint = request.endpoint or ""
                autorizado = tiene_permiso_endpoint(role_id=role_id, endpoint=endpoint)

            if not autorizado:
                if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({
                        "error": "No tienes permisos para acceder a este recurso."
                    }), 403
                return render_template("/hc/acceso_denegado.html"), 403

            return view_func(*args, **kwargs)
        return wrapped_view
    return wrapper