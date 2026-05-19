from flask import Blueprint, render_template

bp_financiero_glosas = Blueprint(
    "bp_financiero_glosas",
    __name__,
    url_prefix="/financiero/glosas"
)

@bp_financiero_glosas.route("/")
def glosas():

    return render_template(
        "financiero/glosas.html"
    )