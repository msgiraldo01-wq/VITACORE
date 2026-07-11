# ============================================================================
# Rutas: entradas/salidas manuales, existencias y kardex
# ============================================================================
from flask import flash, redirect, render_template, request, url_for

from repositories import inventario_repository as repo
from services import inventario_service as svc
from services.inventario_service import InventarioError

from . import contexto_empresa, inventario_bp


@inventario_bp.route("/movimientos/entrada", methods=["GET", "POST"])
@contexto_empresa
def entrada(empresa_id, usuario_id):
    if request.method == "POST":
        try:
            resultado = svc.registrar_entrada_manual(empresa_id, usuario_id, request.form)
            flash(f"Entrada registrada. Saldo resultante: {resultado.get('saldo_resultante')} "
                  f"— Costo promedio: ${resultado.get('costo_promedio'):,.2f}", "success")
            return redirect(url_for("inventario.entrada"))
        except InventarioError as e:
            flash(str(e), "error")

    return render_template("inventario/movimientos/entrada.html",
                           bodegas=repo.listar_bodegas(empresa_id, solo_activas=True),
                           productos=repo.listar_productos(empresa_id),
                           tipos=svc.TIPOS_ENTRADA_MANUAL)


@inventario_bp.route("/movimientos/salida", methods=["GET", "POST"])
@contexto_empresa
def salida(empresa_id, usuario_id):
    if request.method == "POST":
        try:
            resultado = svc.registrar_salida_manual(empresa_id, usuario_id, request.form)
            lotes = ", ".join(f"{d['lote']} ({d['cantidad']})"
                              for d in resultado.get("lotes_afectados", []))
            flash(f"Salida registrada (FEFO). Lotes afectados: {lotes}", "success")
            return redirect(url_for("inventario.salida"))
        except InventarioError as e:
            flash(str(e), "error")

    return render_template("inventario/movimientos/salida.html",
                           bodegas=repo.listar_bodegas(empresa_id, solo_activas=True),
                           productos=repo.listar_productos(empresa_id),
                           tipos=svc.TIPOS_SALIDA_MANUAL)


@inventario_bp.route("/existencias")
@contexto_empresa
def existencias(empresa_id, usuario_id):
    bodega_id = request.args.get("bodega_id", "")
    filas = repo.existencias(empresa_id, bodega_id)
    return render_template("inventario/existencias/lista.html",
                           filas=filas,
                           bodegas=repo.listar_bodegas(empresa_id),
                           bodega_id=bodega_id)


@inventario_bp.route("/kardex")
@contexto_empresa
def kardex(empresa_id, usuario_id):
    producto_id = request.args.get("producto_id", "")
    bodega_id = request.args.get("bodega_id", "")
    movimientos = repo.kardex(empresa_id, producto_id, bodega_id) if producto_id else []
    return render_template("inventario/kardex/kardex.html",
                           movimientos=movimientos,
                           productos=repo.listar_productos(empresa_id),
                           bodegas=repo.listar_bodegas(empresa_id),
                           producto_id=producto_id, bodega_id=bodega_id)


@inventario_bp.route("/movimientos")
@contexto_empresa
def movimientos_lista(empresa_id, usuario_id):
    filtros = {
        "desde": request.args.get("desde", ""),
        "hasta": request.args.get("hasta", ""),
        "tipo": request.args.get("tipo", ""),
        "bodega_id": request.args.get("bodega_id", ""),
    }
    movimientos = repo.movimientos_filtrados(empresa_id, **filtros)
    tipos_todos = svc.TIPOS_ENTRADA_MANUAL + svc.TIPOS_SALIDA_MANUAL + (
        "ENTRADA_COMPRA", "ENTRADA_TRASLADO", "SALIDA_TRASLADO", "SALIDA_DISPENSACION")
    return render_template("inventario/movimientos/lista.html",
                           movimientos=movimientos, filtros=filtros,
                           bodegas=repo.listar_bodegas(empresa_id),
                           tipos=sorted(tipos_todos))
