import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List

from ...core.database import get_db
from ...core.deps import get_current_user
from ...core.config import settings
from ...models.user import User
from ...models.expediente import Expediente, Archivo, TipoCambio, TipoArchivo, EstadoExpediente
from ...schemas.expediente import (
    ExpedienteCreate, ExpedienteResponse, ExpedienteListItem, ExpedienteUpdate
)

router = APIRouter(prefix="/expedientes", tags=["expedientes"])


@router.get("", response_model=List[ExpedienteListItem])
def listar_expedientes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Expediente).filter(Expediente.user_id == current_user.id).order_by(
        Expediente.created_at.desc()
    ).all()


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
    if exp.user_id != user.id and user.role.value != "ADMIN":
        raise HTTPException(status_code=403, detail="Sin acceso a este expediente")
    return exp
