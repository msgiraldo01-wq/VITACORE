# blueprints/citas/routes.py

from flask import Blueprint, jsonify, request, render_template, session, send_file
from repositories import hc_citas_repo as repo
from datetime import datetime, timedelta
from services.pdf_service import PDFService, AssetHelper
import os
import io   


bp_citas = Blueprint("citas", __name__, url_prefix="/citas")


# --------------------------------------------------
# VISTAS
# --------------------------------------------------

@bp_citas.route("/")
def agenda():
    return render_template("citas/agenda.html")

@bp_citas.route("/nueva")
def nueva_cita():
    return render_template("citas/nueva.html")


@bp_citas.route("/test")
def test_citas():
    try:
        data = repo.listar_por_fecha("2026-04-29")
        return jsonify({"ok": True, "total": len(data), "data": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API: AGENDA
# --------------------------------------------------

@bp_citas.route("/api/agenda")
def api_agenda():
    try:
        fecha = request.args.get("fecha")
        medico_id = request.args.get("medico_id", type=int)
        sede_id = request.args.get("sede_id", type=int)

        if not fecha:
            return {"ok": False, "error": "Fecha requerida"}, 400

        data = repo.listar_por_fecha(fecha=fecha, medico_id=medico_id, sede_id=sede_id)

        return {"ok": True, "total": len(data), "data": data}

    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# API: CREAR CITA
# --------------------------------------------------

@bp_citas.route("/api/crear", methods=["POST"])
def api_crear_cita():
    try:
        data = request.json or {}
 
        # -----------------------------
        # EXTRAER PROCEDIMIENTOS ANTES
        # (no forman parte del payload de hc_citas)
        # -----------------------------
        procedimientos = data.pop("procedimientos", [])
 
        # -----------------------------
        # VALIDACIÓN EMPRESA
        # -----------------------------
        empresa = session.get("empresa_id") or data.get("empresa_id")
 
        if empresa is None:
            return {"ok": False, "error": "empresa_id es obligatorio"}, 400
 
        try:
            empresa = int(empresa)
        except:
            return {"ok": False, "error": "empresa_id inválido"}, 400
 
        data["empresa_id"] = empresa
 
        # -----------------------------
        # CAMPOS OBLIGATORIOS
        # -----------------------------
        campos_requeridos = [
            "paciente_id", "medico_id", "fecha", "hora_inicio",
            "tipo_atencion", "modalidad", "finalidad_consulta", "motivo_consulta"
        ]
 
        for campo in campos_requeridos:
            if not data.get(campo):
                return {"ok": False, "error": f"Campo obligatorio: {campo}"}, 400
 
        # -----------------------------
        # TIPOS NUMÉRICOS
        # -----------------------------
        try:
            data["paciente_id"] = int(data["paciente_id"])
            data["medico_id"]   = int(data["medico_id"])
        except:
            return {"ok": False, "error": "paciente_id o medico_id inválidos"}, 400
 
        # -----------------------------
        # LIMPIEZA DE CAMPOS OPCIONALES
        # -----------------------------
        for campo in ["sede_id", "consultorio_id", "eps_id"]:
            valor = data.get(campo)
            if valor in (None, "", "None", "null"):
                data[campo] = None
            else:
                try:
                    data[campo] = int(valor)
                except:
                    data[campo] = None
 
        # -----------------------------
        # VALIDAR FORMATO HORA
        # -----------------------------
        try:
            hora_inicio = datetime.strptime(data["hora_inicio"], "%H:%M")
        except:
            return {"ok": False, "error": "Formato de hora inválido (HH:MM)"}, 400
 
        # -----------------------------
        # DURACIÓN
        # La duración viene del frontend (suma de procedimientos o ajuste manual).
        # Se respeta tal como llega — el usuario puede haberla modificado.
        # -----------------------------
        try:
            duracion = int(data.get("duracion", 20))
        except:
            return {"ok": False, "error": "duracion inválida"}, 400
 
        # -----------------------------
        # CALCULAR HORA FIN
        # -----------------------------
        hora_fin         = hora_inicio + timedelta(minutes=duracion)
        data["hora_fin"] = hora_fin.time().isoformat()
 
        # -----------------------------
        # VALIDAR CRUCES
        # -----------------------------
        citas = repo.listar_por_fecha(
            data["fecha"],
            medico_id=data["medico_id"],
            empresa_id=data["empresa_id"]
        )
 
        for c in citas:
            if c.get("estado") == "CANCELADA":
                continue
 
            try:
                inicio_existente = datetime.strptime(c["hora_inicio"][:5], "%H:%M")
                fin_existente    = datetime.strptime(
                    (c.get("hora_fin") or c["hora_inicio"])[:5], "%H:%M"
                )
            except:
                continue
 
            if hora_inicio < fin_existente and hora_fin > inicio_existente:
                if not data.get("es_adicional"):
                    return {
                        "ok": False,
                        "error": "El médico ya tiene una cita en ese horario"
                    }, 400
 
        # -----------------------------
        # CREAR CITA
        # -----------------------------
        cita = repo.crear(data)
 
        if not cita:
            return {"ok": False, "error": "No se pudo crear la cita"}, 500
 
        # -----------------------------
        # GUARDAR PROCEDIMIENTOS
        # Solo se insertan si vienen en el payload.
        # -----------------------------
        if procedimientos:
            from repositories import hc_cita_procedimientos_repo
            hc_cita_procedimientos_repo.crear_bulk(cita["id"], procedimientos)
 
        return {"ok": True, "data": cita}
 
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# API: CAMBIAR ESTADO
# --------------------------------------------------

@bp_citas.route("/api/estado", methods=["POST"])
def api_estado():
    try:
        data = request.get_json(force=True, silent=True) or {}

        cita_id = data.get("cita_id")
        estado = data.get("estado")

        if not cita_id or not estado:
            return {"ok": False, "error": "cita_id y estado son requeridos"}, 400

        # Validar estado permitido
        estados_validos = {"PENDIENTE", "CONFIRMADA", "EN_ATENCION", "FINALIZADA", "CANCELADA", "FACTURADA"}
        if estado not in estados_validos:
            return {"ok": False, "error": f"Estado inválido. Use: {', '.join(estados_validos)}"}, 400

        repo.cambiar_estado(cita_id, estado)

        return {"ok": True, "msg": f"Estado actualizado a {estado}"}

    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# API: ACTUALIZAR CITA
# --------------------------------------------------

@bp_citas.route("/api/actualizar/<int:cita_id>", methods=["PUT"])
def api_actualizar_cita(cita_id):
    try:
        data = request.get_json(force=True, silent=True) or {}

        if not data:
            return {"ok": False, "error": "No hay datos para actualizar"}, 400

        # No permitir cambiar empresa_id ni id
        data.pop("empresa_id", None)
        data.pop("id", None)

        resultado = repo.actualizar(cita_id, data)

        return {"ok": True, "data": resultado}

    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --------------------------------------------------
# API: ELIMINAR CITA (soft delete vía estado)
# --------------------------------------------------

@bp_citas.route("/api/cancelar/<int:cita_id>", methods=["POST"])
def api_cancelar_cita(cita_id):
    try:
        repo.cambiar_estado(cita_id, "CANCELADA")
        return {"ok": True, "msg": "Cita cancelada"}

    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
    
# blueprints/citas/routes.py  (agregar al final)

@bp_citas.route("/api/pacientes")
def api_pacientes():
    try:
        from repositories import hc_pacientes_repo as pac_repo
        
        q = request.args.get("q", "")
        limite = request.args.get("limite", 15, type=int)
        
        # Si hay búsqueda, usar buscar. Si no, listar
        if q:
            data = pac_repo.buscar(q=q, limite=limite)
        else:
            data = pac_repo.listar(completo=False)
            
        return {"ok": True, "data": data}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
    
# blueprints/citas/routes.py  (agregar al final)

@bp_citas.route("/api/medicos")
def api_medicos():
    try:
        from repositories import hc_profesionales_repo as med_repo
        
        data = med_repo.listar()
        return {"ok": True, "data": data}
        
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
    
@bp_citas.route("/api/sedes")
def api_sedes():
    try:
        from repositories import hc_sedes_repo as sede_repo

        data = sede_repo.listar()
        return {"ok": True, "data": data}
    
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500
    

# ------------------------------------------------------------------
# GET /citas/api/medico/<medico_id>/procedimientos
# Devuelve los CUPS asignados al médico (para poblar el buscador)
# ------------------------------------------------------------------
@bp_citas.route("/api/medico/<int:medico_id>/procedimientos", methods=["GET"])
def api_procedimientos_medico(medico_id):
    try:
        from repositories import prof_procedimientos_repository as prof_cups
 
        data = prof_cups.listar_por_profesional(medico_id)
 
        resultado = []
        for row in data:
            cups = row.get("hc_cups") or {}
            resultado.append({
                "id":          row["id"],
                "cups_id":     row["cups_id"],
                "codigo":      cups.get("codigo", ""),
                "descripcion": cups.get("descripcion", ""),
                "duracion_min": row.get("duracion_min", 20),
            })
 
        return jsonify({"ok": True, "data": resultado})
 
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
 



@bp_citas.route("/api/detalle/<int:cita_id>", methods=["GET"])
def api_detalle_cita(cita_id):
    try:
        detalle = repo.obtener_detalle(cita_id)
 
        if not detalle:
            return jsonify({"ok": False, "error": "Cita no encontrada"}), 404
 
        return jsonify({"ok": True, "data": detalle})
 
    except Exception as e:
        import traceback
        print("ERROR /api/detalle:", traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500
    


def fmt_fecha(f):
    if not f:
        return "—"
    DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    try:
        d = datetime.strptime(f, "%Y-%m-%d")
        return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"
    except Exception:
        return str(f)


def fmt_hora(h):
    if not h:
        return "—"
    try:
        t = datetime.strptime(str(h)[:5], "%H:%M")
        hora = t.hour % 12 or 12
        ampm = "AM" if t.hour < 12 else "PM"
        return f"{hora}:{t.strftime('%M')} {ampm}"
    except Exception:
        return str(h)[:5]


def _obtener_datos_cita(cita_id: int) -> dict:
    """Centraliza obtención de datos para cita (DRY)."""
    datos = repo.obtener_datos_pdf(cita_id)
    if not datos:
        raise ValueError("Cita no encontrada")
    
    # Logo como base64 (elimina dependencia de filesystem en producción)
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    logo_path = os.path.join(base_dir, "static", "img", "vitacore", "logo_vitacore.png")
    
    return {
        **datos,
        "logo_b64": AssetHelper.img_to_base64(logo_path),
        "fecha_larga": fmt_fecha(datos.get("fecha")),
        "hora_inicio": fmt_hora(datos.get("hora_inicio")),
        "hora_fin": fmt_hora(datos.get("hora_fin")),
    }


# ============================================
# ENDPOINTS
# ============================================

@bp_citas.route("/api/detalle/<int:cita_id>/html", methods=["GET"])
def api_html_cita(cita_id):
    """
    Devuelve HTML para previsualización en navegador.
    El médico/admin ve esto y decide si imprimir o descargar PDF.
    """
    try:
        ctx = _obtener_datos_cita(cita_id)
        return render_template("citas/pdf_cita.html", **ctx)
    
    except ValueError:
        return jsonify({"ok": False, "error": "Cita no encontrada"}), 404
    except Exception as e:
        import traceback
        print("ERROR /html:", traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500


@bp_citas.route("/api/detalle/<int:cita_id>/pdf", methods=["GET"])
def api_pdf_cita(cita_id):
    """
    Genera PDF profesional vía Playwright (Chromium headless).
    MISMO template que /html, pero renderizado a PDF.
    """
    try:
        ctx = _obtener_datos_cita(cita_id)
        
        # Renderizar MISMO template
        html_str = render_template("citas/pdf_cita.html", **ctx)
        
        # Generar PDF con Playwright
        pdf_bytes = PDFService.sync_html_to_pdf(
            html_content=html_str,
            wait_for_network=False  # todo es inline/base64, no esperamos red
        )
        
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=False,           # True si quieres forzar descarga
            download_name=f"cita_{cita_id}_{ctx.get('paciente_doc', 'paciente')}.pdf"
        )

    except ValueError:
        return jsonify({"ok": False, "error": "Cita no encontrada"}), 404
    except Exception as e:
        import traceback
        print("ERROR /pdf:", traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500



# --------------------------------------------------
# API: CLIENTES (para cascada en modal de cita)     
# --------------------------------------------------

@bp_citas.route("/api/clientes")
def api_clientes():
    """Lista todos los clientes activos para el select del modal."""
    try:
        from repositories import hc_clientes_repo as cli_repo

        data = cli_repo.listar()
        # Filtrar solo activos
        activos = [c for c in data if c.get("estado") == "ACTIVO"]
        return jsonify({"ok": True, "data": activos})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API: CONTRATOS POR CLIENTE
# --------------------------------------------------

@bp_citas.route("/api/cliente/<int:cliente_id>/contratos")
def api_contratos_cliente(cliente_id):
    """Lista los contratos activos de un cliente específico."""
    try:
        from repositories import hc_contratos_repo as cont_repo

        todos = cont_repo.listar_por_cliente(cliente_id)
        # Filtrar solo activos
        activos = [c for c in todos if c.get("estado") == "ACTIVO"]
        return jsonify({"ok": True, "data": activos})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API: TARIFAS DEL MANUAL TARIFARIO (por contrato)
# --------------------------------------------------

@bp_citas.route("/api/contrato/<int:contrato_id>/tarifas")
def api_tarifas_contrato(contrato_id):
    """
    Dado un contrato, busca su manual_tarifario (por nombre)
    y devuelve los procedimientos con tarifas de ese manual.
    El valor_total depende del tipo_contrato:
      - PAQUETE → valor_paquete
      - EVENTO  → valor_procedimiento + valor_suministro
    """
    try:
        from repositories import hc_contratos_repo as cont_repo
        from repositories import hc_manuales_repo as man_repo
 
        # 1. Obtener el contrato
        contrato = cont_repo.obtener(contrato_id)
        if not contrato:
            return jsonify({"ok": False, "error": "Contrato no encontrado"}), 404
 
        nombre_manual = (contrato.get("manual_tarifario") or "").strip()
        tipo_contrato = (contrato.get("tipo_contrato") or "EVENTO").upper()
 
        if not nombre_manual:
            return jsonify({
                "ok": True,
                "data": [],
                "msg": "El contrato no tiene manual tarifario asignado"
            })
 
        # 2. Buscar el manual por nombre
        from services.supabase_service import get_supabase_public
        sb = get_supabase_public()
 
        res_manual = (
            sb.table("hc_manuales_tarifarios")
            .select("id, nombre, codigo")
            .eq("nombre", nombre_manual)
            .limit(1)
            .execute()
        )
 
        if not res_manual.data:
            return jsonify({
                "ok": True,
                "data": [],
                "msg": f"No se encontró el manual '{nombre_manual}'"
            })
 
        manual = res_manual.data[0]
        manual_id = manual["id"]
 
        # 3. Traer procedimientos del manual con tarifas
        procedimientos = man_repo.listar_procedimientos(manual_id)
 
        # 4. Formatear para el frontend
        resultado = []
        for p in procedimientos:
            vp  = float(p.get("valor_paquete") or 0)
            vpr = float(p.get("valor_procedimiento") or 0)
            vs  = float(p.get("valor_suministro") or 0)
 
            # Lógica según tipo de contrato
            if tipo_contrato == "PAQUETE":
                valor_total = vp
            else:
                valor_total = vpr + vs
 
            resultado.append({
                "id":                   p["id"],
                "manual_id":            manual_id,
                "manual_nombre":        manual["nombre"],
                "cod_proc":             p.get("cod_proc", ""),
                "nombre_procedimiento": p.get("nombre_procedimiento", ""),
                "cups_codigo":          p.get("cups_codigo", ""),
                "cups_descripcion":     p.get("cups_descripcion", ""),
                "tipo_contrato":        tipo_contrato,
                "valor_paquete":        vp,
                "valor_procedimiento":  vpr,
                "valor_suministro":     vs,
                "valor_total":          valor_total,
            })
 
        return jsonify({
            "ok": True,
            "tipo_contrato": tipo_contrato,
            "manual": {
                "id": manual_id,
                "nombre": manual["nombre"],
                "codigo": manual.get("codigo", ""),
            },
            "data": resultado,
        })
 
    except Exception as e:
        import traceback
        print("ERROR /api/contrato/tarifas:", traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500


# --------------------------------------------------
# API: BUSCAR TARIFA DE UN CUPS ESPECÍFICO EN UN CONTRATO
# --------------------------------------------------

@bp_citas.route("/api/contrato/<int:contrato_id>/tarifa-cups/<int:cups_id>")
def api_tarifa_cups(contrato_id, cups_id):
    """
    Busca la tarifa de un CUPS específico en el manual del contrato.
    El valor_total depende del tipo_contrato:
      - PAQUETE → valor_paquete
      - EVENTO  → valor_procedimiento + valor_suministro
    """
    try:
        from repositories import hc_contratos_repo as cont_repo
        from services.supabase_service import get_supabase_public
 
        sb = get_supabase_public()
 
        # 1. Obtener contrato y su manual
        contrato = cont_repo.obtener(contrato_id)
        if not contrato:
            return jsonify({"ok": False, "error": "Contrato no encontrado"}), 404
 
        nombre_manual = (contrato.get("manual_tarifario") or "").strip()
        tipo_contrato = (contrato.get("tipo_contrato") or "EVENTO").upper()
 
        if not nombre_manual:
            return jsonify({"ok": True, "data": None, "msg": "Sin manual tarifario"})
 
        # 2. Buscar manual por nombre
        res_manual = (
            sb.table("hc_manuales_tarifarios")
            .select("id")
            .eq("nombre", nombre_manual)
            .limit(1)
            .execute()
        )
 
        if not res_manual.data:
            return jsonify({"ok": True, "data": None, "msg": f"Manual '{nombre_manual}' no encontrado"})
 
        manual_id = res_manual.data[0]["id"]
 
        # 3. Buscar el procedimiento en el manual por cups_id
        res_proc = (
            sb.table("hc_mt_procedimientos")
            .select("*")
            .eq("manual_id", manual_id)
            .eq("cups_id", cups_id)
            .limit(1)
            .execute()
        )
 
        if not res_proc.data:
            return jsonify({
                "ok": True,
                "data": None,
                "msg": "Procedimiento no encontrado en el manual tarifario"
            })
 
        p   = res_proc.data[0]
        vp  = float(p.get("valor_paquete") or 0)
        vpr = float(p.get("valor_procedimiento") or 0)
        vs  = float(p.get("valor_suministro") or 0)
 
        # Lógica según tipo de contrato
        if tipo_contrato == "PAQUETE":
            valor_total = vp
        else:
            valor_total = vpr + vs
 
        return jsonify({
            "ok": True,
            "data": {
                "tipo_contrato":       tipo_contrato,
                "valor_paquete":       vp,
                "valor_procedimiento": vpr,
                "valor_suministro":    vs,
                "valor_total":         valor_total,
            }
        })
 
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
