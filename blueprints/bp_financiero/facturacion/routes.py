"""
Rutas del módulo de facturación — Vitacore
Blueprint: bp_facturacion  →  /facturacion/...
"""

from flask import Blueprint, render_template, request, jsonify, Response
from repositories import fin_facturacion_repo as repo

bp_facturacion = Blueprint(
    "facturacion",
    __name__,
    url_prefix="/facturacion",
    template_folder="templates",
)


# =============================================================
# VISTAS HTML
# =============================================================

@bp_facturacion.route("/")
def index():
    """Página principal del módulo de facturación."""
    return render_template("financiero/facturacion/facturacion.html")


@bp_facturacion.route("/facturas")
def lista_facturas():
    """Listado de facturas emitidas."""
    return render_template("financiero/facturacion/facturas_lista.html")


@bp_facturacion.route("/configuracion")
def configuracion():
    """Configuración de consecutivos y resoluciones."""
    return render_template("financiero/facturacion/facturacion_configuracion.html")


@bp_facturacion.route("/factura/<int:factura_id>/vista")
def vista_factura(factura_id):
    """Vista de factura para impresión y descarga PDF."""
    return render_template("financiero/facturacion/factura_vista.html", factura_id=factura_id)


# =============================================================
# API — BUSCAR CITAS FACTURABLES
# =============================================================

@bp_facturacion.route("/api/buscar-paciente", methods=["GET"])
def api_buscar_paciente():
    """
    Busca paciente por cédula y retorna sus citas facturables.
    Query params: cedula
    """
    try:
        cedula = request.args.get("cedula", "").strip()
        if not cedula:
            return jsonify({"ok": False, "error": "Ingrese un número de cédula"}), 400

        paciente, citas = repo.buscar_citas_facturables(cedula)

        if not paciente:
            return jsonify({"ok": False, "error": "Paciente no encontrado"}), 404

        # Enriquecer citas con procedimientos
        for cita in citas:
            procs = repo.obtener_procedimientos_cita(cita["id"])
            cita["procedimientos"] = []
            for p in procs:
                cups = p.get("hc_cups", {}) or {}
                cita["procedimientos"].append({
                    "id": p["id"],
                    "cups_id": p["cups_id"],
                    "codigo": cups.get("codigo", ""),
                    "descripcion": cups.get("descripcion", ""),
                    "duracion_min": p["duracion_min"],
                })

            # Aplanar joins
            prof = cita.pop("hc_profesionales", None) or {}
            sede = cita.pop("hc_sedes", None) or {}
            cliente = cita.pop("hc_clientes", None) or {}
            contrato = cita.pop("hc_contratos", None) or {}

            cita["medico_nombre"] = prof.get("nombre_completo", "")
            cita["sede_nombre"] = sede.get("nombre", "")
            cita["cliente_nombre"] = cliente.get("nombre", "")
            cita["cliente_nit"] = cliente.get("nit", "")
            cita["contrato_nro"] = contrato.get("nro_contrato", "")
            cita["manual_tarifario"] = contrato.get("manual_tarifario", "")
            cita["tipo_contrato"] = contrato.get("tipo_contrato", "")

        # Nombre completo del paciente
        nombre = " ".join(filter(None, [
            paciente.get("primer_nombre"),
            paciente.get("segundo_nombre"),
            paciente.get("primer_apellido"),
            paciente.get("segundo_apellido"),
        ]))
        paciente["nombre_completo"] = nombre

        return jsonify({"ok": True, "paciente": paciente, "citas": citas})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — GENERAR PREFACTURA
# =============================================================

@bp_facturacion.route("/api/prefactura", methods=["POST"])
def api_crear_prefactura():
    """
    Crea una prefactura a partir de citas seleccionadas.
    Body: { paciente_id, cliente_id, contrato_id, sede_id, cita_ids: [...] }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}

        paciente_id = data.get("paciente_id")
        cliente_id = data.get("cliente_id")
        contrato_id = data.get("contrato_id")
        sede_id = data.get("sede_id")
        cita_ids = data.get("cita_ids", [])

        if not paciente_id or not cliente_id or not contrato_id:
            return jsonify({"ok": False, "error": "paciente_id, cliente_id y contrato_id son requeridos"}), 400

        if not cita_ids:
            return jsonify({"ok": False, "error": "Seleccione al menos una cita"}), 400

        # Obtener procedimientos y calcular valores
        items = []
        subtotal = 0

        for cita_id in cita_ids:
            procs = repo.obtener_procedimientos_cita(cita_id)

            if not procs:
                # Cita sin procedimientos, usar valor_tarifa directo
                cita_res = (
                    repo._sb()
                    .table("hc_citas")
                    .select("valor_tarifa, motivo_consulta")
                    .eq("id", cita_id)
                    .single()
                    .execute()
                )
                cita_data = cita_res.data or {}
                valor = float(cita_data.get("valor_tarifa", 0) or 0)

                items.append({
                    "cita_id": cita_id,
                    "codigo_cups": "000000",
                    "descripcion": cita_data.get("motivo_consulta", "Consulta médica"),
                    "cantidad": 1,
                    "valor_unitario": valor,
                    "valor_total": valor,
                })
                subtotal += valor
            else:
                for p in procs:
                    cups = p.get("hc_cups", {}) or {}
                    # Buscar tarifa en el manual del contrato
                    tarifa = repo.obtener_tarifa_cups(contrato_id, p["cups_id"])
                    valor = float(tarifa["valor_total"]) if tarifa else 0

                    items.append({
                        "cita_id": cita_id,
                        "cita_procedimiento_id": p["id"],
                        "codigo_cups": cups.get("codigo", ""),
                        "descripcion": cups.get("descripcion", ""),
                        "cantidad": 1,
                        "valor_unitario": valor,
                        "valor_total": valor,
                    })
                    subtotal += valor

        # Crear prefactura
        prefactura_data = {
            "empresa_id": 1,
            "paciente_id": paciente_id,
            "cliente_id": cliente_id,
            "contrato_id": contrato_id,
            "sede_id": sede_id,
            "subtotal": subtotal,
            "valor_neto": subtotal,
            "estado": "ABIERTA",
        }
        prefactura = repo.crear_prefactura(prefactura_data)

        if not prefactura:
            return jsonify({"ok": False, "error": "Error al crear prefactura"}), 500

        # Agregar ítems
        for item in items:
            item["prefactura_id"] = prefactura["id"]

        repo.agregar_items_prefactura(items)

        return jsonify({
            "ok": True,
            "prefactura_id": prefactura["id"],
            "subtotal": subtotal,
            "items_count": len(items),
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — OBTENER PREFACTURA CON ÍTEMS
# =============================================================

@bp_facturacion.route("/api/prefactura/<int:prefactura_id>", methods=["GET"])
def api_obtener_prefactura(prefactura_id):
    try:
        prefactura = repo.obtener_prefactura(prefactura_id)
        if not prefactura:
            return jsonify({"ok": False, "error": "Prefactura no encontrada"}), 404

        items = repo.obtener_items_prefactura(prefactura_id)

        return jsonify({"ok": True, "data": prefactura, "items": items})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — ACTUALIZAR COPAGOS / CUOTAS EN PREFACTURA
# =============================================================

@bp_facturacion.route("/api/prefactura/<int:prefactura_id>/ajustar", methods=["POST"])
def api_ajustar_prefactura(prefactura_id):
    """
    Actualiza copago, cuota moderadora, cuota recuperación y descuento.
    Recalcula el valor neto.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}

        prefactura = repo.obtener_prefactura(prefactura_id)
        if not prefactura:
            return jsonify({"ok": False, "error": "Prefactura no encontrada"}), 404

        subtotal = float(prefactura.get("subtotal", 0))
        copago = float(data.get("valor_copago", 0))
        cuota_mod = float(data.get("valor_cuota_moderadora", 0))
        cuota_rec = float(data.get("valor_cuota_recuperacion", 0))
        descuento = float(data.get("descuento", 0))

        valor_neto = subtotal - descuento - copago - cuota_mod - cuota_rec

        update = {
            "valor_copago": copago,
            "valor_cuota_moderadora": cuota_mod,
            "valor_cuota_recuperacion": cuota_rec,
            "descuento": descuento,
            "valor_neto": max(0, valor_neto),
            "updated_at": "now()",
        }

        repo.actualizar_prefactura(prefactura_id, update)

        return jsonify({"ok": True, "valor_neto": max(0, valor_neto)})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — GENERAR FACTURA DESDE PREFACTURA
# =============================================================

@bp_facturacion.route("/api/facturar", methods=["POST"])
def api_facturar():
    """
    Genera una factura definitiva desde una prefactura.
    Body: { prefactura_id, copago, cuota_moderadora, cuota_recuperacion,
            pagos_compartidos, numero_poliza, observaciones }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        prefactura_id = data.get("prefactura_id")

        if not prefactura_id:
            return jsonify({"ok": False, "error": "prefactura_id es requerido"}), 400

        # Obtener prefactura
        prefactura = repo.obtener_prefactura(prefactura_id)
        if not prefactura:
            return jsonify({"ok": False, "error": "Prefactura no encontrada"}), 404

        if prefactura["estado"] == "FACTURADA":
            return jsonify({"ok": False, "error": "Esta prefactura ya fue facturada"}), 400

        # Obtener consecutivo
        consecutivo = repo.obtener_consecutivo_activo(sede_id=prefactura.get("sede_id"))
        if not consecutivo:
            return jsonify({"ok": False, "error": "No hay consecutivo de facturación activo. Configure uno en el módulo de facturación."}), 400

        numero_factura, error = repo.incrementar_consecutivo(consecutivo["id"])
        if error:
            return jsonify({"ok": False, "error": error}), 400

        # Obtener datos del contrato para campos FEV
        contrato = prefactura.get("hc_contratos", {}) or {}
        sede_data = (
            repo._sb()
            .table("hc_sedes")
            .select("codigo")
            .eq("id", prefactura["sede_id"])
            .single()
            .execute()
        ).data if prefactura.get("sede_id") else {}

        # Determinar modalidad de pago
        tipo_contrato = contrato.get("tipo_contrato", "").upper()
        if "CAPITA" in tipo_contrato:
            modalidad_pago = "PAGO_POR_CAPITACION"
        elif "EVENTO" in tipo_contrato:
            modalidad_pago = "PAGO_POR_EVENTO"
        elif "PAQUETE" in tipo_contrato:
            modalidad_pago = "PAQUETE_CANASTA"
        else:
            modalidad_pago = "PAGO_POR_EVENTO"

        # Calcular totales
        copago = float(data.get("copago", prefactura.get("valor_copago", 0)))
        cuota_mod = float(data.get("cuota_moderadora", prefactura.get("valor_cuota_moderadora", 0)))
        cuota_rec = float(data.get("cuota_recuperacion", prefactura.get("valor_cuota_recuperacion", 0)))
        pagos_comp = float(data.get("pagos_compartidos", 0))
        subtotal = float(prefactura.get("subtotal", 0))
        descuento = float(prefactura.get("descuento", 0))
        total = subtotal - descuento

        # Crear factura
        factura_data = {
            "empresa_id": 1,
            "consecutivo_id": consecutivo["id"],
            "prefijo": consecutivo["prefijo"],
            "numero_factura": numero_factura,
            "prefactura_id": prefactura_id,
            "paciente_id": prefactura["paciente_id"],
            "cliente_id": prefactura["cliente_id"],
            "contrato_id": prefactura["contrato_id"],
            "sede_id": prefactura.get("sede_id"),
            "subtotal": subtotal,
            "descuento": descuento,
            "total": total,
            # 11 campos sector salud
            "codigo_prestador": (sede_data or {}).get("codigo", ""),
            "modalidad_pago": modalidad_pago,
            "cobertura_plan_beneficios": data.get("cobertura_plan_beneficios", "PBS_CONTRIBUTIVO"),
            "numero_contrato": contrato.get("nro_contrato", ""),
            "numero_poliza": data.get("numero_poliza", ""),
            "copago": copago,
            "cuota_moderadora": cuota_mod,
            "cuota_recuperacion": cuota_rec,
            "pagos_compartidos": pagos_comp,
            "periodo_facturacion_inicio": prefactura.get("periodo_inicio"),
            "periodo_facturacion_fin": prefactura.get("periodo_fin"),
            # Estado
            "estado": "EMITIDA",
            "observaciones": data.get("observaciones", ""),
        }

        factura = repo.crear_factura(factura_data)
        if not factura:
            return jsonify({"ok": False, "error": "Error al crear factura"}), 500

        # Copiar ítems de prefactura a detalle de factura
        items_pref = repo.obtener_items_prefactura(prefactura_id)
        detalle = []
        cita_ids = set()

        for item in items_pref:
            cita_id = item.get("cita_id")
            if cita_id:
                cita_ids.add(cita_id)

            detalle.append({
                "factura_id": factura["id"],
                "cita_id": cita_id,
                "cita_procedimiento_id": item.get("cita_procedimiento_id"),
                "codigo_cups": item["codigo_cups"],
                "descripcion": item["descripcion"],
                "cantidad": item["cantidad"],
                "valor_unitario": item["valor_unitario"],
                "valor_total": item["valor_total"],
                "diagnostico_principal": item.get("diagnostico_principal"),
                "tipo_diagnostico": item.get("tipo_diagnostico"),
            })

        if detalle:
            repo.agregar_detalle_factura(detalle)

        # Marcar prefactura como facturada
        repo.actualizar_prefactura(prefactura_id, {"estado": "FACTURADA"})

        # Marcar citas como facturadas
        if cita_ids:
            repo.marcar_citas_facturadas(list(cita_ids))

        return jsonify({
            "ok": True,
            "factura_id": factura["id"],
            "numero_factura": numero_factura,
            "total": total,
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — LISTAR FACTURAS
# =============================================================

@bp_facturacion.route("/api/facturas", methods=["GET"])
def api_listar_facturas():
    try:
        estado = request.args.get("estado")
        cliente_id = request.args.get("cliente_id", type=int)
        fecha_desde = request.args.get("fecha_desde")
        fecha_hasta = request.args.get("fecha_hasta")

        facturas = repo.listar_facturas(
            estado=estado,
            cliente_id=cliente_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )

        # Aplanar joins
        for f in facturas:
            pac = f.pop("hc_pacientes", None) or {}
            cli = f.pop("hc_clientes", None) or {}
            nombre = f"{pac.get('primer_nombre', '')} {pac.get('primer_apellido', '')}".strip()
            f["paciente_nombre"] = nombre
            f["paciente_documento"] = pac.get("numero_documento", "")
            f["cliente_nombre"] = cli.get("nombre", "")
            f["cliente_nit"] = cli.get("nit", "")

        return jsonify({"ok": True, "data": facturas})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — DETALLE DE UNA FACTURA
# =============================================================

@bp_facturacion.route("/api/factura/<int:factura_id>", methods=["GET"])
def api_detalle_factura(factura_id):
    try:
        factura = repo.obtener_factura(factura_id)
        if not factura:
            return jsonify({"ok": False, "error": "Factura no encontrada"}), 404

        detalle = repo.obtener_detalle_factura(factura_id)
        notas = repo.listar_notas_factura(factura_id)

        return jsonify({"ok": True, "data": factura, "detalle": detalle, "notas": notas})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — DESCARGAR PDF DE FACTURA
# =============================================================

@bp_facturacion.route("/api/factura/<int:factura_id>/pdf", methods=["GET"])
def api_factura_pdf(factura_id):
    """Genera y descarga el PDF de una factura."""
    try:
        from services.fin_factura_pdf import generar_factura_pdf

        factura = repo.obtener_factura(factura_id)
        if not factura:
            return jsonify({"ok": False, "error": "Factura no encontrada"}), 404

        detalle = repo.obtener_detalle_factura(factura_id)

        # Datos de empresa — ajusta según tu configuración
        empresa = {
            "nombre": "IPS VITACORE S.A.S",
            "nit": "NIT: 000.000.000-0",
            "direccion": "",
            "telefono": "",
            "ciudad": "",
        }

        pdf_bytes = generar_factura_pdf(factura, detalle, empresa)
        numero = factura.get("numero_factura", "factura")

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename=factura_{numero}.pdf"
            }
        )

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@bp_facturacion.route("/api/factura/<int:factura_id>/anular", methods=["POST"])
def api_anular_factura(factura_id):
    try:
        data = request.get_json(force=True, silent=True) or {}
        motivo = data.get("motivo", "")

        factura = repo.obtener_factura(factura_id)
        if not factura:
            return jsonify({"ok": False, "error": "Factura no encontrada"}), 404

        if factura["estado"] == "ANULADA":
            return jsonify({"ok": False, "error": "La factura ya está anulada"}), 400

        repo.anular_factura(factura_id, motivo)

        return jsonify({"ok": True, "msg": "Factura anulada correctamente"})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — CREAR NOTA CRÉDITO / DÉBITO
# =============================================================

@bp_facturacion.route("/api/nota", methods=["POST"])
def api_crear_nota():
    try:
        data = request.get_json(force=True, silent=True) or {}

        factura_id = data.get("factura_id")
        tipo = data.get("tipo")
        motivo = data.get("motivo")
        valor = data.get("valor")

        if not all([factura_id, tipo, motivo, valor]):
            return jsonify({"ok": False, "error": "factura_id, tipo, motivo y valor son requeridos"}), 400

        if tipo not in ("CREDITO", "DEBITO"):
            return jsonify({"ok": False, "error": "tipo debe ser CREDITO o DEBITO"}), 400

        # Generar número de nota
        prefijo = "NC" if tipo == "CREDITO" else "ND"
        import time
        numero_nota = f"{prefijo}{int(time.time())}"

        nota_data = {
            "empresa_id": 1,
            "factura_id": factura_id,
            "tipo": tipo,
            "numero_nota": numero_nota,
            "motivo": motivo,
            "concepto": data.get("concepto", ""),
            "valor": float(valor),
            "estado": "EMITIDA",
        }

        nota = repo.crear_nota(nota_data)

        return jsonify({"ok": True, "data": nota})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — CONSECUTIVOS
# =============================================================

@bp_facturacion.route("/api/consecutivos", methods=["GET"])
def api_listar_consecutivos():
    try:
        data = repo.listar_consecutivos()
        for c in data:
            sede = c.pop("hc_sedes", None) or {}
            c["sede_nombre"] = sede.get("nombre", "Todas")
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/consecutivos", methods=["POST"])
def api_crear_consecutivo():
    try:
        data = request.get_json(force=True, silent=True) or {}
        consecutivo = repo.crear_consecutivo({
            "empresa_id": 1,
            "sede_id": data.get("sede_id"),
            "prefijo": data.get("prefijo", "FV"),
            "consecutivo_actual": int(data.get("consecutivo_inicial", 0)),
            "rango_desde": data.get("rango_desde"),
            "rango_hasta": data.get("rango_hasta"),
            "resolucion_dian": data.get("resolucion_dian"),
            "fecha_resolucion": data.get("fecha_resolucion"),
            "fecha_vencimiento": data.get("fecha_vencimiento"),
            "estado": "ACTIVO",
            "es_principal": data.get("es_principal", True),
        })
        return jsonify({"ok": True, "data": consecutivo})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — RESUMEN / DASHBOARD
# =============================================================

@bp_facturacion.route("/api/resumen", methods=["GET"])
def api_resumen():
    try:
        resumen = repo.resumen_facturacion()
        return jsonify({"ok": True, "data": resumen})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — FACTURACIÓN LIBRE (SIN CITA)
# =============================================================

@bp_facturacion.route("/api/prefactura-libre", methods=["POST"])
def api_crear_prefactura_libre():
    """
    Crea una prefactura sin necesidad de citas previas.
    Permite facturar procedimientos, medicamentos o insumos
    directamente al paciente.

    Body: {
      paciente_id, cliente_id, contrato_id, sede_id,
      items: [
        { codigo_cups, descripcion, cantidad, valor_unitario, cups_id (opcional) }
      ]
    }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}

        paciente_id = data.get("paciente_id")
        cliente_id = data.get("cliente_id")
        contrato_id = data.get("contrato_id")
        sede_id = data.get("sede_id")
        items_raw = data.get("items", [])

        if not paciente_id or not cliente_id or not contrato_id:
            return jsonify({"ok": False, "error": "paciente_id, cliente_id y contrato_id son requeridos"}), 400

        if not items_raw:
            return jsonify({"ok": False, "error": "Agregue al menos un ítem"}), 400

        # Construir ítems y calcular subtotal
        items = []
        subtotal = 0

        for item in items_raw:
            cantidad = int(item.get("cantidad", 1))
            cups_id = item.get("cups_id")

            # Si hay cups_id y contrato, buscar tarifa del manual
            if cups_id and contrato_id:
                tarifa = repo.obtener_tarifa_cups(int(contrato_id), int(cups_id))
                valor_unitario = float(tarifa["valor_total"]) if tarifa else float(item.get("valor_unitario", 0))
            else:
                valor_unitario = float(item.get("valor_unitario", 0))

            valor_total = valor_unitario * cantidad

            items.append({
                "codigo_cups": item.get("codigo_cups", ""),
                "descripcion": item.get("descripcion", ""),
                "cantidad": cantidad,
                "valor_unitario": valor_unitario,
                "valor_total": valor_total,
            })
            subtotal += valor_total

        # Crear prefactura
        prefactura_data = {
            "empresa_id": 1,
            "paciente_id": paciente_id,
            "cliente_id": cliente_id,
            "contrato_id": contrato_id,
            "sede_id": sede_id,
            "subtotal": subtotal,
            "valor_neto": subtotal,
            "estado": "ABIERTA",
        }

        prefactura, items_creados = repo.crear_prefactura_libre(prefactura_data, items)

        if not prefactura:
            return jsonify({"ok": False, "error": "Error al crear prefactura"}), 500

        return jsonify({
            "ok": True,
            "prefactura_id": prefactura["id"],
            "subtotal": subtotal,
            "items_count": len(items_creados),
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — BUSCAR CUPS (para facturación libre)
# =============================================================

@bp_facturacion.route("/api/buscar-cups", methods=["GET"])
def api_buscar_cups():
    """Busca procedimientos CUPS por código o descripción."""
    try:
        q = request.args.get("q", "").strip()
        if len(q) < 2:
            return jsonify({"ok": True, "data": []})

        cups = repo.buscar_cups_por_texto(q)
        return jsonify({"ok": True, "data": cups})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — TARIFA DE UN CUPS EN EL CONTRATO
# =============================================================

@bp_facturacion.route("/api/tarifa-cups", methods=["GET"])
def api_tarifa_cups():
    """
    Consulta la tarifa de un procedimiento CUPS en el manual
    del contrato.
    Query params: contrato_id, cups_id
    """
    try:
        contrato_id = request.args.get("contrato_id", type=int)
        cups_id = request.args.get("cups_id", type=int)

        if not contrato_id or not cups_id:
            return jsonify({"ok": False, "error": "contrato_id y cups_id son requeridos"}), 400

        tarifa = repo.obtener_tarifa_cups(contrato_id, cups_id)

        if not tarifa:
            return jsonify({"ok": False, "error": "Procedimiento no encontrado en el manual tarifario"}), 404

        return jsonify({"ok": True, "data": tarifa})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500