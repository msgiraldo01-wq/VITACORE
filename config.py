import os
from dotenv import load_dotenv # type: ignore

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_TABLE_HC_PROFESIONALES = os.getenv("SUPABASE_TABLE_HC_PROFESIONALES", "hc_profesionales")

    # IA para el análisis de glosas (blueprints/bp_financiero/glosas/glosas.py).
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

    # Factus — facturación electrónica ante la DIAN
    # (repositories/fin_factus_repo.py, blueprints/bp_financiero/facturacion/routes.py).
    FACTUS_ENV = os.getenv("FACTUS_ENV", "sandbox")
    FACTUS_CLIENT_ID = os.getenv("FACTUS_CLIENT_ID", "")
    FACTUS_CLIENT_SECRET = os.getenv("FACTUS_CLIENT_SECRET", "")
    FACTUS_USERNAME = os.getenv("FACTUS_USERNAME", "")
    FACTUS_PASSWORD = os.getenv("FACTUS_PASSWORD", "")
    FACTUS_HABILITADO = os.getenv("FACTUS_HABILITADO", "true").strip().lower() == "true"

    # Correos al paciente (crear/confirmar/cancelar/reprogramar cita) vía Resend.
    # Si cualquiera de las dos falta, email_service simplemente no envía nada
    # (lo deja registrado en consola) sin romper la acción sobre la cita.
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")

    # Dominio público real de la app (p. ej. https://vitacore.cloud, SIN
    # slash al final), para armar el enlace de confirmar/cancelar que va
    # en esos correos. Si se deja vacío, se usa request.host_url como
    # respaldo (el host con el que el navegador del personal llegó a la
    # app -- útil en desarrollo, pero un localhost/IP interna no le sirve
    # de nada a un paciente real, así que en producción esto SIEMPRE debe
    # quedar configurado).
    APP_BASE_URL = os.getenv("APP_BASE_URL", "")

