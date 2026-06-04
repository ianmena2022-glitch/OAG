"""
Cache de respuestas IA indexado por SHA256(archivo) + identificador de tarea.
Persistido en disco bajo UPLOAD_DIR/_ai_cache/.
"""
import os
import json
import hashlib
from typing import Optional, Any
from ..core.config import settings


def _cache_dir() -> str:
    d = os.path.join(settings.UPLOAD_DIR, "_ai_cache")
    os.makedirs(d, exist_ok=True)
    return d


def file_hash(path: str) -> str:
    """SHA256 del contenido binario del archivo."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def cache_key(task: str, file_path: str, *extras: str) -> str:
    """
    Genera clave de cache para (tarea, archivo, parámetros extra).
    Cualquier cambio en `extras` (schema, exclusiones, etc.) invalida el cache.
    """
    fh = file_hash(file_path)
    extra_combined = "|".join(e for e in extras if e) if extras else ""
    if extra_combined:
        extra_h = hashlib.sha256(extra_combined.encode("utf-8")).hexdigest()[:12]
        return f"{task}_{fh[:16]}_{extra_h}"
    return f"{task}_{fh[:16]}"


def get(key: str) -> Optional[Any]:
    """Lee del cache. Retorna None si no existe."""
    path = os.path.join(_cache_dir(), f"{key}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def put(key: str, value: Any) -> None:
    """Guarda en el cache."""
    path = os.path.join(_cache_dir(), f"{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, default=str)
    except OSError:
        pass  # falla silenciosa: el cache es opcional


def invalidate(key: str) -> None:
    """Elimina una entrada del cache."""
    path = os.path.join(_cache_dir(), f"{key}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
