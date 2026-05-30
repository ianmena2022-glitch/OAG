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
from ..ai.smart_parser import parsear_excel
from ..core.config import settings
from .paso1_service import normalizar_tipo_comprobante, normalizar_monto


CRM_SCHEMA = {
    "fecha_crm": ["fecha", "date", "fecha factura", "fecha venta"],
    "tipo_crm": ["tipo de comprobante", "tipo comprobante", "tipo"],
    "numero_crm": ["número desde", "numero desde", "nro comprobante",
                   "nro. comprobante", "número factura", "número", "numero",
                   "nro", "comprobante", "factura"],
    "cuit_cliente_crm": ["cuit cliente", "cuit comprador", "cuit", "cuil"],
    "cliente_crm": ["cliente", "razón social", "razon social", "denominación",
                    "denominacion", "nombre cliente"],
    "producto_crm": ["producto", "artículo", "articulo", "descripción producto",
                     "descripcion producto", "descripción", "descripcion", "item"],
    "cantidad_crm": ["cantidad", "cant", "qty", "unidades", "vol"],
    "monto_crm": ["monto usd", "importe usd", "total usd", "monto",
                  "importe total", "total"],
}

CRM_EXCLUSIONES = {
    "numero_crm": ["cuit", "cuil", "doc"],
    "cuit_cliente_crm": ["proveedor", "vendedor"],
    "cantidad_crm": ["monto", "importe", "precio"],
}


def leer_crm(path: str):
    """Lee reporte CRM usando smart_parser. Retorna (df_renombrado, info_parser)."""
    resultado = parsear_excel(
        path=path,
        task_id="crm",
        schema=CRM_SCHEMA,
        excluir_si_contiene=CRM_EXCLUSIONES,
        columnas_criticas=["fecha_crm", "numero_crm", "producto_crm", "monto_crm"],
    )
    df = resultado["df"]
    mapping = resultado["mapping"]

    rename_map = {orig: std for std, orig in mapping.items() if orig}
    df = df.rename(columns=rename_map)

    print(f"[CRM] método={resultado['metodo']} conf={resultado['confianza']:.2f} "
          f"mapping={mapping} warnings={resultado['warnings']}")
    return df, resultado


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
    df_crm, crm_info = leer_crm(path_crm)

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

    # Diagnóstico estructurado
    parser_diagnostico = []
    if crm_info:
        parser_diagnostico.append({
            "archivo": "CRM Syngenta",
            "metodo": crm_info["metodo"],
            "confianza": crm_info["confianza"],
            "mapping": crm_info["mapping"],
            "columnas_archivo": crm_info.get("columnas_archivo", []),
            "columnas_faltantes": crm_info.get("columnas_faltantes", []),
            "columnas_no_mapeadas": crm_info.get("columnas_no_mapeadas", []),
            "warnings": crm_info.get("warnings", []),
        })

    return {
        "conciliacion": conciliacion,
        "resumen": resumen,
        "parser_diagnostico": parser_diagnostico,
    }


def _preparar_gestion(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza el DataFrame de gestión Syngenta para el cruce con CRM.

    Es tolerante a los dos esquemas en los que puede venir el archivo:
      - Esquema nuevo (Paso 1 line-item): tipo, numero, fecha, cliente,
        cuit_cliente, articulo, monto_usd, ...
      - Esquema viejo: tipo_comprobante, numero_comprobante, ...
    Y también a columnas faltantes (ej: 'cantidad' puede no existir todavía).
    """
    df = df.copy()
    cols = set(df.columns)

    def _col_or_default(*names, default=""):
        """Devuelve la primera columna que exista como Series, sino una Serie con default."""
        for n in names:
            if n in cols:
                return df[n]
        return pd.Series([default] * len(df), index=df.index)

    df["fecha"] = pd.to_datetime(_col_or_default("fecha", default=""), errors="coerce")

    # tipo_comprobante: nuevo "tipo" o viejo "tipo_comprobante"
    tipo_series = _col_or_default("tipo_comprobante", "tipo", default="FC")
    df["tipo_comprobante"] = tipo_series.astype(str).apply(normalizar_tipo_comprobante)

    df["numero_comprobante"] = _col_or_default(
        "numero_comprobante", "numero", default=""
    ).astype(str).str.strip()
    df["cuit_cliente"] = _col_or_default("cuit_cliente", default="").astype(str).str.strip()
    df["articulo"] = _col_or_default("articulo", default="").astype(str).str.strip().str.upper()

    # cantidad puede no existir si la bajada se generó con la versión vieja
    # de Paso 1 (que no la capturaba) — default 0.
    df["cantidad"] = pd.to_numeric(
        _col_or_default("cantidad", default=0), errors="coerce"
    ).fillna(0)

    df["monto_usd"] = pd.to_numeric(
        _col_or_default("monto_usd", "monto_total", default=0), errors="coerce"
    ).fillna(0)
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
