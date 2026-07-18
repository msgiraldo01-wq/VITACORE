from flask import flash, redirect, render_template, request, url_for
from repositories import inventario_repository as repo
from . import contexto_empresa, inventario_bp


@inventario_bp.route("/dispensacion")
@contexto_empresa
def dispensacion_cola(empresa_id, usuario_id):
    return render_template("inventario/dispensacion/cola.html",
                           formulas=repo.cola_formulas(empresa_id),
                           dispensaciones=repo.listar_dispensaciones(empresa_id),
                           nombre=repo.buscar_paciente_nombre)


# Paso 1: VALIDACIÓN — el QF revisa la fórmula, elige producto del maestro y cantidad
@inventario_bp.route("/dispensacion/validar/<int:evolucion_id>", methods=["GET", "POST"])
@contexto_empresa
def dispensacion_validar(empresa_id, usuario_id, evolucion_id):
    evo, meds = repo.formula_de_evolucion(evolucion_id)
    if not evo or not meds:
        flash("Fórmula no encontrada o sin medicamentos.", "error")
        return redirect(url_for("inventario.dispensacion_cola"))

    if request.method == "POST":
        bodega_id = request.form.get("bodega_id")
        if not bodega_id:
            flash("Selecciona la bodega de dispensación.", "error")
            return redirect(request.url)
        items = []
        for m in meds:
            producto_id = request.form.get(f"producto_{m['id']}")
            cantidad = request.form.get(f"cantidad_{m['id']}")
            if not producto_id or not cantidad or float(cantidad) <= 0:
                continue  # medicamento sin producto asignado = no se dispensa
            prod = repo.obtener_producto(producto_id)
            items.append({
                "medicamento_formula_id": m["id"],
                "medicamento_prescrito": m.get("medicamento_nombre"),
                "producto_id": producto_id,
                "hc_medicamento_id": _hc_med_id(prod),
                "cantidad_prescrita": float(cantidad),
            })
        if not items:
            flash("Asigna al menos un producto del inventario a la fórmula.", "error")
            return redirect(request.url)
        d = repo.crear_dispensacion({
            "empresa_id": empresa_id, "paciente_id": evo["paciente_id"],
            "evolucion_id": evolucion_id, "medico_id": evo.get("medico_id"),
            "bodega_id": bodega_id, "estado": "VALIDADA",
            "validada_por": usuario_id, "fecha_validacion": "now()",
            "observaciones": request.form.get("observaciones", "").strip() or None,
        }, items)
        flash("Fórmula validada. Continúa con la dispensación.", "success")
        return redirect(url_for("inventario.dispensacion_detalle", disp_id=d["id"]))

    return render_template("inventario/dispensacion/validar.html",
                           evo=evo, meds=meds,
                           bodegas=[b for b in repo.listar_bodegas(empresa_id, solo_activas=True)
                                    if b.get("permite_dispensacion")],
                           productos=repo.listar_productos(empresa_id),
                           nombre=repo.buscar_paciente_nombre(evo["paciente_id"]))


# Paso 2: DISPENSACIÓN — descarga FEFO + cargo a cuenta
@inventario_bp.route("/dispensacion/<disp_id>", methods=["GET", "POST"])
@contexto_empresa
def dispensacion_detalle(empresa_id, usuario_id, disp_id):
    d, items = repo.obtener_dispensacion(empresa_id, disp_id)
    if not d:
        flash("Dispensación no encontrada.", "error")
        return redirect(url_for("inventario.dispensacion_cola"))

    if request.method == "POST" and d["estado"] in ("VALIDADA", "PARCIAL"):
        entregado_a = request.form.get("entregado_a", "").strip()
        documento = request.form.get("documento_receptor", "").strip()
        if not entregado_a:
            flash("Registra a quién se entrega el medicamento.", "error")
            return redirect(request.url)
        payload = []
        for it in items:
            cant = request.form.get(f"cantidad_{it['id']}")
            if cant and float(cant) > 0:
                payload.append({
                    "item_id": it["id"], "producto_id": it["producto_id"],
                    "hc_medicamento_id": it["hc_medicamento_id"],
                    "cantidad": float(cant),
                })
        if not payload:
            flash("Indica la cantidad a dispensar.", "error")
            return redirect(request.url)
        try:
            repo.actualizar_dispensacion(disp_id, {
                "entregado_a": entregado_a, "documento_receptor": documento or None})
            r = repo.dispensar(empresa_id, disp_id, usuario_id, payload)
            if r.get("facturacion") == "CARGADA":
                flash("Medicamento dispensado y cargado a la cuenta del paciente.", "success")
            else:
                flash("Medicamento dispensado. Sin prefactura abierta: quedó PENDIENTE "
                      "DE FACTURAR para conciliar después.", "warning")
        except Exception as e:
            flash("Stock insuficiente en la bodega." if "insuficiente" in str(e)
                  else "No fue posible dispensar. Revisa el stock.", "error")
        return redirect(url_for("inventario.dispensacion_detalle", disp_id=disp_id))

    return render_template("inventario/dispensacion/detalle.html",
                           d=d, items=items,
                           nombre=repo.buscar_paciente_nombre(d["paciente_id"]))


def _hc_med_id(producto):
    """Intenta mapear el producto del maestro a hc_medicamentos.id por CUM.
    Si no hay match, devuelve None (el precio quedará en 0 y se marca para revisión)."""
    if not producto or not producto.get("cum"):
        return None
    try:
        r = (repo._client().table("hc_medicamentos").select("id")
             .eq("cum", producto["cum"]).limit(1).execute().data)
        return r[0]["id"] if r else None
    except Exception:
        return None