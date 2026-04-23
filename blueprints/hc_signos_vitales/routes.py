from flask import Blueprint, render_template, request, redirect, flash, url_for

from repositories import hc_signos_repo as repo


bp_hc_signos = Blueprint(
    "hc_signos",
    __name__,
    url_prefix="/hc/signos"
)


@bp_hc_signos.route("/paciente/<int:paciente_id>")
def signos_paciente(paciente_id):

    signos = repo.listar_por_paciente(paciente_id)

    return render_template(
        "hc/signos_vitales/signos_list.html",
        signos=signos,
        paciente_id=paciente_id
    )


@bp_hc_signos.route("/nuevo/<int:paciente_id>")
def signos_nuevo(paciente_id):

    return render_template(
        "hc/signos_vitales/signos_form.html",
        paciente_id=paciente_id
    )


@bp_hc_signos.route("/crear/<int:paciente_id>", methods=["POST"])
def signos_crear(paciente_id):

    peso = float(request.form.get("peso") or 0)
    talla = float(request.form.get("talla") or 0)

    imc = 0

    if talla > 0:
        imc = peso / ((talla/100) ** 2)

    data = {

        "paciente_id": paciente_id,
        "peso": peso,
        "talla": talla,
        "imc": round(imc,2),

        "presion_sistolica": request.form.get("presion_sistolica"),
        "presion_diastolica": request.form.get("presion_diastolica"),

        "frecuencia_cardiaca": request.form.get("frecuencia_cardiaca"),
        "frecuencia_respiratoria": request.form.get("frecuencia_respiratoria"),

        "temperatura": request.form.get("temperatura"),

        "observaciones": request.form.get("observaciones")

    }

    repo.crear(data)

    flash("Signos vitales registrados", "success")

    return redirect(
        url_for("hc_signos.signos_paciente", paciente_id=paciente_id)
    )
