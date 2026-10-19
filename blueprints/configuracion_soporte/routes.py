"""
Soporte · errores de la aplicación.

Pantalla para ver qué se está rompiendo en producción. El usuario reporta
un código (VTC-7F3A91) y aquí se busca ese código y se ve el detalle
completo: ruta, usuario, empresa, navegador y la traza.

Va bajo /hc/configuracion pero tiene su PROPIO módulo de permisos
('soporte'), porque las trazas muestran rutas y estructura interna del
sistema y no todo el que administra catálogos tiene por qué verlas.
"""

from flask import Blueprint, render_template, request, jsonify, redirect

from blueprints.auth.decorators import login_required
from services.permisos_service import requiere_permiso
from repositories import app_errores_repo as repo

bp_soporte = Blueprint(
    "soporte",
    __name__,
    url_prefix="/hc/configuracion/soporte",
)


@bp_soporte.route("/")
@login_required
@requiere_permiso("soporte", "view")
def index():
    estado = (request.args.get("estado") or "").upper()
    busqueda = request.args.get("q") or ""
    modulo = request.args.get("modulo") or ""

    errores = repo.listar(estado=estado, busqueda=busqueda, modulo=modulo)
    resumen = repo.resumen()

    return render_template(
        "hc/configuracion/soporte.html",
        errores=errores,
        resumen=resumen,
        estado_filtro=estado,
        busqueda=busqueda,
        modulo_filtro=modulo,
    )


@bp_soporte.route("/<int:error_id>")
@login_required
@requiere_permiso("soporte", "view")
def detalle(error_id):
    error = repo.obtener(error_id)
    if not error:
        return redirect("/hc/configuracion/soporte/")
    return render_template("hc/configuracion/soporte_detalle.html", error=error)


@bp_soporte.route("/<int:error_id>/estado", methods=["POST"])
@login_required
@requiere_permiso("soporte", "edit")
def cambiar_estado(error_id):
    datos = request.get_json(silent=True) or {}
    estado = datos.get("estado") or ""
    notas = datos.get("notas")

    try:
        actualizado = repo.cambiar_estado(error_id, estado, notas)
    except ValueError as e:
        return jsonify({"ok": False, "message": str(e)}), 400

    if not actualizado:
        return jsonify({"ok": False, "message": "No se encontró el error."}), 404

    return jsonify({"ok": True, "estado": actualizado.get("estado")})
