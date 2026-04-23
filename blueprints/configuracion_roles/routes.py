from flask import Blueprint, render_template, request, redirect, url_for, flash # type: ignore

from blueprints.auth.decorators import login_required, rol_required

from repositories.roles_repository import (
    listar_roles,
    obtener_rol_por_id,
    construir_matriz_roles,
    guardar_permisos_rol,
    crear_rol,
)

from repositories import hc_servicios_repo
from repositories import hc_especialidades_repo


bp_roles = Blueprint(
    "configuracion_roles",
    __name__,
    url_prefix="/hc/configuracion/roles-permisos"
)


# =========================================================
# ROLES Y PERMISOS
# =========================================================

@bp_roles.route("/", methods=["GET", "POST"])
@login_required
@rol_required(usar_matriz=True)
def roles_permisos():

    roles = listar_roles()

    role_id_raw = request.args.get("role_id") or request.form.get("role_id")
    role_id = None

    if role_id_raw and str(role_id_raw).isdigit():
        role_id = int(role_id_raw)
    elif roles:
        role_id = roles[0]["id"]

    rol_activo = obtener_rol_por_id(role_id) if role_id else None

    if request.method == "POST":

        if not rol_activo:
            flash("Rol no válido.", "danger")
            return redirect(url_for("configuracion_roles.roles_permisos"))

        permisos = []

        modulo_ids = request.form.getlist("modulo_ids")

        for modulo_id_raw in modulo_ids:

            if not str(modulo_id_raw).isdigit():
                continue

            modulo_id = int(modulo_id_raw)

            can_view = request.form.get(f"view_{modulo_id}") == "1"
            can_create = request.form.get(f"create_{modulo_id}") == "1"
            can_edit = request.form.get(f"edit_{modulo_id}") == "1"
            can_delete = request.form.get(f"delete_{modulo_id}") == "1"

            if can_view or can_create or can_edit or can_delete:

                permisos.append({
                    "role_id": rol_activo["id"],
                    "modulo_id": modulo_id,
                    "can_view": can_view,
                    "can_create": can_create,
                    "can_edit": can_edit,
                    "can_delete": can_delete,
                })

        guardar_permisos_rol(rol_activo["id"], permisos)

        flash("Permisos actualizados correctamente.", "success")

        return redirect(
            url_for(
                "configuracion_roles.roles_permisos",
                role_id=rol_activo["id"]
            )
        )

    matriz = construir_matriz_roles(role_id) if role_id else {}

    return render_template(
        "hc/configuracion/roles_permisos.html",
        roles=roles,
        rol_activo=rol_activo,
        matriz=matriz,
    )


# =========================================================
# CREAR ROL
# =========================================================

@bp_roles.route("/crear", methods=["POST"])
@login_required
@rol_required(usar_matriz=True)
def crear_rol_view():

    code = (request.form.get("code") or "").strip().lower()
    name = (request.form.get("name") or "").strip()

    if not code or not name:
        flash("Debes ingresar código y nombre del rol.", "warning")
        return redirect(url_for("configuracion_roles.roles_permisos"))

    try:

        nuevo = crear_rol(code=code, name=name)

        if not nuevo:
            flash("No fue posible crear el rol.", "danger")
            return redirect(url_for("configuracion_roles.roles_permisos"))

        flash("Rol creado correctamente.", "success")

        return redirect(
            url_for(
                "configuracion_roles.roles_permisos",
                role_id=nuevo["id"]
            )
        )

    except Exception as e:

        flash(f"Error al crear el rol: {str(e)}", "danger")

        return redirect(url_for("configuracion_roles.roles_permisos"))


# =========================================================
# SERVICIOS
# =========================================================

@bp_roles.route("/servicios")
@login_required
@rol_required(usar_matriz=True)
def servicios():

    servicios = hc_servicios_repo.listar_servicios()

    return render_template(
        "hc/configuracion/servicios.html",
        servicios=servicios
    )


@bp_roles.route("/servicios/nuevo")
@login_required
@rol_required(usar_matriz=True)
def servicios_nuevo():

    especialidades = hc_especialidades_repo.listar_especialidades()

    return render_template(
        "hc/configuracion/servicios_form.html",
        modo="crear",
        servicio=None,
        especialidades=especialidades
    )


@bp_roles.route("/servicios/crear", methods=["POST"])
@login_required
@rol_required(usar_matriz=True)
def servicios_crear():

    data = {
        "codigo": request.form.get("codigo"),
        "nombre": request.form.get("nombre"),
        "especialidad_id": request.form.get("especialidad_id") or None,
        "descripcion": request.form.get("descripcion"),
    }

    hc_servicios_repo.crear_servicio(data)

    flash("Servicio creado correctamente", "success")

    return redirect(url_for("configuracion_roles.servicios"))


@bp_roles.route("/servicios/<int:id>/editar")
@login_required
@rol_required(usar_matriz=True)
def servicios_editar(id):

    servicio = hc_servicios_repo.obtener_servicio(id)

    especialidades = hc_especialidades_repo.listar_especialidades()

    return render_template(
        "hc/configuracion/servicios_form.html",
        modo="editar",
        servicio=servicio,
        especialidades=especialidades
    )


@bp_roles.route("/servicios/<int:id>/actualizar", methods=["POST"])
@login_required
@rol_required(usar_matriz=True)
def servicios_actualizar(id):

    data = {
        "codigo": request.form.get("codigo"),
        "nombre": request.form.get("nombre"),
        "especialidad_id": request.form.get("especialidad_id") or None,
        "descripcion": request.form.get("descripcion"),
    }

    hc_servicios_repo.actualizar_servicio(id, data)

    flash("Servicio actualizado", "success")

    return redirect(url_for("configuracion_roles.servicios"))