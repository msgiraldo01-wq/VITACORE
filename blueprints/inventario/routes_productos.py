# ============================================================================
# Rutas: dashboard, catálogo de productos y principios activos
# ============================================================================
from flask import flash, jsonify, redirect, render_template, request, url_for

from repositories import inventario_repository as repo
from services import inventario_service as svc
from services.inventario_service import InventarioError

from . import contexto_empresa, inventario_bp


# ------------------------------- DASHBOARD ---------------------------------

@inventario_bp.route("/")
@inventario_bp.route("/dashboard")
@contexto_empresa
def dashboard(empresa_id, usuario_id):
    resumen = repo.dashboard(empresa_id) or {}
    movimientos = repo.ultimos_movimientos(empresa_id)
    return render_template("inventario/dashboard.html",
                           resumen=resumen, movimientos=movimientos)


# ------------------------------- PRODUCTOS ---------------------------------

@inventario_bp.route("/productos")
@contexto_empresa
def productos_lista(empresa_id, usuario_id):
    busqueda = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "").strip()
    productos = repo.listar_productos(empresa_id, busqueda, tipo)
    return render_template("inventario/productos/lista.html",
                           productos=productos, busqueda=busqueda, tipo=tipo)


@inventario_bp.route("/productos/nuevo", methods=["GET", "POST"])
@inventario_bp.route("/productos/<producto_id>/editar", methods=["GET", "POST"])
@contexto_empresa
def productos_form(empresa_id, usuario_id, producto_id=None):
    producto = repo.obtener_producto(producto_id) if producto_id else None

    if request.method == "POST":
        try:
            svc.guardar_producto(empresa_id, usuario_id, request.form, producto_id)
            flash("Producto guardado correctamente.", "success")
            return redirect(url_for("inventario.productos_lista"))
        except InventarioError as e:
            flash(str(e), "error")
            producto = dict(request.form)  # conservar lo digitado
            producto["id"] = producto_id

    return render_template(
        "inventario/productos/form.html",
        producto=producto,
        principios=repo.listar_principios(empresa_id),
        formas=svc.FORMAS_FARMACEUTICAS,
        vias=svc.VIAS_ADMINISTRACION,
        unidades=svc.UNIDADES_MEDIDA,
    )


@inventario_bp.route("/api/cum")
@contexto_empresa
def api_buscar_cum(empresa_id, usuario_id):
    """Autocompletar desde el catálogo oficial INVIMA."""
    termino = request.args.get("q", "").strip()
    if len(termino) < 3:
        return jsonify([])
    return jsonify(repo.buscar_cum(termino))


# --------------------------- PRINCIPIOS ACTIVOS ----------------------------

@inventario_bp.route("/principios", methods=["GET", "POST"])
@contexto_empresa
def principios(empresa_id, usuario_id):
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        if not nombre:
            flash("El nombre del principio activo es obligatorio.", "error")
        else:
            try:
                repo.crear_principio(empresa_id, nombre,
                                     request.form.get("codigo_atc", ""), usuario_id)
                flash("Principio activo creado.", "success")
            except Exception:
                flash("Ese principio activo ya existe.", "error")
        return redirect(url_for("inventario.principios"))

    return render_template("inventario/principios/lista.html",
                           principios=repo.listar_principios(empresa_id))


@inventario_bp.route("/principios/<principio_id>/estado", methods=["POST"])
@contexto_empresa
def principios_estado(empresa_id, usuario_id, principio_id):
    nuevo = request.form.get("estado", "INACTIVO")
    repo.cambiar_estado_principio(principio_id, nuevo)
    flash("Estado actualizado.", "success")
    return redirect(url_for("inventario.principios"))
