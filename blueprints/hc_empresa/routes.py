from flask import Blueprint, render_template, request, redirect, session, jsonify
from services.supabase_service import get_supabase_admin

bp_hc_empresa = Blueprint(
    "bp_hc_empresa",
    __name__,
    url_prefix="/empresa"
)

def es_super_admin():
    return session.get("rol") == "SUPER_ADMIN"

def es_ajax():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


@bp_hc_empresa.route("/seleccionar")
def seleccionar_empresa():
    if not es_super_admin():
        return redirect("/hc")

    sb = get_supabase_admin()

    empresas = sb.table("hc_empresas") \
        .select("""
            id,
            nit,
            nombre_comercial,
            razon_social,
            tipo_empresa,
            nivel_complejidad,
            pais,
            departamento,
            municipio,
            direccion,
            telefono,
            email,
            codigo_habilitacion,
            numero_resolucion,
            logo_url,
            color_primario,
            color_secundario,
            estado
        """) \
        .order("razon_social") \
        .execute().data

    return render_template("hc/empresa/seleccionar.html", empresas=empresas)


@bp_hc_empresa.route("/entrar/<int:empresa_id>")
def entrar_empresa(empresa_id):
    if not es_super_admin():
        return redirect("/hc")

    session["empresa_id"] = empresa_id
    return redirect("/")


@bp_hc_empresa.route("/crear", methods=["GET", "POST"])
def crear_empresa():
    if not es_super_admin():
        return redirect("/hc")

    if request.method == "POST":
        data = request.form
        sb = get_supabase_admin()

        nit = (data.get("nit") or "").strip()
        razon_social = (data.get("razon_social") or "").strip()
        tipo_empresa = (data.get("tipo_empresa") or "").strip()

        if not nit or not razon_social or not tipo_empresa:
            mensaje = "NIT, tipo de empresa y razón social son obligatorios."
            if es_ajax():
                return jsonify({"ok": False, "message": mensaje}), 400
            return render_template("hc/empresa/crear.html", error=mensaje), 400

        empresa = {
            "nit": nit,
            "razon_social": razon_social,
            "nombre_comercial": (data.get("nombre_comercial") or "").strip() or None,
            "tipo_empresa": tipo_empresa,
            "nivel_complejidad": (data.get("nivel_complejidad") or "").strip() or None,
            "pais": (data.get("pais") or "").strip() or None,
            "departamento": (data.get("departamento") or "").strip() or None,
            "municipio": (data.get("municipio") or "").strip() or None,
            "direccion": (data.get("direccion") or "").strip() or None,
            "telefono": (data.get("telefono") or "").strip() or None,
            "email": (data.get("email") or "").strip() or None,
            "codigo_habilitacion": (data.get("codigo_habilitacion") or "").strip() or None,
            "numero_resolucion": (data.get("numero_resolucion") or "").strip() or None,
            "logo_url": (data.get("logo_url") or "").strip() or None,
            "color_primario": (data.get("color_primario") or "").strip() or None,
            "color_secundario": (data.get("color_secundario") or "").strip() or None,
            "estado": (data.get("estado") or "ACTIVA").strip() or "ACTIVA",
        }

        try:
            res = sb.table("hc_empresas").insert(empresa).execute()
            empresa_id = res.data[0]["id"]
            session["empresa_id"] = empresa_id

            if es_ajax():
                return jsonify({
                    "ok": True,
                    "message": "Empresa creada correctamente.",
                    "redirect": "/empresa/seleccionar"
                })

            return redirect("/empresa/seleccionar")

        except Exception as exc:
            mensaje = str(exc)
            if "duplicate" in mensaje.lower() or "unique" in mensaje.lower():
                mensaje = "Ya existe una empresa registrada con ese NIT."

            if es_ajax():
                return jsonify({"ok": False, "message": mensaje}), 400

            return render_template("hc/empresa/crear.html", error=mensaje), 400

    return render_template("hc/empresa/crear.html")


@bp_hc_empresa.route("/editar/<int:empresa_id>", methods=["GET", "POST"])
def editar_empresa(empresa_id):
    if not es_super_admin():
        return redirect("/hc")

    sb = get_supabase_admin()

    empresa = sb.table("hc_empresas") \
        .select("*") \
        .eq("id", empresa_id) \
        .limit(1) \
        .execute().data

    if not empresa:
        if es_ajax():
            return jsonify({"ok": False, "message": "Empresa no encontrada."}), 404
        return redirect("/empresa/seleccionar")

    empresa = empresa[0]

    if request.method == "POST":
        data = request.form

        nit = (data.get("nit") or "").strip()
        razon_social = (data.get("razon_social") or "").strip()
        tipo_empresa = (data.get("tipo_empresa") or "").strip()

        if not nit or not razon_social or not tipo_empresa:
            mensaje = "NIT, tipo de empresa y razón social son obligatorios."
            if es_ajax():
                return jsonify({"ok": False, "message": mensaje}), 400
            return render_template("hc/empresa/editar.html", empresa=empresa, error=mensaje), 400

        payload = {
            "nit": nit,
            "razon_social": razon_social,
            "nombre_comercial": (data.get("nombre_comercial") or "").strip() or None,
            "tipo_empresa": tipo_empresa,
            "nivel_complejidad": (data.get("nivel_complejidad") or "").strip() or None,
            "pais": (data.get("pais") or "").strip() or None,
            "departamento": (data.get("departamento") or "").strip() or None,
            "municipio": (data.get("municipio") or "").strip() or None,
            "direccion": (data.get("direccion") or "").strip() or None,
            "telefono": (data.get("telefono") or "").strip() or None,
            "email": (data.get("email") or "").strip() or None,
            "codigo_habilitacion": (data.get("codigo_habilitacion") or "").strip() or None,
            "numero_resolucion": (data.get("numero_resolucion") or "").strip() or None,
            "logo_url": (data.get("logo_url") or "").strip() or None,
            "color_primario": (data.get("color_primario") or "").strip() or None,
            "color_secundario": (data.get("color_secundario") or "").strip() or None,
            "estado": (data.get("estado") or empresa.get("estado") or "ACTIVA").strip() or "ACTIVA",
        }

        try:
            sb.table("hc_empresas").update(payload).eq("id", empresa_id).execute()

            if es_ajax():
                return jsonify({
                    "ok": True,
                    "message": "Empresa actualizada correctamente.",
                    "redirect": "/empresa/seleccionar"
                })

            return redirect("/empresa/seleccionar")

        except Exception as exc:
            mensaje = str(exc)
            if "duplicate" in mensaje.lower() or "unique" in mensaje.lower():
                mensaje = "Ya existe otra empresa registrada con ese NIT."

            if es_ajax():
                return jsonify({"ok": False, "message": mensaje}), 400

            empresa.update(payload)
            return render_template("hc/empresa/editar.html", empresa=empresa, error=mensaje), 400

    return render_template("hc/empresa/editar.html", empresa=empresa)


@bp_hc_empresa.route("/estado/<int:empresa_id>", methods=["POST"])
def cambiar_estado_empresa(empresa_id):
    if not es_super_admin():
        return jsonify({"ok": False, "message": "No autorizado"}), 403

    sb = get_supabase_admin()

    empresa = sb.table("hc_empresas") \
        .select("id, estado") \
        .eq("id", empresa_id) \
        .limit(1) \
        .execute().data

    if not empresa:
        return jsonify({"ok": False, "message": "Empresa no encontrada"}), 404

    empresa = empresa[0]
    estado_actual = (empresa.get("estado") or "INACTIVA").upper()
    nuevo_estado = "INACTIVA" if estado_actual == "ACTIVA" else "ACTIVA"

    try:
        sb.table("hc_empresas").update({"estado": nuevo_estado}).eq("id", empresa_id).execute()

        if session.get("empresa_id") == empresa_id and nuevo_estado != "ACTIVA":
            session.pop("empresa_id", None)

        return jsonify({
            "ok": True,
            "message": f"Empresa {nuevo_estado.lower()} correctamente.",
            "nuevo_estado": nuevo_estado
        })
    except Exception as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
