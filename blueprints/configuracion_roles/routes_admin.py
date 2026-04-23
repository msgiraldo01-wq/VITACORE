from flask import Blueprint, current_app, jsonify
from services.supabase_service import get_supabase_admin
from blueprints.auth.decorators import rol_required, login_required

bp_admin = Blueprint("admin_tools", __name__, url_prefix="/admin")


@bp_admin.route("/sync_rutas")
@login_required
@rol_required(usar_matriz=True)
def sync_rutas():
    supabase = get_supabase_admin()

    rutas_guardadas = []

    for rule in current_app.url_map.iter_rules():

        endpoint = rule.endpoint
        ruta = str(rule)
        metodos = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))

        # ignorar estáticos
        if endpoint.startswith("static"):
            continue

        data = {
            "endpoint": endpoint,
            "ruta": ruta,
            "metodos": metodos
        }

        try:
            supabase.table("rutas").upsert(data, on_conflict="endpoint").execute()
            rutas_guardadas.append(endpoint)
        except Exception as e:
            print("Error guardando ruta:", endpoint, e)

    return jsonify({
        "status": "ok",
        "rutas_sincronizadas": len(rutas_guardadas)
    })