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

def detectar_header_row(path: str, max_skip: int = 10) -> int:
    """
    Detecta cuántas filas saltar antes del verdadero encabezado.

    Heurística mejorada que distingue entre:
    - Filas de título (1-2 celdas largas, el resto vacío) → penalizar
    - Filas de datos (mix de fechas, números, texto largo) → penalizar
    - Filas de headers reales (muchas celdas cortas con texto descriptivo) → premiar
    """
    best_row = 0
    best_score = -1
    for skip in range(max_skip):
        try:
            df = pd.read_excel(path, header=skip, dtype=str, nrows=3)
        except Exception:
            continue
        cols = list(df.columns)
        total_cols = len(cols)
        if total_cols < 2:
            continue

        named_cols = []
        for c in cols:
            cs = str(c).strip()
            if cs and not cs.lower().startswith("unnamed") and not cs.replace(".", "").isdigit():
                named_cols.append(cs)

        n_named = len(named_cols)
        if n_named == 0:
            continue

        # Spread: qué fracción de columnas tienen nombre real (headers reales tienen alta fracción)
        spread = n_named / total_cols

        # Longitud promedio de los nombres (headers son cortos: "Fecha", "Total"; títulos son largos)
        avg_len = sum(len(c) for c in named_cols) / n_named
        # Penalizar nombres muy largos (>30 chars típico de título/razón social)
        length_penalty = max(0, (avg_len - 20) / 20)  # 0 si avg<=20, >0 si más largo

        # Diversidad: headers reales mezclan diferentes "tipos" de palabras
        # Una fila de título suele tener 1 columna con mucho texto
        solo_una = 1.0 if n_named == 1 else 0.0

        score = spread * 10 - length_penalty * 3 - solo_una * 5 + n_named * 0.5

        if score > best_score:
            best_score = score
            best_row = skip

    return best_row


def detectar_metadata_reporte(path: str, header_row: int) -> dict:
    """
    Lee las filas ANTES del header para extraer metadatos del reporte:
    - titulo: título del reporte (ej: "LISTADO DE NOTAS DE CREDITO")
    - tipo_inferido: "NC" | "ND" | "FC" | None (inferido del título)
    - empresa: nombre de empresa si aparece
    """
    metadata = {"titulo": None, "tipo_inferido": None, "empresa": None}
    if header_row == 0:
        return metadata

    try:
        df_pre = pd.read_excel(path, header=None, dtype=str, nrows=header_row)
    except Exception:
        return metadata

    # Juntar todo el texto de las filas previas
    textos = []
    for _, row in df_pre.iterrows():
        for val in row:
            s = str(val).strip()
            if s and s.lower() not in ("nan", "none", ""):
                textos.append(s)

    texto_completo = " ".join(textos).upper()
    metadata["titulo"] = " | ".join(textos[:5]) if textos else None

    # Inferir tipo de comprobante del título
    NC_KEYWORDS = ["NOTA DE CREDITO", "NOTA DE CRÉDITO", "NOTAS DE CREDITO",
                   "NOTAS DE CRÉDITO", "N. CREDITO", "N. CRÉDITO", "N/C", " NC "]
    ND_KEYWORDS = ["NOTA DE DEBITO", "NOTA DE DÉBITO", "NOTAS DE DEBITO",
                   "NOTAS DE DÉBITO", "N. DEBITO", "N. DÉBITO", "N/D", " ND "]

    if any(kw in texto_completo for kw in NC_KEYWORDS):
        metadata["tipo_inferido"] = "NC"
    elif any(kw in texto_completo for kw in ND_KEYWORDS):
        metadata["tipo_inferido"] = "ND"

    return metadata


# ─── Sanity check de contenido ────────────────────────────────────────────────

# Códigos numéricos que AFIP usa para "Tipo de Comprobante".
# Si una columna mapeada como numero_comprobante tiene solo estos valores
# → es la columna de tipo, no de número → hay que redirigir a IA.
_CODIGOS_AFIP = frozenset([
    "1","2","3","4","5","6","7","8","9","10","11","12","13",
    "51","52","53",
    "201","202","203","206","207","208","211","212","213",
])


def _verificar_contenido_mapping(df: pd.DataFrame, mapping: dict) -> list:
    """
    Valida semánticamente que las columnas mapeadas contengan el tipo de dato
    esperado, detectando errores que el keyword matching no puede ver.

    Retorna lista de campos cuyo mapeo es sospechoso (deben re-detectarse con IA).

    Checks actuales
    ───────────────
    numero_comprobante
        Si ≥ 80 % de la muestra son códigos de tipo AFIP (1-213) con poca
        variedad (≤ 10 valores únicos) → la columna es probablemente
        "Tipo de Comprobante" mal asignada (ocurre cuando el nombre de
        "Número Desde" tiene encoding roto y no matchea keywords).
    """
    sospechosos = []

    col = mapping.get("numero_comprobante")
    if col and col in df.columns:
        muestra = (
            df[col].dropna().head(30).astype(str).str.strip().tolist()
        )
        muestra = [v for v in muestra if v and v.lower() not in ("nan", "none", "")]
        if muestra:
            n_codigos = sum(1 for v in muestra if v in _CODIGOS_AFIP)
            n_unicos  = len(set(muestra))
            # Condición doble: mayoría de valores son códigos AFIP + poca diversidad
            if n_codigos / len(muestra) >= 0.8 and n_unicos <= 10:
                sospechosos.append("numero_comprobante")

    return sospechosos


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

    Garantía: una columna física nunca se asigna a dos campos estándar distintos.
    Si ya fue asignada, queda excluida de las candidatas siguientes.
    """
    cols_norm = {_norm(c): c for c in cols}
    mapping = {}
    used_cols: set = set()   # columnas originales ya asignadas a algún campo

    for std_col, keywords in schema.items():
        exclude_terms = (excluir_si_contiene or {}).get(std_col, [])
        # Candidatas: sin exclusiones explícitas Y sin columnas ya asignadas
        candidatas = {
            cn: co for cn, co in cols_norm.items()
            if not any(_norm(ex) in cn for ex in exclude_terms)
            and co not in used_cols
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
        if encontrada:
            used_cols.add(encontrada)   # marcar columna como usada

    return mapping


# ─── Detección con IA (fallback) ───────────────────────────────────────────────

SYSTEM_COLUMN_MAPPER = """Eres un experto en contabilidad y análisis de archivos Excel de sistemas ERP argentinos (Tango, SAP B1, Dynamics NAV, Bejerman, Evolution, Flexxus, Oracle, Odoo, exportaciones ad-hoc) y de AFIP/ARCA.
Tu tarea es mapear las columnas reales de un archivo Excel a un schema de columnas estándar requeridas.

CONTEXTO: El archivo puede provenir de CUALQUIER sistema ERP. Los nombres de columnas son heterogéneos y varían enormemente entre distribuidores. Algunos archivos tienen encabezados en filas intermedias, columnas combinadas, o nomenclatura en español con/sin acentos.

Reglas críticas:
- "numero_comprobante" = NÚMERO DE LA FACTURA/COMPROBANTE (ej: 0001-00001234), NO el CUIT del receptor.
- "punto_venta" = el prefijo de la factura (ej: "0001", "00002"), columnas como "PV", "Sucursal", "Pto. Vta.".
- "cuit_cliente" = CUIT del CLIENTE/COMPRADOR/RECEPTOR. Formato argentino: XX-XXXXXXXX-X.
- "monto_total" = importe TOTAL CON IVA. En algunos ERPs se llama "Total", "Importe", "Bruto".
- "monto_neto" = importe SIN impuestos: "Neto", "Gravado", "Base imponible".
- "tipo_cambio" = cotización ARS→USD (número >1, ej: 1050.50). NO confundir con "tipo de comprobante".
- "moneda" = divisa: ARS/$, USD/U$S/Dólar. Puede ser un código o descripción.
- "tipo_comprobante" = clase del documento: Factura/FC, Nota de Crédito/NC, Nota de Débito/ND.
- "fecha" = fecha de EMISIÓN del comprobante. NO confundir con fecha de vencimiento o pago.

IMPORTANTE: Si ves columnas con nombres muy distintos a los aliases del schema pero que por el contenido de muestra claramente corresponden a un campo estándar, mapéalas igual (priorizá el contenido sobre el nombre).

Devolvé ÚNICAMENTE un JSON con el formato exacto:
{
  "mapping": {"std_col": "Nombre Columna Original" | null, ...},
  "confianza": 0.0 a 1.0,
  "warnings": ["mensaje opcional si algo es ambiguo o falta"]
}
Si una columna estándar no existe en el archivo, usá null. Confianza alta (>0.8) solo si estás seguro del mapping. Bajá la confianza si hay ambigüedad."""


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
    # 1. Cache lookup — el key incluye schema Y excluir_si_contiene, así
    # cambios en cualquiera de los dos invalidan el cache automáticamente
    # (importante para no propagar mappings viejos cuando se ajustan reglas).
    cache_k = cache.cache_key(
        task_id, path,
        json.dumps(schema, sort_keys=True),
        json.dumps(excluir_si_contiene or {}, sort_keys=True),
    )
    if use_cache:
        cached = cache.get(cache_k)
        if cached:
            df = pd.read_excel(path, header=cached["header_row"], dtype=str)
            df = df.dropna(how="all").dropna(axis=1, how="all")
            # Sanity check incluso sobre el cache: si el mapping guardado es
            # semánticamente incorrecto, re-detectamos en lugar de propagarlo.
            if not _verificar_contenido_mapping(df, cached["mapping"]):
                return {**cached, "df": df, "metodo": "cache"}
            # Si hay sospechosos: caemos al flujo normal de detección

    # 2. Detectar header y metadatos del reporte (título, tipo inferido)
    header_row = detectar_header_row(path)
    metadata = detectar_metadata_reporte(path, header_row)
    df = pd.read_excel(path, header=header_row, dtype=str)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    cols = [str(c) for c in df.columns]

    warnings = []
    if metadata.get("titulo"):
        warnings.append(f"Título del reporte detectado: '{metadata['titulo']}'")
    if metadata.get("tipo_inferido"):
        warnings.append(f"Tipo de comprobante inferido del título: {metadata['tipo_inferido']}")

    # 3. Intento 1: keywords
    mapping = detectar_por_keywords(cols, schema, excluir_si_contiene)
    metodo = "keywords"
    confianza = 1.0

    # 3b. Sanity check de contenido — atrapa mapeos semánticamente incorrectos
    #     que el keyword matching aceptó (ej: columna de tipo AFIP como número)
    contenido_sospechoso = _verificar_contenido_mapping(df, mapping)
    if contenido_sospechoso:
        warnings.append(
            f"Sanity check: contenido sospechoso en {contenido_sospechoso} "
            f"(posible encoding roto o columna errónea) → re-detectando con IA"
        )

    # 4. Validar confianza
    criticas = columnas_criticas or list(schema.keys())
    # Unir columnas faltantes + columnas con contenido sospechoso
    faltantes = list({c for c in criticas if not mapping.get(c)} | set(contenido_sospechoso))

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
        "metadata_reporte": metadata,  # título, tipo_inferido, empresa
    }

    # Persistir en cache (sin el DataFrame)
    if use_cache:
        cache.put(cache_k, resultado)

    resultado["df"] = df
    return resultado
