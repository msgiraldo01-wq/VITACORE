from services.supabase_service import get_supabase_admin
from flask import session


def _sb():
    return get_supabase_admin()


def _empresa_id():
    return session.get("empresa_id")


def timeline_paciente(paciente_id: int):

    empresa_id = _empresa_id()

    if not paciente_id or not empresa_id:
        return []

    sb = _sb()

    # 🔒 VALIDAR QUE EL PACIENTE ES DE LA EMPRESA
    valid = (
        sb.table("hc_pacientes")
        .select("id")
        .eq("id", paciente_id)
        .eq("empresa_id", empresa_id)
        .limit(1)
        .execute()
    )

    if not valid.data:
        return []  # 🚫 acceso inválido

    # 🔥 Traemos TODO junto (evolución + signos)
    data = (
        sb.table("hc_evoluciones")
        .select("""
            *,
            medico:hc_profesionales(nombre_completo),
            signos:hc_evolucion_signos(*)
        """)
        .eq("paciente_id", paciente_id)
        .eq("empresa_id", empresa_id)  # 🔥 CLAVE
        .order("fecha", desc=True)
        .execute()
    ).data or []

    timeline = []

    for e in data:

        # ===== EVOLUCION =====
        timeline.append({
            "tipo": "evolucion",
            "fecha": e.get("fecha"),
            "data": {
                "id": e.get("id"),
                "medico": (
                    e.get("medico", {}).get("nombre_completo")
                    if isinstance(e.get("medico"), dict)
                    else "No asignado"
                ),
                "motivo_consulta": e.get("motivo_consulta"),
                "cie10_codigo": e.get("cie10_codigo"),
                "plan": e.get("plan")
            }
        })

        # ===== SIGNOS (HIJOS) =====
        signos = e.get("signos") or []

        for s in signos:
            timeline.append({
                "tipo": "signos",
                "fecha": e.get("fecha"),
                "data": s
            })

    # 🔥 ORDEN FINAL
    timeline.sort(
        key=lambda x: x["fecha"] or "",
        reverse=True
    )

    return timeline