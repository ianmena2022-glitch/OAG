"""
Paso 1 — Cruce de Base de Datos
Compara bajada de gestión vs comprobantes emitidos (ARCA).
Salida: conciliación por comprobante con diferencias.
"""
import io
import os
import json
from typing import Tuple
from datetime import date
import pandas as pd
import numpy as np

from ..ai.normalizador import normalizar_columnas, aplicar_normalizacion
from ..core.config import settings

# Tipos de comprobante reconocidos
TIPOS_FC = {"FC", "FACTURA", "FAC", "F"}
TIPOS_NC = {"NC", "NOTA DE CREDITO", "NOTA DE CRÉDITO", "NCD", "N/C"}
TIPOS_ND = {"ND", "NOTA DE DEBITO", "NOTA DE DÉBITO", "NDD", "N/D"}

COLUMNAS_ARCA = {
    "fecha": ["Fecha", "Fecha Comprobante", "Fecha de Emisión"],
    "tipo_comprobante": ["Tipo", "Tipo Comprobante", "Tipo de Comprobante"],
    "punto_venta": ["Punto de Venta", "PV", "Pto Vta"],
    "numero": ["Número", "Numero", "Nro Comprobante", "Número Desde"],
    "cuit_cliente": ["CUIT", "Cuit", "CUIT Comprador"],
    "nombre_cliente": ["Denominación", "Nombre", "Razón Social"],
    "moneda": ["Moneda", "Mon"],
    "tipo_cambio": ["Tipo de Cambio", "TC", "T/C"],
    "importe_gravado": ["Imp. Neto Gravado", "Importe Neto Gravado", "Gravado"],
    "importe_total": ["Importe Total", "Total", "Imp. Total"],
}


def normalizar_tipo_comprobante(tipo: str) -> str:
    if not tipo or pd.isna(tipo):
        return "FC"
    tipo_upper = str(tipo).upper().strip()
    if any(t in tipo_upper for t in TIPOS_NC):
        return "NC"
    if any(t in tipo_upper for t in TIPOS_ND):
        return "ND"
    return "FC"


def construir_numero_comprobante(row: pd.Series, col_pv: str = None, col_num: str = None) -> str:
    """Construye clave única: tipo-PUNTOVENTA-NUMERO"""
    pv = str(row.get(col_pv, "0")).strip().zfill(5) if col_pv else "00000"
    num = str(row.get(col_num, "0")).strip().zfill(8) if col_num else "00000000"
    return f"{pv}-{num}"


def obtener_tipo_cambio_fecha(tc_map: dict, fecha: date, moneda: str) -> float:
    """Retorna el tipo de cambio para una fecha dada. Si no existe exacto, usa el más cercano anterior."""
    if str(moneda).upper() in ("USD", "U$S", "DOLAR", "DÓLAR", "DOL"):
        return 1.0

    fecha_str = fecha.strftime("%Y-%m-%d") if hasattr(fecha, "strftime") else str(fecha)

    if fecha_str in tc_map:
        return tc_map[fecha_str]

    # Buscar fecha más cercana anterior
    fechas_disponibles = sorted(tc_map.keys())
    anterior = None
    for f in fechas_disponibles:
        if f <= fecha_str:
            anterior = f
        else:
            break

    if anterior:
        return tc_map[anterior]

    # Usar primera disponible como fallback
    if fechas_disponibles:
        return tc_map[fechas_disponibles[0]]

    return 1.0


def leer_tipos_cambio(path: str) -> dict:
    """Lee archivo de tipos de cambio. Retorna dict {fecha_str: cotizacion}"""
    df = pd.read_excel(path)
    tc_map = {}

    # Detectar columnas de fecha y cotización
    col_fecha = None
    col_tc = None
    for col in df.columns:
        col_l = str(col).lower()
        if any(k in col_l for k in ["fecha", "date"]):
            col_fecha = col
        if any(k in col_l for k in ["cotiz", "tc", "cambio", "dolar", "usd", "valor"]):
            col_tc = col

    if not col_fecha or not col_tc:
        # Asumir primera col = fecha, segunda = cotización
        cols = list(df.columns)
        col_fecha = cols[0]
        col_tc = cols[1]

    for _, row in df.iterrows():
        try:
            fecha = pd.to_datetime(row[col_fecha])
            tc = float(row[col_tc])
            tc_map[fecha.strftime("%Y-%m-%d")] = tc
        except (ValueError, TypeError):
            continue

    return tc_map


def leer_bajada_gestion(path: str) -> Tuple[pd.DataFrame, dict]:
    """
    Lee bajada de gestión (formato variable).
    Retorna (df_normalizado, mapping_columnas).
    Usa Claude para detectar columnas.
    """
    df_raw = pd.read_excel(path, dtype=str)
    df_raw = df_raw.dropna(how="all")

    # Detectar si hay filas de encabezado extra (comunes en ERPs)
    # Intentar saltar filas hasta encontrar encabezados coherentes
    for skip in range(5):
        df_try = pd.read_excel(path, header=skip, dtype=str)
        df_try = df_try.dropna(how="all").dropna(axis=1, how="all")
        if len(df_try.columns) >= 6:
            df_raw = df_try
            break

    mapping = normalizar_columnas(df_raw)
    df_norm = aplicar_normalizacion(df_raw, mapping)

    return df_norm, mapping


def leer_comprobantes_emitidos_arca(path: str) -> pd.DataFrame:
    """
    Lee archivo de comprobantes emitidos de ARCA (formato relativamente fijo).
    """
    for skip in range(5):
        try:
            df = pd.read_excel(path, header=skip, dtype=str)
            df = df.dropna(how="all").dropna(axis=1, how="all")
            if len(df.columns) >= 5:
                break
        except Exception:
            continue

    return df


def normalizar_monto(valor) -> float:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return 0.0
    try:
        s = str(valor).replace("$", "").replace(".", "").replace(",", ".").strip()
        return float(s)
    except ValueError:
        return 0.0


def ejecutar_paso1(
    path_bajada: str,
    path_emitidos: str,
    path_tc: str,
    expediente_id: int,
) -> dict:
    """
    Ejecuta el cruce completo del Paso 1.
    Retorna dict con:
      - conciliacion: lista de dicts con resultado por comprobante
      - resumen: totales y conteos
      - bajada_normalizada_path: path del Excel normalizado
      - mapping_columnas: dict de mapping detectado
    """
    # 1. Cargar tipos de cambio
    tc_map = leer_tipos_cambio(path_tc)

    # 2. Cargar y normalizar bajada de gestión
    df_gestion, mapping = leer_bajada_gestion(path_bajada)

    # 3. Cargar comprobantes ARCA
    df_arca_raw = leer_comprobantes_emitidos_arca(path_emitidos)

    # 4. Procesar bajada de gestión
    registros_gestion = _procesar_gestion(df_gestion, tc_map)

    # 5. Procesar comprobantes ARCA
    registros_arca = _procesar_arca(df_arca_raw, tc_map)

    # 6. Cruce / Conciliación
    conciliacion = _cruzar_comprobantes(registros_gestion, registros_arca)

    # 7. Guardar bajada normalizada (para Paso 2)
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(expediente_id))
    os.makedirs(upload_dir, exist_ok=True)
    path_normalizada = os.path.join(upload_dir, "bajada_gestion_normalizada.xlsx")
    _exportar_bajada_normalizada(df_gestion, tc_map, path_normalizada)

    # 8. Calcular resumen
    solo_arca = [r for r in conciliacion if r["estado"] == "SOLO_ARCA"]
    solo_gestion = [r for r in conciliacion if r["estado"] == "SOLO_GESTION"]
    diferencia = [r for r in conciliacion if r["estado"] == "DIFERENCIA"]
    ok = [r for r in conciliacion if r["estado"] == "OK"]

    resumen = {
        "total_arca": len(registros_arca),
        "total_gestion": len(registros_gestion),
        "ok": len(ok),
        "solo_arca": len(solo_arca),
        "solo_gestion": len(solo_gestion),
        "con_diferencia": len(diferencia),
        "monto_total_arca_usd": sum(r["monto_usd_arca"] for r in registros_arca),
        "monto_total_gestion_usd": sum(r["monto_usd"] for r in registros_gestion),
    }

    return {
        "conciliacion": conciliacion,
        "resumen": resumen,
        "bajada_normalizada_path": path_normalizada,
        "mapping_columnas": mapping,
    }


def _procesar_gestion(df: pd.DataFrame, tc_map: dict) -> list:
    registros = []
    for _, row in df.iterrows():
        try:
            tipo = normalizar_tipo_comprobante(row.get("tipo_comprobante"))
            fecha = pd.to_datetime(row.get("fecha"), errors="coerce")
            if pd.isna(fecha):
                continue

            numero = str(row.get("numero_comprobante", "")).strip()
            moneda = str(row.get("moneda", "ARS")).upper()
            tc = normalizar_monto(row.get("tipo_cambio")) or 1.0
            monto_total = normalizar_monto(row.get("monto_total"))

            # Determinar TC correcto
            if moneda in ("USD", "U$S", "DOLAR", "DÓLAR"):
                monto_usd = monto_total
            else:
                tc_real = tc if tc > 1 else obtener_tipo_cambio_fecha(tc_map, fecha.date(), moneda)
                monto_usd = monto_total / tc_real if tc_real else monto_total

            # Signo por tipo de comprobante
            if tipo == "NC":
                monto_usd = -abs(monto_usd)
            else:
                monto_usd = abs(monto_usd)

            registros.append({
                "tipo": tipo,
                "numero": numero,
                "fecha": fecha.strftime("%Y-%m-%d"),
                "cliente": str(row.get("cliente", "")),
                "cuit_cliente": str(row.get("cuit_cliente", "")),
                "moneda": moneda,
                "monto_original": monto_total,
                "monto_usd": round(monto_usd, 2),
                "key": f"{tipo}-{numero}",
            })
        except Exception:
            continue
    return registros


def _procesar_arca(df: pd.DataFrame, tc_map: dict) -> list:
    """Procesa comprobantes emitidos de ARCA."""
    registros = []

    # Detectar columnas ARCA
    cols = {c.lower(): c for c in df.columns}

    col_tipo = _find_col(cols, ["tipo", "tipo comprobante"])
    col_pv = _find_col(cols, ["punto de venta", "pto vta", "pv"])
    col_num = _find_col(cols, ["número", "numero", "nro", "número desde"])
    col_fecha = _find_col(cols, ["fecha", "fecha comprobante"])
    col_moneda = _find_col(cols, ["moneda", "mon"])
    col_tc = _find_col(cols, ["tipo de cambio", "tc", "t/c"])
    col_total = _find_col(cols, ["importe total", "total", "imp. total"])

    for _, row in df.iterrows():
        try:
            tipo = normalizar_tipo_comprobante(row.get(col_tipo, "FC"))
            fecha_raw = row.get(col_fecha)
            fecha = pd.to_datetime(fecha_raw, errors="coerce")
            if pd.isna(fecha):
                continue

            pv = str(row.get(col_pv, "0")).strip().zfill(5) if col_pv else "00000"
            num = str(row.get(col_num, "0")).strip().zfill(8) if col_num else "00000000"
            numero = f"{pv}-{num}"

            moneda = str(row.get(col_moneda, "ARS")).upper() if col_moneda else "ARS"
            tc = normalizar_monto(row.get(col_tc)) if col_tc else 1.0
            monto_total = normalizar_monto(row.get(col_total, 0))

            if moneda in ("USD", "U$S", "DOLAR", "DÓLAR"):
                monto_usd = monto_total
            else:
                tc_real = tc if tc > 1 else obtener_tipo_cambio_fecha(tc_map, fecha.date(), moneda)
                monto_usd = monto_total / tc_real if tc_real else monto_total

            # ARCA: NC siempre positivo → negativizar
            if tipo == "NC":
                monto_usd = -abs(monto_usd)
            else:
                monto_usd = abs(monto_usd)

            registros.append({
                "tipo": tipo,
                "numero": numero,
                "fecha": fecha.strftime("%Y-%m-%d"),
                "moneda": moneda,
                "monto_original": monto_total,
                "monto_usd_arca": round(monto_usd, 2),
                "key": f"{tipo}-{numero}",
            })
        except Exception:
            continue

    return registros


def _find_col(cols_lower: dict, keywords: list):
    for kw in keywords:
        for col_l, col_orig in cols_lower.items():
            if kw in col_l:
                return col_orig
    return None


def _cruzar_comprobantes(gestion: list, arca: list) -> list:
    """Cruza registros y retorna conciliación."""
    arca_map = {r["key"]: r for r in arca}
    gestion_map = {r["key"]: r for r in gestion}

    conciliacion = []
    procesados = set()

    # Registros en ARCA
    for key, r_arca in arca_map.items():
        procesados.add(key)
        if key in gestion_map:
            r_gest = gestion_map[key]
            diff = round(r_gest["monto_usd"] - r_arca["monto_usd_arca"], 2)
            tolerancia = 1.0  # USD 1 de tolerancia por redondeo

            if abs(diff) <= tolerancia:
                estado = "OK"
            else:
                estado = "DIFERENCIA"

            conciliacion.append({
                "key": key,
                "tipo": r_arca["tipo"],
                "numero": r_arca["numero"],
                "fecha": r_arca["fecha"],
                "cliente": r_gest.get("cliente", ""),
                "monto_usd_arca": r_arca["monto_usd_arca"],
                "monto_usd_gestion": r_gest["monto_usd"],
                "diferencia_usd": diff,
                "estado": estado,
            })
        else:
            conciliacion.append({
                "key": key,
                "tipo": r_arca["tipo"],
                "numero": r_arca["numero"],
                "fecha": r_arca["fecha"],
                "cliente": "",
                "monto_usd_arca": r_arca["monto_usd_arca"],
                "monto_usd_gestion": None,
                "diferencia_usd": None,
                "estado": "SOLO_ARCA",
            })

    # Registros solo en gestión
    for key, r_gest in gestion_map.items():
        if key not in procesados:
            conciliacion.append({
                "key": key,
                "tipo": r_gest["tipo"],
                "numero": r_gest["numero"],
                "fecha": r_gest["fecha"],
                "cliente": r_gest.get("cliente", ""),
                "monto_usd_arca": None,
                "monto_usd_gestion": r_gest["monto_usd"],
                "diferencia_usd": None,
                "estado": "SOLO_GESTION",
            })

    # Ordenar por fecha
    conciliacion.sort(key=lambda x: x["fecha"])
    return conciliacion


def _exportar_bajada_normalizada(df_norm: pd.DataFrame, tc_map: dict, path: str):
    """Exporta la bajada de gestión normalizada con montos en USD calculados."""
    df_export = df_norm.copy()

    # Calcular montos USD
    def calc_usd(row):
        moneda = str(row.get("moneda", "ARS")).upper()
        if moneda in ("USD", "U$S", "DOLAR", "DÓLAR"):
            return normalizar_monto(row.get("monto_total"))
        fecha = pd.to_datetime(row.get("fecha"), errors="coerce")
        if pd.isna(fecha):
            return normalizar_monto(row.get("monto_total"))
        tc = normalizar_monto(row.get("tipo_cambio")) or obtener_tipo_cambio_fecha(
            tc_map, fecha.date(), moneda
        )
        return round(normalizar_monto(row.get("monto_total")) / tc, 2) if tc else 0

    df_export["monto_usd"] = df_export.apply(calc_usd, axis=1)

    # Aplicar signo NC
    def aplicar_signo(row):
        tipo = normalizar_tipo_comprobante(row.get("tipo_comprobante"))
        val = row["monto_usd"]
        if tipo == "NC":
            return -abs(val)
        return abs(val)

    df_export["monto_usd"] = df_export.apply(aplicar_signo, axis=1)

    df_export.to_excel(path, index=False)
