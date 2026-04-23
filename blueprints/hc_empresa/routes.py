from flask import Blueprint, render_template, request, redirect, session
from services.supabase_service import get_supabase_admin

bp_hc_empresa = Blueprint(
    "bp_hc_empresa",
    __name__,
    url_prefix="/empresa"
)

# ===============================
# 🔐 VALIDACIÓN SUPER ADMIN
# ===============================
def es_super_admin():
    return session.get("rol") == "SUPER_ADMIN"


# ===============================
# 🏢 SELECTOR DE EMPRESA
# ===============================
@bp_hc_empresa.route("/seleccionar")
def seleccionar_empresa():

    if not es_super_admin():
        return redirect("/hc")

    sb = get_supabase_admin()

    empresas = sb.table("hc_empresas")\
        .select("id, nombre_comercial, razon_social, estado")\
        .order("razon_social")\
        .execute().data

    return render_template(
        "hc/empresa/seleccionar.html",
        empresas=empresas
    )


# ===============================
# 🚀 ENTRAR A EMPRESA
# ===============================
@bp_hc_empresa.route("/entrar/<int:empresa_id>")
def entrar_empresa(empresa_id):

    if not es_super_admin():
        return redirect("/hc")

    session["empresa_id"] = empresa_id

    return redirect("/hc")


# ===============================
# ➕ CREAR EMPRESA
# ===============================
@bp_hc_empresa.route("/crear", methods=["GET", "POST"])
def crear_empresa():

    if not es_super_admin():
        return redirect("/hc")

    if request.method == "POST":

        data = request.form
        sb = get_supabase_admin()

        empresa = {
            "nit": data.get("nit"),
            "razon_social": data.get("razon_social"),
            "nombre_comercial": data.get("nombre_comercial"),
            "tipo_empresa": data.get("tipo_empresa"),
            "telefono": data.get("telefono"),
            "email": data.get("email"),
            "municipio": data.get("municipio"),
            "departamento": data.get("departamento"),
        }

        res = sb.table("hc_empresas").insert(empresa).execute()

        # 👉 opcional: entrar automáticamente
        empresa_id = res.data[0]["id"]
        session["empresa_id"] = empresa_id

        return redirect("/hc")

    return render_template("hc/empresa/crear.html")