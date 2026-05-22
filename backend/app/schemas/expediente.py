from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from ..models.expediente import EstadoExpediente, TipoArchivo


class ExpedienteCreate(BaseModel):
    nombre_distribuidor: str
    cuit_distribuidor: str
    anio_analisis: int


class ExpedienteUpdate(BaseModel):
    nombre_distribuidor: Optional[str] = None
    cuit_distribuidor: Optional[str] = None
    anio_analisis: Optional[int] = None
    estado: Optional[EstadoExpediente] = None


class ArchivoResponse(BaseModel):
    id: int
    tipo: TipoArchivo
    nombre_original: str
    size_bytes: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class TipoCambioResponse(BaseModel):
    fecha: str
    cotizacion_usd: float


class ExpedienteResponse(BaseModel):
    id: int
    nombre_distribuidor: str
    cuit_distribuidor: str
    anio_analisis: int
    estado: EstadoExpediente
    paso_actual: int
    pasos_completados: List[int]
    created_at: datetime
    updated_at: Optional[datetime]
    archivos: List[ArchivoResponse] = []

    class Config:
        from_attributes = True


class ExpedienteListItem(BaseModel):
    id: int
    nombre_distribuidor: str
    cuit_distribuidor: str
    anio_analisis: int
    estado: EstadoExpediente
    paso_actual: int
    pasos_completados: List[int]
    created_at: datetime

    class Config:
        from_attributes = True
