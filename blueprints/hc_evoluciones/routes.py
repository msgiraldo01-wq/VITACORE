from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from repositories import hc_evoluciones_repo as repo
from repositories import hc_evolucion_medicamentos_repo as repo_meds
from repositories import hc_profesionales_repo as repo_prof
from repositories import hc_sedes_repo as repo_sedes
from repositories import rda_catalogos_repo as repo_rda_cat
from repositories import hc_especialidades_repo as repo_especialidades



bp_hc_evoluciones = Blueprint(
    "hc_evoluciones",
    __name__,
    url_prefix="/hc/evoluciones"
)


# =========================
# LISTAR EVOLUCIONES
# =========================

@bp_hc_evoluciones.route("/paciente/<int:paciente_id>")
def evoluciones_paciente(paciente_id):
    """Lista las evoluciones de un paciente"""
    
    # Obtener paciente con manejo de errores
    paciente = repo.obtener_paciente(paciente_id)
    if not paciente:
        flash("Paciente no encontrado", "error")
        return redirect(url_for("hc_pacientes.listar"))  # Ajusta esta ruta
    
    evoluciones = repo.listar_por_paciente(paciente_id)

    return render_template(
        "hc/evoluciones/evoluciones_list.html",
        evoluciones=evoluciones,
        paciente=paciente,
        paciente_id=paciente_id
    )


# =========================
# NUEVA EVOLUCION (WIZARD)
# =========================

@bp_hc_evoluciones.route("/nuevo/<int:paciente_id>")
def evolucion_nuevo(paciente_id):
    """Muestra el formulario wizard de nueva evolución"""
    
    # Obtener paciente con manejo de errores
    paciente = repo.obtener_paciente(paciente_id)
    if not paciente:
        flash("Paciente no encontrado", "error")
        return redirect(url_for("hc_pacientes.listar"))
    
    # Obtener lista de médicos
    medicos = repo.listar_medicos()
    sedes = repo_sedes.listar_select()
    especialidades = repo_especialidades.listar_select()

    return render_template(
        "hc/evoluciones/evoluciones_form.html",
        paciente=paciente,
        paciente_id=paciente_id,
        medicos=medicos,
        sedes=sedes,
        especialidades=especialidades,
        rda_causas_externas=repo_rda_cat.listar("causa_externa"),
        rda_tipos_diagnostico=repo_rda_cat.listar("tipo_diagnostico"),
        rda_entornos=repo_rda_cat.listar("entorno"),
    )

# =========================
# CREAR EVOLUCION
# =========================

# =========================
# CREAR EVOLUCION
# =========================

@bp_hc_evoluciones.route("/crear/<int:paciente_id>", methods=["POST"])
def evolucion_crear(paciente_id):

    # =========================
    # VALIDAR PACIENTE
    # =========================
    paciente = repo.obtener_paciente(paciente_id)
    if not paciente:
        flash("Paciente no encontrado", "error")
        return redirect(url_for("hc_pacientes.listar"))

    try:
        # =========================
        # DATOS PRINCIPALES
        # =========================
        data = {
            "paciente_id": paciente_id,
            "medico_id": request.form.get("medico_id"),
            "tipo_atencion": request.form.get("tipo_atencion", "CONSULTA_EXTERNA"),
            "sede_id": request.form.get("sede_id") or None,
            "servicio": request.form.get("servicio", "").strip() or None,

            "motivo_consulta": request.form.get("motivo_consulta", ""),
            "enfermedad_actual": request.form.get("enfermedad_actual", ""),
            "examen_fisico": request.form.get("examen_fisico", ""),
            "examen_sistemas": request.form.get("examen_sistemas", ""),

            "cie10_codigo": request.form.get("cie10_codigo"),
            "cie10_nombre": request.form.get("cie10_nombre", ""),

            "impresion_diagnostica": request.form.get("impresion_diagnostica", ""),
            "resultados_paraclinicos": request.form.get("resultados_paraclinicos", ""),

            "plan": request.form.get("plan", ""),
            "recomendaciones": request.form.get("recomendaciones", ""),
            "proximo_control_fecha": request.form.get("proximo_control_fecha"),
            "proximo_control_tipo": request.form.get("proximo_control_tipo", ""),
            "destino_paciente": request.form.get("destino_paciente", "").strip() or None,

            "causa_externa_codigo": request.form.get("causa_externa_codigo"),
            "tipo_diagnostico_codigo": request.form.get("tipo_diagnostico_codigo"),
            "entorno_codigo": request.form.get("entorno_codigo") or "05",
            "cups_id": request.form.get("cups_id") or None,

            "created_by": session.get("user", {}).get("id")
        }

        nueva_evolucion = repo.crear(data)

        if not nueva_evolucion:
            raise Exception("No se pudo crear la evolución")

        evolucion_id = nueva_evolucion.get("id")

        # =========================
        # CONEXIÓN SUPABASE
        # =========================
        from services.supabase_service import get_supabase_admin
        sb = get_supabase_admin()

        # =========================
        # 🔥 GUARDAR SIGNOS
        # =========================
        sb.table("hc_evolucion_signos").insert({
            "evolucion_id": evolucion_id,

            "ta": request.form.get("ta") or None,
            "fc": request.form.get("fc") or None,
            "fr": request.form.get("fr") or None,

            "temperatura": request.form.get("temperatura") or None,
            "peso": request.form.get("peso") or None,
            "talla": request.form.get("talla") or None,
            "imc": request.form.get("imc") or None,

            "saturacion_oxigeno": request.form.get("spo2") or None,
        }).execute()

        # =========================
        # 🔥 GUARDAR ALERTAS
        # =========================
        sb.table("hc_evolucion_alertas").insert({
            "evolucion_id": evolucion_id,
            "antecedentes": request.form.get("antecedentes") or None,
            "alergias": request.form.get("alergias") or None,
        }).execute()

        # =========================
        # 🔥 MEDICAMENTOS
        # =========================
        med_nombres = request.form.getlist("med_nombre[]")
        med_dosis = request.form.getlist("med_dosis[]")
        med_freq = request.form.getlist("med_frecuencia[]")
        med_duracion = request.form.getlist("med_duracion[]")
        med_via = request.form.getlist("med_via[]")

        for i in range(len(med_nombres)):
            if not med_nombres[i]:
                continue

            repo_meds.crear({
                "evolucion_id": evolucion_id,
                "medicamento_nombre": med_nombres[i],
                "dosis": med_dosis[i],
                "frecuencia": med_freq[i],
                "duracion": med_duracion[i],
                "via_administracion": med_via[i],
            })

        flash("Evolución registrada correctamente", "success")

        # =========================================================
        # 🏛️ TRANSMITIR RDA AL MINISTERIO (Resolución 1888)
        # ---------------------------------------------------------
        # Se lanza EN SEGUNDO PLANO: el médico no espera. La evolución
        # ya está guardada; el RDA viaja aparte y su resultado queda
        # registrado en rda_envios, visible en el panel /rda/.
        # Un fallo del RDA nunca afecta la atención clínica.
        # =========================================================
        try:
            from blueprints.rda import rda_service

            empresa_id = session.get("empresa_id")
            if empresa_id:
                rda_service.transmitir_en_segundo_plano(evolucion_id, empresa_id)
                flash("El RDA se está transmitiendo al Ministerio (ver panel de RDA).", "info")
            else:
                print("[RDA] Sin empresa activa en sesión; no se transmite.")

        except Exception as rda_err:
            # Nunca propagar: la evolución ya está guardada.
            print("[RDA] No se pudo lanzar la transmisión:", rda_err)

        return redirect(
            url_for("hc_evoluciones.evoluciones_paciente", paciente_id=paciente_id)
        )

    except Exception as e:
        flash(f"Error al guardar la evolución: {str(e)}", "error")
        print("ERROR creando evolución:", e)
        return redirect(request.referrer)
# =========================
# BUSCADOR CIE10
# =========================

@bp_hc_evoluciones.route("/cie10/buscar")
def cie10_buscar():
    """API para buscar códigos CIE10"""
    q = request.args.get("q", "")
    items = repo.listar_cie10(q)
    return jsonify(items)


# =========================
# BUSCADOR MEDICAMENTOS
# =========================

@bp_hc_evoluciones.route("/medicamentos/buscar")
def medicamentos_buscar():
    """API para buscar medicamentos"""
    q = request.args.get("q", "")
    
    if len(q) < 2:
        return jsonify([])
    
    try:
        # Ajusta según tu tabla de medicamentos
        from services.supabase_service import get_supabase_admin
        sb = get_supabase_admin()
        
        r = (
            sb.table("hc_medicamentos")
            .select("id, principio_activo, concentracion, forma_farmaceutica")
            .ilike("principio_activo", f"%{q}%")
            .limit(20)
            .execute()
        )
        
        return jsonify(r.data or [])
        
    except Exception as e:
        print(f"Error buscando medicamentos: {e}")
        return jsonify([])


# =========================
# VER EVOLUCION DETALLE
# =========================

@bp_hc_evoluciones.route("/ver/<int:evolucion_id>")
def evolucion_ver(evolucion_id):
    """Muestra el detalle de una evolución"""
    
    evolucion = repo.obtener(evolucion_id)
    if not evolucion:
        return "Evolución no encontrada", 404

    paciente = repo.obtener_paciente(evolucion.get("paciente_id"))
    if not paciente:
        return "Paciente no encontrado", 404
    
    medicamentos = repo_meds.listar_por_evolucion(evolucion_id)
    medico = repo_prof.obtener(evolucion.get("medico_id"))

    return render_template(
        "hc/evoluciones/evolucion_detalle.html",
        evolucion=evolucion,
        paciente=paciente,
        medicamentos=medicamentos,
        medico=medico
    )


# =========================
# FORMULA MEDICA HTML
# =========================

@bp_hc_evoluciones.route("/formula/<int:evolucion_id>")
def formula_medica(evolucion_id):
    """Muestra la fórmula médica en HTML"""
    
    evolucion = repo.obtener(evolucion_id)
    if not evolucion:
        return "No encontrada", 404

    paciente = repo.obtener_paciente(evolucion.get("paciente_id"))
    if not paciente:
        return "Paciente no encontrado", 404
    
    medicamentos = repo_meds.listar_por_evolucion(evolucion_id)
    medico = repo_prof.obtener(evolucion.get("medico_id"))

    return render_template(
        "hc/evoluciones/formula_medica.html",
        evolucion=evolucion,
        paciente=paciente,
        medicamentos=medicamentos,
        medico=medico
    )


# =========================
# FORMULA PDF
# =========================

@bp_hc_evoluciones.route("/formula_pdf/<int:evolucion_id>")
def formula_pdf(evolucion_id):
    """Muestra el reporte completo de historia clínica (versión para imprimir/PDF)"""
    
    evolucion = repo.obtener(evolucion_id)
    if not evolucion:
        return "Evolución no encontrada", 404

    paciente = repo.obtener_paciente(evolucion.get("paciente_id"))
    if not paciente:
        return "Paciente no encontrado", 404
    
    medicamentos = repo_meds.listar_por_evolucion(evolucion_id)
    medico = repo_prof.obtener(evolucion.get("medico_id"))

    return render_template(
        "hc/evoluciones/evolucion_medica_reporte.html",
        evolucion=evolucion,
        paciente=paciente,
        medicamentos=medicamentos,
        medico=medico
    )