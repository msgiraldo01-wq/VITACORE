from flask import flash, redirect, render_template, request, url_for
from repositories import inventario_repository as repo
from . import contexto_empresa, inventario_bp


@inventario_bp.route("/condiciones", methods=["GET", "POST"])
@contexto_empresa
def condiciones(empresa_id, usuario_id):
    if request.method == "POST":
        temp = request.form.get("temperatura")
        hum = request.form.get("humedad")
        if not request.form.get("bodega_id") or (not temp and not hum):
            flash("Selecciona la bodega y registra al menos temperatura o humedad.", "error")
        else:
            fuera = request.form.get("fuera_de_rango") == "on"
            acciones = request.form.get("acciones_correctivas", "").strip()
            if fuera and not acciones:
                flash("Si el registro está fuera de rango, las acciones correctivas son obligatorias.", "error")
                return redirect(url_for("inventario.condiciones"))
            repo.registrar_condicion({
                "empresa_id": empresa_id,
                "bodega_id": request.form["bodega_id"],
                "temperatura": float(temp) if temp else None,
                "humedad": float(hum) if hum else None,
                "equipo": request.form.get("equipo", "").strip() or None,
                "fuera_de_rango": fuera,
                "acciones_correctivas": acciones or None,
                "registrado_por": usuario_id,
            })
            flash("Registro de condiciones guardado.", "success")
        return redirect(url_for("inventario.condiciones"))
    bodega_id = request.args.get("bodega_id", "")
    return render_template("inventario/condiciones/registro.html",
                           registros=repo.listar_condiciones(empresa_id, bodega_id),
                           bodegas=repo.listar_bodegas(empresa_id, solo_activas=True),
                           bodega_id=bodega_id)
