"""
Rutas unificadas para ejecutar los 6 pasos de auditoría.
"""
import os
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from ...core.database import get_db
from ...core.deps import get_current_user
from ...models.user import User
from ...models.expediente import (
    Expediente, Archivo, ResultadoPaso, MaestroSyngenta, Glosario,
    AnotacionConciliacion, TipoArchivo, EstadoExpediente
)
from ...services import paso1_service, paso2_service, paso3_service
from ...services import paso4_service, paso5_service, paso6_service
from ...ai.validator import validar_paso

router = APIRouter(prefix="/expedientes/{exp_id}/pasos", tags=["pasos"])


def _get_exp(exp_id, db, user):
    exp = db.query(Expediente).filter(Expediente.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "Expediente no encontrado")
    if exp.user_id != user.id and user.role.value != "ADMIN":
        raise HTTPException(403, "Sin acceso")
    return exp


def _get_archivo_path(exp_id, tipo, db) -> str:
    a = db.query(Archivo).filter(
        Archivo.expediente_id == exp_id,
        Archivo.tipo == tipo,
    ).first()
    if not a:
        raise HTTPException(400, f"Archivo {tipo.value} no cargado")
    if not os.path.exists(a.path):
        raise HTTPException(
            400,
            f"El archivo {tipo.value} se perdió del servidor (probablemente por un "
            f"redeploy). Volvé a subirlo desde el expediente."
        )
    return a.path


def _save_resultado(db, exp_id, paso, subtipo, datos=None, archivo_path=None):
    existing = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == paso,
        ResultadoPaso.subtipo == subtipo,
    ).first()
    if existing:
        existing.datos = datos
        existing.archivo_path = archivo_path
    else:
        db.add(ResultadoPaso(
            expediente_id=exp_id,
            paso=paso,
            subtipo=subtipo,
            datos=datos,
            archivo_path=archivo_path,
        ))
    db.commit()


def _marcar_paso_completado(exp, paso, db):
    completados = exp.pasos_completados or []
    if paso not in completados:
        completados.append(paso)
    exp.pasos_completados = completados
    exp.paso_actual = max(completados) + 1 if completados else 1
    if 6 in completados:
        exp.estado = EstadoExpediente.COMPLETADO
    elif completados:
        exp.estado = EstadoExpediente.EN_PROCESO
    db.commit()


# ── PASO 1 ────────────────────────────────────────────────────────────────────

@router.post("/1/ejecutar")
def ejecutar_paso1(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)

    # Múltiples archivos de Bajada de Gestión
    archivos_bajada = db.query(Archivo).filter(
        Archivo.expediente_id == exp_id,
        Archivo.tipo == TipoArchivo.BAJADA_GESTION,
    ).order_by(Archivo.created_at).all()
    if not archivos_bajada:
        raise HTTPException(400, "No hay archivos de Bajada de Gestión cargados")
    paths_bajada = []
    for a in archivos_bajada:
        if not os.path.exists(a.path):
            raise HTTPException(
                400,
                f"El archivo '{a.nombre_original}' se perdió del servidor "
                f"(probablemente por un redeploy). Volvé a subirlo desde el expediente."
            )
        paths_bajada.append((a.path, a.nombre_original))

    path_emitidos = _get_archivo_path(exp_id, TipoArchivo.COMPROBANTES_EMITIDOS, db)
    path_tc = _get_archivo_path(exp_id, TipoArchivo.TIPOS_CAMBIO, db)

    try:
        resultado = paso1_service.ejecutar_paso1(paths_bajada, path_emitidos, path_tc, exp_id)
    except Exception as e:
        raise HTTPException(500, f"Error en Paso 1: {str(e)}")

    _save_resultado(db, exp_id, 1, "conciliacion", datos=resultado["conciliacion"])
    _save_resultado(db, exp_id, 1, "resumen", datos=resultado["resumen"])
    _save_resultado(db, exp_id, 1, "bajada_normalizada",
                    archivo_path=resultado["bajada_normalizada_path"])
    _save_resultado(db, exp_id, 1, "validacion", datos=resultado.get("validacion"))
    _save_resultado(db, exp_id, 1, "parser_diagnostico",
                    datos={"items": resultado.get("parser_diagnostico", [])})
    _marcar_paso_completado(exp, 1, db)

    return {
        "resumen": resultado["resumen"],
        "conciliacion": resultado["conciliacion"][:500],  # Limitar para respuesta API
        "total_registros": len(resultado["conciliacion"]),
        "validacion": resultado.get("validacion"),
        "parser_diagnostico": resultado.get("parser_diagnostico", []),
    }


@router.get("/1/resultado")
def resultado_paso1(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_exp(exp_id, db, current_user)
    res = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == 1,
    ).all()
    if not res:
        raise HTTPException(404, "Paso 1 no ejecutado aún")

    datos = {r.subtipo: r.datos for r in res}

    # Mergear anotaciones manuales en la conciliación
    anotaciones = db.query(AnotacionConciliacion).filter(
        AnotacionConciliacion.expediente_id == exp_id,
        AnotacionConciliacion.paso == 1,
    ).all()

    if anotaciones and datos.get("conciliacion"):
        anot_idx = {a.comprobante_key: a for a in anotaciones}
        conciliacion = datos["conciliacion"]
        for row in conciliacion:
            key = row.get("key")
            if key and key in anot_idx:
                a = anot_idx[key]
                # Aplicar campos editados
                if a.cliente is not None:
                    row["cliente"] = a.cliente
                if a.monto_gestion_usd is not None:
                    row["monto_usd_gestion"] = a.monto_gestion_usd
                    row["diferencia_usd"] = round(
                        a.monto_gestion_usd - (row.get("monto_usd_arca") or 0), 2
                    )
                # Estado: MANUAL si había monto_gestion o es_agroquimico respondido
                row["estado"] = "MANUAL"
                # Datos de anotación para el frontend
                row["anotacion"] = {
                    "es_agroquimico": a.es_agroquimico,
                    "producto": a.producto,
                    "cantidad": a.cantidad,
                    "unidad": a.unidad,
                    "cliente": a.cliente,
                    "monto_gestion_usd": a.monto_gestion_usd,
                }
        datos["conciliacion"] = conciliacion

    return datos


# ── Schema y endpoint de anotaciones ──────────────────────────────────────────

class AnotacionPayload(BaseModel):
    tipo: Optional[str] = None
    numero: Optional[str] = None
    fecha: Optional[str] = None
    cliente: Optional[str] = None
    monto_gestion_usd: Optional[float] = None
    es_agroquimico: Optional[bool] = None
    producto: Optional[str] = None
    cantidad: Optional[float] = None
    unidad: Optional[str] = None


@router.put("/1/anotaciones/{key:path}")
def guardar_anotacion(
    exp_id: int,
    key: str,
    payload: AnotacionPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea o actualiza la anotación manual de un comprobante de la conciliación."""
    _get_exp(exp_id, db, current_user)

    anot = db.query(AnotacionConciliacion).filter(
        AnotacionConciliacion.expediente_id == exp_id,
        AnotacionConciliacion.paso == 1,
        AnotacionConciliacion.comprobante_key == key,
    ).first()

    if anot is None:
        anot = AnotacionConciliacion(
            expediente_id=exp_id,
            paso=1,
            comprobante_key=key,
        )
        db.add(anot)

    # Actualizar campos provistos
    for field in ("tipo", "numero", "fecha", "cliente", "monto_gestion_usd",
                  "es_agroquimico", "producto", "cantidad", "unidad"):
        val = getattr(payload, field)
        if val is not None:
            setattr(anot, field, val)

    db.commit()
    db.refresh(anot)
    return {"ok": True, "key": key}


@router.get("/1/anotaciones")
def listar_anotaciones(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_exp(exp_id, db, current_user)
    anotaciones = db.query(AnotacionConciliacion).filter(
        AnotacionConciliacion.expediente_id == exp_id,
        AnotacionConciliacion.paso == 1,
    ).all()
    return [
        {
            "key": a.comprobante_key,
            "tipo": a.tipo,
            "numero": a.numero,
            "fecha": a.fecha,
            "cliente": a.cliente,
            "monto_gestion_usd": a.monto_gestion_usd,
            "es_agroquimico": a.es_agroquimico,
            "producto": a.producto,
            "cantidad": a.cantidad,
            "unidad": a.unidad,
        }
        for a in anotaciones
    ]


# ── PASO 2 ────────────────────────────────────────────────────────────────────

@router.post("/2/ejecutar")
def ejecutar_paso2(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)

    # Verificar Paso 1 completado
    if 1 not in (exp.pasos_completados or []):
        raise HTTPException(400, "Completar Paso 1 antes de ejecutar Paso 2")

    # Obtener bajada normalizada
    bajada_res = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == 1,
        ResultadoPaso.subtipo == "bajada_normalizada",
    ).first()
    if not bajada_res or not bajada_res.archivo_path:
        raise HTTPException(400, "Bajada normalizada no disponible")

    # Maestro Syngenta
    maestro = db.query(MaestroSyngenta).filter(MaestroSyngenta.is_active == True).all()
    maestro_nombres = [m.nombre_estandar for m in maestro]

    # Clientes especiales (opcional)
    clientes_especiales = []
    arch_esp = db.query(Archivo).filter(
        Archivo.expediente_id == exp_id,
        Archivo.tipo == TipoArchivo.CLIENTES_ESPECIALES,
    ).first()
    if arch_esp:
        import pandas as pd
        df_esp = pd.read_excel(arch_esp.path, dtype=str)
        col = df_esp.columns[0]
        clientes_especiales = df_esp[col].dropna().str.strip().str.upper().tolist()

    try:
        resultado = paso2_service.ejecutar_paso2(
            bajada_res.archivo_path,
            maestro_nombres,
            clientes_especiales,
            exp_id,
            exp.anio_analisis,
        )
    except Exception as e:
        raise HTTPException(500, f"Error en Paso 2: {str(e)}")

    _save_resultado(db, exp_id, 2, "ranking_clientes", datos=resultado["ranking_clientes"])
    _save_resultado(db, exp_id, 2, "ranking_productos", datos=resultado["ranking_productos"])
    _save_resultado(db, exp_id, 2, "muestreo", datos=resultado["muestreo"])
    _save_resultado(db, exp_id, 2, "clasificacion", datos=resultado["clasificacion"])
    _save_resultado(db, exp_id, 2, "tabla_apertura", datos=resultado["tabla_apertura"])
    _save_resultado(db, exp_id, 2, "agroquimicos", archivo_path=resultado["agroquimicos_path"])
    _save_resultado(db, exp_id, 2, "totales", datos=resultado["totales"])

    # Validación IA
    validacion = validar_paso(2, resultado["totales"], muestra=resultado["ranking_clientes"][:5])
    _save_resultado(db, exp_id, 2, "validacion", datos=validacion)
    _marcar_paso_completado(exp, 2, db)

    return {
        "totales": resultado["totales"],
        "ranking_clientes_top10": resultado["ranking_clientes"][:10],
        "ranking_productos_top10": resultado["ranking_productos"][:10],
        "muestreo": resultado["muestreo"],
        "tabla_apertura": resultado["tabla_apertura"][:50],
        "validacion": validacion,
    }


@router.get("/2/resultado")
def resultado_paso2(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_exp(exp_id, db, current_user)
    res = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == 2,
    ).all()
    if not res:
        raise HTTPException(404, "Paso 2 no ejecutado aún")
    return {r.subtipo: r.datos for r in res}


# ── PASO 3 ────────────────────────────────────────────────────────────────────

@router.post("/3/ejecutar")
def ejecutar_paso3(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)

    if 2 not in (exp.pasos_completados or []):
        raise HTTPException(400, "Completar Paso 2 antes de ejecutar Paso 3")

    # Agroquímicos Syngenta del Paso 2
    agro_res = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == 2,
        ResultadoPaso.subtipo == "agroquimicos",
    ).first()
    if not agro_res or not agro_res.archivo_path:
        raise HTTPException(400, "Archivo de agroquímicos no disponible")

    # CRM
    path_crm = _get_archivo_path(exp_id, TipoArchivo.CRM, db)

    try:
        resultado = paso3_service.ejecutar_paso3(
            agro_res.archivo_path, path_crm, exp_id
        )
    except Exception as e:
        raise HTTPException(500, f"Error en Paso 3: {str(e)}")

    _save_resultado(db, exp_id, 3, "conciliacion", datos=resultado["conciliacion"])
    _save_resultado(db, exp_id, 3, "resumen", datos=resultado["resumen"])
    _save_resultado(db, exp_id, 3, "parser_diagnostico",
                    datos={"items": resultado.get("parser_diagnostico", [])})

    # Validación IA
    validacion = validar_paso(3, resultado["resumen"], muestra=resultado["conciliacion"][:5])
    _save_resultado(db, exp_id, 3, "validacion", datos=validacion)
    _marcar_paso_completado(exp, 3, db)

    return {**resultado, "validacion": validacion}


@router.get("/3/resultado")
def resultado_paso3(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_exp(exp_id, db, current_user)
    res = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == 3,
    ).all()
    if not res:
        raise HTTPException(404, "Paso 3 no ejecutado aún")
    return {r.subtipo: r.datos for r in res}


# ── PASO 4 ────────────────────────────────────────────────────────────────────

@router.post("/4/ejecutar")
def ejecutar_paso4(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)

    path_recibidos = _get_archivo_path(exp_id, TipoArchivo.COMPROBANTES_RECIBIDOS, db)
    path_tc = _get_archivo_path(exp_id, TipoArchivo.TIPOS_CAMBIO, db)

    proveedores_apertura = []
    arch_prov = db.query(Archivo).filter(
        Archivo.expediente_id == exp_id,
        Archivo.tipo == TipoArchivo.PROVEEDORES_APERTURA,
    ).first()
    if arch_prov:
        import pandas as pd
        df_prov = pd.read_excel(arch_prov.path, dtype=str)
        col = df_prov.columns[0]
        proveedores_apertura = df_prov[col].dropna().str.strip().str.upper().tolist()

    try:
        resultado = paso4_service.ejecutar_paso4(
            path_recibidos, path_tc, proveedores_apertura, exp.anio_analisis
        )
    except Exception as e:
        raise HTTPException(500, f"Error en Paso 4: {str(e)}")

    _save_resultado(db, exp_id, 4, "resumen", datos=resultado["resumen"])
    _save_resultado(db, exp_id, 4, "totales", datos=resultado["totales"])
    _save_resultado(db, exp_id, 4, "parser_diagnostico",
                    datos={"items": resultado.get("parser_diagnostico", [])})

    # Validación IA
    validacion = validar_paso(4, resultado["totales"], muestra=resultado["resumen"][:5])
    _save_resultado(db, exp_id, 4, "validacion", datos=validacion)
    _marcar_paso_completado(exp, 4, db)

    return {
        "totales": resultado["totales"],
        "resumen_top20": resultado["resumen"][:20],
        "parser_diagnostico": resultado.get("parser_diagnostico", []),
        "validacion": validacion,
    }


@router.get("/4/resultado")
def resultado_paso4(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_exp(exp_id, db, current_user)
    res = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == 4,
    ).all()
    if not res:
        raise HTTPException(404, "Paso 4 no ejecutado aún")
    return {r.subtipo: r.datos for r in res}


# ── PASO 5 ────────────────────────────────────────────────────────────────────

@router.post("/5/ejecutar")
def ejecutar_paso5(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)

    reqs = [2, 3, 4]
    faltantes = [p for p in reqs if p not in (exp.pasos_completados or [])]
    if faltantes:
        raise HTTPException(400, f"Completar pasos {faltantes} antes del Paso 5")

    # Cargar datos de pasos anteriores
    def get_datos(paso, subtipo):
        r = db.query(ResultadoPaso).filter(
            ResultadoPaso.expediente_id == exp_id,
            ResultadoPaso.paso == paso,
            ResultadoPaso.subtipo == subtipo,
        ).first()
        return r.datos if r else []

    resumen_compras = get_datos(4, "resumen")
    tabla_apertura = get_datos(2, "tabla_apertura")
    conciliacion_crm = get_datos(3, "conciliacion")

    expediente_info = {
        "nombre_distribuidor": exp.nombre_distribuidor,
        "cuit_distribuidor": exp.cuit_distribuidor,
        "anio_analisis": exp.anio_analisis,
    }

    try:
        resultado = paso5_service.ejecutar_paso5(
            resumen_compras, tabla_apertura, conciliacion_crm,
            expediente_info, exp_id
        )
    except Exception as e:
        raise HTTPException(500, f"Error en Paso 5: {str(e)}")

    _save_resultado(db, exp_id, 5, "informe", archivo_path=resultado["excel_path"])
    _save_resultado(db, exp_id, 5, "totales", datos=resultado["totales"])

    # Validación IA
    validacion = validar_paso(5, resultado["totales"])
    _save_resultado(db, exp_id, 5, "validacion", datos=validacion)
    _marcar_paso_completado(exp, 5, db)

    return {**resultado, "validacion": validacion}


@router.get("/5/descargar")
def descargar_paso5(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_exp(exp_id, db, current_user)
    res = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == 5,
        ResultadoPaso.subtipo == "informe",
    ).first()
    if not res or not res.archivo_path:
        raise HTTPException(404, "Informe no generado aún")
    return FileResponse(
        res.archivo_path,
        filename=f"OAG_Informe_Paso5_Exp{exp_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── PASO 6 ────────────────────────────────────────────────────────────────────

@router.post("/6/ejecutar")
def ejecutar_paso6(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = _get_exp(exp_id, db, current_user)

    if 5 not in (exp.pasos_completados or []):
        raise HTTPException(400, "Completar Paso 5 antes del Paso 6")

    def get_datos(paso, subtipo):
        r = db.query(ResultadoPaso).filter(
            ResultadoPaso.expediente_id == exp_id,
            ResultadoPaso.paso == paso,
            ResultadoPaso.subtipo == subtipo,
        ).first()
        return r.datos if r else []

    resumen_compras = get_datos(4, "resumen")
    tabla_apertura = get_datos(2, "tabla_apertura")
    conciliacion_crm = get_datos(3, "conciliacion")

    glosario = db.query(Glosario).filter(Glosario.is_active == True).all()
    glosario_list = [{"nombre_original": g.nombre_original, "nombre_estandar": g.nombre_estandar} for g in glosario]

    expediente_info = {
        "nombre_distribuidor": exp.nombre_distribuidor,
        "cuit_distribuidor": exp.cuit_distribuidor,
        "anio_analisis": exp.anio_analisis,
    }

    try:
        resultado = paso6_service.ejecutar_paso6(
            resumen_compras, tabla_apertura, conciliacion_crm,
            glosario_list, expediente_info, exp_id
        )
    except Exception as e:
        raise HTTPException(500, f"Error en Paso 6: {str(e)}")

    _save_resultado(db, exp_id, 6, "informe", archivo_path=resultado["excel_path"])
    _save_resultado(db, exp_id, 6, "totales", datos=resultado["totales"])

    # Validación IA
    validacion = validar_paso(6, resultado["totales"])
    _save_resultado(db, exp_id, 6, "validacion", datos=validacion)
    _marcar_paso_completado(exp, 6, db)

    return {**resultado, "validacion": validacion}


@router.get("/6/descargar")
def descargar_paso6(
    exp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_exp(exp_id, db, current_user)
    res = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == 6,
        ResultadoPaso.subtipo == "informe",
    ).first()
    if not res or not res.archivo_path:
        raise HTTPException(404, "Informe no generado aún")
    return FileResponse(
        res.archivo_path,
        filename=f"OAG_Informe_Final_Exp{exp_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
