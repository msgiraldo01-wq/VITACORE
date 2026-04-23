from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from repositories import hc_medicamentos_repo as repo



bp_hc_medicamentos = Blueprint(
    "hc_medicamentos",
    __name__,
    url_prefix="/hc/medicamentos"
)


# =========================
# LISTADO
# =========================

@bp_hc_medicamentos.route("/")
def index():

    items = repo.listar()

    return render_template(
        "hc/medicamentos/index.html",
        items=items
    )


# =========================
# NUEVO
# =========================

@bp_hc_medicamentos.route("/nuevo", methods=["GET","POST"])
def nuevo():

    if request.method == "POST":

        data = {
            "principio_activo": request.form.get("principio_activo"),
            "nombre_comercial": request.form.get("nombre_comercial"),
            "forma_farmaceutica": request.form.get("forma"),
            "concentracion": request.form.get("concentracion"),
            "via_administracion": request.form.get("via"),
            "registro_invima": request.form.get("invima"),
            "laboratorio": request.form.get("laboratorio"),
            "estado": request.form.get("estado") or "ACTIVO",
            "cum": request.form.get("cum" or "").strip(),
        }

        repo.crear(data)

        flash(f"Medcamento creado exitosamente", "success")
        return redirect(url_for("hc_medicamentos.index"))

    return render_template(
        "hc/medicamentos/form.html",
        item={},        
        modo="crear"    
    )

@bp_hc_medicamentos.route("/buscar")
def buscar():

    q = request.args.get("q", "")

    if not q:
        return jsonify([])

    items = repo.buscar(q)

    return jsonify(items)

# =========================
# EDITAR
# =========================

@bp_hc_medicamentos.route("/<int:id>/editar", methods=["GET","POST"])
def editar(id):

    item = repo.obtener(id)

    if not item:
        flash(f"El medicamento no existe.", "error")
        return redirect(url_for("hc_medicamentos.index"))

    if request.method == "POST":

        data = {
            "codigo_atc": request.form.get("codigo_atc"),
            "principio_activo": request.form.get("principio_activo"),
            "nombre_comercial": request.form.get("nombre_comercial"),
            "concentracion": request.form.get("concentracion"),
            "forma_farmaceutica": request.form.get("forma"),
            "via_administracion": request.form.get("via"),
            "registro_invima": request.form.get("invima"),
            "laboratorio": request.form.get("laboratorio"),
            "cum": (request.form.get("cum") or "").strip(),
        }

        repo.actualizar(id, data)

        flash(f"Medciamento editado correctamente","success")
        return redirect(url_for("hc_medicamentos.index"))

    return render_template(
        "hc/medicamentos/form.html",
        item=item
    )
    
    # =========================
# CAMBIAR ESTADO
# =========================

@bp_hc_medicamentos.route("/toggle/<int:id>", methods=["POST"])
def toggle(id):

    item = repo.obtener(id)

    if not item:
        flash("El medicamento no existe.", "error")
        return redirect(url_for("hc_medicamentos.index"))

    nuevo_estado = "INACTIVO" if item.get("estado") == "ACTIVO" else "ACTIVO"

    repo.cambiar_estado(id, nuevo_estado)

    flash(f"Medicamento {'inactivado' if nuevo_estado == 'INACTIVO' else 'activado'} correctamente.","success")

    return redirect(url_for("hc_medicamentos.index"))

