from flask import Blueprint, render_template, request, redirect, url_for, flash
from blueprints.auth.decorators import login_required, rol_required
from repositories.security_repository import (
    listar_roles,
    obtener_rol_por_id,
    construir_matriz_rutas,
    guardar_permisos_rutas,
)

bp_permisos_rutas = Blueprint(
    "permisos_rutas",
    __name__,
    url_prefix="/hc/configuracion/permisos-rutas"
)


@bp_permisos_rutas.route("/", methods=["GET", "POST"])
@login_required
def index():
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
            return redirect(url_for("permisos_rutas.index"))

        ruta_ids_raw = request.form.getlist("ruta_ids")
        ruta_ids = []

        for rid in ruta_ids_raw:
            if str(rid).isdigit():
                ruta_ids.append(int(rid))

        guardar_permisos_rutas(rol_activo["id"], ruta_ids)
        flash("Permisos por ruta actualizados correctamente.", "success")
        return redirect(url_for("permisos_rutas.index", role_id=rol_activo["id"]))

    rutas = construir_matriz_rutas(role_id) if role_id else []

    return render_template(
        "hc/configuracion/permisos_rutas.html",
        roles=roles,
        rol_activo=rol_activo,
        rutas=rutas,
    )