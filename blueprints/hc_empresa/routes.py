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
        .select("id, nombre_comercial, razon_social, estado") \
        .order("razon_social") \
        .execute().data

    return render_template(
        "hc/empresa/seleccionar.html",
        empresas=empresas
    )


@bp_hc_empresa.route("/entrar/<int:empresa_id>")
def entrar_empresa(empresa_id):
    if not es_super_admin():
        return redirect("/hc")

    session["empresa_id"] = empresa_id
    return redirect("/hc")


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
                    "redirect": "/hc"
                })

            return redirect("/hc")

        except Exception as exc:
            mensaje = str(exc)

            if "duplicate" in mensaje.lower() or "unique" in mensaje.lower():
                mensaje = "Ya existe una empresa registrada con ese NIT."

            if es_ajax():
                return jsonify({"ok": False, "message": mensaje}), 400

            return render_template("hc/empresa/crear.html", error=mensaje), 400

    return render_template("hc/empresa/crear.html")
