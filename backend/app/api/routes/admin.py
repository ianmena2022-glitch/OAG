from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import pandas as pd
import io

from ...core.database import get_db
from ...core.deps import get_current_user, require_admin
from ...core.auth import get_password_hash
from ...models.user import User
from ...models.expediente import MaestroSyngenta, Glosario
from ...schemas.auth import UserCreate, UserResponse

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
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    user = User(
        email=data.email,
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
    Columnas esperadas: código (opcional), nombre_estandar, principio_activo (opcional), categoría (opcional).
    """
    content = file.file.read()
    df = pd.read_excel(io.BytesIO(content), dtype=str)

    # Detectar columna de nombre
    cols_lower = {c.lower(): c for c in df.columns}
    col_nombre = None
    for kw in ["nombre", "producto", "descripcion", "estandar"]:
        for cl, co in cols_lower.items():
            if kw in cl:
                col_nombre = co
                break
        if col_nombre:
            break

    if not col_nombre:
        raise HTTPException(status_code=400, detail="No se encontró columna de nombre de producto")

    col_codigo = next((co for cl, co in cols_lower.items() if "codigo" in cl or "código" in cl), None)
    col_pa = next((co for cl, co in cols_lower.items() if "principio" in cl or "activo" in cl), None)
    col_cat = next((co for cl, co in cols_lower.items() if "categor" in cl), None)

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
    return {"message": f"Maestro actualizado: {count} productos cargados"}


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
    Columnas esperadas: nombre_original, nombre_estandar.
    """
    content = file.file.read()
    df = pd.read_excel(io.BytesIO(content), dtype=str)

    cols_lower = {c.lower(): c for c in df.columns}
    col_orig = next((co for cl, co in cols_lower.items() if "original" in cl), None)
    col_est = next((co for cl, co in cols_lower.items() if "estandar" in cl or "estándar" in cl), None)

    if not col_orig or not col_est:
        if len(df.columns) >= 2:
            col_orig = df.columns[0]
            col_est = df.columns[1]
        else:
            raise HTTPException(status_code=400, detail="Se requieren columnas nombre_original y nombre_estandar")

    db.query(Glosario).update({"is_active": False})

    count = 0
    for _, row in df.iterrows():
        orig = str(row.get(col_orig, "")).strip()
        est = str(row.get(col_est, "")).strip()
        if not orig or not est:
            continue
        db.add(Glosario(nombre_original=orig, nombre_estandar=est, is_active=True))
        count += 1

    db.commit()
    return {"message": f"Glosario actualizado: {count} entradas cargadas"}


@router.get("/glosario")
def obtener_glosario(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    items = db.query(Glosario).filter(Glosario.is_active == True).all()
    return [{"nombre_original": i.nombre_original, "nombre_estandar": i.nombre_estandar} for i in items]
