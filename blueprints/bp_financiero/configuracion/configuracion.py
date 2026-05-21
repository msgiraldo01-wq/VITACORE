from flask import Blueprint, render_template

bp_financiero_configuracion = Blueprint(
    "bp_financiero_configuracion",
    __name__,
    url_prefix="/financiero/configuracion"
)

@bp_financiero_configuracion.route("/")
def index():

    return render_template(
        "financiero/configuracion.html"
    )