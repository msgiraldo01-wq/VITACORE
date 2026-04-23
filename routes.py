from flask import Blueprint, render_template # type: ignore
from blueprints.auth.decorators import login_required # type: ignore

bp_hc_dashboard = Blueprint(
    "hc_dashboard",
    __name__,
    url_prefix="/hc"
)

@bp_hc_dashboard.route("/")
@login_required
def index():
    return render_template("hc/dashboard.html")

