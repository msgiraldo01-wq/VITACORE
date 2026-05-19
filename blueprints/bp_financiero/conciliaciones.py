from flask import Blueprint, render_template

bp_financiero_conciliaciones = Blueprint(
    "bp_financiero_conciliaciones",
    __name__,
    url_prefix="/financiero/conciliaciones"
)

@bp_financiero_conciliaciones.route("/")
def conciliaciones():

    return render_template(
        "financiero/conciliaciones.html"
    )