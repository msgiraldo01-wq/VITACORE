# blueprints/citas/routes.py

from flask import Blueprint, jsonify, request, render_template, session
from repositories import hc_citas_repo as repo
from datetime import datetime, timedelta


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
        # VALIDACIÓN EMPRESA
        # -----------------------------
        empresa = session.get("empresa_id") or data.get("empresa_id")

        if empresa is None:
            return {
                "ok": False,
                "error": "empresa_id es obligatorio"
            }, 400

        try:
            empresa = int(empresa)
        except:
            return {
                "ok": False,
                "error": "empresa_id inválido"
            }, 400

        data["empresa_id"] = empresa

        # -----------------------------
        # CAMPOS OBLIGATORIOS
        # -----------------------------
        campos_requeridos = [
            "paciente_id",
            "medico_id",
            "fecha",
            "hora_inicio",
            "tipo_atencion",
            "modalidad",
            "finalidad_consulta",
            "motivo_consulta"
        ]

        for campo in campos_requeridos:
            if not data.get(campo):
                return {
                    "ok": False,
                    "error": f"Campo obligatorio: {campo}"
                }, 400

        # -----------------------------
        # TIPOS NUMÉRICOS
        # -----------------------------
        try:
            data["paciente_id"] = int(data["paciente_id"])
            data["medico_id"] = int(data["medico_id"])
        except:
            return {
                "ok": False,
                "error": "paciente_id o medico_id inválidos"
            }, 400

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
            return {
                "ok": False,
                "error": "Formato de hora inválido (HH:MM)"
            }, 400

        # -----------------------------
        # DURACIÓN
        # -----------------------------
        try:
            duracion = int(data.get("duracion", 20))
        except:
            return {
                "ok": False,
                "error": "duracion inválida"
            }, 400

        # -----------------------------
        # CALCULAR HORA FIN
        # -----------------------------
        hora_fin = hora_inicio + timedelta(minutes=duracion)
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
                inicio_existente = datetime.strptime(
                    c["hora_inicio"][:5], "%H:%M"
                )

                fin_existente = datetime.strptime(
                    (c.get("hora_fin") or c["hora_inicio"])[:5],
                    "%H:%M"
                )
            except:
                continue

            if hora_inicio < fin_existente and hora_fin > inicio_existente:
                return {
                    "ok": False,
                    "error": "El médico ya tiene una cita en ese horario"
                }, 400

        # -----------------------------
        # CREAR
        # -----------------------------
        cita = repo.crear(data)

        return {
            "ok": True,
            "data": cita
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }, 500

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
        estados_validos = {"PENDIENTE", "CONFIRMADA", "EN_ATENCION", "FINALIZADA", "CANCELADA"}
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