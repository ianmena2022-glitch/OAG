import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .core.database import engine, Base
from .models import user, expediente  # noqa: F401 — importar para crear tablas
from .api.routes import auth, expedientes, admin, pasos

# Crear tablas
Base.metadata.create_all(bind=engine)

# Crear directorio de uploads
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(expedientes.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(pasos.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}


# Crear usuario admin inicial si no existe
from .core.database import SessionLocal
from .core.auth import get_password_hash
from .models.user import User, UserRole


def create_initial_admin():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if existing:
            print(f"✓ Admin ya existe: {existing.email}")
        else:
            admin = User(
                email="admin@oag.com",
                nombre="Administrador OAG",
                hashed_password=get_password_hash("oag2024"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            print("✓ Usuario admin creado: admin@oag.com / oag2024")
    except Exception as e:
        print(f"✗ Error creando admin: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


create_initial_admin()
