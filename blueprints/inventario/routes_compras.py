from flask import flash, redirect, render_template, request, url_for
from repositories import inventario_repository as repo
from . import contexto_empresa, inventario_bp

CHECKS = ("factura_conforme", "cantidades_conformes", "embalaje_conforme",
          "etiquetado_conforme", "registro_invima_conforme")


@inventario_bp.route("/proveedores", methods=["GET", "POST"])
@contexto_empresa
def proveedores(empresa_id, usuario_id):
    if request.method == "POST":
        nit = request.form.get("numero_documento", "").strip()
        razon = request.form.get("razon_social", "").strip()
        if not nit or not razon:
            flash("NIT y razón social son obligatorios.", "error")
        else:
            datos = {
                "empresa_id": empresa_id,
                "tipo_documento": request.form.get("tipo_documento", "NIT"),
                "numero_documento": nit,
                "razon_social": razon.upper(),
                "contacto": request.form.get("contacto", "").strip() or None,
                "telefono": request.form.get("telefono", "").strip() or None,
                "email": request.form.get("email", "").strip() or None,
                "ciudad": request.form.get("ciudad", "").strip() or None,
                "condiciones_pago": request.form.get("condiciones_pago", "CONTADO"),
                "estado": request.form.get("estado", "ACTIVO"),
            }
            try:
                pid = request.form.get("proveedor_id") or None
                if pid:
                    repo.actualizar_proveedor(pid, datos)
                else:
                    datos["created_by"] = usuario_id
                    repo.crear_proveedor(datos)
                flash("Proveedor guardado.", "success")
            except Exception:
                flash("Ya existe un proveedor con ese NIT.", "error")
        return redirect(url_for("inventario.proveedores"))
    return render_template("inventario/proveedores/lista.html",
                           proveedores=repo.listar_proveedores(empresa_id))


@inventario_bp.route("/compras")
@contexto_empresa
def compras_lista(empresa_id, usuario_id):
    return render_template("inventario/compras/lista.html",
                           ordenes=repo.listar_ordenes(empresa_id))


@inventario_bp.route("/compras/nueva", methods=["GET", "POST"])
@contexto_empresa
def compras_nueva(empresa_id, usuario_id):
    if request.method == "POST":
        productos = request.form.getlist("producto_id[]")
        cantidades = request.form.getlist("cantidad[]")
        precios = request.form.getlist("precio[]")
        ivas = request.form.getlist("iva[]")
        items, subtotal, iva_total = [], 0.0, 0.0
        for p, c, pr, iv in zip(productos, cantidades, precios, ivas):
            if not (p and c and pr):
                continue
            c, pr, iv = float(c), float(pr), float(iv or 0)
            items.append({"producto_id": p, "cantidad": c,
                          "precio_unitario": pr, "porcentaje_iva": iv})
            subtotal += c * pr
            iva_total += c * pr * iv / 100
        if not request.form.get("proveedor_id") or not request.form.get("bodega_destino_id"):
            flash("Selecciona proveedor y bodega destino.", "error")
        elif not items:
            flash("Agrega al menos un producto con cantidad y precio.", "error")
        else:
            oc = repo.crear_orden({
                "empresa_id": empresa_id,
                "proveedor_id": request.form["proveedor_id"],
                "bodega_destino_id": request.form["bodega_destino_id"],
                "fecha_entrega_esperada": request.form.get("fecha_entrega_esperada") or None,
                "subtotal": round(subtotal, 2), "iva": round(iva_total, 2),
                "total": round(subtotal + iva_total, 2),
                "observaciones": request.form.get("observaciones", "").strip() or None,
                "elaborado_por": usuario_id,
            }, items)
            flash(f"Orden de compra #{oc['consecutivo']} creada en borrador.", "success")
            return redirect(url_for("inventario.compras_detalle", orden_id=oc["id"]))
    return render_template("inventario/compras/form.html",
                           proveedores=repo.listar_proveedores(empresa_id, solo_activos=True),
                           bodegas=repo.listar_bodegas(empresa_id, solo_activas=True),
                           productos=repo.listar_productos(empresa_id))


@inventario_bp.route("/compras/<orden_id>", methods=["GET", "POST"])
@contexto_empresa
def compras_detalle(empresa_id, usuario_id, orden_id):
    if request.method == "POST":
        accion = request.form.get("accion")
        if accion == "aprobar":
            repo.cambiar_estado_orden(empresa_id, orden_id, "APROBADA", usuario_id)
            flash("Orden aprobada. Ya puedes registrar recepciones.", "success")
        elif accion == "anular":
            repo.cambiar_estado_orden(empresa_id, orden_id, "ANULADA")
            flash("Orden anulada.", "success")
        return redirect(url_for("inventario.compras_detalle", orden_id=orden_id))
    oc, items, recepciones = repo.obtener_orden(empresa_id, orden_id)
    if not oc:
        flash("Orden no encontrada.", "error")
        return redirect(url_for("inventario.compras_lista"))
    return render_template("inventario/compras/detalle.html",
                           oc=oc, items=items, recepciones=recepciones)


@inventario_bp.route("/compras/<orden_id>/recepcion", methods=["GET", "POST"])
@contexto_empresa
def compras_recepcion(empresa_id, usuario_id, orden_id):
    oc, items, _ = repo.obtener_orden(empresa_id, orden_id)
    if not oc or oc["estado"] not in ("APROBADA", "RECIBIDA_PARCIAL"):
        flash("La orden debe estar APROBADA para recibirla.", "error")
        return redirect(url_for("inventario.compras_detalle", orden_id=orden_id))
    if request.method == "POST":
        filas = []
        for it in items:
            rec = request.form.get(f"recibida_{it['id']}")
            if not rec or float(rec) <= 0:
                continue
            acep = request.form.get(f"aceptada_{it['id']}") or rec
            lote = request.form.get(f"lote_{it['id']}", "").strip().upper()
            venc = request.form.get(f"venc_{it['id']}")
            if it["inv_productos"]["requiere_lote"] and (not lote or not venc):
                flash(f"El producto {it['inv_productos']['nombre']} exige lote y vencimiento.", "error")
                return redirect(url_for("inventario.compras_recepcion", orden_id=orden_id))
            filas.append({
                "producto_id": it["producto_id"], "orden_item_id": it["id"],
                "numero_lote": lote or "SIN-LOTE", "fecha_vencimiento": venc or "2099-12-31",
                "cantidad_recibida": float(rec), "cantidad_aceptada": float(acep),
                "precio_unitario": float(request.form.get(f"precio_{it['id']}") or it["precio_unitario"]),
                "motivo_rechazo": request.form.get(f"motivo_{it['id']}", "").strip() or None,
            })
        if not filas:
            flash("Registra al menos un ítem con cantidad recibida.", "error")
            return redirect(url_for("inventario.compras_recepcion", orden_id=orden_id))
        cabecera = {
            "orden_id": orden_id, "proveedor_id": oc["proveedor_id"],
            "bodega_id": oc["bodega_destino_id"],
            "numero_factura_proveedor": request.form.get("numero_factura", "").strip() or None,
            "temperatura_recepcion": request.form.get("temperatura_recepcion") or "",
            "cadena_frio_conforme": request.form.get("cadena_frio_conforme", ""),
            "observaciones": request.form.get("observaciones", "").strip() or None,
            "recibido_por": usuario_id,
        }
        for c in CHECKS:
            cabecera[c] = request.form.get(c) == "on"
        try:
            r = repo.registrar_recepcion(empresa_id, cabecera, filas)
            flash(f"Recepción #{r['consecutivo']} registrada ({r['estado']}). "
                  "Lo aceptado ya está en el kardex.", "success")
        except Exception as e:
            flash("No fue posible registrar la recepción. " +
                  ("Verifica lotes y vencimientos." if "vencido" in str(e) else ""), "error")
        return redirect(url_for("inventario.compras_detalle", orden_id=orden_id))
    return render_template("inventario/compras/recepcion.html", oc=oc, items=items)
