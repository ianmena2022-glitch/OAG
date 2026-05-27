from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import pandas as pd
import io
import os
import tempfile
import unicodedata


def _norm(s: str) -> str:
    """Elimina acentos y pasa a minúsculas para comparación flexible."""
    return unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode('ascii').lower().strip()

from ...core.database import get_db
from ...core.deps import get_current_user, require_admin
from ...core.auth import get_password_hash
from ...models.user import User
from ...models.expediente import MaestroSyngenta, Glosario
from ...schemas.auth import UserCreate, UserResponse
from ...ai.smart_parser import parsear_excel


MAESTRO_SCHEMA = {
    "nombre_estandar": ["nombre estandar", "nombre estándar", "descripción homogénea",
                        "descripcion homogenea", "nombre producto", "producto",
                        "descripción producto", "descripcion producto",
                        "descripción", "descripcion", "nombre", "articulo", "artículo"],
    "codigo": ["código", "codigo", "cod", "sku", "id"],
    "principio_activo": ["principio activo", "principio", "activo"],
    "categoria": ["categoría", "categoria", "categ", "tipo"],
}

GLOSARIO_SCHEMA = {
    "nombre_original": ["nombre original", "original", "articulo facturado",
                        "artículo facturado", "facturado", "nombre factura",
                        "producto factura", "nombre ds", "ds"],
    "nombre_estandar": ["nombre estandar", "nombre estándar", "glosario",
                       "nombre glosario", "estandar", "estándar",
                       "nombre normalizado", "normalizado"],
}


def _guardar_temp(content: bytes, suffix: str = ".xlsx") -> str:
    """Guarda bytes a un archivo temporal, retorna el path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    return path

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Usuarios ────────────────────────────────────────────────────────────────

@router.get("/usuarios", response_model=list[UserResponse])
def listar_usuarios(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    return db.query(User).all()


@router.post("/usuarios", response_model=UserResponse)
def crear_usuario(
    data: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    from sqlalchemy import func
    email_norm = (data.email or "").strip().lower()
    if db.query(User).filter(func.lower(User.email) == email_norm).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    user = User(
        email=email_norm,
        nombre=data.nombre,
        hashed_password=get_password_hash(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/usuarios/{user_id}/estado")
def toggle_usuario(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.is_active = not user.is_active
    db.commit()
    return {"id": user.id, "is_active": user.is_active}


# ── Maestro Syngenta ─────────────────────────────────────────────────────────

@router.post("/maestro-syngenta")
def cargar_maestro_syngenta(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Carga/actualiza el maestro de productos Syngenta desde un Excel.
    Usa smart_parser para detectar las columnas con IA si los keywords fallan.
    """
    content = file.file.read()
    tmp_path = _guardar_temp(content)
    try:
        resultado = parsear_excel(
            path=tmp_path,
            task_id="maestro_syngenta",
            schema=MAESTRO_SCHEMA,
            columnas_criticas=["nombre_estandar"],
        )
        df = resultado["df"]
        mapping = resultado["mapping"]
        col_nombre = mapping.get("nombre_estandar") or df.columns[0]
        col_codigo = mapping.get("codigo")
        col_pa = mapping.get("principio_activo")
        col_cat = mapping.get("categoria")

        # Marcar todos los anteriores como inactivos
        db.query(MaestroSyngenta).update({"is_active": False})

        count = 0
        for _, row in df.iterrows():
            nombre = str(row.get(col_nombre, "")).strip()
            if not nombre or nombre.lower() == "nan":
                continue
            item = MaestroSyngenta(
                codigo=str(row.get(col_codigo, "")).strip() if col_codigo else None,
                nombre_estandar=nombre,
                principio_activo=str(row.get(col_pa, "")).strip() if col_pa else None,
                categoria=str(row.get(col_cat, "")).strip() if col_cat else None,
                is_active=True,
            )
            db.add(item)
            count += 1

        db.commit()
        return {
            "message": f"Maestro actualizado: {count} productos cargados",
            "count": count,
            "mapping": mapping,
            "metodo_deteccion": resultado["metodo"],
            "confianza": resultado["confianza"],
            "warnings": resultado["warnings"],
            "columnas_archivo": resultado.get("columnas_archivo", []),
            "columnas_faltantes": resultado.get("columnas_faltantes", []),
            "columnas_no_mapeadas": resultado.get("columnas_no_mapeadas", []),
        }
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@router.get("/maestro-syngenta")
def obtener_maestro_syngenta(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    items = db.query(MaestroSyngenta).filter(MaestroSyngenta.is_active == True).all()
    return [
        {
            "id": i.id,
            "codigo": i.codigo,
            "nombre_estandar": i.nombre_estandar,
            "principio_activo": i.principio_activo,
            "categoria": i.categoria,
        }
        for i in items
    ]


# ── Glosario ─────────────────────────────────────────────────────────────────

@router.post("/glosario")
def cargar_glosario(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    Carga el glosario de productos desde un Excel.
    Usa smart_parser para detectar columnas (nombre_original → nombre_estandar).
    """
    content = file.file.read()
    tmp_path = _guardar_temp(content)
    try:
        resultado = parsear_excel(
            path=tmp_path,
            task_id="glosario",
            schema=GLOSARIO_SCHEMA,
            columnas_criticas=["nombre_original", "nombre_estandar"],
        )
        df = resultado["df"]
        mapping = resultado["mapping"]
        col_orig = mapping.get("nombre_original")
        col_est = mapping.get("nombre_estandar")

        # Fallback: si la IA tampoco encontró, usar primera y segunda columnas
        if not col_orig or not col_est:
            if len(df.columns) >= 2:
                col_orig = col_orig or df.columns[0]
                col_est = col_est or df.columns[1]
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Se requieren columnas nombre_original y nombre_estandar",
                )

        db.query(Glosario).update({"is_active": False})
        db.flush()

        registros = []
        for _, row in df.iterrows():
            orig = str(row.get(col_orig, "")).strip()
            est = str(row.get(col_est, "")).strip()
            if not orig or not est or orig.lower() == "nan" or est.lower() == "nan":
                continue
            registros.append({"nombre_original": orig, "nombre_estandar": est, "is_active": True})

        if registros:
            db.bulk_insert_mappings(Glosario, registros)

        db.commit()
        count = len(registros)
        return {
            "message": f"Glosario actualizado: {count} entradas cargadas",
            "count": count,
            "mapping": mapping,
            "metodo_deteccion": resultado["metodo"],
            "confianza": resultado["confianza"],
            "warnings": resultado["warnings"],
            "columnas_archivo": resultado.get("columnas_archivo", []),
            "columnas_faltantes": resultado.get("columnas_faltantes", []),
            "columnas_no_mapeadas": resultado.get("columnas_no_mapeadas", []),
        }
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@router.get("/glosario")
def obtener_glosario(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    total = db.query(Glosario).filter(Glosario.is_active == True).count()
    items = db.query(Glosario).filter(Glosario.is_active == True).limit(200).all()
    return {
        "total": total,
        "items": [{"nombre_original": i.nombre_original, "nombre_estandar": i.nombre_estandar} for i in items],
    }
