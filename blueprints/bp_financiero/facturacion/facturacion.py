from flask import Blueprint, render_template

bp_financiero_facturacion = Blueprint(
    "bp_financiero_facturacion",
    __name__,
    url_prefix="/financiero/facturacion"
)

@bp_financiero_facturacion.route("/")
def facturacion():

    return render_template(
        "financiero/facturacion.html"
    )