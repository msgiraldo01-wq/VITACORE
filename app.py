from flask import Flask, render_template, session, redirect, url_for, request, jsonify # type: ignore
from config import Config
from services import permisos_service
from blueprints.auth.routes import bp_auth
from blueprints.configuracion_roles.routes import bp_roles
from blueprints.configuracion_usuarios.routes import bp_usuarios
from blueprints.configuracion_auditoria.routes import bp_auditoria
from blueprints.hc_configuracion.routes import bp_hc_configuracion
from routes import bp_hc_dashboard
from blueprints.hc_pacientes.routes import bp_hc_pacientes
from blueprints.hc_evoluciones.routes import bp_hc_evoluciones
from blueprints.hc_signos_vitales.routes import bp_hc_signos
from blueprints.hc_historia_clinica.routes import bp_hc_historia
from blueprints.hc_medicamentos._ini_ import bp_hc_medicamentos
from blueprints.citas.routes import bp_citas
from blueprints.hc_empresa.routes import bp_hc_empresa
from blueprints.bp_financiero.contratos.contratos import bp_financiero_contratos
from blueprints.bp_financiero.dashborad.dashboard import bp_financiero_dashboard
from blueprints.bp_financiero.facturacion.routes import bp_facturacion
from blueprints.bp_financiero.glosas.glosas import bp_financiero_glosas
from blueprints.bp_financiero.cartera.cartera import bp_financiero_cartera
from blueprints.bp_financiero.conciliaciones.conciliaciones import bp_financiero_conciliaciones
from blueprints.bp_financiero.tesoreria import bp_financiero_tesoreria
from blueprints.bp_financiero.caja.routes import bp_caja
from blueprints.bp_financiero.radicacion.radicacion import bp_financiero_radicacion
from blueprints.bp_financiero.configuracion.configuracion import bp_financiero_configuracion
from blueprints.rda.routes import bp_rda
from blueprints.inventario import inventario_bp
from blueprints.hc.historia_clinica.routes import bp_hc_home
from blueprints.hc_reportes.routes import bp_hc_reportes
from blueprints.hc_admisiones.routes import bp_hc_admisiones
from blueprints.hc_agenda_clinica.routes import bp_hc_agenda_clinica









app = Flask(__name__, template_folder="templates")
app.config.from_object(Config)

app.register_blueprint(bp_auth)
app.register_blueprint(bp_roles)
app.register_blueprint(bp_usuarios)
app.register_blueprint(bp_auditoria)
app.register_blueprint(bp_hc_configuracion)
app.register_blueprint(bp_hc_dashboard)
app.register_blueprint(bp_hc_pacientes)
app.register_blueprint(bp_hc_evoluciones)
app.register_blueprint(bp_hc_signos)
app.register_blueprint(bp_hc_historia)
app.register_blueprint(bp_hc_medicamentos)
app.register_blueprint(bp_citas)
app.register_blueprint(bp_hc_empresa)
app.register_blueprint(bp_financiero_contratos)
app.register_blueprint(bp_financiero_dashboard)
app.register_blueprint(bp_facturacion)
app.register_blueprint(bp_financiero_glosas)
app.register_blueprint(bp_financiero_cartera)
app.register_blueprint(bp_financiero_conciliaciones)
app.register_blueprint(bp_financiero_tesoreria)
app.register_blueprint(bp_caja)
app.register_blueprint(bp_financiero_radicacion)
app.register_blueprint(bp_financiero_configuracion)
app.register_blueprint(bp_rda)
app.register_blueprint(inventario_bp)
app.register_blueprint(bp_hc_home)
app.register_blueprint(bp_hc_reportes)
app.register_blueprint(bp_hc_admisiones)
app.register_blueprint(bp_hc_agenda_clinica)

@app.route("/")
def inicio():
    if not session.get("user"):
        return redirect(url_for("auth.login"))
    return render_template("/hc/index.html")

# en tu app Flask
@app.route('/ping')
def ping():
    return '', 204


# =========================================================
# CONTROL DE ACCESO CENTRAL POR MÓDULO
# =========================================================
# Reemplaza la verificación por rutas técnicas (que dependía de un
# role_id que el login nunca guardaba en sesión, ver
# blueprints/auth/routes.py) por una sola matriz por módulo de
# negocio (roles_modulos), la misma que se configura con checkboxes
# en /hc/configuracion/roles-permisos.
@app.before_request
def gate_permisos_por_modulo():
    if not session.get("user"):
        return None  # login_required de cada vista se encarga de esto

    modulo_code = permisos_service.resolver_modulo_code(request.path)
    if not modulo_code:
        return None  # ruta pública o todavía no mapeada a un módulo

    if permisos_service.puede(modulo_code, "view"):
        return None

    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"error": "No tienes permisos para acceder a este recurso."}), 403
    return render_template("/hc/acceso_denegado.html"), 403


@app.context_processor
def inyectar_helpers_permisos():
    return {"puede_ver": permisos_service.puede_ver, "puede": permisos_service.puede}

if __name__ == "__main__":
    app.run(debug=True)

