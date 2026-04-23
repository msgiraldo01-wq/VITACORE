from flask import Blueprint, render_template

from repositories import hc_historia_repo as repo
from repositories import hc_pacientes_repo as repo_pac


bp_hc_historia = Blueprint(
    "hc_historia",
    __name__,
    url_prefix="/hc/historia"
)


@bp_hc_historia.route("/paciente/<int:paciente_id>")
def historia_paciente(paciente_id):

    paciente = repo_pac.obtener(paciente_id)

    timeline = repo.timeline_paciente(paciente_id)

    return render_template(
        "hc/historia/timeline.html",
        paciente=paciente,
        timeline=timeline
    )