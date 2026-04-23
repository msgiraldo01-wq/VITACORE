import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "hc_consultorios.json")


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
    return sorted(
        items,
        key=lambda x: (
            (x.get("estado") != "ACTIVO"),
            str(x.get("sede_nombre") or "").lower(),
            str(x.get("nombre") or "").lower(),
        )
    )


def obtener(item_id: int):
    for item in _read_all():
        if int(item["id"]) == int(item_id):
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
        "sede_id": int(data.get("sede_id")) if data.get("sede_id") else None,
        "sede_nombre": (data.get("sede_nombre") or "").strip(),
        "codigo": (data.get("codigo") or "").strip().upper(),
        "nombre": (data.get("nombre") or "").strip(),
        "piso": (data.get("piso") or "").strip(),
        "descripcion": (data.get("descripcion") or "").strip(),
        "estado": ((data.get("estado") or "ACTIVO").strip().upper()),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": None,
    }

    items.append(nuevo)
    _write_all(items)
    return nuevo


def actualizar(item_id: int, data: dict):
    items = _read_all()
    updated = None

    for item in items:
        if int(item["id"]) == int(item_id):
            item["sede_id"] = int(data.get("sede_id")) if data.get("sede_id") else None
            item["sede_nombre"] = (data.get("sede_nombre") or "").strip()
            item["codigo"] = (data.get("codigo") or "").strip().upper()
            item["nombre"] = (data.get("nombre") or "").strip()
            item["piso"] = (data.get("piso") or "").strip()
            item["descripcion"] = (data.get("descripcion") or "").strip()
            item["estado"] = ((data.get("estado") or "ACTIVO").strip().upper())
            item["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = item
            break

    if updated:
        _write_all(items)

    return updated


def cambiar_estado(item_id: int, nuevo_estado: str):
    items = _read_all()
    updated = None

    for item in items:
        if int(item["id"]) == int(item_id):
            item["estado"] = (nuevo_estado or "").strip().upper()
            item["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = item
            break

    if updated:
        _write_all(items)

    return updated