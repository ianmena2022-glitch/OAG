"""
Paso 4 — Análisis Detallado de Compras
Lee comprobantes recibidos de ARCA, convierte a USD, genera resumen de compras.
"""
import pandas as pd
import numpy as np
from typing import List, Dict

from .paso1_service import (
    normalizar_tipo_comprobante,
    normalizar_monto,
    leer_tipos_cambio,
    obtener_tipo_cambio_fecha,
)

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def ejecutar_paso4(
    path_recibidos: str,
    path_tc: str,
    proveedores_apertura: List[str],
    anio_analisis: int,
) -> dict:
    """
    Ejecuta el análisis de compras.
    proveedores_apertura: lista de nombres de proveedores que necesitan
                          desglose por tipo de comprobante (FC/NC/ND).
    """
    tc_map = leer_tipos_cambio(path_tc)
    df = _leer_comprobantes_recibidos(path_recibidos)
    df = _procesar_recibidos(df, tc_map, anio_analisis)

    resumen = _generar_resumen_compras(df, proveedores_apertura)
    totales = {
        "total_compras_usd": round(df["monto_usd"].sum(), 2),
        "total_proveedores": df["nombre_proveedor"].nunique(),
    }

    return {
        "resumen": resumen,
        "totales": totales,
        "detalle": df.to_dict(orient="records"),
    }


def _leer_comprobantes_recibidos(path: str) -> pd.DataFrame:
    """Lee archivo de comprobantes recibidos de ARCA."""
    for skip in range(5):
        try:
            df = pd.read_excel(path, header=skip, dtype=str)
            df = df.dropna(how="all").dropna(axis=1, how="all")
            if len(df.columns) >= 5:
                break
        except Exception:
            continue
    return df


def _procesar_recibidos(df: pd.DataFrame, tc_map: dict, anio: int) -> pd.DataFrame:
    """Normaliza y convierte a USD los comprobantes recibidos."""
    cols_lower = {c.lower(): c for c in df.columns}

    def find(kws):
        for kw in kws:
            for cl, co in cols_lower.items():
                if kw in cl:
                    return co
        return None

    col_fecha = find(["fecha", "date"])
    col_tipo = find(["tipo", "comprobante"])
    col_pv = find(["punto de venta", "pto vta", "pv"])
    col_num = find(["número", "numero", "nro"])
    col_cuit = find(["cuit", "cuil"])
    col_nombre = find(["denominación", "denominacion", "nombre", "razon social", "razón social"])
    col_moneda = find(["moneda", "mon"])
    col_tc = find(["tipo de cambio", "tc", "t/c"])
    col_total = find(["importe total", "total", "imp. total"])

    result = []
    for _, row in df.iterrows():
        try:
            tipo = normalizar_tipo_comprobante(row.get(col_tipo, "FC"))
            fecha = pd.to_datetime(row.get(col_fecha, ""), errors="coerce")
            if pd.isna(fecha):
                continue

            if anio and fecha.year != anio:
                continue

            pv = str(row.get(col_pv, "0")).strip().zfill(5) if col_pv else "00000"
            num = str(row.get(col_num, "0")).strip().zfill(8) if col_num else "00000000"
            numero = f"{pv}-{num}"

            cuit = str(row.get(col_cuit, "")).strip() if col_cuit else ""
            nombre = str(row.get(col_nombre, "")).strip().upper() if col_nombre else ""
            moneda = str(row.get(col_moneda, "ARS")).upper() if col_moneda else "ARS"
            tc_val = normalizar_monto(row.get(col_tc)) if col_tc else 0
            monto_total = normalizar_monto(row.get(col_total, 0))

            # Convertir a USD
            if moneda in ("USD", "U$S", "DOLAR", "DÓLAR"):
                monto_usd = monto_total
            else:
                tc_real = tc_val if tc_val > 1 else obtener_tipo_cambio_fecha(tc_map, fecha.date(), moneda)
                monto_usd = monto_total / tc_real if tc_real else monto_total

            # Signo por tipo
            if tipo == "NC":
                monto_usd = -abs(monto_usd)
            else:
                monto_usd = abs(monto_usd)

            result.append({
                "fecha": fecha.strftime("%Y-%m-%d"),
                "mes": fecha.month,
                "tipo_comprobante": tipo,
                "numero_comprobante": numero,
                "cuit_proveedor": cuit,
                "nombre_proveedor": nombre,
                "moneda": moneda,
                "monto_usd": round(monto_usd, 2),
            })
        except Exception:
            continue

    return pd.DataFrame(result)


def _generar_resumen_compras(df: pd.DataFrame, proveedores_apertura: List[str]) -> List[Dict]:
    """
    Genera resumen mensual por proveedor.
    Para proveedores en proveedores_apertura, genera filas separadas por FC/NC/ND.
    """
    if df.empty:
        return []

    proveedores_apertura_upper = {p.upper().strip() for p in proveedores_apertura}
    result = []

    proveedores = df["nombre_proveedor"].unique()

    for prov in proveedores:
        df_prov = df[df["nombre_proveedor"] == prov]
        cuit = df_prov["cuit_proveedor"].iloc[0] if not df_prov.empty else ""

        if prov in proveedores_apertura_upper:
            # Apertura por tipo de comprobante
            for tipo in ["FC", "ND", "NC"]:
                df_tipo = df_prov[df_prov["tipo_comprobante"] == tipo]
                if df_tipo.empty:
                    continue
                row = _construir_fila_mensual(df_tipo, f"{prov} — {tipo}", cuit)
                result.append(row)
        else:
            row = _construir_fila_mensual(df_prov, prov, cuit)
            result.append(row)

    # Ordenar por total descendente
    result.sort(key=lambda x: x.get("Total", 0), reverse=True)
    return result


def _construir_fila_mensual(df: pd.DataFrame, nombre: str, cuit: str) -> Dict:
    meses_vals = {}
    for m in range(1, 13):
        val = df[df["mes"] == m]["monto_usd"].sum()
        meses_vals[MESES[m - 1]] = round(float(val), 2)
    total = round(sum(meses_vals.values()), 2)
    return {
        "nombre_proveedor": nombre,
        "cuit_proveedor": cuit,
        **meses_vals,
        "Total": total,
    }
