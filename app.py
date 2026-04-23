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



@app.route("/")
def inicio():
    if not session.get("user"):
        return redirect(url_for("auth.login"))
    return render_template("/hc/index.html")

if __name__ == "__main__":
    app.run(debug=True)

app.register_blueprint(bp_hc_medicamentos)