import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, JSON, Date, Float, Boolean
from sqlalchemy.orm import relationship
from ..core.database import Base


class EstadoExpediente(str, enum.Enum):
    BORRADOR = "BORRADOR"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADO = "COMPLETADO"


class TipoArchivo(str, enum.Enum):
    BAJADA_GESTION = "BAJADA_GESTION"
    COMPROBANTES_EMITIDOS = "COMPROBANTES_EMITIDOS"
    COMPROBANTES_RECIBIDOS = "COMPROBANTES_RECIBIDOS"
    TIPOS_CAMBIO = "TIPOS_CAMBIO"
    CRM = "CRM"
    MAESTRO_SYNGENTA = "MAESTRO_SYNGENTA"
    GLOSARIO = "GLOSARIO"
    CLIENTES_ESPECIALES = "CLIENTES_ESPECIALES"
    PROVEEDORES_APERTURA = "PROVEEDORES_APERTURA"


class Expediente(Base):
    __tablename__ = "expedientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre_distribuidor = Column(String(255), nullable=False)
    cuit_distribuidor = Column(String(20), nullable=False)
    anio_analisis = Column(Integer, nullable=False)
    estado = Column(Enum(EstadoExpediente), default=EstadoExpediente.BORRADOR)
    paso_actual = Column(Integer, default=1)
    pasos_completados = Column(JSON, default=list)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    archivos = relationship("Archivo", back_populates="expediente", cascade="all, delete-orphan")
    tipos_cambio = relationship("TipoCambio", back_populates="expediente", cascade="all, delete-orphan")
    resultados = relationship("ResultadoPaso", back_populates="expediente", cascade="all, delete-orphan")


class Archivo(Base):
    __tablename__ = "archivos"

    id = Column(Integer, primary_key=True, index=True)
    expediente_id = Column(Integer, ForeignKey("expedientes.id"), nullable=False)
    tipo = Column(Enum(TipoArchivo), nullable=False)
    nombre_original = Column(String(500), nullable=False)
    path = Column(String(1000), nullable=False)
    size_bytes = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    expediente = relationship("Expediente", back_populates="archivos")


class TipoCambio(Base):
    __tablename__ = "tipos_cambio"

    id = Column(Integer, primary_key=True, index=True)
    expediente_id = Column(Integer, ForeignKey("expedientes.id"), nullable=False)
    fecha = Column(Date, nullable=False)
    cotizacion_usd = Column(Float, nullable=False)

    expediente = relationship("Expediente", back_populates="tipos_cambio")


class ResultadoPaso(Base):
    __tablename__ = "resultados_pasos"

    id = Column(Integer, primary_key=True, index=True)
    expediente_id = Column(Integer, ForeignKey("expedientes.id"), nullable=False)
    paso = Column(Integer, nullable=False)
    subtipo = Column(String(100), nullable=False)
    datos = Column(JSON, nullable=True)
    archivo_path = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    expediente = relationship("Expediente", back_populates="resultados")


class MaestroSyngenta(Base):
    __tablename__ = "maestro_syngenta"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(100), nullable=True)
    nombre_estandar = Column(String(500), nullable=False)
    principio_activo = Column(String(500), nullable=True)
    categoria = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Glosario(Base):
    __tablename__ = "glosario"

    id = Column(Integer, primary_key=True, index=True)
    nombre_original = Column(String(500), nullable=False)
    nombre_estandar = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
