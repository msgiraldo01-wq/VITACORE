import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "hc_sedes.json")


def _ensure_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def _read_all():
    _ensure_file()
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_all(items):
    _ensure_file()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def listar():
    items = _read_all()
    return sorted(items, key=lambda x: ((x.get("estado") != "ACTIVA"), (x.get("nombre") or "").lower()))


def obtener(sede_id: int):
    for item in _read_all():
        if int(item["id"]) == int(sede_id):
            return item
    return None


def existe_codigo(codigo: str, exclude_id: int | None = None):
    codigo = (codigo or "").strip().lower()
    if not codigo:
        return False

    for item in _read_all():
        if exclude_id is not None and int(item["id"]) == int(exclude_id):
            continue
        if (item.get("codigo") or "").strip().lower() == codigo:
            return True
    return False


def crear(data: dict):
    items = _read_all()
    next_id = max([int(x["id"]) for x in items], default=0) + 1

    nuevo = {
        "id": next_id,
        "codigo": (data.get("codigo") or "").strip(),
        "nombre": (data.get("nombre") or "").strip(),
        "ciudad": (data.get("ciudad") or "").strip(),
        "direccion": (data.get("direccion") or "").strip(),
        "telefono": (data.get("telefono") or "").strip(),
        "estado": ((data.get("estado") or "ACTIVA").strip().upper()),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": None,
    }

    items.append(nuevo)
    _write_all(items)
    return nuevo


def actualizar(sede_id: int, data: dict):
    items = _read_all()
    updated = None

    for item in items:
        if int(item["id"]) == int(sede_id):
            item["codigo"] = (data.get("codigo") or "").strip()
            item["nombre"] = (data.get("nombre") or "").strip()
            item["ciudad"] = (data.get("ciudad") or "").strip()
            item["direccion"] = (data.get("direccion") or "").strip()
            item["telefono"] = (data.get("telefono") or "").strip()
            item["estado"] = ((data.get("estado") or "ACTIVA").strip().upper())
            item["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = item
            break

    if updated:
        _write_all(items)

    return updated


def cambiar_estado(sede_id: int, nuevo_estado: str):
    items = _read_all()
    updated = None

    for item in items:
        if int(item["id"]) == int(sede_id):
            item["estado"] = (nuevo_estado or "").strip().upper()
            item["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = item
            break

    if updated:
        _write_all(items)

    return updated