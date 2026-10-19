from flask import Blueprint, render_template
from blueprints.auth.decorators import login_required

bp_financiero_configuracion = Blueprint(
    "bp_financiero_configuracion",
    __name__,
    url_prefix="/financiero/configuracion"
)

@bp_financiero_configuracion.route("/")
@login_required
def index():

    return render_template(
        "financiero/configuracion.html"
    )