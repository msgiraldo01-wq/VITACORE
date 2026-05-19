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


@bp_financiero_facturacion.route("/detalle/<factura>")
def factura_detalle(factura):

    data = {
        "numero_factura": factura
    }

    return render_template(
        "financiero/factura_detalle.html",
        data=data
    )