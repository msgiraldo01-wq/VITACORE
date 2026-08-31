from flask import Blueprint, render_template, redirect, url_for, flash

from blueprints.auth.decorators import login_required
from services.permisos_service import es_super_admin
from repositories.auth_historial_repo import listar_historial_todos

bp_auditoria = Blueprint(
    "configuracion_auditoria",
    __name__,
    url_prefix="/hc/configuracion/auditoria-accesos"
)


@bp_auditoria.route("/")
@login_required
def index():
    # Exclusivo de SUPER_ADMIN -- a propósito NO se usa la matriz de
    # permisos por rol/módulo (roles_modulos): esta pantalla muestra el
    # historial de acceso de TODOS los usuarios de TODAS las empresas,
    # y ese alcance nunca debe depender de un permiso asignable desde
    # Roles y permisos. Mismo criterio que ya usa el selector de
    # empresas para SUPER_ADMIN.
    if not es_super_admin():
        flash("No tienes permisos para acceder a este recurso.", "danger")
        return render_template("hc/acceso_denegado.html"), 403

    historial = listar_historial_todos(limit=100)

    return render_template(
        "hc/configuracion/auditoria_accesos.html",
        historial=historial,
    )
