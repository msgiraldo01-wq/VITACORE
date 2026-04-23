from flask import Blueprint, render_template, request, redirect, url_for, flash
from blueprints.auth.decorators import login_required, rol_required
from repositories.users_repository import (
    listar_roles_activos,
    listar_usuarios,
    obtener_usuario,
    crear_usuario_con_perfil,
    actualizar_usuario,
    cambiar_estado_usuario,
)

bp_usuarios = Blueprint(
    "configuracion_usuarios",
    __name__,
    url_prefix="/hc/configuracion/usuarios"
)


@bp_usuarios.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        role_id_raw = (request.form.get("role_id") or "").strip()

        if not username or not full_name or not email or not password or not role_id_raw:
            flash("Debes completar todos los campos.", "warning")
            return redirect(url_for("configuracion_usuarios.index"))

        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "warning")
            return redirect(url_for("configuracion_usuarios.index"))

        if not role_id_raw.isdigit():
            flash("Rol inválido.", "danger")
            return redirect(url_for("configuracion_usuarios.index"))

        role_id = int(role_id_raw)

        try:
            crear_usuario_con_perfil(
                username=username,
                full_name=full_name,
                email=email,
                password=password,
                role_id=role_id,
            )
            flash("Usuario creado correctamente.", "success")
            return redirect(url_for("configuracion_usuarios.index"))

        except Exception as e:
            flash(f"Error al crear usuario: {str(e)}", "danger")
            return redirect(url_for("configuracion_usuarios.index"))

    roles = listar_roles_activos()
    usuarios = listar_usuarios()

    return render_template(
        "hc/configuracion/usuarios.html",
        roles=roles,
        usuarios=usuarios,
    )


@bp_usuarios.route("/<string:user_id>/editar", methods=["GET", "POST"])
@login_required
def editar(user_id: str):
    usuario = obtener_usuario(user_id)
    if not usuario:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("configuracion_usuarios.index"))

    roles = listar_roles_activos()

    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        role_id_raw = (request.form.get("role_id") or "").strip()
        is_active = request.form.get("is_active") == "1"

        if not username or not full_name or not email or not role_id_raw:
            flash("Debes completar todos los campos.", "warning")
            return redirect(url_for("configuracion_usuarios.editar", user_id=user_id))

        if not role_id_raw.isdigit():
            flash("Rol inválido.", "danger")
            return redirect(url_for("configuracion_usuarios.editar", user_id=user_id))

        role_id = int(role_id_raw)

        try:
            actualizar_usuario(
                user_id=user_id,
                username=username,
                full_name=full_name,
                email=email,
                role_id=role_id,
                is_active=is_active,
            )
            flash("Usuario actualizado correctamente.", "success")
            return redirect(url_for("configuracion_usuarios.index"))

        except Exception as e:
            flash(f"Error al actualizar usuario: {str(e)}", "danger")
            return redirect(url_for("configuracion_usuarios.editar", user_id=user_id))

    return render_template(
        "hc/configuracion/usuario_editar.html",
        usuario=usuario,
        roles=roles,
    )


@bp_usuarios.route("/<string:user_id>/estado", methods=["POST"])
@login_required
def cambiar_estado(user_id: str):
    usuario = obtener_usuario(user_id)
    if not usuario:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("configuracion_usuarios.index"))

    nuevo_estado = not bool(usuario.get("is_active"))

    try:
        cambiar_estado_usuario(user_id, nuevo_estado)
        flash("Estado del usuario actualizado correctamente.", "success")
    except Exception as e:
        flash(f"Error al cambiar estado: {str(e)}", "danger")

    return redirect(url_for("configuracion_usuarios.index"))