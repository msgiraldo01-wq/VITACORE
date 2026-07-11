# ============================================================================
# Rutas: bodegas
# ============================================================================
from flask import flash, redirect, render_template, request, url_for

from repositories import inventario_repository as repo
from services import inventario_service as svc
from services.inventario_service import InventarioError

from . import contexto_empresa, inventario_bp


@inventario_bp.route("/bodegas", methods=["GET", "POST"])
@contexto_empresa
def bodegas(empresa_id, usuario_id):
    if request.method == "POST":
        bodega_id = request.form.get("bodega_id") or None
        try:
            svc.guardar_bodega(empresa_id, usuario_id, request.form, bodega_id)
            flash("Bodega guardada correctamente.", "success")
        except InventarioError as e:
            flash(str(e), "error")
        except Exception:
            flash("Ya existe una bodega con ese nombre.", "error")
        return redirect(url_for("inventario.bodegas"))

    return render_template("inventario/bodegas/lista.html",
                           bodegas=repo.listar_bodegas(empresa_id),
                           tipos=svc.TIPOS_BODEGA)
