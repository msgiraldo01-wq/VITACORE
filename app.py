import os
import time

from flask import Flask, render_template, session, redirect, url_for, request, jsonify, abort, g # type: ignore
from werkzeug.exceptions import HTTPException

from config import Config
from services import permisos_service
from services import modulos_service
from services import error_service
from services import sesion_service
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
from blueprints.bp_financiero.dashborad.dashboard import bp_financiero_dashboard
from blueprints.bp_financiero.facturacion.routes import bp_facturacion
from blueprints.bp_financiero.glosas.glosas import bp_financiero_glosas
from blueprints.bp_financiero.cartera.cartera import bp_financiero_cartera
from blueprints.bp_financiero.conciliaciones.conciliaciones import bp_financiero_conciliaciones
from blueprints.bp_financiero.tesoreria import bp_financiero_tesoreria
from blueprints.bp_financiero.caja.routes import bp_caja
from blueprints.bp_financiero.radicacion.radicacion import bp_financiero_radicacion
from blueprints.bp_financiero.configuracion.configuracion import bp_financiero_configuracion
from blueprints.bp_financiero.contabilidad.contabilidad import bp_financiero_contabilidad
from blueprints.rda.routes import bp_rda
from blueprints.inventario import inventario_bp
from blueprints.hc.historia_clinica.routes import bp_hc_home
from blueprints.hc_reportes.routes import bp_hc_reportes
from blueprints.hc_admisiones.routes import bp_hc_admisiones
from blueprints.hc_agenda_clinica.routes import bp_hc_agenda_clinica
from blueprints.configuracion_soporte.routes import bp_soporte




app = Flask(__name__, template_folder="templates")
app.config.from_object(Config)

# Logger a archivo rotativo (logs/vitacore.log) + consola.
error_service.configurar_logging(app)
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
app.register_blueprint(bp_financiero_contabilidad)
app.register_blueprint(bp_hc_reportes)
app.register_blueprint(bp_hc_admisiones)
app.register_blueprint(bp_hc_agenda_clinica)
app.register_blueprint(bp_soporte)

@app.route("/")
def inicio():
    if not session.get("user"):
        return redirect(url_for("auth.login"))
    return render_template("/hc/index.html")

# en tu app Flask
@app.route('/ping')
def ping():
    return '', 204


@app.route('/sesion/renovar', methods=["POST"])
def renovar_sesion():
    """
    El botón "Seguir trabajando" del aviso de caducidad.

    No hace nada por sí misma: lo que renueva la sesión es haber
    llegado hasta aquí, porque esta ruta NO está en la lista de exentas
    y el guardia de arriba ya le puso la marca de actividad. Si la
    sesión ya había caducado, el guardia respondió 401 antes y esto no
    se ejecuta.
    """
    if not session.get("user"):
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True})


@app.context_processor
def politica_de_sesion():
    """La política vigente, para que base.html arme su contador."""
    if not session.get("user"):
        return {}
    return {"sesion_politica": sesion_service.politica(session.get("empresa_id"))}


# =========================================================
# CONTROL DE ACCESO CENTRAL POR MÓDULO
# =========================================================
# Reemplaza la verificación por rutas técnicas (que dependía de un
# role_id que el login nunca guardaba en sesión, ver
# blueprints/auth/routes.py) por una sola matriz por módulo de
# negocio (roles_modulos), la misma que se configura con checkboxes
# en /hc/configuracion/roles-permisos.
# =========================================================
# CUÁNTO TARDÓ EL SERVIDOR
# =========================================================
# Flask sabe cuánto tardó en armar cada respuesta y hasta ahora no lo
# decía. Con esta cabecera el navegador puede separar lo que es lento
# por la red de lo que es lento por la aplicación, que es la pregunta
# que uno se hace cuando "el sistema está lento".

@app.before_request
def marcar_inicio():
    g._inicio_peticion = time.perf_counter()


@app.after_request
def informar_tiempo_servidor(respuesta):
    inicio = getattr(g, "_inicio_peticion", None)
    if inicio is not None:
        ms = (time.perf_counter() - inicio) * 1000
        respuesta.headers["X-Tiempo-Servidor"] = f"{ms:.0f}"
        # para que el navegador pueda leerla también en peticiones fetch
        respuesta.headers["Timing-Allow-Origin"] = "*"
    return respuesta


@app.before_request
def cerrar_sesion_caducada():
    """
    Cierra la sesión por inactividad o por jornada.

    Va ANTES del control de módulos a propósito: a una sesión caducada
    no hay que decirle qué módulos tiene contratados, hay que sacarla.

    El servidor es la autoridad. El navegador también lleva su contador
    (base.html) para avisar antes de cortar, pero es solo cortesía: si
    alguien lo desactiva, manipula el reloj de su máquina o deja un
    script dando clics, aquí se cierra igual.
    """
    if not session.get("user"):
        return None
    if sesion_service.es_exenta(request.path):
        return None

    ahora = time.time()
    politica = sesion_service.politica(session.get("empresa_id"))
    motivo = sesion_service.motivo_de_cierre(
        session.get("ultima_actividad"),
        session.get("inicio_sesion"),
        ahora,
        politica,
    )

    if motivo:
        session.clear()
        destino = url_for("auth.login", caducada=motivo)
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "error": "La sesión caducó.",
                "redirect": destino,
            }), 401
        return redirect(destino)

    # No se reescribe la cookie en cada petición: con la ventana más
    # corta que admitimos (5 minutos) medio minuto de desfase no cambia
    # nada, y evita un Set-Cookie en cada clic.
    try:
        if ahora - float(session.get("ultima_actividad") or 0) > 30:
            session["ultima_actividad"] = ahora
    except (TypeError, ValueError):
        session["ultima_actividad"] = ahora

    return None


@app.before_request
def gate_permisos_por_modulo():
    if not session.get("user"):
        return None  # login_required de cada vista se encarga de esto

    modulo_code = permisos_service.resolver_modulo_code(request.path)
    if not modulo_code:
        return None  # ruta pública o todavía no mapeada a un módulo

    # Módulo que la empresa no contrató: se responde como si la ruta no
    # existiera. Un 403 confirmaría que el módulo está ahí; con 404 el
    # sistema se ve hecho a la medida de lo que cada IPS compró.
    if not modulos_service.tiene(modulo_code):
        abort(404)

    if permisos_service.puede(modulo_code, "view"):
        return None

    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"error": "No tienes permisos para acceder a este recurso."}), 403
    return render_template("/hc/acceso_denegado.html"), 403


@app.context_processor
def inyectar_helpers_permisos():
    # menu_modulos arma el menú lateral desde la tabla `modulos`, ya
    # filtrado por lo que la empresa contrató y lo que el rol puede ver.
    return {
        "puede_ver": permisos_service.puede_ver,
        "puede": permisos_service.puede,
        "menu_modulos": lambda: modulos_service.menu_visible(permisos_service.puede_ver),
    }

# =========================================================
# MANEJO DE ERRORES
# =========================================================
# Todo lo que no se atrape en una vista termina aquí: se registra con un
# código y al usuario se le muestra ese código, nunca la traza. Las
# peticiones AJAX reciben el mismo código en JSON, para que el frontend
# lo pueda mostrar sin inventarse un mensaje.

def _es_ajax():
    return (request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.path.startswith("/api/")
            or "/api/" in request.path)


def _pagina_error(codigo_http, titulo, mensaje, codigo_error=None):
    if _es_ajax():
        cuerpo = {"ok": False, "error": mensaje}
        if codigo_error:
            cuerpo["codigo"] = codigo_error
        return jsonify(cuerpo), codigo_http
    return render_template(
        "hc/error.html", codigo_http=codigo_http, titulo=titulo,
        mensaje=mensaje, codigo_error=codigo_error,
    ), codigo_http


@app.errorhandler(404)
def error_404(e):
    return _pagina_error(404, "Página no encontrada",
                         "La dirección que abriste no existe o cambió de lugar.")


@app.errorhandler(403)
def error_403(e):
    return _pagina_error(403, "Sin permiso",
                         "Tu rol no tiene acceso a esta parte del sistema.")


@app.errorhandler(Exception)
def error_no_controlado(e):
    # Los errores HTTP "normales" (404, 405, 413...) no son fallas del
    # sistema: no se registran como tales.
    if isinstance(e, HTTPException) and e.code and e.code < 500:
        return _pagina_error(e.code, e.name or "No se pudo completar",
                             e.description or "La petición no se pudo procesar.")

    codigo = error_service.registrar(e)
    return _pagina_error(
        500, "Algo falló de nuestro lado",
        "El equipo de soporte ya tiene el detalle. Si necesitas ayuda, "
        "dicta este código.", codigo_error=codigo,
    )


if __name__ == "__main__":
    # debug=True levanta el depurador de Werkzeug, que permite ejecutar
    # código en el servidor desde el navegador: NUNCA en producción.
    # En el servidor se arranca con un WSGI real, por ejemplo:
    #     waitress-serve --host=0.0.0.0 --port=8000 app:app
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="0.0.0.0")

