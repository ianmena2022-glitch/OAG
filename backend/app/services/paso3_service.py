"""
Paso 3 — Cruce CRM
Compara agroquímicos Syngenta (bajada de gestión) vs CRM de Syngenta.
Genera conciliación con justificaciones IA.
"""
import os
import pandas as pd
import numpy as np
from typing import List, Dict

from ..ai.justificador import generar_justificaciones
from ..core.config import settings
from .paso1_service import normalizar_tipo_comprobante, normalizar_monto


def leer_crm(path: str) -> pd.DataFrame:
    """Lee reporte CRM de Syngenta."""
    for skip in range(5):
        try:
            df = pd.read_excel(path, header=skip, dtype=str)
            df = df.dropna(how="all").dropna(axis=1, how="all")
            if len(df.columns) >= 4:
                break
        except Exception:
            continue

    cols_lower = {c.lower(): c for c in df.columns}

    # Detectar columnas
    col_fecha = _find_col(cols_lower, ["fecha", "date"])
    col_tipo = _find_col(cols_lower, ["tipo", "comprobante"])
    col_numero = _find_col(cols_lower, ["numero", "nro", "número"])
    col_cuit = _find_col(cols_lower, ["cuit", "cuil"])
    col_cliente = _find_col(cols_lower, ["cliente", "razon", "nombre"])
    col_producto = _find_col(cols_lower, ["producto", "articulo", "artículo", "descripcion"])
    col_cantidad = _find_col(cols_lower, ["cantidad", "cant", "qty"])
    col_monto = _find_col(cols_lower, ["monto", "importe", "total", "usd"])

    rename_map = {}
    for std, orig in [
        ("fecha_crm", col_fecha),
        ("tipo_crm", col_tipo),
        ("numero_crm", col_numero),
        ("cuit_cliente_crm", col_cuit),
        ("cliente_crm", col_cliente),
        ("producto_crm", col_producto),
        ("cantidad_crm", col_cantidad),
        ("monto_crm", col_monto),
    ]:
        if orig:
            rename_map[orig] = std

    df = df.rename(columns=rename_map)
    return df


def _find_col(cols_lower: dict, keywords: list):
    for kw in keywords:
        for col_l, col_orig in cols_lower.items():
            if kw in col_l:
                return col_orig
    return None


def ejecutar_paso3(
    path_agroquimicos_syngenta: str,
    path_crm: str,
    expediente_id: int,
) -> dict:
    """
    Cruza agroquímicos Syngenta (Paso 2) vs CRM.
    """
    # Cargar datos
    df_agro = pd.read_excel(path_agroquimicos_syngenta, dtype=str)
    df_crm = leer_crm(path_crm)

    # Preparar DataFrame de gestión (solo Syngenta)
    df_gestion = _preparar_gestion(df_agro)
    df_crm = _preparar_crm(df_crm)

    # Cruce
    conciliacion = _cruzar_crm(df_gestion, df_crm)

    # Generar justificaciones con IA para diferencias
    diferencias_para_ia = [
        r for r in conciliacion
        if r.get("diferencia_monto") and abs(r["diferencia_monto"]) > 0.01
    ]
    if diferencias_para_ia:
        justificaciones = generar_justificaciones(diferencias_para_ia)
        # Mapear justificaciones de vuelta
        j_idx = 0
        for r in conciliacion:
            if r.get("diferencia_monto") and abs(r["diferencia_monto"]) > 0.01:
                if j_idx < len(justificaciones):
                    r["justificacion"] = justificaciones[j_idx]
                    j_idx += 1

    resumen = {
        "total_lineas": len(conciliacion),
        "sin_diferencia": sum(1 for r in conciliacion if r.get("estado") == "OK"),
        "con_diferencia": sum(1 for r in conciliacion if r.get("estado") == "DIFERENCIA"),
        "solo_gestion": sum(1 for r in conciliacion if r.get("estado") == "SOLO_GESTION"),
        "solo_crm": sum(1 for r in conciliacion if r.get("estado") == "SOLO_CRM"),
    }

    return {
        "conciliacion": conciliacion,
        "resumen": resumen,
    }


def _preparar_gestion(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fecha"] = pd.to_datetime(df.get("fecha", ""), errors="coerce")
    df["tipo_comprobante"] = df.get("tipo_comprobante", "FC").apply(normalizar_tipo_comprobante)
    df["numero_comprobante"] = df.get("numero_comprobante", "").astype(str).str.strip()
    df["cuit_cliente"] = df.get("cuit_cliente", "").astype(str).str.strip()
    df["articulo"] = df.get("articulo", "").astype(str).str.strip().str.upper()
    df["cantidad"] = pd.to_numeric(df.get("cantidad"), errors="coerce").fillna(0)
    df["monto_usd"] = pd.to_numeric(df.get("monto_usd", df.get("monto_total", 0)), errors="coerce").fillna(0)
    return df


def _preparar_crm(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["fecha_crm"] = pd.to_datetime(df.get("fecha_crm", ""), errors="coerce")
    df["numero_crm"] = df.get("numero_crm", "").astype(str).str.strip()
    df["cuit_cliente_crm"] = df.get("cuit_cliente_crm", "").astype(str).str.strip()
    df["producto_crm"] = df.get("producto_crm", "").astype(str).str.strip().str.upper()
    df["cantidad_crm"] = pd.to_numeric(df.get("cantidad_crm"), errors="coerce").fillna(0)
    df["monto_crm"] = pd.to_numeric(df.get("monto_crm"), errors="coerce").fillna(0)
    return df


def _cruzar_crm(df_gestion: pd.DataFrame, df_crm: pd.DataFrame) -> List[Dict]:
    """
    Cruza por: producto + nro comprobante + cuit cliente.
    """
    conciliacion = []

    # Crear keys
    def key_gestion(row):
        return f"{row['articulo']}||{row['numero_comprobante']}||{row['cuit_cliente']}"

    def key_crm(row):
        return f"{row['producto_crm']}||{row['numero_crm']}||{row['cuit_cliente_crm']}"

    gestion_map = {}
    for _, row in df_gestion.iterrows():
        k = key_gestion(row)
        gestion_map.setdefault(k, []).append(row)

    crm_map = {}
    for _, row in df_crm.iterrows():
        k = key_crm(row)
        crm_map.setdefault(k, []).append(row)

    all_keys = set(gestion_map.keys()) | set(crm_map.keys())

    for k in all_keys:
        g_rows = gestion_map.get(k, [])
        c_rows = crm_map.get(k, [])

        if g_rows and c_rows:
            g = g_rows[0]
            c = c_rows[0]

            cant_g = float(g.get("cantidad", 0))
            cant_c = float(c.get("cantidad_crm", 0))
            monto_g = float(g.get("monto_usd", 0))
            monto_c = float(c.get("monto_crm", 0))
            diff_cant = round(cant_g - cant_c, 4)
            diff_monto = round(monto_g - monto_c, 2)

            estado = "OK" if abs(diff_monto) < 1.0 else "DIFERENCIA"

            conciliacion.append({
                "producto": str(g.get("articulo", "")),
                "fecha": str(g.get("fecha", ""))[:10],
                "tipo_comprobante": str(g.get("tipo_comprobante", "")),
                "numero_comprobante": str(g.get("numero_comprobante", "")),
                "cuit_cliente": str(g.get("cuit_cliente", "")),
                "cantidad_gestion": round(cant_g, 4),
                "cantidad_crm": round(cant_c, 4),
                "diferencia_cantidad": round(diff_cant, 4),
                "monto_gestion_usd": round(monto_g, 2),
                "monto_crm_usd": round(monto_c, 2),
                "diferencia_monto": round(diff_monto, 2),
                "justificacion": "" if estado == "OK" else "Pendiente de análisis",
                "estado": estado,
            })
        elif g_rows:
            g = g_rows[0]
            conciliacion.append({
                "producto": str(g.get("articulo", "")),
                "fecha": str(g.get("fecha", ""))[:10],
                "tipo_comprobante": str(g.get("tipo_comprobante", "")),
                "numero_comprobante": str(g.get("numero_comprobante", "")),
                "cuit_cliente": str(g.get("cuit_cliente", "")),
                "cantidad_gestion": float(g.get("cantidad", 0)),
                "cantidad_crm": 0,
                "diferencia_cantidad": float(g.get("cantidad", 0)),
                "monto_gestion_usd": float(g.get("monto_usd", 0)),
                "monto_crm_usd": 0,
                "diferencia_monto": float(g.get("monto_usd", 0)),
                "justificacion": "Venta sin reporte en CRM",
                "estado": "SOLO_GESTION",
            })
        else:
            c = c_rows[0]
            conciliacion.append({
                "producto": str(c.get("producto_crm", "")),
                "fecha": str(c.get("fecha_crm", ""))[:10],
                "tipo_comprobante": "",
                "numero_comprobante": str(c.get("numero_crm", "")),
                "cuit_cliente": str(c.get("cuit_cliente_crm", "")),
                "cantidad_gestion": 0,
                "cantidad_crm": float(c.get("cantidad_crm", 0)),
                "diferencia_cantidad": -float(c.get("cantidad_crm", 0)),
                "monto_gestion_usd": 0,
                "monto_crm_usd": float(c.get("monto_crm", 0)),
                "diferencia_monto": -float(c.get("monto_crm", 0)),
                "justificacion": "Reportado en CRM sin factura correspondiente en gestión",
                "estado": "SOLO_CRM",
            })

    conciliacion.sort(key=lambda x: x.get("fecha", ""))
    return conciliacion
