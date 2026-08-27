from flask import flash, redirect, render_template, request, url_for
from repositories import inventario_repository as repo
from . import contexto_empresa, inventario_bp


@inventario_bp.route("/solicitudes")
@contexto_empresa
def solicitudes_lista(empresa_id, usuario_id):
    return render_template("inventario/solicitudes/lista.html",
                           solicitudes=repo.listar_solicitudes(empresa_id),
                           bajo_minimo=repo.productos_bajo_minimo(empresa_id))


@inventario_bp.route("/solicitudes/nueva", methods=["GET", "POST"])
@contexto_empresa
def solicitudes_nueva(empresa_id, usuario_id):
    if request.method == "POST":
        productos = request.form.getlist("producto_id[]")
        cantidades = request.form.getlist("cantidad[]")
        items = [{"producto_id": p, "cantidad": float(c)}
                 for p, c in zip(productos, cantidades) if p and c and float(c) > 0]
        if not items:
            flash("Agrega al menos un producto con cantidad.", "error")
        else:
            s = repo.crear_solicitud({
                "empresa_id": empresa_id,
                "bodega_destino_id": request.form.get("bodega_destino_id") or None,
                "justificacion": request.form.get("justificacion", "").strip() or None,
                "solicitado_por": usuario_id,
            }, items)
            flash(f"Solicitud #{s['consecutivo']} enviada para aprobación.", "success")
            return redirect(url_for("inventario.solicitudes_detalle", solicitud_id=s["id"]))
    # ?sugerido=1 → prellenar con los productos bajo stock mínimo
    sugeridos = repo.productos_bajo_minimo(empresa_id) if request.args.get("sugerido") else []
    return render_template("inventario/solicitudes/form.html",
                           bodegas=repo.listar_bodegas(empresa_id, solo_activas=True),
                           productos=repo.listar_productos(empresa_id),
                           sugeridos=sugeridos)


@inventario_bp.route("/solicitudes/<solicitud_id>", methods=["GET", "POST"])
@contexto_empresa
def solicitudes_detalle(empresa_id, usuario_id, solicitud_id):
    s, items = repo.obtener_solicitud(empresa_id, solicitud_id)
    if not s:
        flash("Solicitud no encontrada.", "error")
        return redirect(url_for("inventario.solicitudes_lista"))
    if request.method == "POST":
        accion = request.form.get("accion")
        base = {"resuelto_por": usuario_id, "fecha_resolucion": "now()"}
        if accion == "aprobar" and s["estado"] == "PENDIENTE":
            repo.resolver_solicitud(solicitud_id, {**base, "estado": "APROBADA"})
            flash("Solicitud aprobada. Ya puedes convertirla en orden de compra.", "success")
        elif accion == "rechazar" and s["estado"] == "PENDIENTE":
            motivo = request.form.get("motivo_rechazo", "").strip()
            if not motivo:
                flash("El rechazo exige un motivo.", "error")
            else:
                repo.resolver_solicitud(solicitud_id, {**base, "estado": "RECHAZADA",
                                                       "motivo_rechazo": motivo})
                flash("Solicitud rechazada.", "success")
        elif accion == "convertir" and s["estado"] == "APROBADA":
            proveedor_id = request.form.get("proveedor_id")
            if not proveedor_id or not s.get("bodega_destino_id"):
                flash("Selecciona el proveedor (y la solicitud debe tener bodega destino).", "error")
            else:
                oc_items, subtotal = [], 0.0
                for it in items:
                    precio = repo.ultimo_precio_compra(empresa_id, it["producto_id"])
                    oc_items.append({"producto_id": it["producto_id"],
                                     "cantidad": it["cantidad"],
                                     "precio_unitario": precio, "porcentaje_iva": 0})
                    subtotal += it["cantidad"] * precio
                oc = repo.crear_orden({
                    "empresa_id": empresa_id, "proveedor_id": proveedor_id,
                    "bodega_destino_id": s["bodega_destino_id"],
                    "subtotal": round(subtotal, 2), "iva": 0,
                    "total": round(subtotal, 2),
                    "observaciones": f"Generada desde solicitud #{s['consecutivo']}",
                    "elaborado_por": usuario_id,
                }, oc_items)
                repo.resolver_solicitud(solicitud_id, {"estado": "CONVERTIDA_OC",
                                                       "orden_id": oc["id"]})
                flash(f"OC #{oc['consecutivo']} creada en borrador con precios de la última "
                      "compra (el precio definitivo se confirma en la recepción).", "success")
                return redirect(url_for("inventario.compras_detalle", orden_id=oc["id"]))
        return redirect(url_for("inventario.solicitudes_detalle", solicitud_id=solicitud_id))
    return render_template("inventario/solicitudes/detalle.html", s=s, items=items,
                           proveedores=repo.listar_proveedores(empresa_id, solo_activos=True))