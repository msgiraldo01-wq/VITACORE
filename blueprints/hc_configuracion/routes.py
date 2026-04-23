from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from repositories import hc_sedes_repo as repo
from repositories import hc_tipos_documento_repo as repo_td
from repositories import hc_especialidades_repo as repo_esp
from repositories import hc_consultorios_repo as repo_cons
from repositories import hc_sedes_repo as repo_sedes
from repositories import hc_profesionales_repo as repo_prof
from repositories import hc_servicios_repo
from repositories import hc_paises_repo as repo_paises
from repositories import hc_cie10_repo as repo_cie10
from repositories import hc_departamentos_repo as repo_dep
from repositories import hc_municipios_repo as repo_muni
from repositories import hc_eps_repo as repo_eps
from repositories import hc_recursos_repo as repo_recursos
from repositories import hc_agendas_repo as agendas_repo
from repositories import hc_cups_repo as repo_cups
import repositories.prof_procedimientos_repository as prof_proc_repo
import repositories.rec_procedimientos_repository  as rec_proc_repo
import io 
import csv




bp_hc_configuracion = Blueprint(
    "hc_configuracion",
    __name__,
    url_prefix="/hc/configuracion"
)


@bp_hc_configuracion.route("/")
def index():
    return render_template("hc/configuracion/index.html")




@bp_hc_configuracion.route("/sedes")
def sedes():
    items = repo.listar()
    return render_template("hc/configuracion/sedes.html", items=items)


@bp_hc_configuracion.route("/sedes/nueva", methods=["GET", "POST"])
def sede_nueva():
    if request.method == "POST":
        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "ciudad": request.form.get("ciudad"),
            "direccion": request.form.get("direccion"),
            "telefono": request.form.get("telefono"),
            "estado": request.form.get("estado"),
        }

        if not (data["codigo"] or "").strip():
            flash("El código es obligatorio.", "warning")
            return render_template("hc/configuracion/sedes_form.html", modo="crear", item=data)

        if not (data["nombre"] or "").strip():
            flash("El nombre es obligatorio.", "warning")
            return render_template("hc/configuracion/sedes_form.html", modo="crear", item=data)

        if repo.existe_codigo(data["codigo"]):
            flash("Ya existe una sede con ese código.", "warning")
            return render_template("hc/configuracion/sedes_form.html", modo="crear", item=data)

        repo.crear(data)
        flash("Sede creada correctamente.", "success")
        return redirect(url_for("hc_configuracion.sedes"))

    return render_template("hc/configuracion/sedes_form.html", modo="crear", item={})


@bp_hc_configuracion.route("/sedes/editar/<int:sede_id>", methods=["GET", "POST"])
def sede_editar(sede_id):
    item = repo.obtener(sede_id)
    if not item:
        flash("La sede no existe.", "error")
        return redirect(url_for("hc_configuracion.sedes"))

    if request.method == "POST":
        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "ciudad": request.form.get("ciudad"),
            "direccion": request.form.get("direccion"),
            "telefono": request.form.get("telefono"),
            "estado": request.form.get("estado"),
        }

        if not (data["codigo"] or "").strip():
            flash("El código es obligatorio.", "warning")
            return render_template("hc/configuracion/sedes_form.html", modo="editar", item={**item, **data})

        if not (data["nombre"] or "").strip():
            flash("El nombre es obligatorio.", "warning")
            return render_template("hc/configuracion/sedes_form.html", modo="editar", item={**item, **data})

        if repo.existe_codigo(data["codigo"], exclude_id=sede_id):
            flash("Ya existe otra sede con ese código.", "warning")
            return render_template("hc/configuracion/sedes_form.html", modo="editar", item={**item, **data})

        repo.actualizar(sede_id, data)
        flash("Sede actualizada correctamente.", "success")
        return redirect(url_for("hc_configuracion.sedes"))

    return render_template("hc/configuracion/sedes_form.html", modo="editar", item=item)


@bp_hc_configuracion.route("/sedes/toggle/<int:sede_id>", methods=["POST"])
def sede_toggle(sede_id):
    item = repo.obtener(sede_id)
    if not item:
        flash("La sede no existe.", "error")
        return redirect(url_for("hc_configuracion.sedes"))

    nuevo_estado = "INACTIVA" if item.get("estado") == "ACTIVA" else "ACTIVA"
    repo.cambiar_estado(sede_id, nuevo_estado)

    flash(
        f"Sede {'inactivada' if nuevo_estado == 'INACTIVA' else 'activada'} correctamente.",
        "success"
    )
    return redirect(url_for("hc_configuracion.sedes"))


@bp_hc_configuracion.route("/tipos-documento")
def tipos_documento():
    items = repo_td.listar()
    return render_template("hc/configuracion/tipos_documento.html", items=items)


@bp_hc_configuracion.route("/tipos-documento/nuevo", methods=["GET", "POST"])
def tipo_documento_nuevo():
    if request.method == "POST":
        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion"),
            "estado": request.form.get("estado"),
        }

        if not (data["codigo"] or "").strip():
            flash("El código es obligatorio.", "warning")
            return render_template("hc/configuracion/tipos_documento_form.html", modo="crear", item=data)

        if not (data["nombre"] or "").strip():
            flash("El nombre es obligatorio.", "warning")
            return render_template("hc/configuracion/tipos_documento_form.html", modo="crear", item=data)

        if repo_td.existe_codigo(data["codigo"]):
            flash("Ya existe un tipo de documento con ese código.", "warning")
            return render_template("hc/configuracion/tipos_documento_form.html", modo="crear", item=data)

        repo_td.crear(data)
        flash("Tipo de documento creado correctamente.", "success")
        return redirect(url_for("hc_configuracion.tipos_documento"))

    return render_template("hc/configuracion/tipos_documento_form.html", modo="crear", item={})


@bp_hc_configuracion.route("/tipos-documento/editar/<int:item_id>", methods=["GET", "POST"])
def tipo_documento_editar(item_id):
    item = repo_td.obtener(item_id)
    if not item:
        flash("El tipo de documento no existe.", "error")
        return redirect(url_for("hc_configuracion.tipos_documento"))

    if request.method == "POST":
        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion"),
            "estado": request.form.get("estado"),
        }

        if not (data["codigo"] or "").strip():
            flash("El código es obligatorio.", "warning")
            return render_template("hc/configuracion/tipos_documento_form.html", modo="editar", item={**item, **data})

        if not (data["nombre"] or "").strip():
            flash("El nombre es obligatorio.", "warning")
            return render_template("hc/configuracion/tipos_documento_form.html", modo="editar", item={**item, **data})

        if repo_td.existe_codigo(data["codigo"], exclude_id=item_id):
            flash("Ya existe otro tipo de documento con ese código.", "warning")
            return render_template("hc/configuracion/tipos_documento_form.html", modo="editar", item={**item, **data})

        repo_td.actualizar(item_id, data)
        flash("Tipo de documento actualizado correctamente.", "success")
        return redirect(url_for("hc_configuracion.tipos_documento"))

    return render_template("hc/configuracion/tipos_documento_form.html", modo="editar", item=item)


@bp_hc_configuracion.route("/tipos-documento/toggle/<int:item_id>", methods=["POST"])
def tipo_documento_toggle(item_id):
    item = repo_td.obtener(item_id)
    if not item:
        flash("El tipo de documento no existe.", "error")
        return redirect(url_for("hc_configuracion.tipos_documento"))

    nuevo_estado = "INACTIVO" if item.get("estado") == "ACTIVO" else "ACTIVO"
    repo_td.cambiar_estado(item_id, nuevo_estado)

    flash(
        f"Tipo de documento {'inactivado' if nuevo_estado == 'INACTIVO' else 'activado'} correctamente.",
        "success"
    )
    return redirect(url_for("hc_configuracion.tipos_documento"))

@bp_hc_configuracion.route("/especialidades")
def especialidades():
    items = repo_esp.listar()
    return render_template("hc/configuracion/especialidades.html", items=items)


@bp_hc_configuracion.route("/especialidades/nueva", methods=["GET", "POST"])
def especialidad_nueva():
    if request.method == "POST":
        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion"),
            "estado": request.form.get("estado"),
        }

        if not (data["codigo"] or "").strip():
            flash("El código es obligatorio.", "warning")
            return render_template("hc/configuracion/especialidades_form.html", modo="crear", item=data)

        if not (data["nombre"] or "").strip():
            flash("El nombre es obligatorio.", "warning")
            return render_template("hc/configuracion/especialidades_form.html", modo="crear", item=data)

        if repo_esp.existe_codigo(data["codigo"]):
            flash("Ya existe una especialidad con ese código.", "warning")
            return render_template("hc/configuracion/especialidades_form.html", modo="crear", item=data)

        repo_esp.crear(data)
        flash("Especialidad creada correctamente.", "success")
        return redirect(url_for("hc_configuracion.especialidades"))

    return render_template("hc/configuracion/especialidades_form.html", modo="crear", item={})


@bp_hc_configuracion.route("/especialidades/editar/<int:item_id>", methods=["GET", "POST"])
def especialidad_editar(item_id):
    item = repo_esp.obtener(item_id)
    if not item:
        flash("La especialidad no existe.", "error")
        return redirect(url_for("hc_configuracion.especialidades"))

    if request.method == "POST":
        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion"),
            "estado": request.form.get("estado"),
        }

        if not (data["codigo"] or "").strip():
            flash("El código es obligatorio.", "warning")
            return render_template("hc/configuracion/especialidades_form.html", modo="editar", item={**item, **data})

        if not (data["nombre"] or "").strip():
            flash("El nombre es obligatorio.", "warning")
            return render_template("hc/configuracion/especialidades_form.html", modo="editar", item={**item, **data})

        if repo_esp.existe_codigo(data["codigo"], exclude_id=item_id):
            flash("Ya existe otra especialidad con ese código.", "warning")
            return render_template("hc/configuracion/especialidades_form.html", modo="editar", item={**item, **data})

        repo_esp.actualizar(item_id, data)
        flash("Especialidad actualizada correctamente.", "success")
        return redirect(url_for("hc_configuracion.especialidades"))

    return render_template("hc/configuracion/especialidades_form.html", modo="editar", item=item)


@bp_hc_configuracion.route("/especialidades/toggle/<int:item_id>", methods=["POST"])
def especialidad_toggle(item_id):
    item = repo_esp.obtener(item_id)
    if not item:
        flash("La especialidad no existe.", "error")
        return redirect(url_for("hc_configuracion.especialidades"))

    nuevo_estado = "INACTIVA" if item.get("estado") == "ACTIVA" else "ACTIVA"
    repo_esp.cambiar_estado(item_id, nuevo_estado)

    flash(
        f"Especialidad {'inactivada' if nuevo_estado == 'INACTIVA' else 'activada'} correctamente.",
        "success"
    )
    return redirect(url_for("hc_configuracion.especialidades"))

@bp_hc_configuracion.route("/consultorios")
def consultorios():
    items = repo_cons.listar()
    return render_template("hc/configuracion/consultorios.html", items=items)


@bp_hc_configuracion.route("/consultorios/nuevo", methods=["GET", "POST"])
def consultorio_nuevo():
    sedes = repo_sedes.listar()

    if request.method == "POST":
        sede_id_raw = (request.form.get("sede_id") or "").strip()
        sede_id = int(sede_id_raw) if sede_id_raw.isdigit() else None

        sede_item = repo_sedes.obtener(sede_id) if sede_id else None

        data = {
            "sede_id": sede_id,
            "sede_nombre": (sede_item.get("nombre") if sede_item else ""),
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "piso": request.form.get("piso"),
            "descripcion": request.form.get("descripcion"),
            "estado": request.form.get("estado"),
        }

        if not sede_id:
            flash("Debes seleccionar una sede.", "warning")
            return render_template("hc/configuracion/consultorios_form.html", modo="crear", item=data, sedes=sedes)

        if not (data["codigo"] or "").strip():
            flash("El código es obligatorio.", "warning")
            return render_template("hc/configuracion/consultorios_form.html", modo="crear", item=data, sedes=sedes)

        if not (data["nombre"] or "").strip():
            flash("El nombre es obligatorio.", "warning")
            return render_template("hc/configuracion/consultorios_form.html", modo="crear", item=data, sedes=sedes)

        if repo_cons.existe_codigo(data["codigo"]):
            flash("Ya existe un consultorio con ese código.", "warning")
            return render_template("hc/configuracion/consultorios_form.html", modo="crear", item=data, sedes=sedes)

        repo_cons.crear(data)
        flash("Consultorio creado correctamente.", "success")
        return redirect(url_for("hc_configuracion.consultorios"))

    return render_template("hc/configuracion/consultorios_form.html", modo="crear", item={}, sedes=sedes)


@bp_hc_configuracion.route("/consultorios/editar/<int:item_id>", methods=["GET", "POST"])
def consultorio_editar(item_id):
    item = repo_cons.obtener(item_id)
    if not item:
        flash("El consultorio no existe.", "error")
        return redirect(url_for("hc_configuracion.consultorios"))

    sedes = repo_sedes.listar()

    if request.method == "POST":
        sede_id_raw = (request.form.get("sede_id") or "").strip()
        sede_id = int(sede_id_raw) if sede_id_raw.isdigit() else None

        sede_item = repo_sedes.obtener(sede_id) if sede_id else None

        data = {
            "sede_id": sede_id,
            "sede_nombre": (sede_item.get("nombre") if sede_item else ""),
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "piso": request.form.get("piso"),
            "descripcion": request.form.get("descripcion"),
            "estado": request.form.get("estado"),
        }

        if not sede_id:
            flash("Debes seleccionar una sede.", "warning")
            return render_template("hc/configuracion/consultorios_form.html", modo="editar", item={**item, **data}, sedes=sedes)

        if not (data["codigo"] or "").strip():
            flash("El código es obligatorio.", "warning")
            return render_template("hc/configuracion/consultorios_form.html", modo="editar", item={**item, **data}, sedes=sedes)

        if not (data["nombre"] or "").strip():
            flash("El nombre es obligatorio.", "warning")
            return render_template("hc/configuracion/consultorios_form.html", modo="editar", item={**item, **data}, sedes=sedes)

        if repo_cons.existe_codigo(data["codigo"], exclude_id=item_id):
            flash("Ya existe otro consultorio con ese código.", "warning")
            return render_template("hc/configuracion/consultorios_form.html", modo="editar", item={**item, **data}, sedes=sedes)

        repo_cons.actualizar(item_id, data)
        flash("Consultorio actualizado correctamente.", "success")
        return redirect(url_for("hc_configuracion.consultorios"))

    return render_template("hc/configuracion/consultorios_form.html", modo="editar", item=item, sedes=sedes)


@bp_hc_configuracion.route("/consultorios/toggle/<int:item_id>", methods=["POST"])
def consultorio_toggle(item_id):
    item = repo_cons.obtener(item_id)
    if not item:
        flash("El consultorio no existe.", "error")
        return redirect(url_for("hc_configuracion.consultorios"))

    nuevo_estado = "INACTIVO" if item.get("estado") == "ACTIVO" else "ACTIVO"
    repo_cons.cambiar_estado(item_id, nuevo_estado)

    flash(
        f"Consultorio {'inactivado' if nuevo_estado == 'INACTIVO' else 'activado'} correctamente.",
        "success"
    )
    return redirect(url_for("hc_configuracion.consultorios"))

@bp_hc_configuracion.route("/profesionales")
def profesionales():

    items = repo_prof.listar()

    return render_template(
        "hc/configuracion/profesionales.html",
        items=items
    )



@bp_hc_configuracion.route("/profesionales/nuevo", methods=["GET", "POST"])
def profesional_nuevo():

    tipos_documento = repo_td.listar()
    especialidades = repo_esp.listar()
    sedes = repo_sedes.listar()
    consultorios = repo_cons.listar()

    if request.method == "POST":

        data = {
            "tipo_documento_id": request.form.get("tipo_documento_id"),
            "numero_documento": request.form.get("numero_documento"),
            "nombres": request.form.get("nombres"),
            "apellidos": request.form.get("apellidos"),
            "especialidad_id": request.form.get("especialidad_id"),
            "sede_id": request.form.get("sede_id"),
            "consultorio_id": request.form.get("consultorio_id"),
            "registro_profesional": request.form.get("registro_profesional"),
            "correo": request.form.get("correo"),
            "telefono": request.form.get("telefono"),
            "estado": request.form.get("estado"),
        }

        if not (data["tipo_documento_id"] or "").strip():
            flash("Debes seleccionar tipo de documento.", "warning")
            return render_template(
                "hc/configuracion/profesionales_form.html",
                modo="crear",
                item=data,
                tipos_documento=tipos_documento,
                especialidades=especialidades,
                sedes=sedes,
                consultorios=consultorios
            )

        if not (data["numero_documento"] or "").strip():
            flash("El número de documento es obligatorio.", "warning")
            return render_template(
                "hc/configuracion/profesionales_form.html",
                modo="crear",
                item=data,
                tipos_documento=tipos_documento,
                especialidades=especialidades,
                sedes=sedes,
                consultorios=consultorios
            )

        if not (data["nombres"] or "").strip():
            flash("Los nombres son obligatorios.", "warning")
            return render_template(
                "hc/configuracion/profesionales_form.html",
                modo="crear",
                item=data,
                tipos_documento=tipos_documento,
                especialidades=especialidades,
                sedes=sedes,
                consultorios=consultorios
            )

        if not (data["apellidos"] or "").strip():
            flash("Los apellidos son obligatorios.", "warning")
            return render_template(
                "hc/configuracion/profesionales_form.html",
                modo="crear",
                item=data,
                tipos_documento=tipos_documento,
                especialidades=especialidades,
                sedes=sedes,
                consultorios=consultorios
            )

        if repo_prof.existe_documento(
            data["tipo_documento_id"],
            data["numero_documento"]
        ):
            flash("Ya existe un profesional con ese tipo y número de documento.", "warning")
            return render_template(
                "hc/configuracion/profesionales_form.html",
                modo="crear",
                item=data,
                tipos_documento=tipos_documento,
                especialidades=especialidades,
                sedes=sedes,
                consultorios=consultorios
            )

        repo_prof.crear(data)

        flash("Profesional creado correctamente.", "success")

        return redirect(url_for("hc_configuracion.profesionales"))

    return render_template(
        "hc/configuracion/profesionales_form.html",
        modo="crear",
        item={},
        tipos_documento=tipos_documento,
        especialidades=especialidades,
        sedes=sedes,
        consultorios=consultorios
    )



@bp_hc_configuracion.route("/profesionales/editar/<int:item_id>", methods=["GET", "POST"])
def profesional_editar(item_id):

    item = repo_prof.obtener(item_id)

    if not item:
        flash("El profesional no existe.", "error")
        return redirect(url_for("hc_configuracion.profesionales"))

    tipos_documento = repo_td.listar()
    especialidades = repo_esp.listar()
    sedes = repo_sedes.listar()
    consultorios = repo_cons.listar()

    if request.method == "POST":

        data = {
            "tipo_documento_id": request.form.get("tipo_documento_id"),
            "numero_documento": request.form.get("numero_documento"),
            "nombres": request.form.get("nombres"),
            "apellidos": request.form.get("apellidos"),
            "especialidad_id": request.form.get("especialidad_id"),
            "sede_id": request.form.get("sede_id"),
            "consultorio_id": request.form.get("consultorio_id"),
            "registro_profesional": request.form.get("registro_profesional"),
            "correo": request.form.get("correo"),
            "telefono": request.form.get("telefono"),
            "estado": request.form.get("estado"),
        }

        if repo_prof.existe_documento(
            data["tipo_documento_id"],
            data["numero_documento"],
            exclude_id=item_id
        ):
            flash("Ya existe otro profesional con ese tipo y número de documento.", "warning")
            return render_template(
                "hc/configuracion/profesionales_form.html",
                modo="editar",
                item={**item, **data},
                tipos_documento=tipos_documento,
                especialidades=especialidades,
                sedes=sedes,
                consultorios=consultorios
            )

        repo_prof.actualizar(item_id, data)

        flash("Profesional actualizado correctamente.", "success")

        return redirect(url_for("hc_configuracion.profesionales"))

    return render_template(
        "hc/configuracion/profesionales_form.html",
        modo="editar",
        item=item,
        tipos_documento=tipos_documento,
        especialidades=especialidades,
        sedes=sedes,
        consultorios=consultorios
    )


@bp_hc_configuracion.route("/profesionales/toggle/<int:item_id>", methods=["POST"])
def profesional_toggle(item_id):

    item = repo_prof.obtener(item_id)

    if not item:
        flash("El profesional no existe.", "error")
        return redirect(url_for("hc_configuracion.profesionales"))

    nuevo_estado = "INACTIVO" if item.get("estado") == "ACTIVO" else "ACTIVO"

    repo_prof.cambiar_estado(item_id, nuevo_estado)

    flash(
        f"Profesional {'inactivado' if nuevo_estado == 'INACTIVO' else 'activado'} correctamente.",
        "success"
    )

    return redirect(url_for("hc_configuracion.profesionales"))

# ================================
# SERVICIOS
# ================================

@bp_hc_configuracion.route("/servicios")
def servicios():

    servicios = hc_servicios_repo.listar_servicios()

    return render_template(
        "hc/configuracion/servicios.html",
        servicios=servicios
    )


@bp_hc_configuracion.route("/servicios/nuevo")
def servicios_nuevo():

    especialidades = repo_esp.listar()

    return render_template(
        "hc/configuracion/servicios_form.html",
        modo="crear",
        servicio=None,
        especialidades=especialidades
    )


@bp_hc_configuracion.route("/servicios/crear", methods=["POST"])
def servicios_crear():

    data = {
        "codigo": request.form.get("codigo"),
        "nombre": request.form.get("nombre"),
        "especialidad_id": request.form.get("especialidad_id") or None,
        "descripcion": request.form.get("descripcion"),
    }

    hc_servicios_repo.crear_servicio(data)

    flash("Servicio creado correctamente", "success")

    return redirect("/hc/configuracion/servicios")


@bp_hc_configuracion.route("/servicios/<int:id>/editar")
def servicios_editar(id):

    servicio = hc_servicios_repo.obtener_servicio(id)

    especialidades = repo_esp.listar()

    return render_template(
        "hc/configuracion/servicios_form.html",
        modo="editar",
        servicio=servicio,
        especialidades=especialidades
    )


@bp_hc_configuracion.route("/servicios/<int:id>/actualizar", methods=["POST"])
def servicios_actualizar(id):

    data = {
        "codigo": request.form.get("codigo"),
        "nombre": request.form.get("nombre"),
        "especialidad_id": request.form.get("especialidad_id") or None,
        "descripcion": request.form.get("descripcion"),
    }

    hc_servicios_repo.actualizar_servicio(id, data)

    flash("Servicio actualizado", "success")

    return redirect("/hc/configuracion/servicios")

@bp_hc_configuracion.route("/servicios/toggle/<int:item_id>", methods=["POST"])
def servicio_toggle(item_id):

    item = hc_servicios_repo.obtener_servicio(item_id)

    if not item:
        flash("El servicio no existe.", "error")
        return redirect(url_for("hc_configuracion.servicios"))

    nuevo_estado = "INACTIVO" if item.get("estado") == "ACTIVO" else "ACTIVO"

    hc_servicios_repo.cambiar_estado(item_id, nuevo_estado)

    flash(
        f"Servicio {'inactivado' if nuevo_estado == 'INACTIVO' else 'activado'} correctamente.",
        "success"
    )

    return redirect(url_for("hc_configuracion.servicios"))


# ============================================
# PAISES
# ============================================

@bp_hc_configuracion.route("/paises")
def paises():

    items = repo_paises.listar()

    return render_template(
        "hc/configuracion/paises.html",
        items=items
    )


# ===============================
# CREAR
# ===============================

@bp_hc_configuracion.route("/paises/nuevo", methods=["GET", "POST"])
def pais_nuevo():

    if request.method == "POST":

        data = {
            "codigo_iso2": (request.form.get("codigo_iso2") or "").strip().upper(),
            "codigo_iso3": (request.form.get("codigo_iso3") or "").strip().upper(),
            "nombre": (request.form.get("nombre") or "").strip(),
        }

        # VALIDACIONES

        if not data["codigo_iso2"]:
            flash("El código ISO2 es obligatorio.", "warning")
            return render_template(
                "hc/configuracion/paises_form.html",
                modo="crear",
                item=data
            )

        if not data["nombre"]:
            flash("El nombre del país es obligatorio.", "warning")
            return render_template(
                "hc/configuracion/paises_form.html",
                modo="crear",
                item=data
            )

        # VALIDAR DUPLICADO ISO2
        existente = repo_paises.obtener_por_iso2(data["codigo_iso2"])

        if existente:
            flash(
                f"Ya existe un país con código ISO2 '{data['codigo_iso2']}'.",
                "warning"
            )
            return render_template(
                "hc/configuracion/paises_form.html",
                modo="crear",
                item=data
            )

        try:

            repo_paises.crear(data)

            flash("País creado correctamente.", "success")

            return redirect(url_for("hc_configuracion.paises"))

        except Exception as e:

            flash("Error al crear el país.", "error")

            return render_template(
                "hc/configuracion/paises_form.html",
                modo="crear",
                item=data
            )

    return render_template(
        "hc/configuracion/paises_form.html",
        modo="crear",
        item={}
    )


# ===============================
# EDITAR
# ===============================

@bp_hc_configuracion.route("/paises/editar/<int:item_id>", methods=["GET", "POST"])
def pais_editar(item_id):

    item = repo_paises.obtener(item_id)

    if not item:
        flash("El país no existe.", "error")
        return redirect(url_for("hc_configuracion.paises"))

    if request.method == "POST":

        data = {
            "codigo_iso2": (request.form.get("codigo_iso2") or "").strip().upper(),
            "codigo_iso3": (request.form.get("codigo_iso3") or "").strip().upper(),
            "nombre": (request.form.get("nombre") or "").strip(),
        }

        if not data["codigo_iso2"]:
            flash("El código ISO2 es obligatorio.", "warning")
            return render_template(
                "hc/configuracion/paises_form.html",
                modo="editar",
                item={**item, **data}
            )

        if not data["nombre"]:
            flash("El nombre del país es obligatorio.", "warning")
            return render_template(
                "hc/configuracion/paises_form.html",
                modo="editar",
                item={**item, **data}
            )

        # VALIDAR DUPLICADO ISO2 (EXCEPTO EL MISMO)
        existente = repo_paises.obtener_por_iso2(data["codigo_iso2"])

        if existente and existente["id"] != item_id:

            flash(
                f"Ya existe otro país con ISO2 '{data['codigo_iso2']}'.",
                "warning"
            )

            return render_template(
                "hc/configuracion/paises_form.html",
                modo="editar",
                item={**item, **data}
            )

        try:

            repo_paises.actualizar(item_id, data)

            flash("País actualizado correctamente.", "success")

            return redirect(url_for("hc_configuracion.paises"))

        except Exception:

            flash("Error al actualizar el país.", "error")

            return render_template(
                "hc/configuracion/paises_form.html",
                modo="editar",
                item={**item, **data}
            )

    return render_template(
        "hc/configuracion/paises_form.html",
        modo="editar",
        item=item
    )


# ===============================
# TOGGLE
# ===============================

@bp_hc_configuracion.route("/paises/toggle/<int:item_id>", methods=["POST"])
def pais_toggle(item_id):

    item = repo_paises.obtener(item_id)

    if not item:
        flash("El país no existe.", "error")
        return redirect(url_for("hc_configuracion.paises"))

    nuevo_estado = "INACTIVO" if item.get("estado") == "ACTIVO" else "ACTIVO"

    repo_paises.cambiar_estado(item_id, nuevo_estado)

    flash(
        f"País {'inactivado' if nuevo_estado == 'INACTIVO' else 'activado'} correctamente.",
        "success"
    )

    return redirect(url_for("hc_configuracion.paises"))



# ===============================
# CIE 10
# ===============================

@bp_hc_configuracion.route("/cie10")
def cie10():

    items = repo_cie10.listar()

    return render_template(
        "hc/configuracion/cie10.html",
        items=items
    )

@bp_hc_configuracion.route("/cie10/nuevo")
def cie10_nuevo():

    return render_template(
        "hc/configuracion/cie10_form.html",
        modo="crear",
        item=None
    )

@bp_hc_configuracion.route("/cie10/crear", methods=["POST"])
def cie10_crear():

    data = {

        "codigo": request.form.get("codigo"),
        "nombre": request.form.get("nombre"),
        "descripcion": request.form.get("descripcion"),
        "categoria": request.form.get("categoria")

    }

    repo_cie10.crear(data)

    flash("Diagnóstico CIE10 creado", "success")

    return redirect("/hc/configuracion/cie10")

    
@bp_hc_configuracion.route("/cie10/<int:item_id>/editar")
def cie10_editar(item_id):

    item = repo_cie10.obtener(item_id)

    return render_template(
        "hc/configuracion/cie10_form.html",
        modo="editar",
        item=item
    )

@bp_hc_configuracion.route("/cie10/<int:item_id>/actualizar", methods=["POST"])
def cie10_actualizar(item_id):

    data = {

        "codigo": request.form.get("codigo"),
        "nombre": request.form.get("nombre"),
        "descripcion": request.form.get("descripcion"),
        "categoria": request.form.get("categoria")

    }

    repo_cie10.actualizar(item_id, data)

    flash("Diagnóstico actualizado", "success")

    return redirect("/hc/configuracion/cie10")

@bp_hc_configuracion.route("/cie10/toggle/<int:item_id>", methods=["POST"])
def cie10_toggle(item_id):

    item = repo_cie10.obtener(item_id)

    if not item:
        flash("El diagnóstico no existe.", "error")
        return redirect(url_for("hc_configuracion.cie10"))

    nuevo_estado = "INACTIVO" if item.get("estado") == "ACTIVO" else "ACTIVO"

    repo_cie10.cambiar_estado(item_id, nuevo_estado)

    flash(
        f"Diagnóstico {'inactivado' if nuevo_estado == 'INACTIVO' else 'activado'} correctamente.",
        "success"
    )

    return redirect(url_for("hc_configuracion.cie10"))

@bp_hc_configuracion.route("/cie10/buscar")
def cie10_buscar():

    q = request.args.get("q","")

    items = repo_cie10.buscar(q)

    return jsonify(items)


@bp_hc_configuracion.route("/departamentos")
def departamentos():

    items = repo_dep.listar()

    return render_template(
        "hc/configuracion/departamentos.html",
        items=items
    )


@bp_hc_configuracion.route("/departamentos/nuevo", methods=["GET","POST"])
def departamento_nuevo():

    paises = repo_paises.listar()

    if request.method == "POST":

        data = {
            "pais_id": request.form.get("pais_id"),
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
        }

        repo_dep.crear(data)

        flash("Departamento creado correctamente.", "success")
        return redirect(url_for("hc_configuracion.departamentos"))

    return render_template(
        "hc/configuracion/departamentos_form.html",
        paises=paises,
        item={},
        modo="crear"
    )


@bp_hc_configuracion.route("/departamentos/editar/<int:item_id>", methods=["GET","POST"])
def departamento_editar(item_id):

    item = repo_dep.obtener(item_id)
    paises = repo_paises.listar()

    if request.method == "POST":

        data = {
            "pais_id": request.form.get("pais_id"),
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
        }

        repo_dep.actualizar(item_id, data)

        flash("Departamento actualizado.", "success")
        return redirect(url_for("hc_configuracion.departamentos"))

    return render_template(
        "hc/configuracion/departamentos_form.html",
        item=item,
        paises=paises,
        modo="editar"
    )


@bp_hc_configuracion.route("/departamentos/toggle/<int:item_id>", methods=["POST"])
def departamento_toggle(item_id):

    item = repo_dep.obtener(item_id)

    nuevo_estado = "INACTIVO" if item["estado"] == "ACTIVO" else "ACTIVO"

    repo_dep.cambiar_estado(item_id, nuevo_estado)

    flash("Estado actualizado.", "success")

    return redirect(url_for("hc_configuracion.departamentos"))


@bp_hc_configuracion.route("/municipios")
def municipios():

    items = repo_muni.listar()

    return render_template(
        "hc/configuracion/municipios.html",
        items=items
    )


@bp_hc_configuracion.route("/municipios/nuevo", methods=["GET","POST"])
def municipio_nuevo():

    departamentos = repo_dep.listar()

    if request.method == "POST":

        data = {
            "departamento_id": request.form.get("departamento_id"),
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
        }

        repo_muni.crear(data)

        flash("Municipio creado correctamente.", "success")
        return redirect(url_for("hc_configuracion.municipios"))

    return render_template(
        "hc/configuracion/municipios_form.html",
        departamentos=departamentos
    )


@bp_hc_configuracion.route("/municipios/editar/<int:item_id>", methods=["GET","POST"])
def municipio_editar(item_id):

    item = repo_muni.obtener(item_id)
    departamentos = repo_dep.listar()

    if request.method == "POST":

        data = {
            "departamento_id": request.form.get("departamento_id"),
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
        }

        repo_muni.actualizar(item_id, data)

        flash("Municipio actualizado.", "success")
        return redirect(url_for("hc_configuracion.municipios"))

    return render_template(
        "hc/configuracion/municipios_form.html",
        item=item,
        departamentos=departamentos,
        modo="editar"
    )


@bp_hc_configuracion.route("/municipios/toggle/<int:item_id>", methods=["POST"])
def municipio_toggle(item_id):

    item = repo_muni.obtener(item_id)

    nuevo_estado = "INACTIVO" if item["estado"] == "ACTIVO" else "ACTIVO"

    repo_muni.cambiar_estado(item_id, nuevo_estado)

    flash("Estado actualizado.", "success")

    return redirect(url_for("hc_configuracion.municipios"))


# ======================================
# EPS
# ======================================

@bp_hc_configuracion.route("/eps")
def eps():

    items = repo_eps.listar()

    return render_template(
        "hc/configuracion/eps.html",
        items=items
    )


@bp_hc_configuracion.route("/eps/nuevo", methods=["GET","POST"])
def eps_nuevo():

    if request.method == "POST":

        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "nit": request.form.get("nit"),
            "regimen": request.form.get("regimen"),
        }

        repo_eps.crear(data)

        flash("EPS creada correctamente.", "success")
        return redirect(url_for("hc_configuracion.eps"))

    return render_template(
        "hc/configuracion/eps_form.html",
        item={},
        modo="crear"
    )


@bp_hc_configuracion.route("/eps/editar/<int:item_id>", methods=["GET","POST"])
def eps_editar(item_id):

    item = repo_eps.obtener(item_id)

    if request.method == "POST":

        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "nit": request.form.get("nit"),
            "regimen": request.form.get("regimen"),
        }

        repo_eps.actualizar(item_id, data)

        flash("EPS actualizada.", "success")
        return redirect(url_for("hc_configuracion.eps"))

    return render_template(
        "hc/configuracion/eps_form.html",
        item=item,
        modo="editar"
    )


@bp_hc_configuracion.route("/eps/toggle/<int:item_id>", methods=["POST"])
def eps_toggle(item_id):

    item = repo_eps.obtener(item_id)

    nuevo_estado = "INACTIVO" if item["estado"] == "ACTIVO" else "ACTIVO"

    repo_eps.cambiar_estado(item_id, nuevo_estado)

    flash("Estado actualizado.", "success")

    return redirect(url_for("hc_configuracion.eps"))

@bp_hc_configuracion.route("/eps/buscar")
def eps_buscar():
    q = request.args.get("q", "")
    items = repo_eps.buscar(q)
    return jsonify(items)



@bp_hc_configuracion.route("/recursos")
def listar():
    data = repo_recursos.listar()
    return render_template("hc/configuracion/recursos.html", data=data)


# ========================
# NUEVO
# ======================== 

@bp_hc_configuracion.route("/recursos/nuevo", methods=["GET", "POST"])
def nuevo():

    if request.method == "POST":

        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "tipo": request.form.get("tipo"),
            "descripcion": request.form.get("descripcion"),
            "sede_id": request.form.get("sede_id") or None,              # 🔥 nuevo
            "consultorio_id": request.form.get("consultorio_id") or None # 🔥 nuevo
        }

        repo_recursos.crear(data)
        return redirect(url_for("hc_configuracion.listar"))

    # ✅ DEFINIR recurso vacío
    recurso = {
        "codigo": "",
        "nombre": "",
        "tipo": "",
        "descripcion": "",
        "sede_id": None,
        "consultorio_id": None
    }

    return render_template(
        "hc/configuracion/recursos_form.html",
        recurso=recurso,
        modo="crear",
        sedes=repo_sedes.listar(),
        consultorios=repo_cons.listar()
    )


# ========================
# EDITAR
# ========================

@bp_hc_configuracion.route("/recursos/editar/<int:id>", methods=["GET", "POST"])
def editar(id):

    recurso = repo_recursos.obtener(id)

    if request.method == "POST":

        data = {
            "codigo": request.form.get("codigo"),
            "nombre": request.form.get("nombre"),
            "tipo": request.form.get("tipo"),
            "descripcion": request.form.get("descripcion"),

            # 🔥 IMPORTANTE
            "sede_id": request.form.get("sede_id") or None,
            "consultorio_id": request.form.get("consultorio_id") or None
        }

        repo_recursos.actualizar(id, data)
        return redirect(url_for("hc_configuracion.listar"))

    return render_template(
        "hc/configuracion/recursos_form.html",
        recurso=recurso,
        modo="editar",
        sedes=repo_sedes.listar(),        # 🔥 faltaba
        consultorios=repo_cons.listar()   # 🔥 faltaba
    )


# ========================
# TOGGLE
# ========================

@bp_hc_configuracion.route("/recursos/toggle/<int:id>", methods=["POST"])
def toggle(id):
    repo_recursos.toggle(id)
    return redirect(url_for("hc_configuracion.listar"))


# ========================
# AGENDAS LISTAR
# ========================

@bp_hc_configuracion.route("/agendas")
def agendas():

    data = agendas_repo.listar()

    return render_template(
        "hc/configuracion/agendas.html",
        data=data
    )


# ========================
# AGENDAS NUEVO
# ========================

@bp_hc_configuracion.route("/agendas/nuevo", methods=["GET", "POST"])
def agendas_nuevo():

    if request.method == "POST":

        data = {
            "tipo": request.form.get("tipo"),
            "profesional_id": request.form.get("profesional_id") or None,
            "recurso_id": request.form.get("recurso_id") or None,
            "dia_semana": int(request.form.get("dia_semana")),
            "hora_inicio": request.form.get("hora_inicio"),
            "hora_fin": request.form.get("hora_fin"),
            "duracion_min": int(request.form.get("duracion_min")),
        }

        agendas_repo.crear(data)

        return redirect(url_for("hc_configuracion.agendas"))

    return render_template(
        "hc/configuracion/agendas_form.html",
        modo="crear"
    )


# ========================
# AGENDAS TOGGLE
# ========================

@bp_hc_configuracion.route("/agendas/toggle/<int:id>")
def agendas_toggle(id):

    agendas_repo.toggle(id)

    return redirect(url_for("hc_configuracion.agendas"))



# ===============================
# CUPS – listado
# ===============================

@bp_hc_configuracion.route("/cups")
def cups():

    items = repo_cups.listar()

    return render_template(
        "hc/configuracion/cups.html",
        items=items
    )


# ===============================
# CUPS – nuevo (GET formulario)
# ===============================

@bp_hc_configuracion.route("/cups/nuevo")
def cups_nuevo():

    return render_template(
        "hc/configuracion/cups_form.html",
        modo="crear",
        item=None
    )


# ===============================
# CUPS – crear (POST)
# ===============================

@bp_hc_configuracion.route("/cups/crear", methods=["POST"])
def cups_crear():

    data = {
        "codigo":      request.form.get("codigo", "").strip().upper(),
        "descripcion": request.form.get("descripcion", "").strip(),
        "estado":      request.form.get("estado", "ACTIVO"),
    }

    repo_cups.crear(data)

    flash("Procedimiento CUPS creado correctamente.", "success")

    return redirect(url_for("hc_configuracion.cups"))


# ===============================
# CUPS – editar (GET formulario)
# ===============================

@bp_hc_configuracion.route("/cups/<int:item_id>/editar")
def cups_editar(item_id):

    item = repo_cups.obtener(item_id)

    if not item:
        flash("Procedimiento no encontrado.", "error")
        return redirect(url_for("hc_configuracion.cups"))

    return render_template(
        "hc/configuracion/cups_form.html",
        modo="editar",
        item=item
    )


# ===============================
# CUPS – actualizar (POST)
# ===============================

@bp_hc_configuracion.route("/cups/<int:item_id>/actualizar", methods=["POST"])
def cups_actualizar(item_id):

    data = {
        "codigo":      request.form.get("codigo", "").strip().upper(),
        "descripcion": request.form.get("descripcion", "").strip(),
        "estado":      request.form.get("estado", "ACTIVO"),
    }

    repo_cups.actualizar(item_id, data)

    flash("Procedimiento CUPS actualizado.", "success")

    return redirect(url_for("hc_configuracion.cups"))


# ===============================
# CUPS – toggle estado (POST)
# ===============================

@bp_hc_configuracion.route("/cups/toggle/<int:item_id>", methods=["POST"])
def cups_toggle(item_id):

    item = repo_cups.obtener(item_id)

    if not item:
        flash("El procedimiento no existe.", "error")
        return redirect(url_for("hc_configuracion.cups"))

    nuevo_estado = "INACTIVO" if item.get("estado") == "ACTIVO" else "ACTIVO"

    repo_cups.cambiar_estado(item_id, nuevo_estado)

    flash(
        f"Procedimiento {'inactivado' if nuevo_estado == 'INACTIVO' else 'activado'} correctamente.",
        "success"
    )

    return redirect(url_for("hc_configuracion.cups"))


# ===============================
# CUPS – búsqueda AJAX
# ===============================

@bp_hc_configuracion.route("/cups/buscar")
def cups_buscar():

    q = request.args.get("q", "").strip()

    items = repo_cups.buscar(q) if q else []

    return jsonify(items)


# ===============================
# CUPS – exportar CSV
# ===============================

@bp_hc_configuracion.route("/cups/exportar/csv")
def cups_exportar_csv():

    items = repo_cups.listar_todos_exportar()

    def generate():
        header = ["ID", "Código", "Descripción", "Estado"]
        yield ",".join(header) + "\n"
        for row in items:
            line = [
                str(row.get("id", "")),
                row.get("codigo", ""),
                '"' + row.get("descripcion", "").replace('"', '""') + '"',
                row.get("estado", ""),
            ]
            yield ",".join(line) + "\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=cups_export.csv"},
    )


# ===============================
# CUPS – exportar JSON (para PDF
#        lo genera el front con
#        jsPDF desde este endpoint)
# ===============================

@bp_hc_configuracion.route("/cups/exportar/json")
def cups_exportar_json():

    items = repo_cups.listar_todos_exportar()

    return jsonify(items)


# ===============================
# CUPS – importar CSV / Excel
# ===============================

@bp_hc_configuracion.route("/cups/importar", methods=["POST"])
def cups_importar():

    archivo = request.files.get("archivo")

    if not archivo:
        return jsonify({"ok": False, "msg": "No se recibió archivo"}), 400

    nombre = archivo.filename.lower()

    registros = []

    # ── CSV ──────────────────────────────────────────────────────────────────
    if nombre.endswith(".csv"):

        stream = io.StringIO(archivo.stream.read().decode("utf-8-sig"))
        reader = csv.DictReader(stream)

        for fila in reader:

            codigo      = (fila.get("codigo") or fila.get("Código") or "").strip().upper()
            descripcion = (fila.get("descripcion") or fila.get("Descripción") or "").strip()
            estado      = (fila.get("estado") or fila.get("Estado") or "ACTIVO").strip().upper()

            if not codigo or not descripcion:
                continue

            if estado not in ("ACTIVO", "INACTIVO"):
                estado = "ACTIVO"

            registros.append({
                "codigo":      codigo,
                "descripcion": descripcion,
                "estado":      estado,
            })

    # ── Excel (.xlsx / .xls) ─────────────────────────────────────────────────
    elif nombre.endswith(".xlsx") or nombre.endswith(".xls"):

        try:
            import openpyxl
            wb = openpyxl.load_workbook(archivo.stream, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
        except Exception as exc:
            return jsonify({"ok": False, "msg": f"No se pudo leer el Excel: {exc}"}), 400

        if not rows:
            return jsonify({"ok": False, "msg": "El archivo está vacío"}), 400

        # Primera fila = encabezados
        headers = [str(h).strip().lower() if h else "" for h in rows[0]]

        for fila in rows[1:]:

            row_dict = dict(zip(headers, fila))

            codigo      = str(row_dict.get("codigo") or "").strip().upper()
            descripcion = str(row_dict.get("descripcion") or "").strip()
            estado      = str(row_dict.get("estado") or "ACTIVO").strip().upper()

            if not codigo or not descripcion:
                continue

            if estado not in ("ACTIVO", "INACTIVO"):
                estado = "ACTIVO"

            registros.append({
                "codigo":      codigo,
                "descripcion": descripcion,
                "estado":      estado,
            })

    else:
        return jsonify({"ok": False, "msg": "Formato no soportado. Use .csv o .xlsx"}), 400

    if not registros:
        return jsonify({"ok": False, "msg": "No se encontraron registros válidos en el archivo"}), 400

    repo_cups.importar_lote(registros)

    return jsonify({"ok": True, "importados": len(registros)})


# ═══════════════════════════════════════════════════════
#  PROCEDIMIENTOS DE PROFESIONAL (AJAX)
# ═══════════════════════════════════════════════════════

@bp_hc_configuracion.route("/profesionales/<int:prof_id>/procedimientos", methods=["GET"])
def prof_procedimientos_listar(prof_id):
    return jsonify(prof_proc_repo.listar_por_profesional(prof_id))


@bp_hc_configuracion.route("/profesionales/<int:prof_id>/procedimientos/agregar", methods=["POST"])
def prof_procedimientos_agregar(prof_id):
    body = request.get_json()
    try:
        prof_proc_repo.agregar(
            profesional_id = prof_id,
            cups_id        = int(body["cups_id"]),
            duracion_min   = int(body.get("duracion_min", 20)),
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 400


@bp_hc_configuracion.route("/profesionales/procedimientos/<int:id>/duracion", methods=["POST"])
def prof_procedimientos_duracion(id):
    body = request.get_json()
    prof_proc_repo.actualizar_duracion(id, int(body["duracion_min"]))
    return jsonify({"ok": True})


@bp_hc_configuracion.route("/profesionales/procedimientos/<int:id>/eliminar", methods=["POST"])
def prof_procedimientos_eliminar(id):
    prof_proc_repo.eliminar(id)
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════
#  PROCEDIMIENTOS DE RECURSO (AJAX)
# ═══════════════════════════════════════════════════════

@bp_hc_configuracion.route("/recursos/<int:rec_id>/procedimientos", methods=["GET"])
def rec_procedimientos_listar(rec_id):
    return jsonify(rec_proc_repo.listar_por_recurso(rec_id))


@bp_hc_configuracion.route("/recursos/<int:rec_id>/procedimientos/agregar", methods=["POST"])
def rec_procedimientos_agregar(rec_id):
    body = request.get_json()
    try:
        rec_proc_repo.agregar(
            recurso_id   = rec_id,
            cups_id      = int(body["cups_id"]),
            duracion_min = int(body.get("duracion_min", 20)),
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 400


@bp_hc_configuracion.route("/recursos/procedimientos/<int:id>/duracion", methods=["POST"])
def rec_procedimientos_duracion(id):
    body = request.get_json()
    rec_proc_repo.actualizar_duracion(id, int(body["duracion_min"]))
    return jsonify({"ok": True})


@bp_hc_configuracion.route("/recursos/procedimientos/<int:id>/eliminar", methods=["POST"])
def rec_procedimientos_eliminar(id):
    rec_proc_repo.eliminar(id)
    return jsonify({"ok": True})


# ── Buscar CUPS para el selector AJAX ───────────────────
# ── Buscar CUPS para el selector AJAX ───────────────────
@bp_hc_configuracion.route("/cups/buscar-ajax")
def cups_buscar_ajax():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    r = (
        get_supabase_admin()
        .table("hc_cups")
        .select("id,codigo,descripcion")
        .or_(f"codigo.ilike.%{q}%,descripcion.ilike.%{q}%")
        .eq("estado", "ACTIVO")
        .limit(20)
        .execute()
    )
    return jsonify(r.data or [])