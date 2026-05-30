"""
Logging estructurado por expediente. Lo que se escribe acá lo puede ver
el rol TECNICO en la UI y descargar como archivo.

Por qué un log en DB en vez de leer los prints de stdout de Railway:
  - El soporte/auditor técnico no necesita acceso a Railway.
  - Los logs quedan asociados al expediente que estaba en proceso.
  - Sobreviven a redeploys.
"""
from typing import Optional
from sqlalchemy.orm import Session
from ..models.expediente import LogEvento


def log(
    db: Session,
    *,
    expediente_id: Optional[int] = None,
    user_id: Optional[int] = None,
    paso: Optional[int] = None,
    nivel: str = "info",   # "info" | "warning" | "error"
    evento: str = "",
    mensaje: str = "",
    contexto: Optional[dict] = None,
    duracion_ms: Optional[int] = None,
) -> None:
    """
    Escribe una entrada al log. No falla nunca por error en el commit
    (un log roto no debe tumbar la operación del usuario).
    """
    try:
        entry = LogEvento(
            expediente_id=expediente_id,
            user_id=user_id,
            paso=paso,
            nivel=nivel,
            evento=evento or "log",
            mensaje=(mensaje or "")[:2000],
            contexto=contexto,
            duracion_ms=duracion_ms,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        print(f"[LOGGER] Falló al escribir log: {e}")
        try:
            db.rollback()
        except Exception:
            pass
