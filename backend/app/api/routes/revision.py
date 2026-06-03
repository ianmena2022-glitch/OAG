"""
Endpoint del botón "Revisar con IA (Opus)".

Flujo:
  1. Auditor sube el archivo de referencia (su versión correcta).
  2. /revisar carga todo el contexto (output OGSA + parser_diag + sample input)
     y llama a Opus para que diagnostique el bug y proponga un fix.
  3. /aplicar-fix aplica el fix aprobado al expediente y opcionalmente
     guarda el aprendizaje para futuras ejecuciones.
"""
import os
import json
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.deps import get_current_user
from ...models.user import User
from ...models.expediente import (
    Expediente, Archivo, ResultadoPaso, TipoArchivo, AprendizajeIA,
)
from ...ai.claude_client import chat_opus

router = APIRouter(prefix="/expedientes", tags=["revision"])


# Mapeo de paso → tipos de archivo que son INPUT de ese paso
PASO_INPUTS = {
    1: [TipoArchivo.BAJADA_GESTION, TipoArchivo.COMPROBANTES_EMITIDOS],
    2: [TipoArchivo.BAJADA_GESTION],  # usa bajada_normalizada del paso 1
    3: [TipoArchivo.CRM],
    4: [TipoArchivo.COMPROBANTES_RECIBIDOS, TipoArchivo.PROVEEDORES_APERTURA],
    5: [],
    6: [],
}


def _muestra_excel(path: str, max_rows: int = 25) -> dict:
    """Lee las primeras N filas de un .xlsx/.xls para dar muestra al prompt."""
    try:
        import pandas as pd
        df = pd.read_excel(path, header=None, nrows=max_rows + 5)
        rows = df.head(max_rows).fillna("").astype(str).values.tolist()
        return {
            "path": os.path.basename(path),
            "filas_muestra": rows,
            "total_filas_aprox": "ver archivo completo",
        }
    except Exception as e:
        return {"path": os.path.basename(path), "error": f"no se pudo leer: {e}"}


def _contexto_paso(exp_id: int, paso: int, db: Session) -> dict:
    """Recopila todo lo que Opus necesita para diagnosticar."""
    # Output OGSA del paso (todos los resultados)
    resultados = db.query(ResultadoPaso).filter(
        ResultadoPaso.expediente_id == exp_id,
        ResultadoPaso.paso == paso,
    ).all()
    output_ogsa = {}
    for r in resultados:
        if r.datos is not None:
            # Capar tamaño para no explotar el contexto
            datos = r.datos
            if isinstance(datos, list) and len(datos) > 100:
                datos = datos[:100]
                datos_meta = f"(mostrados primeros 100 de {len(r.datos)})"
            else:
                datos_meta = ""
            output_ogsa[r.subtipo] = {"datos": datos, "meta": datos_meta}

    # Inputs del paso (sample)
    inputs_muestra = []
    tipos_input = PASO_INPUTS.get(paso, [])
    for tipo in tipos_input:
        archivos = db.query(Archivo).filter(
            Archivo.expediente_id == exp_id,
            Archivo.tipo == tipo,
        ).all()
        for a in archivos:
            if os.path.exists(a.path):
                inputs_muestra.append({
                    "tipo": tipo.value,
                    "nombre": a.nombre_original,
                    **_muestra_excel(a.path, max_rows=20),
                })

    # Aprendizajes activos para este paso (para que Opus los considere)
    aprendizajes = db.query(AprendizajeIA).filter(
        AprendizajeIA.paso == paso,
        AprendizajeIA.activo == True,
    ).order_by(AprendizajeIA.created_at.desc()).limit(20).all()
    aprendizajes_ctx = [{
        "id": a.id,
        "titulo": a.titulo,
        "descripcion": a.descripcion,
        "causa_raiz": a.causa_raiz,
    } for a in aprendizajes]

    return {
        "output_ogsa": output_ogsa,
        "inputs_muestra": inputs_muestra,
        "aprendizajes_previos": aprendizajes_ctx,
    }


SYSTEM_OPUS_REVISION = """Eres un experto en auditoría comercial agropecuaria \
argentina y depuración de software. Tu rol es diagnosticar bugs cuando un \
auditor humano detecta divergencias entre el output de un sistema (OGSA) y \
su propio archivo de referencia.

Tenés acceso a:
  - El output actual de OGSA para un paso N específico
  - El archivo de referencia del auditor (la versión que él considera correcta)
  - Una muestra de los archivos de entrada que OGSA usó
  - El diagnóstico del parser (qué columnas mapeó)
  - Aprendizajes previos del sistema (correcciones aplicadas antes)

Tu tarea: compará sistemáticamente y diagnosticá el problema. Identificá:
  1. QUÉ está mal exactamente (con ejemplos numéricos concretos)
  2. POR QUÉ está mal (causa raíz — moneda, conversión, clasificación, etc.)
  3. CÓMO arreglarlo en este expediente
  4. CÓMO evitar que vuelva a pasar (aprendizaje universal)

IMPORTANTE: Sé honesto sobre tu nivel de certeza. Si no estás seguro, decilo.

Respondé ÚNICAMENTE un JSON válido con esta estructura:
{
  "analisis": "descripción detallada del bug con ejemplos concretos (montos, comprobantes específicos)",
  "causa_raiz": "explicación técnica de por qué pasa",
  "confianza": 0.0-1.0,
  "fix_inmediato": {
    "tipo": "edicion_filas" | "re_ejecucion_con_override" | "manual",
    "descripcion": "qué se va a cambiar en el expediente",
    "cambios": [
      // Si tipo=edicion_filas: lista de {subtipo, indice_o_key, campo, valor_actual, valor_nuevo}
      // Si tipo=re_ejecucion_con_override: {regla: ..., justificacion: ...}
    ]
  },
  "aprendizaje": {
    "titulo": "frase corta (<80 chars) que describa el patrón",
    "descripcion": "explicación completa del patrón para futuras ejecuciones",
    "regla_estructurada": null o {"cuando": {...}, "entonces": {...}},
    "aplica_a": "general" | "erp_especifico" | "expediente_unico"
  }
}

Si NO encontrás un bug claro, devolvé:
{"analisis": "...", "causa_raiz": "no se detectó bug", "confianza": 0.0,
 "fix_inmediato": null, "aprendizaje": null}
"""


@router.post("/{exp_id}/pasos/{paso}/revisar")
def revisar_con_ia(
    exp_id: int,
    paso: int,
    archivo_referencia: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Llama a Opus para que diagnostique el bug en el paso N."""
    exp = db.query(Expediente).filter(Expediente.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "Expediente no encontrado")
    if paso not in PASO_INPUTS:
        raise HTTPException(400, f"Paso {paso} no soportado")

    # Guardar archivo de referencia temporalmente y leer muestra
    content = archivo_referencia.file.read()
    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(archivo_referencia.filename)[1] or ".xlsx")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        muestra_ref = _muestra_excel(tmp_path, max_rows=50)
        muestra_ref["nombre_original"] = archivo_referencia.filename

        # Recopilar contexto
        ctx = _contexto_paso(exp_id, paso, db)

        # Armar prompt
        user_msg = (
            f"Expediente: {exp.nombre_distribuidor} (CUIT {exp.cuit_distribuidor}), "
            f"año {exp.anio_analisis}\n"
            f"Paso a revisar: {paso}\n\n"
            f"=== ARCHIVO DE REFERENCIA DEL AUDITOR ===\n"
            f"{json.dumps(muestra_ref, ensure_ascii=False, indent=2)[:8000]}\n\n"
            f"=== OUTPUT ACTUAL OGSA ===\n"
            f"{json.dumps(ctx['output_ogsa'], ensure_ascii=False, indent=2, default=str)[:20000]}\n\n"
            f"=== MUESTRA DE INPUTS USADOS POR OGSA ===\n"
            f"{json.dumps(ctx['inputs_muestra'], ensure_ascii=False, indent=2)[:10000]}\n\n"
        )
        if ctx["aprendizajes_previos"]:
            user_msg += (
                f"=== APRENDIZAJES PREVIOS DEL SISTEMA (para este paso) ===\n"
                f"{json.dumps(ctx['aprendizajes_previos'], ensure_ascii=False, indent=2)[:3000]}\n\n"
            )
        user_msg += (
            "Compará el OUTPUT OGSA contra el ARCHIVO DE REFERENCIA del auditor. "
            "Identificá divergencias significativas. Diagnosticá el bug, proponé "
            "fix inmediato + aprendizaje universal. Respondé en JSON válido."
        )

        # Llamada a Opus
        try:
            resp = chat_opus(SYSTEM_OPUS_REVISION, user_msg,
                              max_tokens=16384, thinking_budget=8000)
        except Exception as e:
            raise HTTPException(500, f"Error llamando a Opus: {type(e).__name__}: {e}")

        # Parsear respuesta JSON (limpiar markdown fences si los hay)
        text = resp["text"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            if text.startswith("json"):
                text = text[4:].lstrip("\n")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            return {
                "error_parsing": True,
                "raw_response": resp["text"],
                "parse_error": str(e),
                "costo_usd": resp["costo_usd_estimado"],
            }

        parsed["_meta"] = {
            "modelo": resp["model"],
            "input_tokens": resp["input_tokens"],
            "output_tokens": resp["output_tokens"],
            "costo_usd": resp["costo_usd_estimado"],
        }
        return parsed
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@router.post("/{exp_id}/pasos/{paso}/aplicar-fix")
def aplicar_fix(
    exp_id: int,
    paso: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Aplica el fix aprobado al expediente y opcionalmente guarda el aprendizaje.

    payload esperado:
    {
      "fix_inmediato": {tipo, cambios, ...},
      "aprendizaje": {titulo, descripcion, regla_estructurada, ...} o null,
      "analisis": "..."  (para guardar en el aprendizaje)
      "causa_raiz": "..."
      "confianza": 0.95
    }
    """
    exp = db.query(Expediente).filter(Expediente.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "Expediente no encontrado")

    fix = payload.get("fix_inmediato") or {}
    tipo_fix = fix.get("tipo")
    cambios_aplicados = []

    if tipo_fix == "edicion_filas":
        # Aplica cambios a los resultados JSON del paso
        cambios = fix.get("cambios", [])
        for c in cambios:
            subtipo = c.get("subtipo")
            rp = db.query(ResultadoPaso).filter(
                ResultadoPaso.expediente_id == exp_id,
                ResultadoPaso.paso == paso,
                ResultadoPaso.subtipo == subtipo,
            ).first()
            if not rp or rp.datos is None:
                continue
            datos = rp.datos if isinstance(rp.datos, list) else []
            idx = c.get("indice")
            key = c.get("key")
            campo = c.get("campo")
            nuevo = c.get("valor_nuevo")

            target_idx = None
            if idx is not None and 0 <= int(idx) < len(datos):
                target_idx = int(idx)
            elif key is not None:
                for i, fila in enumerate(datos):
                    if isinstance(fila, dict) and fila.get("key") == key:
                        target_idx = i; break

            if target_idx is not None and campo:
                datos[target_idx][campo] = nuevo
                cambios_aplicados.append({
                    "subtipo": subtipo, "indice": target_idx,
                    "campo": campo, "valor_nuevo": nuevo,
                })

            # SQLAlchemy JSON mutability: reasignar para que detecte el cambio
            rp.datos = list(datos)

    elif tipo_fix == "re_ejecucion_con_override":
        # Por ahora: marcar el override pendiente. La re-ejecución se hace
        # del lado del front llamando al endpoint normal del paso. En una
        # iteración futura podemos disparar la re-ejecución acá mismo.
        cambios_aplicados.append({
            "nota": "re-ejecución pendiente — el usuario debe correr el paso de nuevo "
                    "para que el override tome efecto."
        })

    elif tipo_fix == "manual" or tipo_fix is None:
        # Solo se guarda el aprendizaje, sin tocar datos
        pass
    else:
        raise HTTPException(400, f"Tipo de fix desconocido: {tipo_fix}")

    # Guardar aprendizaje si vino y el usuario aceptó
    aprendizaje_creado_id = None
    apr = payload.get("aprendizaje")
    if apr and apr.get("titulo"):
        item = AprendizajeIA(
            paso=paso,
            titulo=apr.get("titulo", "")[:300],
            descripcion=apr.get("descripcion", "")[:3000],
            causa_raiz=(payload.get("causa_raiz") or "")[:2000] or None,
            fix_aplicado=fix or None,
            regla_estructurada=apr.get("regla_estructurada"),
            expediente_origen_id=exp_id,
            user_id=current_user.id,
            confianza_ia=payload.get("confianza"),
            activo=True,
        )
        db.add(item)
        db.flush()
        aprendizaje_creado_id = item.id

    db.commit()
    return {
        "ok": True,
        "cambios_aplicados": cambios_aplicados,
        "aprendizaje_id": aprendizaje_creado_id,
    }


@router.get("/aprendizajes")
def listar_aprendizajes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista los aprendizajes activos del sistema (para mostrar en Admin)."""
    items = db.query(AprendizajeIA).filter(AprendizajeIA.activo == True)\
              .order_by(AprendizajeIA.created_at.desc()).limit(200).all()
    return [{
        "id": i.id,
        "paso": i.paso,
        "titulo": i.titulo,
        "descripcion": i.descripcion,
        "causa_raiz": i.causa_raiz,
        "confianza_ia": i.confianza_ia,
        "expediente_origen_id": i.expediente_origen_id,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    } for i in items]


@router.put("/aprendizajes/{apr_id}/toggle")
def toggle_aprendizaje(
    apr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Activa/desactiva un aprendizaje (para revertir si rompe algo)."""
    item = db.query(AprendizajeIA).filter(AprendizajeIA.id == apr_id).first()
    if not item:
        raise HTTPException(404, "Aprendizaje no encontrado")
    item.activo = not item.activo
    db.commit()
    return {"id": item.id, "activo": item.activo}
