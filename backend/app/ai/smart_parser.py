"""
Parser inteligente: dado un archivo Excel y un schema de columnas requeridas,
detecta el mapping correcto.

Estrategia:
  1. Intenta detección por keywords (rápido, gratis, determinístico).
  2. Si la confianza es baja (faltan columnas críticas, ambigüedad detectada),
     llama a Claude.
  3. Si Claude tiene baja confianza, re-intenta con extended thinking.
  4. Cachea por hash del archivo + schema.
"""
import os
import json
import re
import unicodedata
from typing import Optional
import pandas as pd

from . import cache
from .claude_client import chat, chat_with_thinking


# ─── Helpers de normalización ──────────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", _strip_accents(str(s)).lower()).strip()


# ─── Detección de header rows ──────────────────────────────────────────────────

def detectar_header_row(path: str, max_skip: int = 8) -> int:
    """
    Detecta cuántas filas saltar antes del verdadero encabezado.
    Heurística: la fila con más celdas no-vacías y con texto alfabético.
    """
    best_row = 0
    best_score = -1
    for skip in range(max_skip):
        try:
            df = pd.read_excel(path, header=skip, dtype=str, nrows=2)
        except Exception:
            continue
        cols = list(df.columns)
        # Score: columnas no-anónimas con texto
        score = 0
        for c in cols:
            cs = str(c).strip()
            if cs and not cs.lower().startswith("unnamed") and not cs.replace(".", "").isdigit():
                # Bonificar si tiene letras
                if any(ch.isalpha() for ch in cs):
                    score += 1
        if score > best_score:
            best_score = score
            best_row = skip
    return best_row


# ─── Detección de columnas por keywords ────────────────────────────────────────

def detectar_por_keywords(
    cols: list,
    schema: dict,
    excluir_si_contiene: Optional[dict] = None,
) -> dict:
    """
    schema: {std_col: [keyword1, keyword2, ...]} en orden de preferencia.
    excluir_si_contiene: {std_col: [palabras_que_descartan_columna]}.
    Retorna {std_col: col_original|None}.
    """
    cols_norm = {_norm(c): c for c in cols}
    mapping = {}

    for std_col, keywords in schema.items():
        exclude_terms = (excluir_si_contiene or {}).get(std_col, [])
        # Aplicar exclusiones a las candidatas
        candidatas = {
            cn: co for cn, co in cols_norm.items()
            if not any(_norm(ex) in cn for ex in exclude_terms)
        }
        encontrada = None
        for kw in keywords:
            kw_n = _norm(kw)
            # Primero match exacto
            for cn, co in candidatas.items():
                if cn == kw_n:
                    encontrada = co
                    break
            if encontrada:
                break
            # Después substring
            for cn, co in candidatas.items():
                if kw_n in cn:
                    encontrada = co
                    break
            if encontrada:
                break
        mapping[std_col] = encontrada

    return mapping


# ─── Detección con IA (fallback) ───────────────────────────────────────────────

SYSTEM_COLUMN_MAPPER = """Eres un experto en análisis de archivos Excel de sistemas ERP y AFIP/ARCA argentinos.
Tu tarea es mapear las columnas reales de un archivo a un schema de columnas estándar requeridas.

Reglas críticas:
- "número de comprobante" se refiere al NÚMERO DE LA FACTURA, NO al CUIT del receptor/comprador.
- "cuit_cliente" se refiere al CUIT del CLIENTE/COMPRADOR/RECEPTOR.
- "monto_total" es el IMPORTE TOTAL CON IVA del comprobante.
- "tipo_cambio" o "TC" es la cotización ARS→USD (>1 normalmente, ej: 1050.50). NO confundir con tipo de comprobante.
- "moneda" indica si el monto está en pesos (ARS, PES, $) o dólares (USD, U$S).

Devolvé ÚNICAMENTE un JSON con el formato exacto:
{
  "mapping": {"std_col": "Nombre Columna Original" | null, ...},
  "confianza": 0.0 a 1.0,
  "warnings": ["mensaje opcional si algo es ambiguo o falta"]
}
Si una columna estándar no existe, usa null. Confianza alta solo si estás seguro."""


def detectar_con_ia(
    cols: list,
    sample_rows: list,
    schema: dict,
    use_thinking: bool = False,
) -> dict:
    """Llama a Claude para mapear columnas. Retorna {std_col: original|None}."""
    schema_desc = "\n".join(f"- {k}: alias típicos: {', '.join(v[:5])}" for k, v in schema.items())
    user_msg = f"""Schema requerido:
{schema_desc}

Columnas reales del archivo:
{json.dumps(cols, ensure_ascii=False)}

Primeras 3 filas de muestra:
{json.dumps(sample_rows, ensure_ascii=False, default=str)[:3000]}

Devolvé el JSON pedido."""

    fn = chat_with_thinking if use_thinking else chat
    try:
        raw = fn(SYSTEM_COLUMN_MAPPER, user_msg)
    except Exception as e:
        return {"mapping": {k: None for k in schema}, "confianza": 0.0,
                "warnings": [f"IA no disponible: {str(e)[:120]}"]}
    # Extraer JSON
    txt = raw.strip()
    if "```" in txt:
        # Sacar bloque markdown
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", txt)
        if m:
            txt = m.group(1)
    # Buscar el primer { ... }
    m = re.search(r"\{[\s\S]*\}", txt)
    if m:
        txt = m.group(0)
    try:
        data = json.loads(txt)
    except json.JSONDecodeError:
        return {"mapping": {k: None for k in schema}, "confianza": 0.0, "warnings": ["Claude no devolvió JSON parseable"]}
    return data


# ─── Smart parser principal ────────────────────────────────────────────────────

def parsear_excel(
    path: str,
    task_id: str,
    schema: dict,
    excluir_si_contiene: Optional[dict] = None,
    columnas_criticas: Optional[list] = None,
    use_cache: bool = True,
) -> dict:
    """
    Parsea un Excel y mapea sus columnas al schema requerido.

    Args:
      path: ruta al archivo
      task_id: identificador único de la tarea (ej: "arca_emitidos", "tipos_cambio")
      schema: {std_col: [keywords_de_busqueda]}
      excluir_si_contiene: {std_col: [palabras_que_NO_deben_estar_en_la_columna]}
      columnas_criticas: lista de std_col que DEBEN estar presentes
      use_cache: usar cache por hash del archivo

    Returns:
      {
        "df": DataFrame con header detectado,
        "mapping": {std_col: col_original|None},
        "header_row": int,
        "metodo": "keywords" | "ia" | "ia_thinking" | "cache",
        "confianza": 0..1,
        "warnings": [str]
      }
    """
    # 1. Cache lookup
    cache_k = cache.cache_key(task_id, path, json.dumps(schema, sort_keys=True))
    if use_cache:
        cached = cache.get(cache_k)
        if cached:
            df = pd.read_excel(path, header=cached["header_row"], dtype=str)
            df = df.dropna(how="all").dropna(axis=1, how="all")
            return {**cached, "df": df, "metodo": "cache"}

    # 2. Detectar header
    header_row = detectar_header_row(path)
    df = pd.read_excel(path, header=header_row, dtype=str)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    cols = [str(c) for c in df.columns]

    warnings = []

    # 3. Intento 1: keywords
    mapping = detectar_por_keywords(cols, schema, excluir_si_contiene)
    metodo = "keywords"
    confianza = 1.0

    # 4. Validar confianza
    criticas = columnas_criticas or list(schema.keys())
    faltantes = [c for c in criticas if not mapping.get(c)]

    if faltantes:
        # Fallback a IA
        sample_rows = df.head(3).to_dict(orient="records")
        ia_result = detectar_con_ia(cols, sample_rows, schema, use_thinking=False)
        ia_mapping = ia_result.get("mapping", {})
        ia_confianza = float(ia_result.get("confianza", 0))
        warnings.extend(ia_result.get("warnings", []))

        # Validar respuesta IA: las columnas que dice deben existir
        ia_mapping_validado = {k: (v if v and v in cols else None) for k, v in ia_mapping.items()}
        faltantes_ia = [c for c in criticas if not ia_mapping_validado.get(c)]

        if faltantes_ia or ia_confianza < 0.7:
            # Último intento: extended thinking
            ia_result_t = detectar_con_ia(cols, sample_rows, schema, use_thinking=True)
            ia_mapping_t = ia_result_t.get("mapping", {})
            ia_mapping_t = {k: (v if v and v in cols else None) for k, v in ia_mapping_t.items()}
            ia_confianza_t = float(ia_result_t.get("confianza", 0))
            warnings.extend(ia_result_t.get("warnings", []))

            if ia_confianza_t > ia_confianza:
                mapping = ia_mapping_t
                confianza = ia_confianza_t
                metodo = "ia_thinking"
            else:
                mapping = ia_mapping_validado
                confianza = ia_confianza
                metodo = "ia"
        else:
            mapping = ia_mapping_validado
            confianza = ia_confianza
            metodo = "ia"

        faltantes_finales = [c for c in criticas if not mapping.get(c)]
        if faltantes_finales:
            warnings.append(f"Columnas críticas no detectadas: {faltantes_finales}")

    # Diagnóstico completo de columnas
    columnas_archivo = cols
    columnas_no_mapeadas = [c for c in cols if c not in (mapping.values())]
    columnas_faltantes = [c for c in criticas if not mapping.get(c)]

    resultado = {
        "mapping": mapping,
        "header_row": header_row,
        "metodo": metodo,
        "confianza": confianza,
        "warnings": warnings,
        "columnas_archivo": columnas_archivo,
        "columnas_no_mapeadas": columnas_no_mapeadas,
        "columnas_faltantes": columnas_faltantes,
        "task_id": task_id,
    }

    # Persistir en cache (sin el DataFrame)
    if use_cache:
        cache.put(cache_k, resultado)

    resultado["df"] = df
    return resultado
