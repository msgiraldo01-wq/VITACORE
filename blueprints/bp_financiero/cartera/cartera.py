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
from flask import Blueprint, render_template

bp_financiero_cartera = Blueprint(
    "bp_financiero_cartera",
    __name__,
    url_prefix="/financiero/cartera"
)


# =========================================
# BANDEJA CARTERA
# =========================================
@bp_financiero_cartera.route("/")
def cartera():

    return render_template(
        "financiero/cartera.html"
    )


# =========================================
# DETALLE CARTERA
# =========================================
@bp_financiero_cartera.route("/detalle/<factura>")
def cartera_detalle(factura):

    data = {
        "numero_factura": factura
    }

    return render_template(
        "financiero/cartera_detalle.html",
        data=data
    )
