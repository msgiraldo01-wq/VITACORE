from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from repositories import hc_pacientes_repo as repo
from repositories import hc_tipos_documento_repo as repo_doc
from repositories import hc_paises_repo as repo_paises
from repositories import hc_departamentos_repo as repo_dep
from repositories import hc_municipios_repo as repo_mun
from repositories import hc_eps_repo as repo_eps


bp_hc_pacientes = Blueprint(
    "hc_pacientes",
    __name__,
    url_prefix="/hc/pacientes"
)


# ======================================
# LISTADO
# ======================================

@bp_hc_pacientes.route("/")
def pacientes():

    pacientes = repo.listar()

    return render_template(
        "hc/pacientes/index.html",
        pacientes=pacientes
    )


# ======================================
# NUEVO PACIENTE
# ======================================

@bp_hc_pacientes.route("/nuevo")
def pacientes_nuevo():

    tipos_doc = repo_doc.listar()
    paises = repo_paises.listar()
    departamentos = repo_dep.listar()
    municipios = repo_mun.listar()
    eps_lista = repo_eps.listar()

    return render_template(
        "hc/pacientes/pacientes_form.html",
        modo="crear",
        paciente=None,
        tipos_doc=tipos_doc,
        paises=paises,
        departamentos=departamentos, 
        municipios=municipios,
        eps_lista=eps_lista,
    )


# ======================================
# CREAR PACIENTE
# ======================================

@bp_hc_pacientes.route("/crear", methods=["POST"])
def pacientes_crear():

    numero_doc = request.form.get("numero_documento")

    existente = repo.buscar_por_documento(numero_doc)

    municipio_id = request.form.get("municipio_id")

    municipio = repo_mun.obtener(int(municipio_id))

    if existente:
        flash("Ya existe un paciente con ese documento.", "error")
        return redirect(url_for("hc_pacientes.pacientes"))

    # Obtener datos de EPS
    eps_id = request.form.get("eps_id")
    eps_nombre = ""
    if eps_id:
        eps = repo_eps.obtener(int(eps_id))
        eps_nombre = eps["nombre"] if eps else ""

    data = {
        "tipo_documento_id": request.form.get("tipo_documento_id"),
        "numero_documento": request.form.get("numero_documento"),

        "primer_nombre": request.form.get("primer_nombre"),
        "segundo_nombre": request.form.get("segundo_nombre"),
        "primer_apellido": request.form.get("primer_apellido"),
        "segundo_apellido": request.form.get("segundo_apellido"),

        "fecha_nacimiento": request.form.get("fecha_nacimiento"),
        "sexo": request.form.get("sexo"),
        "estado_civil": request.form.get("estado_civil"), 

        # contacto
        "telefono": request.form.get("telefono"),
        "celular": request.form.get("celular"),
        "email": request.form.get("email"),
        "direccion": request.form.get("direccion"),

        # ubicación
        "pais_id": request.form.get("pais_id"),
        "municipio_id": municipio_id,
        "departamento_id": municipio["departamento_id"],
        "zona": request.form.get("zona"),  

        # EPS
        "eps_id": eps_id,
        "eps_nombre": eps_nombre,
        "regimen_afiliacion": request.form.get("regimen_afiliacion"),  

        # adicionales
        "ocupacion": request.form.get("ocupacion"),  
        "nivel_educativo": request.form.get("nivel_educativo"),  
        "grupo_poblacional": request.form.get("grupo_poblacional"),  
    }

    repo.crear(data)

    flash("Paciente creado correctamente.", "success")

    return_url = request.form.get("return_url", "").strip()
    if return_url and return_url.startswith("/"):
        return redirect(return_url)

    return redirect(url_for("hc_pacientes.pacientes"))


# ======================================
# EDITAR PACIENTE
# ======================================

@bp_hc_pacientes.route("/editar/<int:item_id>")
def pacientes_editar(item_id):

    paciente = repo.obtener(item_id)

    if not paciente:
        flash("Paciente no encontrado.", "error")
        return redirect(url_for("hc_pacientes.pacientes"))

    tipos_doc = repo_doc.listar()
    paises = repo_paises.listar()
    departamentos = repo_dep.listar()
    municipios = repo_mun.listar()
    eps_lista = repo_eps.listar()

    return render_template(
        "hc/pacientes/pacientes_form.html",
        modo="editar",
        paciente=paciente,
        tipos_doc=tipos_doc,
        paises=paises,
        departamentos=departamentos,
        municipios=municipios,
        eps_lista=eps_lista,
    )


# ======================================
# ACTUALIZAR PACIENTE
# ======================================

@bp_hc_pacientes.route("/actualizar/<int:item_id>", methods=["POST"])
def pacientes_actualizar(item_id):

    municipio_id = request.form.get("municipio_id")

    if not municipio_id:
        flash("Debe seleccionar un municipio.", "error")
        return redirect(url_for("hc_pacientes.pacientes_editar", item_id=item_id))

    try:
        municipio = repo_mun.obtener(int(municipio_id))
    except:
        municipio = None

    if not municipio:
        flash("Municipio inválido.", "error")
        return redirect(url_for("hc_pacientes.pacientes_editar", item_id=item_id))

    # Obtener datos de EPS
    eps_id = request.form.get("eps_id")
    eps_nombre = ""
    if eps_id:
        eps = repo_eps.obtener(int(eps_id))
        eps_nombre = eps["nombre"] if eps else ""

    # =========================
    # DATA
    # =========================
    data = {
        "tipo_documento_id": request.form.get("tipo_documento_id"),
        "numero_documento": request.form.get("numero_documento"),

        "primer_nombre": request.form.get("primer_nombre"),
        "segundo_nombre": request.form.get("segundo_nombre"),
        "primer_apellido": request.form.get("primer_apellido"),
        "segundo_apellido": request.form.get("segundo_apellido"),

        "fecha_nacimiento": request.form.get("fecha_nacimiento"),
        "sexo": request.form.get("sexo"),
        "estado_civil": request.form.get("estado_civil"), 

        # contacto
        "telefono": request.form.get("telefono"),
        "celular": request.form.get("celular"),
        "email": request.form.get("email"),
        "direccion": request.form.get("direccion"),

        # ubicación
        "pais_id": request.form.get("pais_id"),
        "municipio_id": municipio_id,
        "departamento_id": municipio["departamento_id"],
        "zona": request.form.get("zona"),  

        # EPS
        "eps_id": eps_id,
        "eps_nombre": eps_nombre,
        "regimen_afiliacion": request.form.get("regimen_afiliacion"),  

        # adicionales
        "ocupacion": request.form.get("ocupacion"),  
        "nivel_educativo": request.form.get("nivel_educativo"),  
        "grupo_poblacional": request.form.get("grupo_poblacional"),  
    }
    
    repo.actualizar(item_id, data)

    flash("Paciente actualizado correctamente.", "success")

    return redirect(url_for("hc_pacientes.pacientes"))


# ======================================
# TOGGLE ESTADO
# ======================================

@bp_hc_pacientes.route("/toggle/<int:item_id>", methods=["POST"])
def pacientes_toggle(item_id):

    paciente = repo.obtener(item_id)

    if not paciente:
        flash("Paciente no existe.", "error")
        return redirect(url_for("hc_pacientes.pacientes"))

    nuevo_estado = "INACTIVO" if paciente.get("estado") == "ACTIVO" else "ACTIVO"

    repo.cambiar_estado(item_id, nuevo_estado)

    flash(
        f"Paciente {'inactivado' if nuevo_estado == 'INACTIVO' else 'activado'} correctamente.",
        "success"
    )

    return redirect(url_for("hc_pacientes.pacientes"))


# ======================================
# DETALLE PACIENTE
# ======================================

@bp_hc_pacientes.route("/ver/<int:item_id>")
def pacientes_ver(item_id):

    paciente = repo.obtener(item_id)

    if not paciente:
        flash("Paciente no encontrado.", "error")
        return redirect(url_for("hc_pacientes.pacientes"))

    return render_template(
        "hc/pacientes/pacientes_detalle.html",
        paciente=paciente
    )


# ======================================
# API MUNICIPIOS
# ======================================

@bp_hc_pacientes.route("/api/municipios")
def municipios():

    dep_id = request.args.get("departamento_id")

    data = repo_mun.listar_select(dep_id)

    return jsonify(data)


# ======================================
# API BUSCAR PACIENTES
# ======================================

@bp_hc_pacientes.route("/buscar")
def pacientes_buscar():
    q = request.args.get("q", "")
    items = repo.buscar(q)
    return jsonify(items)



