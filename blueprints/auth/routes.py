from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from repositories.auth_repository import obtener_perfil_por_username
from repositories.auth_historial_repo import registrar_intento, listar_historial_usuario
from services.supabase_service import get_supabase_public
from services.geoip_service import obtener_ip_cliente, localizar_ip, parsear_user_agent
from . decorators import login_required

bp_auth = Blueprint("auth", __name__, url_prefix="/auth")


@bp_auth.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user"):
        return redirect(url_for("inicio"))

    if request.method == "GET":
        return render_template("auth/login.html")

    username = (request.form.get("username") or "").strip().lower()
    password = request.form.get("password") or ""

    if not username or not password:
        flash("Debes ingresar usuario y contraseña.", "warning")
        return render_template("auth/login.html")

    # 📍 Auditoría de accesos: datos del intento, calculados una sola
    # vez porque no cambian entre las distintas ramas de abajo.
    ip_address = obtener_ip_cliente(request)
    user_agent = request.headers.get("User-Agent", "")
    dispositivo = parsear_user_agent(user_agent)
    pais, ciudad = localizar_ip(ip_address)

    def _registrar(exito, motivo, user_id=None):
        registrar_intento(
            username=username,
            exito=exito,
            motivo=motivo,
            user_id=user_id,
            ip_address=ip_address,
            pais=pais,
            ciudad=ciudad,
            dispositivo=dispositivo,
            user_agent=user_agent,
        )

    try:
        perfil = obtener_perfil_por_username(username)

        if not perfil:
            flash("El usuario no existe.", "danger")
            _registrar(False, "usuario_no_existe")
            return render_template("auth/login.html")

        if not perfil.get("is_active", True):
            flash("Tu usuario está inactivo.", "warning")
            _registrar(False, "cuenta_inactiva", user_id=perfil.get("id"))
            return render_template("auth/login.html")

        email = (perfil.get("email") or "").strip().lower()
        if not email:
            flash("El usuario no tiene correo configurado.", "danger")
            _registrar(False, "sin_correo_configurado", user_id=perfil.get("id"))
            return render_template("auth/login.html")

        # 🔐 Login con Supabase
        supabase = get_supabase_public()
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        user = getattr(response, "user", None)
        user_session = getattr(response, "session", None)

        if not user or not user_session:
            flash("Usuario o contraseña incorrectos.", "danger")
            _registrar(False, "credenciales_invalidas", user_id=perfil.get("id"))
            return render_template("auth/login.html")

        # 🔥 SESSION LIMPIA (SIN roles raros)
        session["user"] = {
            "id": perfil["id"],
            "username": perfil["username"],
            "full_name": perfil.get("full_name") or "",
            "email": perfil.get("email") or "",
            "role": perfil.get("role", ""),          # 🔥 DESDE BD (legado, SUPER_ADMIN vive aquí)
            "role_id": perfil.get("role_id"),        # 🔥 NECESARIO para la matriz de permisos por módulo
            "empresa_id": perfil.get("empresa_id")   # 🔥 CLAVE MULTIEMPRESA
        }

        # 🔥 ACCESO DIRECTO (para no depender de session["user"])
        session["rol"] = perfil.get("role", "")
        session["empresa_id"] = perfil.get("empresa_id")

        session["supabase_access_token"] = user_session.access_token
        session["supabase_refresh_token"] = user_session.refresh_token

        _registrar(True, "ok", user_id=perfil.get("id"))

        # 🧪 DEBUG (puedes quitar después)
        print("ROL:", session.get("rol"))
        print("EMPRESA:", session.get("empresa_id"))

        flash("Bienvenido a Vitacore.", "success")

        # 👑 SUPER ADMIN → selector de empresa
        if session.get("rol") == "SUPER_ADMIN":
            return redirect("/empresa/seleccionar")

        # 🏥 USUARIO NORMAL SIN EMPRESA → error
        if not session.get("empresa_id"):
            flash("Usuario sin empresa asignada.", "warning")
            return redirect(url_for("auth.login"))

        # 🏥 USUARIO NORMAL → sistema
        return redirect("/hc")  # o url_for("inicio")

    except Exception as e:
        print("ERROR LOGIN:", e)
        flash("Usuario o contraseña incorrectos.", "danger")
        _registrar(False, "error_interno")
        return render_template("auth/login.html")


@bp_auth.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("auth.login"))


@bp_auth.route("/mi-perfil")
@login_required
def mi_perfil():

    if not session.get("user"):
        return redirect(url_for("auth.login"))

    user = session.get("user")
    historial = listar_historial_usuario(user.get("id"), limit=20)

    return render_template(
        "auth/mi_perfil.html",
        user=user,
        historial=historial
    )


@bp_auth.route("/cambiar-password", methods=["POST"])
@login_required
def cambiar_password():

    if not session.get("user"):
        return redirect(url_for("auth.login"))

    password_actual = request.form.get("password_actual")
    password_nueva = request.form.get("password_nueva")

    if not password_actual or not password_nueva:
        flash("Debes completar todos los campos.", "warning")
        return redirect(url_for("auth.mi_perfil"))

    try:

        email = session["user"]["email"]

        supabase = get_supabase_public()

        # volver a autenticar
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password_actual
        })

        if not getattr(response, "user", None):
            flash("La contraseña actual es incorrecta.", "danger")
            return redirect(url_for("auth.mi_perfil"))

        access_token = response.session.access_token

        supabase.auth.update_user(
            {"password": password_nueva},
            access_token
        )

        flash("Contraseña actualizada correctamente.", "success")

    except Exception as e:
        flash(f"Error al cambiar contraseña: {str(e)}", "danger")

    return redirect(url_for("auth.mi_perfil"))