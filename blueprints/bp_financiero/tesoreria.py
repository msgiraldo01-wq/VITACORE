from flask import Blueprint, render_template
from blueprints.auth.decorators import login_required

bp_financiero_tesoreria = Blueprint(
    "bp_financiero_tesoreria",
    __name__,
    url_prefix="/financiero/tesoreria"
)

@bp_financiero_tesoreria.route("/")
@login_required
def tesoreria():

    return render_template(
        "financiero/tesoreria.html"
    )