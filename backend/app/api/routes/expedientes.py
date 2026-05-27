import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List
from pydantic import BaseModel, EmailStr

from ...core.database import get_db
from ...core.deps import get_current_user
from ...core.config import settings
from ...models.user import User
from ...models.expediente import (
    Expediente, Archivo, TipoCambio, TipoArchivo, EstadoExpediente,
    expediente_colaboradores,
)
from ...schemas.expediente import (
    ExpedienteCreate, ExpedienteResponse, ExpedienteListItem, ExpedienteUpdate
)


class ColaboradorInvite(BaseModel):
    email: EmailStr

router = APIRouter(prefix="/expedientes", tags=["expedientes"])


@router.get("", response_model=List[ExpedienteListItem])
def listar_expedientes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Expedientes propios + aquellos en los que es colaborador (Admin ve todos)
    if current_user.role.value == "ADMIN":
        q = db.query(Expediente)
    else:
        # Subquery para los IDs en los que es colaborador
        colab_ids = db.query(expediente_colaboradores.c.expediente_id).filter(
            expediente_colaboradores.c.user_id == current_user.id
        )
        q = db.query(Expediente).filter(
            or_(
                Expediente.user_id == current_user.id,
                Expediente.id.in_(colab_ids),
            )
        )
    return q.order_by(Expediente.created_at.desc()).all()


@router.post("", response_model=ExpedienteResponse)
def crear_expediente(
    data: ExpedienteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = Expediente(
        nombre_distribuidor=data.nombre_distribuidor,
        cuit_distribuidor=data.cuit_distribuidor,
        anio_analisis=data.anio_analisis,
        user_id=current_user.id,
        pasos_completados=[],
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


@router.get("/{exp_id}", response_model=ExpedienteResponse)
def obtener_expediente(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)
    return exp


@router.put("/{exp_id}", response_model=ExpedienteResponse)
def actualizar_expediente(
    exp_id: int,
    data: ExpedienteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(exp, field, value)
    db.commit()
    db.refresh(exp)
    return exp


@router.delete("/{exp_id}")
def eliminar_expediente(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)
    if not _es_owner_o_admin(exp, current_user):
        raise HTTPException(status_code=403, detail="Solo el dueño del expediente puede eliminarlo")
    # Eliminar archivos físicos
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(exp_id))
    if os.path.exists(upload_dir):
        shutil.rmtree(upload_dir)
    db.delete(exp)
    db.commit()
    return {"message": "Expediente eliminado"}


@router.post("/{exp_id}/archivos")
def subir_archivo(
    exp_id: int,
    tipo: TipoArchivo = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)

    upload_dir = os.path.join(settings.UPLOAD_DIR, str(exp_id))
    os.makedirs(upload_dir, exist_ok=True)

    filename = f"{tipo.value}_{file.filename}"
    path = os.path.join(upload_dir, filename)

    with open(path, "wb") as f:
        content = file.file.read()
        f.write(content)
        size = len(content)

    # Eliminar archivo anterior del mismo tipo si existe
    old = db.query(Archivo).filter(
        Archivo.expediente_id == exp_id,
        Archivo.tipo == tipo,
    ).first()
    if old:
        if os.path.exists(old.path):
            os.remove(old.path)
        db.delete(old)

    archivo = Archivo(
        expediente_id=exp_id,
        tipo=tipo,
        nombre_original=file.filename,
        path=path,
        size_bytes=size,
    )
    db.add(archivo)
    db.commit()
    db.refresh(archivo)
    return {"id": archivo.id, "tipo": tipo, "nombre": file.filename, "size": size}


@router.get("/{exp_id}/archivos")
def listar_archivos(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_exp(exp_id, db, current_user)
    archivos = db.query(Archivo).filter(Archivo.expediente_id == exp_id).all()
    return [
        {
            "id": a.id,
            "tipo": a.tipo,
            "nombre_original": a.nombre_original,
            "size_bytes": a.size_bytes,
            "created_at": a.created_at,
        }
        for a in archivos
    ]


def _get_exp(exp_id: int, db: Session, user: User) -> Expediente:
    exp = db.query(Expediente).filter(Expediente.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expediente no encontrado")
    if exp.user_id == user.id:
        return exp
    if user.role.value == "ADMIN":
        return exp
    # Verificar si es colaborador
    es_colab = db.query(expediente_colaboradores).filter(
        expediente_colaboradores.c.expediente_id == exp_id,
        expediente_colaboradores.c.user_id == user.id,
    ).first()
    if es_colab:
        return exp
    raise HTTPException(status_code=403, detail="Sin acceso a este expediente")


def _es_owner_o_admin(exp: Expediente, user: User) -> bool:
    """Solo el dueño o un admin pueden invitar/remover colaboradores y eliminar el expediente."""
    return exp.user_id == user.id or user.role.value == "ADMIN"


# ── Colaboradores ────────────────────────────────────────────────────────────

@router.get("/{exp_id}/colaboradores")
def listar_colaboradores(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)
    # Info del dueño
    owner = db.query(User).filter(User.id == exp.user_id).first()
    # Lista de colaboradores con metadata
    rows = db.query(
        User, expediente_colaboradores.c.invited_at, expediente_colaboradores.c.invited_by
    ).join(
        expediente_colaboradores, User.id == expediente_colaboradores.c.user_id
    ).filter(
        expediente_colaboradores.c.expediente_id == exp_id
    ).all()

    return {
        "owner": {
            "id": owner.id,
            "email": owner.email,
            "nombre": owner.nombre,
        } if owner else None,
        "soy_owner": exp.user_id == current_user.id,
        "soy_admin": current_user.role.value == "ADMIN",
        "colaboradores": [
            {
                "id": u.id,
                "email": u.email,
                "nombre": u.nombre,
                "role": u.role.value,
                "invited_at": invited_at.isoformat() if invited_at else None,
            }
            for (u, invited_at, _invited_by) in rows
        ],
    }


@router.post("/{exp_id}/colaboradores")
def invitar_colaborador(
    exp_id: int,
    data: ColaboradorInvite,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)
    if not _es_owner_o_admin(exp, current_user):
        raise HTTPException(status_code=403, detail="Solo el dueño puede invitar colaboradores")

    target = db.query(User).filter(User.email == data.email).first()
    if not target:
        raise HTTPException(status_code=404, detail=f"No existe un usuario con email {data.email}")
    if not target.is_active:
        raise HTTPException(status_code=400, detail="El usuario está deshabilitado")
    if target.id == exp.user_id:
        raise HTTPException(status_code=400, detail="El usuario ya es dueño de este expediente")

    # Verificar si ya es colaborador
    ya_existe = db.query(expediente_colaboradores).filter(
        expediente_colaboradores.c.expediente_id == exp_id,
        expediente_colaboradores.c.user_id == target.id,
    ).first()
    if ya_existe:
        raise HTTPException(status_code=400, detail=f"{data.email} ya es colaborador de este expediente")

    db.execute(
        expediente_colaboradores.insert().values(
            expediente_id=exp_id,
            user_id=target.id,
            invited_by=current_user.id,
        )
    )
    db.commit()

    return {
        "message": f"{target.nombre} ({target.email}) agregado como colaborador",
        "colaborador": {
            "id": target.id,
            "email": target.email,
            "nombre": target.nombre,
            "role": target.role.value,
        },
    }


@router.delete("/{exp_id}/colaboradores/{user_id}")
def remover_colaborador(
    exp_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)
    # Permitir: el dueño / un admin / el propio colaborador (auto-removerse)
    if not (_es_owner_o_admin(exp, current_user) or current_user.id == user_id):
        raise HTTPException(status_code=403, detail="Sin permiso para remover este colaborador")

    result = db.execute(
        expediente_colaboradores.delete().where(
            expediente_colaboradores.c.expediente_id == exp_id,
            expediente_colaboradores.c.user_id == user_id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="El usuario no era colaborador")
    db.commit()
    return {"message": "Colaborador removido"}
