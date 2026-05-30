"""
Endpoints de logs para el rol TECNICO.
Listar y descargar los eventos registrados por expediente.
"""
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.deps import require_tecnico
from ...models.user import User
from ...models.expediente import LogEvento, Expediente


router = APIRouter(prefix="/expedientes/{exp_id}/logs", tags=["logs"])


def _get_exp(exp_id: int, db: Session) -> Expediente:
    exp = db.query(Expediente).filter(Expediente.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "Expediente no encontrado")
    return exp


@router.get("")
def listar_logs(
    exp_id: int,
    limit: int = 500,
    db: Session = Depends(get_db),
    _user: User = Depends(require_tecnico),
):
    """
    Devuelve los últimos N eventos del expediente, más reciente primero.
    """
    _get_exp(exp_id, db)
    rows = (
        db.query(LogEvento)
        .filter(LogEvento.expediente_id == exp_id)
        .order_by(LogEvento.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "user_id": r.user_id,
            "paso": r.paso,
            "nivel": r.nivel,
            "evento": r.evento,
            "mensaje": r.mensaje,
            "contexto": r.contexto,
            "duracion_ms": r.duracion_ms,
        }
        for r in rows
    ]


@router.get("/descargar")
def descargar_logs(
    exp_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_tecnico),
):
    """
    Descarga TODOS los eventos del expediente como archivo .txt
    legible (cronológico ascendente). Pensado para mandar por mail
    a soporte o adjuntar a un ticket.
    """
    exp = _get_exp(exp_id, db)
    rows = (
        db.query(LogEvento)
        .filter(LogEvento.expediente_id == exp_id)
        .order_by(LogEvento.created_at.asc())
        .all()
    )

    buf = io.StringIO()
    buf.write(f"OGSA Auditorías — Log del expediente #{exp_id}\n")
    buf.write(f"Distribuidor: {exp.nombre_distribuidor} (CUIT {exp.cuit_distribuidor})\n")
    buf.write(f"Año de análisis: {exp.anio_analisis}\n")
    buf.write(f"Generado: {datetime.utcnow().isoformat()}Z\n")
    buf.write(f"Total eventos: {len(rows)}\n")
    buf.write("=" * 80 + "\n\n")

    for r in rows:
        ts = r.created_at.isoformat() if r.created_at else ""
        nivel = (r.nivel or "info").upper().ljust(7)
        paso_s = f"P{r.paso}" if r.paso else "  "
        dur = f" ({r.duracion_ms}ms)" if r.duracion_ms is not None else ""
        buf.write(f"[{ts}] {nivel} {paso_s} {r.evento}{dur}\n")
        if r.mensaje:
            for ln in str(r.mensaje).splitlines():
                buf.write(f"          {ln}\n")
        if r.contexto:
            try:
                ctx = json.dumps(r.contexto, ensure_ascii=False, indent=2, default=str)
                for ln in ctx.splitlines():
                    buf.write(f"          {ln}\n")
            except Exception:
                buf.write(f"          (contexto no serializable)\n")
        buf.write("\n")

    buf.seek(0)
    filename = f"OAG_log_exp{exp_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8")]),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
