from flask import Blueprint, render_template

bp_financiero_tesoreria = Blueprint(
    "bp_financiero_tesoreria",
    __name__,
    url_prefix="/financiero/tesoreria"
)

@bp_financiero_tesoreria.route("/")
def tesoreria():

    return render_template(
        "financiero/tesoreria.html"
    )