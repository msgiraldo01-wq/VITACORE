from flask import Blueprint, render_template

bp_financiero_dashboard = Blueprint(
    "bp_financiero_dashboard",
    __name__,
    url_prefix="/financiero"
)

@bp_financiero_dashboard.route("/dashboard")
def dashboard_financiero():

    return render_template(
        "financiero/dashboard.html"
    )