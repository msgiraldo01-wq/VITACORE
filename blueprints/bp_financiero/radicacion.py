from flask import Blueprint, render_template

bp_financiero_radicacion = Blueprint(
    "bp_financiero_radicacion",
    __name__,
    url_prefix="/financiero/radicacion"
)

@bp_financiero_radicacion.route("/")
def radicacion():

    return render_template(
        "financiero/radicacion.html"
    )