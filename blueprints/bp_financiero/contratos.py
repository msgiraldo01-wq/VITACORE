from flask import Blueprint, render_template

bp_financiero_contratos = Blueprint(
    "bp_financiero_contratos",
    __name__,
    url_prefix="/financiero/contratos"
)

# =========================
# DASHBOARD CONTRATOS
# =========================
@bp_financiero_contratos.route("/")
def dashboard():

    return render_template(
        "financiero/contratos/dashboard.html"
    )