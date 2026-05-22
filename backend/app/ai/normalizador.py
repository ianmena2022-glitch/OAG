"""
Usa Claude para mapear columnas de bajada de gestión (formato variable)
a las columnas estándar del sistema.
"""
import json
import pandas as pd
from .claude_client import chat

COLUMNAS_ESTANDAR = [
    "fecha",
    "tipo_comprobante",
    "numero_comprobante",
    "cliente",
    "cuit_cliente",
    "articulo",
    "cantidad",
    "moneda",
    "tipo_cambio",
    "monto_neto",
    "impuestos",
    "monto_total",
]

SYSTEM_NORMALIZADOR = """Eres un experto en contabilidad y sistemas ERP argentinos.
Tu tarea es analizar los nombres de columnas de un archivo Excel de bajada de gestión
de un distribuidor y mapearlos a las columnas estándar del sistema de auditoría.

Columnas estándar requeridas:
- fecha: fecha del comprobante (puede ser "Fecha", "Fecha Emisión", "Fecha FC", etc.)
- tipo_comprobante: tipo (FC, NC, ND, Factura, Nota de Crédito, etc.)
- numero_comprobante: número o identificador del comprobante
- cliente: nombre/razón social del cliente
- cuit_cliente: CUIT del cliente (puede no existir, en ese caso null)
- articulo: descripción del producto/artículo facturado
- cantidad: cantidad facturada (puede no existir, en ese caso null)
- moneda: moneda del comprobante (ARS, USD, $, U$S, etc.)
- tipo_cambio: cotización/tipo de cambio (puede no existir, en ese caso null)
- monto_neto: importe neto sin impuestos
- impuestos: IVA u otros impuestos
- monto_total: importe total con impuestos

Responde ÚNICAMENTE con un JSON válido con el mapping. Ejemplo:
{
  "fecha": "Fecha Comprobante",
  "tipo_comprobante": "Tipo",
  "numero_comprobante": "Nro.",
  "cliente": "Razón Social",
  "cuit_cliente": null,
  "articulo": "Descripción Producto",
  "cantidad": "Cant.",
  "moneda": "Moneda",
  "tipo_cambio": null,
  "monto_neto": "Importe Neto",
  "impuestos": "IVA",
  "monto_total": "Total"
}
Si una columna estándar no tiene equivalente en el archivo, usa null.
"""


def normalizar_columnas(df: pd.DataFrame) -> dict:
    """
    Dado un DataFrame con columnas desconocidas, retorna el mapping
    {columna_estandar: columna_original} usando Claude.
    Columnas con null no existen en el archivo.
    """
    columnas = list(df.columns)
    sample_rows = df.head(3).to_dict(orient="records")

    user_msg = f"""Columnas del archivo: {columnas}

Primeras 3 filas de muestra:
{json.dumps(sample_rows, ensure_ascii=False, default=str)}

Por favor mapea estas columnas al estándar requerido."""

    response = chat(SYSTEM_NORMALIZADOR, user_msg, max_tokens=1024)

    # Extraer JSON de la respuesta
    try:
        # Limpiar posibles bloques markdown
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except json.JSONDecodeError:
        # Si falla, intentar inferencia básica por keywords
        return _fallback_mapping(columnas)


def _fallback_mapping(columnas: list) -> dict:
    """Mapeo de fallback por keywords si Claude falla."""
    mapping = {col: None for col in COLUMNAS_ESTANDAR}
    cols_lower = {c.lower(): c for c in columnas}

    keywords = {
        "fecha": ["fecha", "date", "fec"],
        "tipo_comprobante": ["tipo", "comprobante", "tcomp", "t_comp"],
        "numero_comprobante": ["numero", "nro", "num", "comprobante"],
        "cliente": ["cliente", "razon", "razón", "social", "nombre"],
        "cuit_cliente": ["cuit", "cuil"],
        "articulo": ["articulo", "artículo", "producto", "descripcion", "descripción", "item"],
        "cantidad": ["cantidad", "cant", "qty", "unidades"],
        "moneda": ["moneda", "divisa", "currency"],
        "tipo_cambio": ["cambio", "cotizacion", "cotización", "tc"],
        "monto_neto": ["neto", "importe neto", "subtotal", "gravado"],
        "impuestos": ["iva", "impuesto", "tax"],
        "monto_total": ["total", "importe total", "monto total"],
    }

    for std_col, kws in keywords.items():
        for kw in kws:
            for col_lower, col_orig in cols_lower.items():
                if kw in col_lower and mapping[std_col] is None:
                    mapping[std_col] = col_orig
                    break

    return mapping


def aplicar_normalizacion(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """
    Aplica el mapping al DataFrame, creando columnas estándar.
    Retorna un nuevo DataFrame con columnas estandarizadas.
    """
    result = pd.DataFrame()

    for std_col, orig_col in mapping.items():
        if orig_col and orig_col in df.columns:
            result[std_col] = df[orig_col]
        else:
            result[std_col] = None

    return result
