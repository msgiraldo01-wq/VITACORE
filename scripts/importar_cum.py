# ============================================================================
# VITACORE HMS — Importador del catálogo CUM (INVIMA) a farm_cum_catalogo
#
# Uso (desde la raíz del proyecto, con el venv activo):
#   python scripts/importar_cum.py "C:\ruta\al\archivo_cum.csv"
#
# - Detecta las columnas del CSV automáticamente (el dataset de datos.gov.co
#   cambia de nombres según cómo se exporte: con tildes, espacios, etc.).
# - Arma el CUM como expediente-consecutivo si no viene una columna directa.
# - Deduplica por CUM y sube por lotes de 1000 con upsert (se puede volver a
#   ejecutar sin duplicar nada).
# ============================================================================
import csv
import os
import sys
import unicodedata

sys.path.insert(0, ".")

TAMANO_LOTE = 1000


def _conectar():
    """Devuelve el cliente admin de Supabase, corriendo FUERA de Flask.

    Vía 1: levanta el contexto de la app real y usa get_supabase_admin()
           (la configuración queda idéntica a la de Vitacore en ejecución).
    Vía 2 (si la app no se puede importar): lee SUPABASE_URL y la service key
           directamente del archivo .env y crea el cliente.
    """
    # ── Vía 1: contexto de la aplicación ──
    try:
        from app import app  # tu app.py define `app = Flask(...)`
        from services.supabase_service import get_supabase_admin
        ctx = app.app_context()
        ctx.push()          # queda activo mientras corre el script
        return get_supabase_admin()
    except Exception as e:
        print(f"(No pude usar el contexto de la app: {e}. Leyendo .env directo...)")

    # ── Vía 2: .env directo ──
    valores = {}
    with open(".env", encoding="utf-8-sig") as f:
        for linea in f:
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                valores[k.strip()] = v.strip().strip('"').strip("'")

    url = valores.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    llave = None
    for nombre in ("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY",
                   "SUPABASE_ADMIN_KEY", "SUPABASE_KEY"):
        if valores.get(nombre) or os.environ.get(nombre):
            llave = valores.get(nombre) or os.environ.get(nombre)
            break
    if not url or not llave:
        print("❌ No encontré SUPABASE_URL y la service key en el .env.")
        print("   Llaves encontradas en tu .env:", ", ".join(valores.keys()))
        sys.exit(1)

    from supabase import create_client
    return create_client(url, llave)


def _normalizar(texto: str) -> str:
    """quita tildes, espacios y mayúsculas: 'Vía Administración' -> 'viaadministracion'"""
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower().replace(" ", "").replace("_", "").replace("-", "").strip()


# Posibles nombres (ya normalizados) para cada campo del dataset oficial
MAPA = {
    "cum": ["cum", "codigocum", "codigounicodemedicamento"],
    "expediente": ["expediente", "expedientecum"],
    "consecutivo": ["consecutivocum", "consecutivo", "cantidadcum"],
    "producto": ["producto", "nombreproducto"],
    "descripcion_comercial": ["descripcioncomercial", "presentacion", "descripcion"],
    "titular": ["titular", "nombretitular", "laboratorio"],
    "registro_sanitario": ["registrosanitario", "numeroregistrosanitario", "registro"],
    "principio_activo": ["principioactivo", "principiosactivos"],
    "cantidad_concentracion": ["cantidad", "cantidadconcentracion"],
    "concentracion": ["concentracion"],
    "unidad_medida": ["unidadmedida", "unidad"],
    "forma_farmaceutica": ["formafarmaceutica"],
    "via_administracion": ["viaadministracion", "via"],
    "estado_registro": ["estadoregistro", "estadocum", "estado"],
    "fecha_vencimiento_registro": ["fechavencimiento", "fechavencimientoregistro",
                                   "vencimientoregistrosanitario"],
}


def _detectar_columnas(encabezados):
    normalizados = {_normalizar(h): h for h in encabezados}
    columnas = {}
    for campo, candidatos in MAPA.items():
        for c in candidatos:
            if c in normalizados:
                columnas[campo] = normalizados[c]
                break
    return columnas


def _fecha(valor):
    """Intenta convertir a YYYY-MM-DD; si no puede, devuelve None."""
    valor = (valor or "").strip().split(" ")[0]
    if not valor:
        return None
    for sep, orden in (("-", "ymd"), ("/", "dmy")):
        partes = valor.split(sep)
        if len(partes) == 3:
            try:
                if orden == "ymd" and len(partes[0]) == 4:
                    a, m, d = partes
                elif len(partes[2]) == 4:
                    d, m, a = partes
                else:
                    continue
                return f"{int(a):04d}-{int(m):02d}-{int(d):02d}"
            except ValueError:
                continue
    return None


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/importar_cum.py <ruta_del_csv>")
        sys.exit(1)

    ruta = sys.argv[1]
    sb = _conectar()

    # utf-8-sig tolera el BOM que suele traer el export de datos.gov.co;
    # si el archivo viene en latin-1 (tildes raras), reintenta con esa codificación.
    try:
        archivo = open(ruta, encoding="utf-8-sig", newline="")
        lector = csv.DictReader(archivo)
        encabezados = lector.fieldnames
    except UnicodeDecodeError:
        archivo = open(ruta, encoding="latin-1", newline="")
        lector = csv.DictReader(archivo)
        encabezados = lector.fieldnames

    if not encabezados:
        print("❌ No pude leer los encabezados del CSV.")
        sys.exit(1)

    columnas = _detectar_columnas(encabezados)
    print("Columnas detectadas en el CSV:")
    for campo, col in columnas.items():
        print(f"  {campo:28s} ← {col}")
    faltan = [c for c in ("producto", "principio_activo") if c not in columnas]
    if "cum" not in columnas and "expediente" not in columnas:
        faltan.append("cum (ni expediente para armarlo)")
    if faltan:
        print(f"\n❌ No encontré columnas para: {', '.join(faltan)}")
        print("   Pega aquí los encabezados de tu CSV y ajustamos el MAPA:")
        print("  ", encabezados)
        sys.exit(1)

    def valor(fila, campo):
        col = columnas.get(campo)
        return (fila.get(col) or "").strip() if col else ""

    registros, vistos = {}, 0
    for fila in lector:
        vistos += 1
        cum = valor(fila, "cum")
        if not cum:
            exp = valor(fila, "expediente")
            cons = valor(fila, "consecutivo")
            cum = f"{exp}-{cons}" if exp and cons else exp
        if not cum:
            continue
        # Concentración real = cantidad + unidad de medida (ej. "5 mg").
        # La columna 'concentracion' del dataset oficial NO trae el valor útil.
        cantidad = valor(fila, "cantidad_concentracion")
        unidad = valor(fila, "unidad_medida")
        if cantidad:
            concentracion = f"{cantidad} {unidad}".strip()
        else:
            c = valor(fila, "concentracion")
            concentracion = c if len(c) > 2 else ""   # descarta códigos tipo "A"
        registros[cum] = {  # dict → deduplica por CUM automáticamente
            "cum": cum[:60],
            "producto": valor(fila, "producto")[:300] or None,
            "descripcion_comercial": valor(fila, "descripcion_comercial")[:300] or None,
            "titular": valor(fila, "titular")[:300] or None,
            "registro_sanitario": valor(fila, "registro_sanitario")[:100] or None,
            "principio_activo": valor(fila, "principio_activo")[:300] or None,
            "concentracion": concentracion[:100] or None,
            "unidad_medida": valor(fila, "unidad_medida")[:100] or None,
            "forma_farmaceutica": valor(fila, "forma_farmaceutica")[:150] or None,
            "via_administracion": valor(fila, "via_administracion")[:150] or None,
            "estado_registro": valor(fila, "estado_registro")[:80] or None,
            "fecha_vencimiento_registro": _fecha(valor(fila, "fecha_vencimiento_registro")),
        }
    archivo.close()

    filas = list(registros.values())
    print(f"\nFilas leídas: {vistos:,} → CUM únicos a cargar: {len(filas):,}")
    if not filas:
        print("❌ Nada para cargar."); sys.exit(1)

    cargadas = 0
    for i in range(0, len(filas), TAMANO_LOTE):
        lote = filas[i:i + TAMANO_LOTE]
        sb.table("farm_cum_catalogo").upsert(lote, on_conflict="cum").execute()
        cargadas += len(lote)
        print(f"  ↑ {cargadas:,}/{len(filas):,} cargadas...", end="\r")

    print(f"\n✅ Importación terminada: {cargadas:,} CUM en farm_cum_catalogo.")
    print("Prueba el autocompletar: Catálogo → Nuevo producto → tipo Medicamento →")
    print("escribe 3+ letras en el nombre (ej. 'aceta').")


if __name__ == "__main__":
    main()