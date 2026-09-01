from flask import Blueprint, render_template
from blueprints.auth.decorators import login_required

bp_financiero_conciliaciones = Blueprint(
    "bp_financiero_conciliaciones",
    __name__,
    url_prefix="/financiero/conciliaciones"
)

@bp_financiero_conciliaciones.route("/")
@login_required
def conciliaciones():

    return render_template(
        "financiero/conciliaciones.html"
    )