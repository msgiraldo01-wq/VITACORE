import os
from dotenv import load_dotenv # type: ignore

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_TABLE_HC_PROFESIONALES = os.getenv("SUPABASE_TABLE_HC_PROFESIONALES", "hc_profesionales")

    # =========================================================
    # FACTUS — Facturación electrónica (DIAN) — API v2
    # =========================================================
    # FACTUS_ENV: "sandbox" o "production". Empezamos en sandbox.
    FACTUS_ENV = os.getenv("FACTUS_ENV", "sandbox")
    FACTUS_CLIENT_ID = os.getenv("FACTUS_CLIENT_ID", "")
    FACTUS_CLIENT_SECRET = os.getenv("FACTUS_CLIENT_SECRET", "")
    FACTUS_USERNAME = os.getenv("FACTUS_USERNAME", "")
    FACTUS_PASSWORD = os.getenv("FACTUS_PASSWORD", "")
    # Habilita/deshabilita el envío real a Factus sin tocar código
    # (útil para pruebas locales sin quemar consecutivos DIAN).
    FACTUS_HABILITADO = os.getenv("FACTUS_HABILITADO", "true").lower() in ("1", "true", "yes", "si")


GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

