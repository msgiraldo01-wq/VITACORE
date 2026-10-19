from flask import Blueprint, render_template, session, jsonify  # type: ignore
from blueprints.auth.decorators import login_required  # type: ignore
from services import dashboard_service
from services import permisos_service

bp_hc_dashboard = Blueprint(
    "hc_dashboard",
    __name__,
    url_prefix="/hc"
)


@bp_hc_dashboard.route("/")
@login_required
def index():
    return render_template("hc/dashboard.html")


@bp_hc_dashboard.route("/api/dashboard")
@login_required
def api_dashboard():
    """
    Datos del Dashboard clinico. Va aparte de la pantalla a proposito: la
    plantilla se pinta de inmediato con sus esqueletos y los numeros entran
    despues, en vez de dejar al usuario mirando una pagina en blanco
    mientras corren las consultas.

    Solo se consulta lo que el rol puede ver: cada tarjeta apagada aqui es
    una consulta que no se hace.
    """
    empresa_id = session.get("empresa_id")
    if not empresa_id:
        return jsonify({"ok": False, "message": "Sin empresa activa."}), 400

    permisos = {
        "agenda": permisos_service.puede("citas", "view"),
        "actividad": permisos_service.puede("historia_clinica", "view"),
        "ultimas": permisos_service.puede("historia_clinica", "view"),
        "rda": permisos_service.puede("rda", "view"),
        "farmacia": permisos_service.puede("farmacia", "view"),
    }

    try:
        datos = dashboard_service.resumen(empresa_id, permisos)
    except Exception as e:
        print("[DASHBOARD] error general:", e)
        return jsonify({"ok": False, "message": "No se pudo cargar el resumen."}), 500

    return jsonify({"ok": True, **datos})
