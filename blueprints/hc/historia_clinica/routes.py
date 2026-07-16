from flask import Blueprint, render_template, request, redirect, jsonify, session

from repositories import hc_pacientes_repo as repo_pacientes
from repositories import hc_evoluciones_repo as repo_evoluciones

bp_hc_home = Blueprint(
    "hc_home",
    __name__,
    url_prefix="/hc",
)


@bp_hc_home.route("/historia-clinica")
def historia_clinica():
    """Pantalla principal de Historia Clínica: buscador de pacientes +
    evoluciones recientes de la IPS."""
    if not session.get("empresa_id"):
        return redirect("/")

    recientes = repo_evoluciones.listar_recientes(limite=20)
    resumen = repo_evoluciones.resumen_evoluciones()

    return render_template(
        "hc/historia-clinica/index.html",
        recientes=recientes,
        resumen=resumen,
    )


@bp_hc_home.route("/historia-clinica/buscar")
def historia_clinica_buscar():
    """API de búsqueda de pacientes para el buscador de esta pantalla."""
    if not session.get("empresa_id"):
        return jsonify([]), 403

    q = request.args.get("q", "")
    if len(q) < 2:
        return jsonify([])

    resultados = repo_pacientes.buscar(q, limite=15)
    data = []
    for p in resultados:
        nombre = " ".join(filter(None, [
            p.get("primer_nombre"), p.get("segundo_nombre"),
            p.get("primer_apellido"), p.get("segundo_apellido"),
        ])) or "Sin nombre"
        data.append({
            "id": p.get("id"),
            "nombre": nombre,
            "documento": p.get("numero_documento") or "",
        })
    return jsonify(data)