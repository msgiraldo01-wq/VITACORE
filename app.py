from flask import Flask, render_template, session, redirect, url_for # type: ignore
from config import Config
from blueprints.auth.routes import bp_auth
from blueprints.configuracion_roles.routes import bp_roles
from blueprints.configuracion_roles.routes_admin import bp_admin
from blueprints.configuracion_roles.routes_rutas import bp_permisos_rutas
from blueprints.configuracion_usuarios.routes import bp_usuarios
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








app = Flask(__name__, template_folder="templates")
app.config.from_object(Config)

app.register_blueprint(bp_auth)
app.register_blueprint(bp_roles)
app.register_blueprint(bp_admin)
app.register_blueprint(bp_permisos_rutas)
app.register_blueprint(bp_usuarios)
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

@app.route("/")
def inicio():
    if not session.get("user"):
        return redirect(url_for("auth.login"))
    return render_template("/hc/index.html")

if __name__ == "__main__":
    app.run(debug=True)

