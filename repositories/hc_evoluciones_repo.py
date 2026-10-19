from typing import Any, Optional
from services.supabase_service import get_supabase_admin
from services import auditoria_service


def _table_name():
    return "hc_evoluciones"


def _sb():
    return get_supabase_admin()


# =========================
# NORMALIZAR
# =========================

def _normalize(row: Optional[dict]) -> Optional[dict]:
    """Normaliza una evolución con relaciones (signos + alertas)"""

    
    if not row:
        return None

    # =========================
    # RELACIONES
    # =========================
    medico_rel = row.get("medico") if isinstance(row.get("medico"), dict) else None

    signos = row.get("signos") or []
    alertas = row.get("alertas") or []

    signo = signos[0] if signos else {}
    alerta = alertas[0] if alertas else {}

    # =========================
    # NORMALIZACIÓN
    # =========================
    return {
        "id": row.get("id"),
        "paciente_id": row.get("paciente_id"),
        "fecha": row.get("fecha"),
        "tipo_atencion": row.get("tipo_atencion"),

        # =========================
        # SUBJETIVO
        # =========================
        "motivo_consulta": row.get("motivo_consulta") or "",
        "enfermedad_actual": row.get("enfermedad_actual") or "",

        # 🔥 ALERTAS (tabla hc_evolucion_alertas)
        "antecedentes": alerta.get("antecedentes") or "",
        "alergias": alerta.get("alergias") or "",

        # =========================
        # OBJETIVO
        # =========================
        "examen_fisico": row.get("examen_fisico") or "",
        "examen_sistemas": row.get("examen_sistemas") or "",

        # 🔥 SIGNOS (tabla hc_evolucion_signos)
        "ta": signo.get("ta"),
        "fc": signo.get("fc"),
        "fr": signo.get("fr"),
        "temperatura": signo.get("temperatura"),
        "peso": signo.get("peso"),
        "talla": signo.get("talla"),
        "imc": signo.get("imc"),
        "spo2": signo.get("saturacion_oxigeno"),

        # =========================
        # ANÁLISIS
        # =========================
        "cie10_codigo": row.get("cie10_codigo"),
        "cie10_nombre": row.get("cie10_nombre") or "",
        "diagnosticos_secundarios": row.get("diagnosticos_secundarios") or "",
        "impresion_diagnostica": row.get("impresion_diagnostica") or "",
        "resultados_paraclinicos": row.get("resultados_paraclinicos") or "",

        # =========================
        # PLAN
        # =========================
        "plan": row.get("plan") or "",
        "recomendaciones": row.get("recomendaciones") or "",
        "proximo_control_fecha": row.get("proximo_control_fecha"),
        "proximo_control_tipo": row.get("proximo_control_tipo") or "",

        # =========================
        # MÉDICO
        # =========================
        "medico_id": row.get("medico_id"),
        "medico_nombre": medico_rel.get("nombre_completo") if medico_rel else "",

        # =========================
        # METADATA
        # =========================
        "estado": row.get("estado") or "ACTIVO",
        "created_at": row.get("created_at"),
        "created_by": row.get("created_by"),

        # =========================
        # AUDITORÍA
        # =========================
        "usuario_creacion": row.get("usuario_creacion"),
        "usuario_creacion_id": row.get("usuario_creacion_id"),
        "fecha_creacion": row.get("fecha_creacion"),
        "ip_privada": row.get("ip_privada"),
        "ip_publica": row.get("ip_publica"),

        # =========================
        # ANULACIÓN (nunca se borra: se marca)
        # =========================
        "anulada": bool(row.get("anulada")),
        "anulada_motivo": row.get("anulada_motivo"),
        "anulada_por": row.get("anulada_por"),
        "anulada_en": row.get("anulada_en"),
        "reemplazada_por_id": row.get("reemplazada_por_id"),
        "rda_composition_id": row.get("rda_composition_id"),
        "rda_pendiente_ministerio": bool(row.get("rda_pendiente_ministerio")),
    }
    

    

# =========================
# OBTENER PACIENTE (CORREGIDO)
# =========================

def obtener_paciente(paciente_id: int) -> Optional[dict]:
    if not paciente_id:
        return None
    try:
        r = (
            _sb()
            .table("hc_pacientes")
            .select("""
                *,
                hc_tipos_documento:tipo_documento_id(nombre)
            """)
            .eq("id", paciente_id)
            .limit(1)
            .execute()
        )
        if not r or not hasattr(r, 'data') or not r.data:
            return None

        paciente = r.data[0]
        if not paciente:
            return None

        # Calcular edad desde fecha_nacimiento
        edad = None
        fn = paciente.get("fecha_nacimiento")
        if fn:
            try:
                from datetime import date, datetime
                if isinstance(fn, str):
                    fn = datetime.strptime(fn[:10], "%Y-%m-%d").date()
                hoy = date.today()
                edad = hoy.year - fn.year - (
                    (hoy.month, hoy.day) < (fn.month, fn.day)
                )
            except Exception:
                pass

        # Tipo documento desde join
        tipo_doc_rel = paciente.get("hc_tipos_documento")
        tipo_doc = (tipo_doc_rel.get("nombre") if isinstance(tipo_doc_rel, dict) else None) or "CC"

        return {
            "id": paciente.get("id"),
            "nombres": f"{paciente.get('primer_nombre', '')} {paciente.get('segundo_nombre', '')}".strip(),
            "apellidos": f"{paciente.get('primer_apellido', '')} {paciente.get('segundo_apellido', '')}".strip(),
            "primer_nombre": paciente.get("primer_nombre", ""),
            "segundo_nombre": paciente.get("segundo_nombre", ""),
            "primer_apellido": paciente.get("primer_apellido", ""),
            "segundo_apellido": paciente.get("segundo_apellido", ""),
            "tipo_documento": tipo_doc,
            "numero_documento": paciente.get("numero_documento", ""),
            "sexo": paciente.get("sexo", ""),
            "edad": edad,
            "fecha_nacimiento": paciente.get("fecha_nacimiento"),
            "tipo_sangre": paciente.get("tipo_sangre", ""),
            "celular": paciente.get("celular", ""),
            "telefono": paciente.get("telefono", ""),
            "email": paciente.get("email", ""),
            "direccion": paciente.get("direccion", ""),
            "eps_nombre": paciente.get("eps_nombre") or paciente.get("aseguradora", ""),
            "aseguradora": paciente.get("aseguradora", ""),
            "regimen_afiliacion": paciente.get("regimen_afiliacion", ""),  # ✅ agregado
            "ocupacion": paciente.get("ocupacion", ""),
            "zona": paciente.get("zona", ""),
            "estado_civil": paciente.get("estado_civil", ""),
            "grupo_poblacional": paciente.get("grupo_poblacional", ""),
            "nivel_educativo": paciente.get("nivel_educativo", ""),
            "contacto_emergencia_nombre": paciente.get("contacto_emergencia_nombre", ""),
            "contacto_emergencia_telefono": paciente.get("contacto_emergencia_telefono", ""),
            "alergias": paciente.get("alergias", ""),
            "created_at": paciente.get("created_at")
        }

    except Exception as e:
        print(f"Error obteniendo paciente {paciente_id}: {e}")
        return None

# =========================
# LISTAR EVOLUCIONES POR PACIENTE
# =========================

def listar_por_paciente(paciente_id: int) -> list:
    """Lista todas las evoluciones de un paciente"""
    if not paciente_id:
        return []

    try:
        r = (
            _sb()
            .table(_table_name())
            .select("""
                *,
                medico:hc_profesionales(id, nombre_completo),
                signos:hc_evolucion_signos(*),
                alertas:hc_evolucion_alertas(*)
            """)
            .eq("paciente_id", paciente_id)
            .order("fecha", desc=True)
            .execute()
        )

        if not r or not hasattr(r, 'data') or not r.data:
            return []

        return [_normalize(row) for row in r.data if row]

    except Exception as e:
        print(f"Error listando evoluciones: {e}")
        return []


# =========================
# OBTENER EVOLUCION
# =========================

def obtener(evolucion_id: int) -> Optional[dict]:
    """Obtiene una evolución específica"""
    if not evolucion_id:
        return None

    try:
        r = (
            _sb()
            .table(_table_name())
            .select("""
                *,
                medico:hc_profesionales(id, nombre_completo),
                signos:hc_evolucion_signos(*),
                alertas:hc_evolucion_alertas(*)
            """)
            .eq("id", evolucion_id)
            .limit(1)
            .execute()
        )

        if not r or not hasattr(r, 'data') or not r.data:
            return None

        return _normalize(r.data[0])

    except Exception as e:
        print(f"Error obteniendo evolución {evolucion_id}: {e}")
        return None


# =========================
# CREAR EVOLUCION
# =========================
def crear(data: dict) -> Optional[dict]:
    """Crea una nueva evolución (sin alertas ni signos embebidos)"""


    required = [
        "paciente_id", "medico_id", "motivo_consulta",
        "enfermedad_actual", "impresion_diagnostica", "plan"
    ]

    for field in required:
        if not data.get(field):
            raise ValueError(f"Campo requerido: {field}")

    try:
        # empresa_id: sin esto la evolucion queda huerfana y no aparece en
        # ninguna consulta filtrada por empresa (dashboard, recientes,
        # resumen de historia clinica). Mismo patron que hc_citas_repo.crear().
        from flask import session
        empresa_id = data.get("empresa_id") or session.get("empresa_id")

        insert_data = {
            "empresa_id": int(empresa_id) if empresa_id else None,
            "paciente_id": data.get("paciente_id"),
            "medico_id": data.get("medico_id"),
            "tipo_atencion": data.get("tipo_atencion", "CONSULTA_EXTERNA"),
            "sede_id": data.get("sede_id") or None,
            "servicio": (data.get("servicio") or "").strip() or None,

            # SUBJETIVO
            "motivo_consulta": (data.get("motivo_consulta") or "").strip(),
            "enfermedad_actual": (data.get("enfermedad_actual") or "").strip(),

            # OBJETIVO
            "examen_fisico": (data.get("examen_fisico") or "").strip() or None,
            "examen_sistemas": (data.get("examen_sistemas") or "").strip() or None,

            # ANÁLISIS
            "cie10_codigo": data.get("cie10_codigo") or None,
            "cie10_nombre": (data.get("cie10_nombre") or "").strip() or None,
            "diagnosticos_secundarios": (data.get("diagnosticos_secundarios") or "").strip() or None,
            "impresion_diagnostica": (data.get("impresion_diagnostica") or "").strip(),
            "resultados_paraclinicos": (data.get("resultados_paraclinicos") or "").strip() or None,

            # PLAN
            "plan": (data.get("plan") or "").strip(),
            "recomendaciones": (data.get("recomendaciones") or "").strip() or None,
            "proximo_control_fecha": data.get("proximo_control_fecha") or None,
            "proximo_control_tipo": (data.get("proximo_control_tipo") or "").strip() or None,
            "destino_paciente": (data.get("destino_paciente") or "").strip() or None,

            # RDA (Resolución 1888)
            "causa_externa_codigo": data.get("causa_externa_codigo") or None,
            "tipo_diagnostico_codigo": data.get("tipo_diagnostico_codigo") or None,
            "cups_id": data.get("cups_id") or None,
            "entorno_codigo": data.get("entorno_codigo") or None,

            # METADATA
            "estado": "ACTIVO",
            "created_by": data.get("created_by"),

            # Quién la registró y desde dónde. Una cita ya guardaba esto;
            # la nota clínica, que es el documento que hay que poder
            # atribuir, no guardaba nada.
            **auditoria_service.datos_de_creacion(),
        }

        try:
            r = (
                _sb()
                .table(_table_name())
                .insert(insert_data)
                .execute()
            )
        except Exception as e:
            # Si la migración de auditoría todavía no se ha corrido, esas
            # columnas no existen y el insert falla. Registrar una atención
            # no se puede caer por eso: se reintenta sin los campos de
            # auditoría y queda constancia en el log.
            campos_auditoria = ("usuario_creacion", "usuario_creacion_id",
                                "ip_privada", "ip_publica")
            if not any(c in str(e) for c in campos_auditoria):
                raise
            print("[EVOLUCIONES] faltan las columnas de auditoría "
                  "(¿migración sin correr?); se guarda la evolución sin ellas:", e)
            for c in campos_auditoria:
                insert_data.pop(c, None)
            r = (
                _sb()
                .table(_table_name())
                .insert(insert_data)
                .execute()
            )

        if not r or not hasattr(r, 'data') or not r.data:
            return None

        return _normalize(r.data[0])

    except Exception as e:
        print(f"Error creando evolución: {e}")
        raise



# =========================
# BUSCAR CIE10
# =========================

def listar_cie10(q: str = "") -> list:
    """Busca códigos CIE10"""
    if not q or len(q) < 2:
        return []

    try:
        r = (
            _sb()
            .table("hc_cie10")
            .select("codigo, nombre")
            .or_(f"codigo.ilike.%{q}%,nombre.ilike.%{q}%")
            .order("codigo")
            .limit(30)
            .execute()
        )

        if not r or not hasattr(r, 'data'):
            return []

        return r.data or []

    except Exception as e:
        print(f"Error buscando CIE10: {e}")
        return []


# =========================
# LISTAR MEDICOS
# =========================

def listar_medicos() -> list:
    """Lista todos los médicos activos"""
    try:
        r = (
            _sb()
            .table("hc_profesionales")
            .select("id, nombre_completo")
            .eq("estado", "ACTIVO")
            .order("nombre_completo")
            .execute()
        )

        if not r or not hasattr(r, 'data'):
            return []

        return r.data or []

    except Exception as e:
        print(f"Error listando médicos: {e}")
        return []
    

# Agregar arriba del archivo, junto a los demás imports:
# from flask import session   (si no está ya importado)


# =========================
# LISTAR EVOLUCIONES RECIENTES (toda la IPS)
# =========================

def listar_recientes(limite: int = 20) -> list:
    """Lista las evoluciones más recientes de la empresa activa, con datos
    básicos del paciente y del médico. Para la pantalla de inicio de
    Historia Clínica (/hc/historia-clinica).

    NOTA: filtra por empresa_id. crear() ya guarda ese campo, pero las
    evoluciones registradas ANTES de ese arreglo lo tienen en NULL y no
    aparecen aquí. Para recuperarlas hay que rellenarlo una vez en la base
    (UPDATE hc_evoluciones SET empresa_id = <id> WHERE empresa_id IS NULL)."""
    from flask import session

    empresa_id = session.get("empresa_id")
    if not empresa_id:
        return []

    try:
        r = (
            _sb()
            .table(_table_name())
            .select("""
                id, paciente_id, fecha, motivo_consulta, cie10_codigo, cie10_nombre,
                medico:hc_profesionales(id, nombre_completo),
                paciente:hc_pacientes(id, primer_nombre, segundo_nombre, primer_apellido, segundo_apellido, numero_documento)
            """)
            .eq("empresa_id", empresa_id)
            .order("fecha", desc=True)
            .limit(limite)
            .execute()
        )

        if not r or not hasattr(r, 'data') or not r.data:
            return []

        out = []
        for row in r.data:
            pac = row.get("paciente") or {}
            med = row.get("medico") or {}
            nombre_pac = " ".join(filter(None, [
                pac.get("primer_nombre"), pac.get("segundo_nombre"),
                pac.get("primer_apellido"), pac.get("segundo_apellido"),
            ])) or "Paciente"

            out.append({
                "id": row.get("id"),
                "paciente_id": row.get("paciente_id"),
                "paciente_nombre": nombre_pac,
                "paciente_documento": pac.get("numero_documento") or "",
                "fecha": row.get("fecha"),
                "motivo_consulta": row.get("motivo_consulta") or "",
                "cie10_codigo": row.get("cie10_codigo") or "",
                "cie10_nombre": row.get("cie10_nombre") or "",
                "medico_nombre": med.get("nombre_completo") or "",
            })
        return out

    except Exception as e:
        print(f"Error listando evoluciones recientes: {e}")
        return []
    
def resumen_evoluciones() -> dict:
    """Conteos rápidos para las tarjetas de la pantalla de Historia Clínica:
    evoluciones de hoy, de esta semana, y pacientes distintos atendidos."""
    from flask import session
    from datetime import date, timedelta

    empresa_id = session.get("empresa_id")
    if not empresa_id:
        return {"hoy": 0, "semana": 0, "pacientes_atendidos": 0}

    try:
        hoy = date.today()
        inicio_semana = hoy - timedelta(days=hoy.weekday())

        r_hoy = (
            _sb().table(_table_name())
            .select("id", count="exact")
            .eq("empresa_id", empresa_id)
            .gte("fecha", hoy.isoformat())
            .execute()
        )
        r_semana = (
            _sb().table(_table_name())
            .select("id", count="exact")
            .eq("empresa_id", empresa_id)
            .gte("fecha", inicio_semana.isoformat())
            .execute()
        )
        r_pac = (
            _sb().table(_table_name())
            .select("paciente_id")
            .eq("empresa_id", empresa_id)
            .execute()
        )
        pacientes_unicos = len({row["paciente_id"] for row in (r_pac.data or []) if row.get("paciente_id")})

        return {
            "hoy": r_hoy.count or 0,
            "semana": r_semana.count or 0,
            "pacientes_atendidos": pacientes_unicos,
        }
    except Exception as e:
        print(f"Error calculando resumen de evoluciones: {e}")
        return {"hoy": 0, "semana": 0, "pacientes_atendidos": 0}


# =========================
# ANULACIÓN
# =========================

def anular(evolucion_id: int, motivo: str, reemplazada_por_id: int = None) -> Optional[dict]:
    """
    Marca una evolución como anulada. NO la borra ni la edita.

    La Resolución 1995 de 1999 no admite enmendaduras en la historia
    clínica: lo que se corrige se corrige por adición. Por eso aquí la
    nota original queda intacta y solo se le agrega el registro de que
    fue anulada, por quién, cuándo y por qué.

    Si esa evolución ya había viajado al Ministerio como RDA, se guarda
    el composition_id y se marca rda_pendiente_ministerio. Ni la
    Resolución 1888 de 2025 ni el manual de operaciones del IHCE
    contemplan retirar un RDA ya aceptado, así que lo único que se puede
    hacer hoy es dejar constancia de cuáles habría que corregir el día
    que exista el procedimiento.
    """
    if not evolucion_id:
        return None
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("La anulación exige un motivo.")

    actual = obtener(evolucion_id)
    if not actual:
        return None
    if actual.get("anulada"):
        raise ValueError("Esa evolución ya está anulada.")

    usuario, usuario_id = auditoria_service.usuario_actual()
    ip_privada, ip_publica = auditoria_service.clasificar_ips()

    # ¿ya se le había enviado un RDA aceptado al Ministerio?
    composition_id, pendiente = None, False
    try:
        envios = (
            _sb().table("rda_envios")
            .select("composition_id, estado")
            .eq("evolucion_id", evolucion_id)
            .eq("estado", "aceptado")
            .limit(1)
            .execute()
        ).data or []
        if envios:
            composition_id = envios[0].get("composition_id")
            pendiente = True
    except Exception as e:
        # que no se pueda consultar el RDA no puede impedir anular una
        # nota clínica: se deja constancia y se sigue.
        print(f"[EVOLUCIONES] no se pudo consultar el RDA de {evolucion_id}: {e}")

    datos = {
        "anulada": True,
        "anulada_motivo": motivo,
        "anulada_por": usuario,
        "anulada_por_id": usuario_id,
        "anulada_en": datetime.now(timezone.utc).isoformat(),
        "anulada_ip": ip_publica or ip_privada,
        "rda_composition_id": composition_id,
        "rda_pendiente_ministerio": pendiente,
    }
    if reemplazada_por_id:
        datos["reemplazada_por_id"] = reemplazada_por_id

    r = _sb().table(_table_name()).update(datos).eq("id", evolucion_id).execute()
    return _normalize((r.data or [None])[0])


def listar_rda_pendientes_ministerio(limite: int = 200) -> list:
    """
    Evoluciones anuladas aquí cuyo RDA sigue en el Ministerio.

    Es la lista que habrá que corregir allá cuando el Ministerio defina
    el procedimiento. Mientras tanto, sirve para saber de cuántas se
    trata y poder sustentarlas ante una auditoría.
    """
    from flask import session
    empresa_id = session.get("empresa_id")
    try:
        q = (
            _sb().table(_table_name())
            .select("id, paciente_id, fecha, anulada_motivo, anulada_por, "
                    "anulada_en, rda_composition_id")
            .eq("rda_pendiente_ministerio", True)
            .order("anulada_en", desc=True)
            .limit(limite)
        )
        if empresa_id:
            q = q.eq("empresa_id", empresa_id)
        return q.execute().data or []
    except Exception as e:
        print(f"[EVOLUCIONES] no se pudieron listar los RDA pendientes: {e}")
        return []
