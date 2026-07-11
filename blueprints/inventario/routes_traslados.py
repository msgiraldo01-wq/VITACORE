from flask import flash, redirect, render_template, request, url_for
from repositories import inventario_repository as repo
from . import contexto_empresa, inventario_bp


@inventario_bp.route("/traslados")
@contexto_empresa
def traslados_lista(empresa_id, usuario_id):
    return render_template("inventario/traslados/lista.html",
                           traslados=repo.listar_traslados(empresa_id))


@inventario_bp.route("/traslados/nuevo", methods=["GET", "POST"])
@contexto_empresa
def traslados_nuevo(empresa_id, usuario_id):
    if request.method == "POST":
        origen = request.form.get("bodega_origen_id")
        destino = request.form.get("bodega_destino_id")
        productos = request.form.getlist("producto_id[]")
        cantidades = request.form.getlist("cantidad[]")
        items = [{"producto_id": p, "cantidad_enviada": float(c)}
                 for p, c in zip(productos, cantidades) if p and c and float(c) > 0]
        if not origen or not destino or origen == destino:
            flash("Selecciona bodegas origen y destino distintas.", "error")
        elif not items:
            flash("Agrega al menos un producto con cantidad.", "error")
        else:
            t = repo.crear_traslado({
                "empresa_id": empresa_id, "bodega_origen_id": origen,
                "bodega_destino_id": destino, "solicitado_por": usuario_id,
                "observaciones": request.form.get("observaciones", "").strip() or None,
            }, items)
            flash("Traslado creado. Ahora despáchalo para descontar el stock.", "success")
            return redirect(url_for("inventario.traslados_detalle", traslado_id=t["id"]))
    return render_template("inventario/traslados/form.html",
                           bodegas=repo.listar_bodegas(empresa_id, solo_activas=True),
                           productos=repo.listar_productos(empresa_id))


@inventario_bp.route("/traslados/<traslado_id>", methods=["GET", "POST"])
@contexto_empresa
def traslados_detalle(empresa_id, usuario_id, traslado_id):
    if request.method == "POST":
        accion = request.form.get("accion")
        try:
            if accion == "despachar":
                repo.despachar_traslado(empresa_id, traslado_id, usuario_id)
                flash("Traslado despachado: el stock salió de la bodega origen (FEFO).", "success")
            elif accion == "recibir":
                repo.recibir_traslado(empresa_id, traslado_id, usuario_id)
                flash("Recepción confirmada: el stock ingresó a la bodega destino.", "success")
        except Exception as e:
            msg = str(e)
            flash("Stock insuficiente en la bodega origen." if "insuficiente" in msg
                  else "No fue posible procesar el traslado.", "error")
        return redirect(url_for("inventario.traslados_detalle", traslado_id=traslado_id))
    t, items = repo.obtener_traslado(empresa_id, traslado_id)
    if not t:
        flash("Traslado no encontrado.", "error")
        return redirect(url_for("inventario.traslados_lista"))
    return render_template("inventario/traslados/detalle.html", t=t, items=items)