from flask import Blueprint, render_template

bp_financiero_cartera = Blueprint(
    "bp_financiero_cartera",
    __name__,
    url_prefix="/financiero/cartera"
)

@bp_financiero_cartera.route("/")
def cartera():

    return render_template(
        "financiero/cartera.html"
    )