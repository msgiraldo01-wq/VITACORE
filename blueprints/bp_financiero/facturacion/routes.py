"""
Rutas del módulo de facturación — Vitacore
Blueprint: bp_facturacion  →  /facturacion/...
"""

import re
import time as _time
from flask import Blueprint, render_template, request, jsonify, Response, session
from blueprints.auth.decorators import login_required
from services.permisos_service import requiere_permiso
from repositories import fin_facturacion_repo as repo
from repositories import fin_factus_repo
from repositories import hc_municipios_repo
from repositories import hc_departamentos_repo
from services import factus_service
from services import factus_mapper
from services.factus_mapper import DatosFaltantesError
from services.factus_service import FactusAPIError

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
@login_required
def index():
    """Página principal del módulo de facturación."""
    return render_template("financiero/facturacion/facturacion.html")


@bp_facturacion.route("/facturas")
@login_required
def lista_facturas():
    """Listado de facturas emitidas."""
    return render_template("financiero/facturacion/facturas_lista.html")

@bp_facturacion.route("/prefacturas")
@login_required
def lista_prefacturas():
    return render_template("financiero/facturacion/prefacturas_lista.html")


@bp_facturacion.route("/configuracion")
@login_required
def configuracion():
    """Configuración de consecutivos y resoluciones."""
    return render_template("financiero/facturacion/facturacion_configuracion.html")


@bp_facturacion.route("/factura/<int:factura_id>/vista")
@login_required
def vista_factura(factura_id):
    """Vista de factura para impresión y descarga PDF."""
    return render_template("financiero/facturacion/factura_vista.html", factura_id=factura_id)


@bp_facturacion.route("/factus/eventos")
@login_required
def factus_eventos():
    """
    Panel de diagnóstico (2026-08-27): muestra en una tabla lo que la app
    le ha mandado a Factus y lo que Factus respondió (éxito o error), leído
    de fin_factus_eventos_log. Reemplaza tener que revisar esto a mano
    desde la consola del navegador cada vez que algo falla.
    """
    return render_template("financiero/facturacion/factus_eventos.html")


# =============================================================
# API — BUSCAR CITAS FACTURABLES
# =============================================================

@bp_facturacion.route("/api/buscar-paciente", methods=["GET"])
@login_required
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
            cita["tipo_factura"] = contrato.get("tipo_factura", "INDIVIDUAL")

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
@login_required
@requiere_permiso("facturacion", "create")
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
@login_required
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
@login_required
@requiere_permiso("facturacion", "edit")
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
# FACTUS — helper de emisión electrónica (DIAN)
# =============================================================


def _construir_adquiriente_o_error(cliente_id, paciente_id):
    """
    Devuelve (adquiriente_tipo, customer_payload, None) o
    (None, None, dict_error_http) si faltan datos.
    """
    cliente = fin_factus_repo.obtener_cliente_para_dian(cliente_id) if cliente_id else None
    paciente = fin_factus_repo.obtener_paciente_para_dian(paciente_id) if paciente_id else None
    try:
        adquiriente_tipo, customer_payload = factus_mapper.construir_adquiriente(cliente, paciente)
        return adquiriente_tipo, customer_payload, None
    except DatosFaltantesError as e:
        return None, None, {
            "ok": False,
            "error": "datos_incompletos",
            "mensaje": str(e),
            "requiere_datos": {
                "entidad": e.entidad,
                "entidad_id": e.entidad_id,
                "campos_faltantes": e.campos_faltantes,
            },
        }


def _obtener_numbering_range_nota(tipo: str):
    """
    Busca EN VIVO en Factus el rango de numeración activo para notas
    crédito ('CREDITO') o débito ('DEBITO'). No se puede reusar el
    numbering_range_id de la factura de venta -- son rangos distintos en
    Factus (se confirmó con una prueba real: Factus rechazó el de la
    factura con "El campo id rango de numeración es inválido"). Devuelve
    (numbering_range_id, None) o (None, mensaje_error) si la cuenta de
    Factus no tiene un rango configurado para este tipo de documento.
    """
    try:
        rangos = factus_service.obtener_rangos_numeracion()
    except FactusAPIError as e:
        return None, f"No se pudo consultar los rangos de numeración en Factus: {e.message}"

    con_tilde = "crédito" if tipo == "CREDITO" else "débito"
    sin_tilde = "credito" if tipo == "CREDITO" else "debito"
    candidatos = [
        r for r in rangos
        if "nota" in (r.get("document") or "").lower()
        and (con_tilde in (r.get("document") or "").lower() or sin_tilde in (r.get("document") or "").lower())
    ]
    if not candidatos:
        etiqueta = "Crédito" if tipo == "CREDITO" else "Débito"
        return None, (
            f"Factus no tiene configurado un rango de numeración para Notas {etiqueta} "
            "en esta cuenta. Debe crearse/activarse desde el panel de Factus antes de "
            "poder emitir una."
        )
    activos = [r for r in candidatos if r.get("is_active")]
    elegido = (activos or candidatos)[0]
    return elegido.get("id"), None


def _emitir_factura_ante_dian(reference_code, numbering_range_id, total, observaciones, items, cliente_id, paciente_id):
    """
    Orquesta la emisión electrónica de una factura de venta ante la DIAN
    vía Factus. No toca la base de datos — solo construye el payload,
    llama a Factus y retorna el resultado (o un dict de error HTTP-friendly).

    Retorna: (resultado_ok: dict|None, error_http: dict|None, status_code: int)
    """
    from flask import current_app
    if not current_app.config.get("FACTUS_HABILITADO", True):
        return None, None, 0  # integración desactivada — el caller usa el flujo local

    if not numbering_range_id:
        return None, {
            "ok": False,
            "error": "configuracion_dian",
            "mensaje": (
                "Esta sede no tiene configurado el rango de numeración de Factus "
                "(factus_numbering_range_id). Configúralo en Facturación → Configuración."
            ),
        }, 400

    adquiriente_tipo, customer_payload, err = _construir_adquiriente_o_error(cliente_id, paciente_id)
    if err:
        return None, err, 409

    codigos_cups = [it.get("codigo_cups") for it in items]
    cups_map = fin_factus_repo.obtener_cups_para_dian(codigos_cups)

    payload = factus_mapper.construir_payload_factura(
        reference_code=f"VITACORE-PF-{reference_code}",
        observaciones=observaciones,
        total=total,
        detalle=items,
        numbering_range_id=numbering_range_id,
        adquiriente_tipo=adquiriente_tipo,
        customer_payload=customer_payload,
        cups_por_codigo=cups_map,
    )

    # Auto-limpieza (2026-08-27): se confirmó con pruebas reales que un
    # intento anterior con este mismo reference_code — sea rechazado por
    # validación (422) o bloqueado con el 409 "pendiente por enviar a la
    # DIAN" — puede dejar atascado un número en la secuencia de Factus que
    # bloquea CUALQUIER intento siguiente (incluso de otra prefactura, si
    # comparte rango de numeración). Antes de cada intento se borra en
    # silencio cualquier factura no validada que exista para este
    # reference_code; si no había nada atascado, Factus responde "no
    # encontrado" y simplemente se ignora — así el usuario ya no tiene que
    # detectarlo ni borrarlo a mano desde el panel de diagnóstico.
    try:
        factus_service.eliminar_factura_pendiente(payload["reference_code"])
        fin_factus_repo.registrar_evento(
            "FACTURA", reference_code, "ELIMINAR_PENDIENTE_AUTO",
            {"reference_code": payload["reference_code"]}, {"ok": True}, True,
        )
    except FactusAPIError:
        pass  # No había nada pendiente (o no se pudo confirmar) — se continúa igual.

    try:
        respuesta = factus_service.crear_y_validar_factura(payload)
        fin_factus_repo.registrar_evento("FACTURA", reference_code, "CREAR_VALIDAR", payload, respuesta, True)
    except FactusAPIError as e:
        fin_factus_repo.registrar_evento("FACTURA", reference_code, "CREAR_VALIDAR", payload, e.to_dict(), False)
        return None, {
            "ok": False,
            "error": "rechazo_dian",
            "mensaje": e.message,
            "detalle_dian": e.errors,
        }, 422

    datos = respuesta.get("data") or respuesta
    bill = datos.get("bill") or datos
    resultado = {
        "numero_factura_dian": bill.get("number") or bill.get("bill_number") or "",
        "cufe": bill.get("cufe") or datos.get("cufe") or "",
        "qr_image": bill.get("qr_image") or datos.get("qr_image") or "",
        "is_validated": datos.get("is_validated", True),
        "adquiriente_tipo": adquiriente_tipo,
        "factus_response": respuesta,
    }
    return resultado, None, 200


# =============================================================
# API — GENERAR FACTURA DESDE PREFACTURA
# =============================================================

@bp_facturacion.route("/api/facturar", methods=["POST"])
@login_required
@requiere_permiso("facturacion", "create")
def api_facturar():
    """
    Genera una factura definitiva desde una prefactura y la emite
    electrónicamente ante la DIAN a través de Factus (si FACTUS_HABILITADO).

    Flujo: se valida y emite ante la DIAN PRIMERO; solo si Factus valida
    (o si la integración está desactivada) se crea la factura local y se
    disparan los efectos colaterales (caja, cartera, marcar citas). Así
    nunca queda una factura "fantasma" que la DIAN rechazó.

    Body: { prefactura_id, copago, cuota_moderadora, cuota_recuperacion,
            pagos_compartidos, numero_poliza, observaciones }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        prefactura_id = data.get("prefactura_id")

        if not prefactura_id:
            return jsonify({"ok": False, "error": "prefactura_id es requerido"}), 400

        # Validar caja abierta
        from repositories import fin_caja_repo as caja_repo
        user = session.get("user", {})
        caja = caja_repo.obtener_caja_abierta(user.get("id", ""))
        if not caja:
            return jsonify({"ok": False, "error": "Debe abrir una caja antes de facturar"}), 400

        # Obtener prefactura
        prefactura = repo.obtener_prefactura(prefactura_id)
        if not prefactura:
            return jsonify({"ok": False, "error": "Prefactura no encontrada"}), 404

        if prefactura["estado"] == "FACTURADA":
            return jsonify({"ok": False, "error": "Esta prefactura ya fue facturada"}), 400

        # ── Bloquear contratos de facturación CONSOLIDADA ──
        contrato = prefactura.get("hc_contratos", {}) or {}
        if contrato.get("tipo_factura", "").upper() == "CONSOLIDADA":
            return jsonify({
                "ok": False,
                "error": "Este contrato es de facturación consolidada. "
                         "Use el módulo de consolidación para facturar."
            }), 400

        # Obtener consecutivo (siempre se necesita: para trazabilidad local
        # y, si aplica, para saber el numbering_range_id de Factus de la sede)
        consecutivo = repo.obtener_consecutivo_activo(sede_id=prefactura.get("sede_id"))
        if not consecutivo:
            return jsonify({"ok": False, "error": "No hay consecutivo de facturación activo. Configure uno en el módulo de facturación."}), 400

        # Obtener datos de sede para campos FEV
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
        copago     = float(data.get("copago", prefactura.get("valor_copago", 0)))
        cuota_mod  = float(data.get("cuota_moderadora", prefactura.get("valor_cuota_moderadora", 0)))
        cuota_rec  = float(data.get("cuota_recuperacion", prefactura.get("valor_cuota_recuperacion", 0)))
        pagos_comp = float(data.get("pagos_compartidos", 0))
        subtotal   = float(prefactura.get("subtotal", 0))
        descuento  = float(prefactura.get("descuento", 0))
        total      = subtotal - descuento

        observaciones = data.get("observaciones", "")
        items_pref_preview = repo.obtener_items_prefactura(prefactura_id)

        # ── Emisión electrónica ante la DIAN (Factus) — ANTES de crear nada ──
        resultado_dian, error_http, _status = _emitir_factura_ante_dian(
            reference_code=prefactura_id,
            numbering_range_id=consecutivo.get("factus_numbering_range_id"),
            total=total,
            observaciones=observaciones,
            items=items_pref_preview,
            cliente_id=prefactura.get("cliente_id"),
            paciente_id=prefactura.get("paciente_id"),
        )
        if error_http:
            return jsonify(error_http), _status

        if resultado_dian:
            numero_factura = resultado_dian["numero_factura_dian"] or f"{consecutivo['prefijo']}{prefactura_id}"
            factus_campos = {
                "cufe":            resultado_dian["cufe"],
                "qr_image":        resultado_dian["qr_image"],
                "factus_estado":   "VALIDADA" if resultado_dian["is_validated"] else "PENDIENTE_DIAN",
                "factus_response": resultado_dian["factus_response"],
                "adquiriente_tipo": resultado_dian["adquiriente_tipo"],
                "enviado_dian_at": "now()",
                "estado_dian":     "VALIDADA" if resultado_dian["is_validated"] else "PENDIENTE",
            }
        else:
            # Integración con Factus desactivada (FACTUS_HABILITADO=false):
            # se conserva el comportamiento local original como respaldo
            # para pruebas/desarrollo sin gastar consecutivos DIAN reales.
            numero_factura, error = repo.incrementar_consecutivo(consecutivo["id"])
            if error:
                return jsonify({"ok": False, "error": error}), 400
            factus_campos = {"factus_estado": "NO_APLICA", "estado_dian": "NO_APLICA"}

        # Crear factura local — solo se llega aquí si la DIAN ya validó
        # (o si Factus está desactivado para este ambiente).
        factura_data = {
            "empresa_id":                1,
            "consecutivo_id":            consecutivo["id"],
            "prefijo":                   consecutivo["prefijo"],
            "numero_factura":            numero_factura,
            "prefactura_id":             prefactura_id,
            "paciente_id":               prefactura["paciente_id"],
            "cliente_id":                prefactura["cliente_id"],
            "contrato_id":               prefactura["contrato_id"],
            "sede_id":                   prefactura.get("sede_id"),
            "subtotal":                  subtotal,
            "descuento":                 descuento,
            "total":                     total,
            "codigo_prestador":          (sede_data or {}).get("codigo", ""),
            "modalidad_pago":            modalidad_pago,
            "cobertura_plan_beneficios": data.get("cobertura_plan_beneficios", "PBS_CONTRIBUTIVO"),
            "numero_contrato":           contrato.get("nro_contrato", ""),
            "numero_poliza":             data.get("numero_poliza", ""),
            "copago":                    copago,
            "cuota_moderadora":          cuota_mod,
            "cuota_recuperacion":        cuota_rec,
            "pagos_compartidos":         pagos_comp,
            "periodo_facturacion_inicio": prefactura.get("periodo_inicio"),
            "periodo_facturacion_fin":    prefactura.get("periodo_fin"),
            "estado":                    "EMITIDA",
            "observaciones":             observaciones,
            **factus_campos,
        }

        factura = repo.crear_factura(factura_data)
        if not factura:
            return jsonify({"ok": False, "error": "Error al crear factura"}), 500

        # Copiar ítems de prefactura a detalle de factura
        items_pref = repo.obtener_items_prefactura(prefactura_id)
        detalle    = []
        cita_ids   = set()

        for item in items_pref:
            cita_id = item.get("cita_id")
            if cita_id:
                cita_ids.add(cita_id)

            detalle.append({
                "factura_id":            factura["id"],
                "cita_id":               cita_id,
                "cita_procedimiento_id": item.get("cita_procedimiento_id"),
                "codigo_cups":           item["codigo_cups"],
                "descripcion":           item["descripcion"],
                "cantidad":              item["cantidad"],
                "valor_unitario":        item["valor_unitario"],
                "valor_total":           item["valor_total"],
                "diagnostico_principal": item.get("diagnostico_principal"),
                "tipo_diagnostico":      item.get("tipo_diagnostico"),
            })

        if detalle:
            repo.agregar_detalle_factura(detalle)

        # Marcar prefactura como FACTURADA
        repo.actualizar_prefactura(prefactura_id, {"estado": "FACTURADA"})

        # Marcar citas como FACTURADA
        if cita_ids:
            repo.marcar_citas_facturadas(list(cita_ids))

        # ── Registrar cobro automático en caja ──
        try:
            caja = caja_repo.obtener_caja_abierta(user.get("id", 0))
            if caja:
                medio_pago       = data.get("medio_pago", "EFECTIVO")
                factura_completa = repo.obtener_factura(factura["id"])
                caja_repo.registrar_cobro_factura(caja["id"], factura_completa, medio_pago)
        except Exception as e_caja:
            print(f"[WARN] Error registrando cobro en caja: {e_caja}")

        # ── Sincronizar automáticamente a Cartera ──
        try:
            from repositories.fin_cartera_repo import sincronizar_factura_a_cartera
            factura_completa = repo.obtener_factura(factura["id"])
            if factura_completa:
                sincronizar_factura_a_cartera(factura_completa)
        except Exception as e_cartera:
            print(f"[WARN] Error sincronizando a cartera: {e_cartera}")

        return jsonify({
            "ok":             True,
            "factura_id":     factura["id"],
            "numero_factura": numero_factura,
            "total":          total,
            "cufe":           factus_campos.get("cufe", ""),
            "qr_image":       factus_campos.get("qr_image", ""),
            "factus_estado":  factus_campos.get("factus_estado", "NO_APLICA"),
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — REINTENTAR EMISIÓN DIAN / COMPLETAR DATOS ADQUIRIENTE
# =============================================================

@bp_facturacion.route("/api/factura/<int:factura_id>/reintentar-dian", methods=["POST"])
@login_required
@requiere_permiso("facturacion", "edit")
def api_reintentar_dian(factura_id):
    """
    Reintenta la emisión electrónica ante Factus para una factura que
    quedó en estado NO_APLICA/PENDIENTE/rechazada (por ejemplo porque al
    facturar Factus estaba deshabilitado, o falló transitoriamente).
    Usa el mismo reference_code (prefactura_id) para que Factus no
    duplique el documento si ya había sido validado antes.
    """
    try:
        factura = repo.obtener_factura(factura_id)
        if not factura:
            return jsonify({"ok": False, "error": "Factura no encontrada"}), 404
        if factura.get("factus_estado") == "VALIDADA":
            return jsonify({"ok": False, "error": "Esta factura ya fue validada por la DIAN"}), 400

        consecutivo = repo.obtener_consecutivo_activo(sede_id=factura.get("sede_id"))
        detalle = repo.obtener_detalle_factura(factura_id)

        resultado_dian, error_http, status_code = _emitir_factura_ante_dian(
            reference_code=factura.get("prefactura_id") or factura_id,
            numbering_range_id=(consecutivo or {}).get("factus_numbering_range_id"),
            total=factura.get("total", 0),
            observaciones=factura.get("observaciones", ""),
            items=detalle,
            cliente_id=factura.get("cliente_id"),
            paciente_id=factura.get("paciente_id"),
        )
        if error_http:
            return jsonify(error_http), status_code
        if not resultado_dian:
            return jsonify({"ok": False, "error": "La integración con Factus está deshabilitada (FACTUS_HABILITADO=false)."}), 400

        repo.registrar_resultado_factus(factura_id, {
            "numero_factura":  resultado_dian["numero_factura_dian"] or factura.get("numero_factura"),
            "cufe":            resultado_dian["cufe"],
            "qr_image":        resultado_dian["qr_image"],
            "factus_estado":   "VALIDADA" if resultado_dian["is_validated"] else "PENDIENTE_DIAN",
            "estado_dian":     "VALIDADA" if resultado_dian["is_validated"] else "PENDIENTE",
            "factus_response": resultado_dian["factus_response"],
            "adquiriente_tipo": resultado_dian["adquiriente_tipo"],
            "enviado_dian_at": "now()",
        })

        return jsonify({"ok": True, "cufe": resultado_dian["cufe"], "qr_image": resultado_dian["qr_image"]})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/adquiriente/completar", methods=["POST"])
@login_required
@requiere_permiso("facturacion", "edit")
def api_completar_datos_adquiriente():
    """
    Guarda los datos DIAN que falten (dirección, email, municipio) de un
    paciente o cliente para poder facturar electrónicamente.
    Body: { tipo: 'PACIENTE'|'CLIENTE', id, direccion, email, telefono, municipio_id }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        tipo = (data.get("tipo") or "").upper()
        entidad_id = data.get("id")

        if tipo not in ("PACIENTE", "CLIENTE") or not entidad_id:
            return jsonify({"ok": False, "error": "tipo ('PACIENTE'|'CLIENTE') e id son requeridos"}), 400

        campos = {}
        for campo in ("direccion", "email", "telefono", "municipio_id"):
            if data.get(campo) not in (None, ""):
                campos[campo] = data.get(campo)

        if not campos:
            return jsonify({"ok": False, "error": "No se recibió ningún campo para actualizar"}), 400

        tabla = "hc_pacientes" if tipo == "PACIENTE" else "hc_clientes"
        repo._sb().table(tabla).update(campos).eq("id", entidad_id).execute()

        return jsonify({"ok": True})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — DIAGNÓSTICO / TABLAS DE REFERENCIA FACTUS
# =============================================================

@bp_facturacion.route("/api/factus/test-conexion", methods=["GET"])
@login_required
def api_factus_test_conexion():
    try:
        resultado = factus_service.test_conexion()
        return jsonify({"ok": True, "data": resultado})
    except FactusAPIError as e:
        return jsonify({"ok": False, "error": e.message, "detalle": e.errors}), e.status_code or 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/factus/eliminar-pendiente", methods=["POST", "DELETE"])
@login_required
@requiere_permiso("facturacion_diagnostico", "delete")
def api_factus_eliminar_pendiente():
    """
    Elimina en Factus una factura NO VALIDADA que está bloqueando el rango
    de numeración con el 409 "Se encontró una factura pendiente por enviar
    a la DIAN" (ver developers.factus.com.co/facturas/eliminar/). Solo
    borra facturas todavía sin validar — si Factus ya la validó, esto no
    aplica y hay que manejarla como factura real (no hay nada que "arreglar").

    Body/query: { prefactura_id } o { reference_code }
    """
    data = request.get_json(force=True, silent=True) or {}
    prefactura_id = data.get("prefactura_id") or request.args.get("prefactura_id", "")
    reference_code = (data.get("reference_code") or request.args.get("reference_code", "")).strip()
    if not reference_code and prefactura_id:
        reference_code = f"VITACORE-PF-{prefactura_id}"
    if not reference_code:
        return jsonify({"ok": False, "error": "Falta prefactura_id o reference_code"}), 400

    # Para el log de auditoría: intenta recuperar el id de documento del
    # propio reference_code (VITACORE-PF-{id}) si no vino explícito.
    documento_id = None
    if prefactura_id:
        try:
            documento_id = int(prefactura_id)
        except (TypeError, ValueError):
            documento_id = None
    if documento_id is None:
        m = re.search(r"(\d+)$", reference_code)
        if m:
            documento_id = int(m.group(1))

    try:
        respuesta = factus_service.eliminar_factura_pendiente(reference_code)
        fin_factus_repo.registrar_evento(
            "FACTURA", documento_id, "ELIMINAR_PENDIENTE",
            {"reference_code": reference_code}, respuesta, True,
        )
        return jsonify({"ok": True, "reference_code": reference_code, "data": respuesta})
    except FactusAPIError as e:
        fin_factus_repo.registrar_evento(
            "FACTURA", documento_id, "ELIMINAR_PENDIENTE",
            {"reference_code": reference_code}, e.to_dict(), False,
        )
        return jsonify({"ok": False, "error": e.message, "detalle": e.errors}), e.status_code or 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/factus/consultar-por-referencia", methods=["GET"])
@login_required
def api_factus_consultar_por_referencia():
    """
    Diagnóstico (2026-08-27): busca EN FACTUS (no en la BD local) qué
    factura(s) existen ya para un reference_code dado. Sirve para cuando
    Factus rechaza un intento de facturar con
    "Se encontró una factura pendiente por enviar a la DIAN": ese mensaje
    significa que un intento anterior con el MISMO reference_code
    (VITACORE-PF-{prefactura_id}) sí alcanzó a crearse del lado de Factus
    y quedó pendiente (filter[status] = 0) de que la DIAN la confirme —
    Factus no deja crear un duplicado mientras esa siga pendiente.

    Query: ?prefactura_id=28  (o directamente ?reference_code=VITACORE-PF-28)
    Query opcional: ?estado=0  (0 = pendiente por validar, 1 = validada) — si
    se omite reference_code/prefactura_id, sirve para listar TODAS las
    facturas en ese estado sin filtrar por referencia (útil porque el
    "pendiente" que bloquea la creación puede no estar amarrado al
    reference_code, sino al rango de numeración / secuencia consecutiva de
    la sede — dos prefacturas distintas comparten el mismo numbering_range_id).

    filter[status] que devuelve Factus: 1 = validada, 0 = pendiente por validar.
    """
    prefactura_id = request.args.get("prefactura_id", "").strip()
    reference_code = request.args.get("reference_code", "").strip() or (
        f"VITACORE-PF-{prefactura_id}" if prefactura_id else ""
    )
    estado = request.args.get("estado", "").strip()

    params = {}
    if reference_code:
        params["filter[reference_code]"] = reference_code
    if estado != "":
        params["filter[status]"] = estado
    params["filter[per_page]"] = request.args.get("per_page", "50")

    try:
        facturas = factus_service.listar_facturas(params=params)
        return jsonify({"ok": True, "reference_code": reference_code or None, "estado": estado or None, "facturas": facturas})
    except FactusAPIError as e:
        return jsonify({"ok": False, "error": e.message, "detalle": e.errors}), e.status_code or 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/factus/eventos", methods=["GET"])
@login_required
def api_factus_eventos():
    """
    Datos para el panel /facturacion/factus/eventos. Lee de
    fin_factus_eventos_log (auditoría local de lo enviado/recibido con
    Factus) — NO llama a Factus, así que funciona aunque Factus esté
    lento o caído.
    Query opcional: ?solo_errores=1, ?limit=100
    """
    solo_errores = request.args.get("solo_errores") in ("1", "true", "True")
    try:
        limite = int(request.args.get("limit", 100))
    except ValueError:
        limite = 100
    try:
        eventos = fin_factus_repo.listar_eventos_recientes(limite=limite, solo_errores=solo_errores)
        return jsonify({"ok": True, "eventos": eventos})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/factus/rangos-numeracion", methods=["GET"])
@login_required
def api_factus_rangos_numeracion():
    """
    Trae en vivo los rangos de numeración configurados en la cuenta de
    Factus (para que el formulario de Configuración los muestre en un
    selector en vez de pedir un ID a ciegas).
    Query param opcional: documento (ej. 'Factura de Venta') para filtrar.
    """
    try:
        rangos = factus_service.obtener_rangos_numeracion()
        documento = request.args.get("documento", "").strip()
        if documento:
            rangos = [r for r in rangos if r.get("document") == documento]
        return jsonify({"ok": True, "data": rangos})
    except FactusAPIError as e:
        return jsonify({"ok": False, "error": e.message, "detalle": e.errors}), e.status_code or 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/factus/municipios", methods=["GET"])
@login_required
def api_factus_buscar_municipios():
    """
    Busca municipios directamente en hc_municipios (los que ya tienen
    codigo_dian asignado, es decir, listos para facturar electrónicamente).
    Devuelve el id REAL de hc_municipios como 'codigo' — es justo lo que
    hc_clientes.municipio_id / hc_pacientes.municipio_id exige por FK, así
    que el modal puede guardarlo tal cual sin pasos adicionales.

    NOTA (2026-08-26): antes buscaba en fin_factus_referencias (un caché
    aparte con el código DIAN de 5 dígitos como valor), pero ese código NO
    es lo que la FK de hc_clientes.municipio_id espera — espera el id
    interno de hc_municipios. Guardar el código DIAN directo ahí causaba
    'violates foreign key constraint hc_clientes_municipio_id_fkey'.
    """
    try:
        q = request.args.get("q", "").strip()
        filas = hc_municipios_repo.buscar_con_codigo_dian(q)
        data = [
            {
                "codigo": f["id"],
                "nombre": f"{f['nombre']} ({f['departamento']})" if f.get("departamento") else f["nombre"],
            }
            for f in filas
        ]
        return jsonify({"ok": True, "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/factus/sincronizar-municipios", methods=["POST"])
@login_required
@requiere_permiso("facturacion_diagnostico", "create")
def api_factus_sincronizar_municipios():
    """
    Trae la tabla oficial de municipios (código DIVIPOLA de 5 dígitos que
    exige la DIAN) desde el portal de datos abiertos del Estado colombiano
    y la usa para completar el campo codigo_dian de hc_municipios: si el
    municipio ya existe (mismo nombre normalizado, mismo departamento) le
    completa el codigo_dian; si no existe, lo crea.

    NOTA (2026-08-26): esto originalmente llamaba a un endpoint de Factus
    (ENDPOINTS["reference_table"], /v2/common/{tabla}) que resultó no
    existir — Factus devolvía su propio 404 ("No se encontró la ruta o
    recurso solicitado"), confirmado además contra la colección Postman
    oficial de Factus v2, que no incluye ninguna tabla de referencia. Los
    códigos de municipio DIAN/DANE son un estándar público que no depende
    de Factus, así que se reemplazó por la fuente oficial (dataset
    DIVIPOLA de la DANE). Además, el primer reemplazo guardaba esto en un
    caché aparte (fin_factus_referencias) que no alimentaba la FK real de
    hc_clientes.municipio_id — ahora se respalda directo sobre
    hc_municipios, que es la tabla que de verdad usa el resto de la app.
    Ejecutar una vez (los municipios de Colombia casi nunca cambian).
    """
    try:
        import requests
        resp = requests.get(
            "https://www.datos.gov.co/resource/gdxc-w37w.json",
            params={"$limit": 1300},
            timeout=30,
        )
        resp.raise_for_status()
        filas_dane = resp.json()
        if not filas_dane:
            return jsonify({
                "ok": False,
                "error": "El portal de datos abiertos DANE respondió sin registros de municipios.",
            }), 502

        # Mapa de departamentos ya existentes en la app, normalizado para
        # poder emparejar contra los nombres del dataset DANE (que vienen
        # en mayúsculas, sin tildes, con puntuación distinta).
        departamentos = hc_departamentos_repo.listar()
        dep_por_nombre = {
            hc_municipios_repo.normalizar_texto(d["nombre"]): d["id"]
            for d in departamentos if d.get("nombre")
        }

        # Municipios ya existentes, indexados por (departamento_id, nombre normalizado).
        existentes = hc_municipios_repo.listar_todos_para_sync()
        existentes_por_clave = {
            (e.get("departamento_id"), hc_municipios_repo.normalizar_texto(e.get("nombre") or "")): e
            for e in existentes
        }

        sin_cambios = 0
        nuevas_filas = []
        pendientes_actualizar = []  # [(id, codigo_dian), ...]
        departamentos_sin_match = set()

        for f in filas_dane:
            codigo_dian = f.get("cod_mpio")
            nombre = (f.get("nom_mpio") or "").strip().title()
            dpto_nombre = (f.get("dpto") or "").strip()
            if not codigo_dian or not nombre or not dpto_nombre:
                continue

            departamento_id = dep_por_nombre.get(hc_municipios_repo.normalizar_texto(dpto_nombre))
            if not departamento_id:
                departamentos_sin_match.add(dpto_nombre)
                continue

            clave = (departamento_id, hc_municipios_repo.normalizar_texto(nombre))
            existente = existentes_por_clave.get(clave)

            if existente:
                if existente.get("codigo_dian") != codigo_dian:
                    pendientes_actualizar.append((existente["id"], codigo_dian))
                else:
                    sin_cambios += 1
            else:
                nuevas_filas.append({
                    "departamento_id": departamento_id,
                    "nombre": nombre,
                    "codigo": codigo_dian,
                    "codigo_dian": codigo_dian,
                    "estado": "ACTIVO",
                })

        creados = 0
        if nuevas_filas:
            hc_municipios_repo.insertar_muchos(nuevas_filas)
            creados = len(nuevas_filas)

        # Las actualizaciones son un llamado HTTP por fila a Supabase — con
        # cientos/miles de filas, hacerlas una por una en serie puede tardar
        # varios minutos, así que se paralelizan con un pool de hilos.
        #
        # Dos vueltas ya dadas aquí:
        # 1. get_supabase_admin() usa current_app.config, que no existe
        #    dentro de un hilo nuevo -> "Working outside of application
        #    context". Solución: leer la URL/key en el hilo principal
        #    (aquí sí hay contexto) y pasarlas como texto plano.
        # 2. Compartir UN solo cliente (una sola conexión HTTP) entre 20
        #    hilos a la vez causó '[WinError 10035] No se puede completar
        #    de forma inmediata una operación de socket' en Windows.
        #    Solución: cada hilo crea SU PROPIO cliente (vía threading.local,
        #    para no crear uno nuevo en cada llamada) y se baja la
        #    concurrencia a 8 en vez de 20.
        actualizados = 0
        if pendientes_actualizar:
            import threading
            from concurrent.futures import ThreadPoolExecutor
            from supabase import create_client
            from flask import current_app

            supabase_url = current_app.config["SUPABASE_URL"]
            supabase_key = current_app.config["SUPABASE_SERVICE_ROLE_KEY"]
            _local = threading.local()

            def _actualizar_una(par):
                cliente = getattr(_local, "cliente", None)
                if cliente is None:
                    cliente = create_client(supabase_url, supabase_key)
                    _local.cliente = cliente
                hc_municipios_repo.actualizar_codigo_dian(par[0], par[1], cliente=cliente)

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(_actualizar_una, pendientes_actualizar))
            actualizados = len(pendientes_actualizar)

        return jsonify({
            "ok": True,
            "creados": creados,
            "actualizados": actualizados,
            "sin_cambios": sin_cambios,
            "departamentos_no_encontrados": sorted(departamentos_sin_match),
        })
    except requests.RequestException as e:
        return jsonify({
            "ok": False,
            "error": f"No se pudo consultar el portal de datos abiertos DANE (revisa la conexión a internet del servidor): {e}",
        }), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — LISTAR FACTURAS
# =============================================================

@bp_facturacion.route("/api/facturas", methods=["GET"])
@login_required
def api_listar_facturas():
    try:
        estado = request.args.get("estado")
        cliente_id = request.args.get("cliente_id", type=int)
        fecha_desde = request.args.get("fecha_desde")
        fecha_hasta = request.args.get("fecha_hasta")
        limit = request.args.get("limit", 20, type=int)
        offset = request.args.get("offset", 0, type=int)

        facturas = repo.listar_facturas(
            estado=estado,
            cliente_id=cliente_id,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            limit=limit,
            offset=offset,
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

        return jsonify({"ok": True, "data": facturas, "has_more": len(facturas) == limit})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — DETALLE DE UNA FACTURA
# =============================================================

@bp_facturacion.route("/api/factura/<int:factura_id>", methods=["GET"])
@login_required
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
@login_required
def api_factura_pdf(factura_id):
    """
    Descarga el PDF de una factura.
    Si la factura ya fue validada por la DIAN (factus_estado == VALIDADA),
    se sirve el PDF OFICIAL de Factus (con CUFE/QR). En caso contrario
    (por ejemplo con Factus deshabilitado), se genera un PDF interno de
    respaldo claramente marcado como no válido ante la DIAN.
    """
    try:
        factura = repo.obtener_factura(factura_id)
        if not factura:
            return jsonify({"ok": False, "error": "Factura no encontrada"}), 404

        numero = factura.get("numero_factura", "factura")

        if factura.get("factus_estado") == "VALIDADA":
            try:
                pdf_bytes = factus_service.descargar_pdf(numero)
                return Response(
                    pdf_bytes,
                    mimetype="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=factura_{numero}.pdf"},
                )
            except FactusAPIError as e:
                return jsonify({
                    "ok": False,
                    "error": "No fue posible descargar el PDF oficial de Factus.",
                    "detalle": e.to_dict(),
                }), 502

        # Respaldo local (factura no validada ante la DIAN todavía)
        from services.factura_pdf_local import generar_factura_pdf_local

        detalle = repo.obtener_detalle_factura(factura_id)
        empresa = {
            "nombre": "IPS VITACORE S.A.S",
            "nit": "NIT: 000.000.000-0",
            "direccion": "",
            "telefono": "",
            "ciudad": "",
        }
        pdf_bytes = generar_factura_pdf_local(factura, detalle, empresa)

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"inline; filename=factura_{numero}_interna.pdf"}
        )

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/factura/<int:factura_id>/xml", methods=["GET"])
@login_required
def api_factura_xml(factura_id):
    """Descarga el XML oficial (UBL) de una factura ya validada por la DIAN."""
    try:
        factura = repo.obtener_factura(factura_id)
        if not factura:
            return jsonify({"ok": False, "error": "Factura no encontrada"}), 404
        if factura.get("factus_estado") != "VALIDADA":
            return jsonify({"ok": False, "error": "Esta factura aún no ha sido validada por la DIAN."}), 400

        numero = factura.get("numero_factura", "factura")
        xml_bytes = factus_service.descargar_xml(numero)
        return Response(
            xml_bytes,
            mimetype="application/xml",
            headers={"Content-Disposition": f"attachment; filename=factura_{numero}.xml"},
        )
    except FactusAPIError as e:
        return jsonify({"ok": False, "error": e.message, "detalle": e.errors}), e.status_code or 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — REENVIAR FACTURA POR CORREO
# =============================================================

@bp_facturacion.route("/api/factura/<int:factura_id>/email", methods=["POST"])
@login_required
@requiere_permiso("facturacion", "edit")
def api_reenviar_email_factura(factura_id):
    """
    Reenvía por correo una factura ya validada por la DIAN (2026-08-27).
    Factus la envía con el PDF/CUFE oficiales al correo del adquiriente
    (cliente o paciente, el que haya quedado en la factura), o al que se
    indique explícitamente en el body -- útil si el correo guardado tenía
    un error y se corrigió después de facturar.
    Body opcional: { email }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        email_override = (data.get("email") or "").strip() or None

        factura = repo.obtener_factura(factura_id)
        if not factura:
            return jsonify({"ok": False, "error": "Factura no encontrada"}), 404
        if factura.get("factus_estado") != "VALIDADA":
            return jsonify({"ok": False, "error": "Esta factura todavía no ha sido validada por la DIAN."}), 400

        # CORREGIDO (2026-08-27): Factus exige el campo "email" en el body
        # de /send-email -- no existe un "correo registrado" que use por
        # defecto si se omite. Si el usuario no escribió uno, se resuelve
        # aquí el correo del adquiriente que quedó guardado en la factura
        # (cliente o paciente, según adquiriente_tipo).
        email_destino = email_override
        if not email_destino:
            if factura.get("adquiriente_tipo") == "PACIENTE":
                paciente = fin_factus_repo.obtener_paciente_para_dian(factura.get("paciente_id"))
                email_destino = (paciente or {}).get("email")
            else:
                cliente = fin_factus_repo.obtener_cliente_para_dian(factura.get("cliente_id"))
                email_destino = (cliente or {}).get("email")

        if not email_destino:
            return jsonify({
                "ok": False,
                "error": "No se encontró un correo registrado para esta factura. Escribe uno manualmente.",
            }), 400

        numero = factura.get("numero_factura")
        try:
            respuesta = factus_service.reenviar_email_factura(numero, email_destino)
        except FactusAPIError as e:
            fin_factus_repo.registrar_evento(
                "FACTURA", factura_id, "REENVIAR_EMAIL",
                {"numero_factura": numero, "email": email_destino}, e.to_dict(), False,
            )
            return jsonify({"ok": False, "error": e.message, "detalle": e.errors}), e.status_code or 500

        fin_factus_repo.registrar_evento(
            "FACTURA", factura_id, "REENVIAR_EMAIL",
            {"numero_factura": numero, "email": email_destino}, respuesta, True,
        )
        return jsonify({"ok": True, "email": email_destino, "data": respuesta})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/factura/<int:factura_id>/anular", methods=["POST"])
@login_required
@requiere_permiso("facturacion", "delete")
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
@login_required
@requiere_permiso("facturacion", "create")
def api_crear_nota():
    """
    Body: { factura_id, tipo: 'CREDITO'|'DEBITO', motivo, concepto, valor,
            motivo_codigo (código DIAN de concepto de corrección, requerido
            para nota crédito electrónica) }
    Si la factura original fue validada por la DIAN (factus_estado ==
    VALIDADA), la nota se emite y valida electrónicamente ante Factus
    referenciando esa factura. Si no, se registra solo localmente.
    """
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

        factura = repo.obtener_factura(factura_id)
        if not factura:
            return jsonify({"ok": False, "error": "Factura no encontrada"}), 404

        # Generar número de nota interno (independiente del número DIAN)
        prefijo = "NC" if tipo == "CREDITO" else "ND"
        numero_nota = f"{prefijo}{int(_time.time())}"

        nota_data = {
            "empresa_id": 1,
            "factura_id": factura_id,
            "tipo": tipo,
            "numero_nota": numero_nota,
            "motivo": motivo,
            "concepto": data.get("concepto", ""),
            "valor": float(valor),
            "estado": "EMITIDA",
            "estado_dian": "NO_APLICA",
        }

        from flask import current_app
        if current_app.config.get("FACTUS_HABILITADO", True) and factura.get("factus_estado") == "VALIDADA":
            detalle = repo.obtener_detalle_factura(factura_id)
            codigos_cups = [d.get("codigo_cups") for d in detalle]
            cups_map = fin_factus_repo.obtener_cups_para_dian(codigos_cups)
            motivo_codigo = data.get("motivo_codigo", "1")  # (VERIFICAR tabla Factus de conceptos de corrección)

            # CORREGIDO (2026-08-27): Factus rechazó la primera prueba real de
            # nota crédito con "customer es obligatorio", "numbering_range_id
            # es obligatorio" y "payment_details es obligatorio" — la nota
            # crédito/débito exige el MISMO adquiriente y rango de numeración
            # que la factura original, no solo la referencia al número de
            # factura. Se reconstruyen aquí igual que al emitir la factura.
            adquiriente_tipo, customer_payload, err = _construir_adquiriente_o_error(
                factura.get("cliente_id"), factura.get("paciente_id")
            )
            if err:
                return jsonify(err), 409

            # CORREGIDO (2026-08-27): la primera prueba real mandó aquí el
            # numbering_range_id de la FACTURA (consecutivo.factus_numbering_range_id)
            # y Factus la rechazó con "El campo id rango de numeración es
            # inválido" -- una nota crédito/débito tiene su PROPIO rango de
            # numeración en Factus, distinto al de la factura de venta (así
            # como cada tipo de documento tiene su propia resolución DIAN).
            # Se busca en vivo en Factus el rango activo de tipo "Nota
            # Crédito"/"Nota Débito" en vez de reusar el de la factura.
            numbering_range_id, err_rango = _obtener_numbering_range_nota(tipo)
            if err_rango:
                return jsonify({"ok": False, "error": "configuracion_dian", "mensaje": err_rango}), 400

            try:
                payload = factus_mapper.construir_payload_nota_credito(
                    factura_dian_number=factura["numero_factura"],
                    motivo_codigo=motivo_codigo,
                    detalle=detalle,
                    valor_total=float(valor),
                    concepto=data.get("concepto", motivo),
                    numbering_range_id=numbering_range_id,
                    customer_payload=customer_payload,
                    cups_por_codigo=cups_map,
                )
                if tipo == "CREDITO":
                    respuesta = factus_service.crear_y_validar_nota_credito(payload)
                else:
                    respuesta = factus_service.crear_y_validar_nota_debito(payload)

                datos = respuesta.get("data") or respuesta
                doc = datos.get("bill") or datos
                nota_data.update({
                    "numero_nota_dian": doc.get("number") or "",
                    "cude": doc.get("cufe") or doc.get("cude") or "",
                    "estado_dian": "VALIDADA",
                    "factus_response": respuesta,
                })
                fin_factus_repo.registrar_evento(
                    "NOTA_" + tipo, factura_id, "CREAR_VALIDAR", payload, respuesta, True
                )
            except FactusAPIError as e:
                fin_factus_repo.registrar_evento(
                    "NOTA_" + tipo, factura_id, "CREAR_VALIDAR", payload, e.to_dict(), False
                )
                return jsonify({
                    "ok": False,
                    "error": "rechazo_dian",
                    "mensaje": e.message,
                    "detalle_dian": e.errors,
                }), 422

        nota = repo.crear_nota(nota_data)

        # Anulación vía nota crédito (2026-08-27): si la factura ya estaba
        # VALIDADA por la DIAN, no basta con marcarla "ANULADA" localmente
        # -- ese documento ya existe ante la DIAN y solo se puede reversar
        # con una nota crédito electrónica (lo que ya se hizo arriba). Si
        # Factus la rechazó, la función ya retornó antes de llegar aquí, así
        # que solo se marca ANULADA cuando la nota quedó bien puesta (o
        # cuando la factura nunca llegó a validarse ante la DIAN, caso en el
        # que no hay nada que reversar y basta con el estado local).
        factura_anulada = False
        if data.get("anular_factura") and tipo == "CREDITO":
            repo.anular_factura(factura_id, motivo)
            factura_anulada = True

        return jsonify({"ok": True, "data": nota, "factura_anulada": factura_anulada})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — CONSECUTIVOS
# =============================================================

@bp_facturacion.route("/api/consecutivos", methods=["GET"])
@login_required
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
@login_required
@requiere_permiso("facturacion_config", "create")
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
            "factus_numbering_range_id": data.get("factus_numbering_range_id"),
        })
        return jsonify({"ok": True, "data": consecutivo})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/consecutivos/<int:consecutivo_id>/factus", methods=["PATCH"])
@login_required
@requiere_permiso("facturacion_config", "edit")
def api_actualizar_consecutivo_factus(consecutivo_id):
    """
    Completa/actualiza el rango de numeración de Factus (y opcionalmente
    la resolución DIAN) de un consecutivo YA EXISTENTE — para sedes que
    venían facturando antes de esta integración y cuyo consecutivo local
    no se puede recrear sin perder el histórico.
    Body: { factus_numbering_range_id, resolucion_dian?, fecha_resolucion?,
            fecha_vencimiento? }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        campos = {}
        if data.get("factus_numbering_range_id") not in (None, ""):
            campos["factus_numbering_range_id"] = int(data["factus_numbering_range_id"])
        for campo in ("resolucion_dian", "fecha_resolucion", "fecha_vencimiento"):
            if data.get(campo) not in (None, ""):
                campos[campo] = data[campo]

        if not campos:
            return jsonify({"ok": False, "error": "No se recibió ningún campo para actualizar"}), 400

        resultado = repo.actualizar_consecutivo(consecutivo_id, campos)
        return jsonify({"ok": True, "data": resultado})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================
# API — RESUMEN / DASHBOARD
# =============================================================

@bp_facturacion.route("/api/resumen", methods=["GET"])
@login_required
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
@login_required
@requiere_permiso("facturacion", "create")
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
@login_required
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
@login_required
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
    

# =============================================================
# API — FACTURACIÓN CONSOLIDADA
# =============================================================

@bp_facturacion.route("/api/prefacturas-consolidables", methods=["GET"])
@login_required
def api_prefacturas_consolidables():
    """
    Lista prefacturas ABIERTA de contratos CONSOLIDADA para un cliente.
    Query params: cliente_id, contrato_id (opcional)
    """
    try:
        cliente_id = request.args.get("cliente_id", type=int)
        contrato_id = request.args.get("contrato_id", type=int)

        if not cliente_id:
            return jsonify({"ok": False, "error": "cliente_id es requerido"}), 400

        prefacturas = repo.listar_prefacturas_consolidables(cliente_id, contrato_id)

        # Aplanar joins para el frontend
        for pf in prefacturas:
            pac = pf.pop("hc_pacientes", None) or {}
            pf["paciente_nombre"] = f"{pac.get('primer_nombre','')} {pac.get('primer_apellido','')}".strip()
            pf["paciente_documento"] = pac.get("numero_documento", "")
            contrato = pf.get("hc_contratos", {}) or {}
            pf["nro_contrato"] = contrato.get("nro_contrato", "")

        return jsonify({
            "ok": True,
            "data": prefacturas,
            "total": sum(float(p.get("subtotal", 0)) for p in prefacturas),
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_facturacion.route("/api/facturar-consolidado", methods=["POST"])
@login_required
@requiere_permiso("facturacion", "create")
def api_facturar_consolidado():
    """
    Genera una factura consolidada desde múltiples prefacturas.
    Body: {
        cliente_id,
        prefactura_ids: [1, 2, 3, ...],
        periodo_inicio, periodo_fin,
        observaciones,
        sede_id  (opcional, para buscar consecutivo)
    }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}

        cliente_id    = data.get("cliente_id")
        prefactura_ids = data.get("prefactura_ids", [])

        if not cliente_id:
            return jsonify({"ok": False, "error": "cliente_id es requerido"}), 400
        if not prefactura_ids:
            return jsonify({"ok": False, "error": "Seleccione al menos una prefactura"}), 400

        # Validar caja abierta
        from repositories import fin_caja_repo as caja_repo
        user = session.get("user", {})
        caja = caja_repo.obtener_caja_abierta(user.get("id", ""))
        if not caja:
            return jsonify({"ok": False, "error": "Debe abrir una caja antes de facturar"}), 400

        # Obtener consecutivo
        sede_id = data.get("sede_id")
        consecutivo = repo.obtener_consecutivo_activo(sede_id=sede_id)
        if not consecutivo:
            return jsonify({"ok": False, "error": "No hay consecutivo de facturación activo"}), 400

        numero_factura, error = repo.incrementar_consecutivo(consecutivo["id"])
        if error:
            return jsonify({"ok": False, "error": error}), 400

        # Crear factura consolidada
        factura = repo.crear_factura_consolidada(
            prefactura_ids=prefactura_ids,
            consecutivo_id=consecutivo["id"],
            numero_factura=numero_factura,
            extra={
                "empresa_id":      1,
                "prefijo":         consecutivo["prefijo"],
                "descuento":       float(data.get("descuento", 0)),
                "observaciones":   data.get("observaciones", ""),
                "periodo_inicio":  data.get("periodo_inicio"),
                "periodo_fin":     data.get("periodo_fin"),
                "modalidad_pago":  data.get("modalidad_pago", "PAGO_POR_EVENTO"),
            }
        )

        # Sincronizar a cartera
        try:
            from repositories.fin_cartera_repo import sincronizar_factura_a_cartera
            factura_completa = repo.obtener_factura(factura["id"])
            if factura_completa:
                sincronizar_factura_a_cartera(factura_completa)
        except Exception as e_cartera:
            print(f"[WARN] Error sincronizando a cartera: {e_cartera}")

        # ── Emisión ante la DIAN (Factus) ──
        # Nota de diseño: a diferencia de /api/facturar (individual), aquí la
        # factura consolidada YA se creó y ya marcó las prefacturas/citas
        # como FACTURADA antes de intentar Factus, porque crear_factura_consolidada
        # hace todo eso en una sola operación difícil de diferir sin duplicar
        # lógica. Si Factus falla aquí, la factura queda con factus_estado de
        # error y se puede reintentar con /api/factura/<id>/reintentar-dian
        # sin perder el trabajo de consolidación ya hecho.
        factus_info = {"factus_estado": "NO_APLICA"}
        try:
            resultado_dian, error_http, status_code = _emitir_factura_ante_dian(
                reference_code=f"CONSOL-{factura['id']}",
                numbering_range_id=consecutivo.get("factus_numbering_range_id"),
                total=factura["total"],
                observaciones=data.get("observaciones", ""),
                items=repo.obtener_detalle_factura(factura["id"]),
                cliente_id=cliente_id,
                paciente_id=None,
            )
            if resultado_dian:
                factus_info = {
                    "numero_factura":  resultado_dian["numero_factura_dian"] or numero_factura,
                    "cufe":            resultado_dian["cufe"],
                    "qr_image":        resultado_dian["qr_image"],
                    "factus_estado":   "VALIDADA" if resultado_dian["is_validated"] else "PENDIENTE_DIAN",
                    "factus_response": resultado_dian["factus_response"],
                    "adquiriente_tipo": "CLIENTE",
                    "enviado_dian_at": "now()",
                }
                repo.registrar_resultado_factus(factura["id"], factus_info)
            elif error_http:
                repo.registrar_resultado_factus(factura["id"], {"factus_estado": "ERROR_DIAN"})
                factus_info = {"factus_estado": "ERROR_DIAN", "error_dian": error_http}
        except Exception as e_factus:
            print(f"[WARN] Error emitiendo factura consolidada ante Factus: {e_factus}")
            repo.registrar_resultado_factus(factura["id"], {"factus_estado": "ERROR_DIAN"})
            factus_info = {"factus_estado": "ERROR_DIAN"}

        return jsonify({
            "ok":             True,
            "factura_id":     factura["id"],
            "numero_factura": factus_info.get("numero_factura", numero_factura),
            "total":          factura["total"],
            "prefacturas_consolidadas": len(prefactura_ids),
            "cufe":           factus_info.get("cufe", ""),
            "qr_image":       factus_info.get("qr_image", ""),
            "factus_estado":  factus_info.get("factus_estado", "NO_APLICA"),
        })

    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    

@bp_facturacion.route("/api/prefacturas", methods=["GET"])
@login_required
def api_listar_prefacturas():
    try:
        estado = request.args.get("estado", "ABIERTA")
        prefacturas = repo.listar_prefacturas(estado=estado)

        for pf in prefacturas:
            con = pf.get("hc_contratos", {}) or {}
            pf["tipo_factura"] = con.get("tipo_factura", "INDIVIDUAL")

        return jsonify({"ok": True, "data": prefacturas})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500