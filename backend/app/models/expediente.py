import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, JSON, Date, Float, Boolean, Table
from sqlalchemy.orm import relationship
from ..core.database import Base


# Tabla de asociación many-to-many entre Expediente y User (colaboradores invitados)
expediente_colaboradores = Table(
    "expediente_colaboradores",
    Base.metadata,
    Column("expediente_id", Integer, ForeignKey("expedientes.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("invited_at", DateTime, default=datetime.utcnow),
    Column("invited_by", Integer, ForeignKey("users.id"), nullable=True),
)


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
    colaboradores = relationship(
        "User",
        secondary=expediente_colaboradores,
        primaryjoin="Expediente.id == expediente_colaboradores.c.expediente_id",
        secondaryjoin="User.id == expediente_colaboradores.c.user_id",
    )


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


class LogEvento(Base):
    """
    Log estructurado por expediente. Captura qué pasó en cada paso
    (ejecución, duración, archivos procesados, mappings detectados, errores).
    Pensado para que el rol TECNICO pueda debuggear sin pedir acceso al server.
    """
    __tablename__ = "logs_evento"

    id            = Column(Integer, primary_key=True, index=True)
    expediente_id = Column(Integer, ForeignKey("expedientes.id", ondelete="CASCADE"),
                          nullable=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    paso          = Column(Integer, nullable=True)              # 1..6 o null
    nivel         = Column(String(20), default="info", nullable=False)  # info|warning|error
    evento        = Column(String(100), nullable=False)         # tag corto: "paso_ejecutado"
    mensaje       = Column(String(2000), nullable=False)        # texto humano
    contexto      = Column(JSON, nullable=True)                 # datos estructurados
    duracion_ms   = Column(Integer, nullable=True)              # si aplica
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class AnotacionConciliacion(Base):
    """
    Anotaciones manuales del auditor sobre comprobantes de la conciliación.
    Una por (expediente, paso, comprobante_key). Persiste entre sesiones.

    Uso principal: completar datos faltantes en SOLO_ARCA (gestión no encontró
    el comprobante) y clasificar si es o no agroquímico para el Paso 2.
    """
    __tablename__ = "anotaciones_conciliacion"

    id            = Column(Integer, primary_key=True, index=True)
    expediente_id = Column(Integer, ForeignKey("expedientes.id", ondelete="CASCADE"), nullable=False, index=True)
    paso          = Column(Integer, nullable=False, default=1)
    # Clave del comprobante en la conciliación, ej: "FC-00001-00000034"
    comprobante_key = Column(String(100), nullable=False)

    # Datos del comprobante (readonly desde ARCA, completables manualmente)
    tipo    = Column(String(10), nullable=True)
    numero  = Column(String(30), nullable=True)
    fecha   = Column(String(20), nullable=True)

    # Datos de Gestión ingresados manualmente
    cliente          = Column(String(500), nullable=True)
    monto_gestion_usd = Column(Float, nullable=True)

    # Clasificación agroquímico
    es_agroquimico = Column(Boolean, nullable=True)   # None = sin responder
    producto       = Column(String(500), nullable=True)
    cantidad       = Column(Float, nullable=True)
    unidad         = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
