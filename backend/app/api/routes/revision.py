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
argentina y depuración de software. Tu rol es AUTO-DIAGNOSTICAR el output \
de un sistema (OGSA) que procesa archivos de gestión/ARCA/CRM contra \
sus propios inputs, buscando inconsistencias internas que indiquen bugs.

NO hay archivo de referencia humano. Tenés que detectar problemas SOLO \
comparando: inputs vs output del sistema + sentido común del dominio.

Tenés acceso a:
  - El output actual de OGSA para un paso N específico
  - Una muestra de los archivos de entrada que OGSA usó (primeras filas)
  - El diagnóstico del parser (qué columnas mapeó)
  - Aprendizajes previos del sistema (correcciones aplicadas antes)
  - Opcional: un archivo de referencia del auditor si lo subió (poco común)

Patrones típicos de bugs que tenés que detectar:

A) MONEDA/CONVERSIÓN
  - Total USD del sistema ≫ Total esperado del dominio (ej. gestión = USD 2.598
    MIL millones cuando ARCA dice USD 3M → diff 770x = típico bug "olvidé
    dividir por TC")
  - Ratio output/input cercano a 1000-1500 = TC peso/USD argentino no aplicado
  - Ratio cercano a 1.21 = IVA argentino no descontado
  - Misma columna leída como USD cuando en realidad está en ARS

B) CLASIFICACIÓN
  - Productos obviamente Syngenta clasificados NO
  - Productos obviamente NO Syngenta (semillas, fertilizantes genéricos) clasificados SI
  - Productos no-agroquímicos (combustibles, servicios, fletes) en tabla de
    agroquímicos

C) PARSER/MAPPING
  - Columna crítica no detectada (ver parser_diagnostico)
  - Confianza < 0.7 en mapeos
  - "TIPO" cuando debería ser "TIPO_CAMBIO" o viceversa
  - Filas filtradas que no deberían (totales bajos sin razón)

D) NÚMEROS ABSURDOS
  - Montos negativos donde deberían ser positivos (NC mal interpretadas)
  - Cantidades enormes (ej. cantidad de 1000L en una fila individual)
  - Fechas fuera del año de análisis no filtradas

Tu tarea:
  1. Hacé checks numéricos cruzados (suma input vs output, ratios, etc.)
  2. Detectá los 1-3 problemas MÁS GRAVES (no menciones nimiedades)
  3. Para cada uno: causa raíz + fix concreto + aprendizaje universal
  4. Sé honesto sobre confianza. Si no encontrás nada raro, decilo claro.

Respondé ÚNICAMENTE un JSON válido:
{
  "analisis": "descripción detallada del/los bugs con ejemplos concretos (montos, comprobantes específicos)",
  "causa_raiz": "explicación técnica de por qué pasa",
  "confianza": 0.0-1.0,
  "fix_inmediato": {
    "tipo": "edicion_filas" | "re_ejecucion_con_override" | "manual",
    "descripcion": "qué se va a cambiar en el expediente",
    "cambios": [
      // Si tipo=edicion_filas: lista de {subtipo, indice_o_key, campo, valor_actual, valor_nuevo}
      // Si tipo=re_ejecucion_con_override: {regla: ..., justificacion: ...}
    ]
  } o null si no hay fix evidente,
  "aprendizaje": {
    "titulo": "frase corta (<80 chars) que describa el patrón",
    "descripcion": "explicación completa del patrón para futuras ejecuciones",
    "regla_estructurada": null o {"cuando": {...}, "entonces": {...}},
    "aplica_a": "general" | "erp_especifico" | "expediente_unico"
  } o null,
  "checks_realizados": [
    "lista breve de las verificaciones que hiciste, ej: 'sum gestión USD vs ARCA USD', 'ratio promedio por comprobante', 'productos clasificados SI sin marca conocida'"
  ]
}

Si TODO se ve consistente:
{"analisis": "No se detectaron inconsistencias significativas. Los números cierran, los ratios son razonables, no hay banderas rojas.",
 "causa_raiz": "—", "confianza": 0.9, "fix_inmediato": null, "aprendizaje": null,
 "checks_realizados": [...]}
"""


@router.post("/{exp_id}/pasos/{paso}/revisar")
def revisar_con_ia(
    exp_id: int,
    paso: int,
    archivo_referencia: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Llama a Opus para auto-diagnosticar el output del paso N comparando
    contra los inputs originales y aplicando sentido común del dominio.

    El archivo de referencia del auditor es OPCIONAL — solo se usa si ya
    existe una auditoría previa manual. Para auditorías nuevas (caso
    típico), Opus detecta inconsistencias internas: ratios sospechosos,
    montos absurdos, clasificaciones obvias mal hechas, mappings de
    columnas mal detectados.
    """
    exp = db.query(Expediente).filter(Expediente.id == exp_id).first()
    if not exp:
        raise HTTPException(404, "Expediente no encontrado")
    if paso not in PASO_INPUTS:
        raise HTTPException(400, f"Paso {paso} no soportado")

    muestra_ref = None
    tmp_path = None
    if archivo_referencia is not None and archivo_referencia.filename:
        content = archivo_referencia.file.read()
        if content:
            fd, tmp_path = tempfile.mkstemp(
                suffix=os.path.splitext(archivo_referencia.filename)[1] or ".xlsx"
            )
            with os.fdopen(fd, "wb") as f:
                f.write(content)
            muestra_ref = _muestra_excel(tmp_path, max_rows=50)
            muestra_ref["nombre_original"] = archivo_referencia.filename

    try:
        ctx = _contexto_paso(exp_id, paso, db)

        user_msg = (
            f"Expediente: {exp.nombre_distribuidor} (CUIT {exp.cuit_distribuidor}), "
            f"año {exp.anio_analisis}\n"
            f"Paso a revisar: {paso}\n\n"
            f"=== OUTPUT ACTUAL OGSA (este es el resultado que el sistema produjo) ===\n"
            f"{json.dumps(ctx['output_ogsa'], ensure_ascii=False, indent=2, default=str)[:22000]}\n\n"
            f"=== MUESTRA DE INPUTS QUE USÓ OGSA (primeras filas de cada archivo) ===\n"
            f"{json.dumps(ctx['inputs_muestra'], ensure_ascii=False, indent=2)[:12000]}\n\n"
        )
        if muestra_ref is not None:
            user_msg += (
                f"=== ARCHIVO DE REFERENCIA OPCIONAL DEL AUDITOR ===\n"
                f"{json.dumps(muestra_ref, ensure_ascii=False, indent=2)[:8000]}\n\n"
            )
        if ctx["aprendizajes_previos"]:
            user_msg += (
                f"=== APRENDIZAJES PREVIOS DEL SISTEMA (correcciones aplicadas antes) ===\n"
                f"{json.dumps(ctx['aprendizajes_previos'], ensure_ascii=False, indent=2)[:3000]}\n\n"
            )
        user_msg += (
            "AUTO-DIAGNOSTICÁ el output del sistema. Hacé checks numéricos "
            "cruzados entre input y output. Aplicá sentido común del dominio "
            "(escala razonable de montos, ratios típicos, clasificaciones "
            "obvias). Detectá inconsistencias. Si encontrás bugs, proponé fix "
            "inmediato + aprendizaje universal. Respondé en JSON válido."
        )

        try:
            resp = chat_opus(SYSTEM_OPUS_REVISION, user_msg,
                              max_tokens=16384, thinking_budget=8000)
        except Exception as e:
            raise HTTPException(500, f"Error llamando a Opus: {type(e).__name__}: {e}")

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
            "uso_referencia": muestra_ref is not None,
        }
        return parsed
    finally:
        if tmp_path:
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
