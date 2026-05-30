import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from ..core.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    AUDITOR = "AUDITOR"
    # TECNICO: rol para soporte/debugging. Tiene los mismos permisos que ADMIN
    # PLUS acceso a los logs detallados de ejecución por expediente.
    TECNICO = "TECNICO"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    nombre = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.AUDITOR, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
