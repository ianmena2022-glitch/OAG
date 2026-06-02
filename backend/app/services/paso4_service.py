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
    normalizar_numero_comprobante,
    _convertir_a_usd,
)
from ..ai.smart_parser import parsear_excel


RECIBIDOS_SCHEMA = {
    "tipo_comprobante": ["tipo de comprobante", "tipo comprobante", "tipo"],
    "punto_venta": ["punto de venta", "pto. vta", "pto vta", "pto venta", "pv"],
    "numero_comprobante": ["número desde", "numero desde", "nro desde",
                            "nro comprobante", "nro. comprobante",
                            "número comprobante", "comprobante", "factura",
                            "número", "numero", "nro"],
    "fecha": ["fecha de emisión", "fecha emisión", "fecha emision",
              "fecha comprobante", "fecha"],
    "cuit_proveedor": ["cuit emisor", "cuit vendedor", "cuit proveedor", "cuit", "cuil"],
    "nombre_proveedor": ["denominación emisor", "denominacion emisor",
                         "razón social", "razon social", "denominación",
                         "denominacion", "nombre"],
    "moneda": ["moneda", "mon"],
    "tipo_cambio": ["tipo de cambio", "t/c", "tc", "cambio"],
    "monto_total": ["importe total", "imp. total", "imp total", "total"],
}

RECIBIDOS_EXCLUSIONES = {
    # En comprobantes RECIBIDOS, el "receptor" es el propio distribuidor → lo excluimos del CUIT del emisor
    "numero_comprobante": ["cuit", "cuil", "receptor", "doc receptor", "denominacion"],
    "cuit_proveedor": ["receptor"],
    "nombre_proveedor": ["receptor"],
    "fecha": ["vencimiento", "vto"],
}

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def leer_archivo_proveedores(path: str) -> dict:
    """
    Lee el archivo de proveedores y devuelve la configuración estructurada.

    Soporta múltiples formatos (cada DS exporta como puede):
      1. Columnas CUIT + RAZÓN SOCIAL + ACCIÓN (ABRIR/INCLUIR)
      2. Columnas CUIT + RAZÓN SOCIAL (sin ACCIÓN) → todos como ABRIR
      3. Sola columna de nombres → todos como ABRIR (legacy)

    Devuelve:
      {
        "por_cuit":    {cuit_normalizado: "ABRIR"|"INCLUIR"},
        "por_nombre":  {nombre_upper: "ABRIR"|"INCLUIR"},
      }
    El caller intenta match por CUIT primero (más robusto), después por nombre.
    """
    try:
        df = pd.read_excel(path, dtype=str)
    except Exception as e:
        print(f"[PROVEEDORES] No se pudo leer {path}: {e}")
        return {"por_cuit": {}, "por_nombre": {}}

    if df.empty:
        return {"por_cuit": {}, "por_nombre": {}}

    def _norm_col(c):
        return str(c or "").strip().lower()

    cols_norm = {_norm_col(c): c for c in df.columns}

    def _find_col(*kws):
        for kw in kws:
            for cn, co in cols_norm.items():
                if kw in cn:
                    return co
        return None

    col_cuit = _find_col("cuit", "cuil")
    col_nombre = _find_col("razon social", "razón social", "razon", "razón",
                           "nombre", "denominacion", "denominación")
    col_accion = _find_col("accion", "acción", "categoria", "categoría",
                           "tipo", "incluir", "abrir")

    # Caso legacy: archivo con sola una columna de nombres
    if not col_cuit and not col_nombre:
        primera = df.columns[0]
        col_nombre = primera

    por_cuit = {}
    por_nombre = {}

    def _digits(s):
        return "".join(c for c in str(s or "") if c.isdigit())

    for _, row in df.iterrows():
        # Detectar acción para esta fila
        accion = "ABRIR"   # default si no hay columna o valor vacío
        if col_accion:
            v = str(row.get(col_accion, "")).strip().upper()
            if "INCLUIR" in v:
                accion = "INCLUIR"
            elif "ABRIR" in v:
                accion = "ABRIR"
            # Otros valores → tratar como ABRIR (default)

        if col_cuit:
            cuit_n = _digits(row.get(col_cuit))
            if cuit_n:
                por_cuit[cuit_n] = accion

        if col_nombre:
            nombre_raw = row.get(col_nombre)
            if nombre_raw is not None and not (isinstance(nombre_raw, float) and pd.isna(nombre_raw)):
                nombre = str(nombre_raw).strip().upper()
                if nombre and nombre != "NAN":
                    por_nombre[nombre] = accion

    print(f"[PROVEEDORES] Cargados: {len(por_cuit)} por CUIT, "
          f"{len(por_nombre)} por nombre. "
          f"Accion={'columna detectada' if col_accion else 'sin columna (default ABRIR)'}")
    return {"por_cuit": por_cuit, "por_nombre": por_nombre}


def ejecutar_paso4(
    path_recibidos: str,
    path_tc: str,
    proveedores_config: dict,
    anio_analisis: int,
) -> dict:
    """
    Ejecuta el análisis de compras.

    proveedores_config: dict {"por_cuit": {...}, "por_nombre": {...}} con la
    accion ("ABRIR" o "INCLUIR") por cuit y por nombre.
      - ABRIR: el proveedor se desglosa en filas separadas FC/NC/ND y se
        incluye siempre en el top 90% de Paso 5 (aunque no califique por monto).
      - INCLUIR: el proveedor aparece como una sola fila y se incluye siempre
        en el top 90% (aunque sea chico).
      - Cualquier otro proveedor: una fila, entra al top 90% solo si su monto
        lo califica.

    Si el archivo de proveedores no se cargó, proveedores_config viene vacío y
    todos los proveedores quedan sin categoría (comportamiento default).
    """
    tc_map = leer_tipos_cambio(path_tc)
    df, recibidos_info = _leer_comprobantes_recibidos(path_recibidos)
    df = _procesar_recibidos(df, tc_map, anio_analisis, recibidos_info["mapping"])

    resumen = _generar_resumen_compras(df, proveedores_config or {})
    totales = {
        "total_compras_usd": round(df["monto_usd"].sum(), 2),
        "total_proveedores": df["nombre_proveedor"].nunique(),
    }

    # Diagnóstico estructurado
    parser_diagnostico = []
    if recibidos_info:
        parser_diagnostico.append({
            "archivo": "Comprobantes Recibidos (ARCA)",
            "metodo": recibidos_info["metodo"],
            "confianza": recibidos_info["confianza"],
            "mapping": recibidos_info["mapping"],
            "columnas_archivo": recibidos_info.get("columnas_archivo", []),
            "columnas_faltantes": recibidos_info.get("columnas_faltantes", []),
            "columnas_no_mapeadas": recibidos_info.get("columnas_no_mapeadas", []),
            "warnings": recibidos_info.get("warnings", []),
        })

    return {
        "resumen": resumen,
        "totales": totales,
        "detalle": df.to_dict(orient="records"),
        "parser_diagnostico": parser_diagnostico,
    }


def _leer_comprobantes_recibidos(path: str):
    """Lee comprobantes recibidos usando smart_parser."""
    resultado = parsear_excel(
        path=path,
        task_id="arca_recibidos",
        schema=RECIBIDOS_SCHEMA,
        excluir_si_contiene=RECIBIDOS_EXCLUSIONES,
        columnas_criticas=["tipo_comprobante", "numero_comprobante", "fecha",
                           "cuit_proveedor", "monto_total"],
    )
    print(f"[Recibidos] método={resultado['metodo']} conf={resultado['confianza']:.2f} "
          f"mapping={resultado['mapping']} warnings={resultado['warnings']}")
    return resultado["df"], resultado


def _procesar_recibidos(df: pd.DataFrame, tc_map: dict, anio: int, mapping: dict = None) -> pd.DataFrame:
    """Normaliza y convierte a USD los comprobantes recibidos usando el mapping del smart_parser."""
    mapping = mapping or {}
    col_fecha = mapping.get("fecha")
    col_tipo = mapping.get("tipo_comprobante")
    col_pv = mapping.get("punto_venta")
    col_num = mapping.get("numero_comprobante")
    col_cuit = mapping.get("cuit_proveedor")
    col_nombre = mapping.get("nombre_proveedor")
    col_moneda = mapping.get("moneda")
    col_tc = mapping.get("tipo_cambio")
    col_total = mapping.get("monto_total")

    result = []
    for _, row in df.iterrows():
        try:
            tipo = normalizar_tipo_comprobante(row.get(col_tipo, "FC"))
            fecha = pd.to_datetime(row.get(col_fecha, ""), errors="coerce")
            if pd.isna(fecha):
                continue

            if anio and fecha.year != anio:
                continue

            pv_raw = row.get(col_pv) if col_pv else None
            num_raw = row.get(col_num) if col_num else None
            numero = normalizar_numero_comprobante(pv=pv_raw, num=num_raw)

            cuit = str(row.get(col_cuit, "")).strip() if col_cuit else ""
            nombre = str(row.get(col_nombre, "")).strip().upper() if col_nombre else ""
            moneda = str(row.get(col_moneda, "ARS")).upper().strip() if col_moneda else "ARS"
            tc_val = normalizar_monto(row.get(col_tc)) if col_tc else 0
            monto_total = normalizar_monto(row.get(col_total, 0))

            monto_usd = _convertir_a_usd(monto_total, moneda, tc_val, fecha, tc_map)

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


def _generar_resumen_compras(df: pd.DataFrame, proveedores_config: dict) -> List[Dict]:
    """
    Genera resumen mensual por proveedor con su categoría (ABRIR/INCLUIR/None).

    Match estrategia:
      1. Por CUIT normalizado (preferido — robusto a variaciones de nombre)
      2. Por nombre upper (fallback si el CUIT no matchea)
    """
    if df.empty:
        return []

    por_cuit = (proveedores_config or {}).get("por_cuit", {})
    por_nombre = (proveedores_config or {}).get("por_nombre", {})

    def _digits(s):
        return "".join(c for c in str(s or "") if c.isdigit())

    def _categoria(cuit_raw, nombre):
        """Devuelve 'ABRIR' | 'INCLUIR' | ''."""
        cuit_n = _digits(cuit_raw)
        if cuit_n and cuit_n in por_cuit:
            return por_cuit[cuit_n]
        nombre_u = str(nombre or "").strip().upper()
        if nombre_u and nombre_u in por_nombre:
            return por_nombre[nombre_u]
        return ""

    result = []
    proveedores = df["nombre_proveedor"].unique()

    for prov in proveedores:
        df_prov = df[df["nombre_proveedor"] == prov]
        cuit = df_prov["cuit_proveedor"].iloc[0] if not df_prov.empty else ""
        categoria = _categoria(cuit, prov)

        if categoria == "ABRIR":
            # Apertura por tipo de comprobante: una fila por FC/ND/NC
            for tipo in ["FC", "ND", "NC"]:
                df_tipo = df_prov[df_prov["tipo_comprobante"] == tipo]
                if df_tipo.empty:
                    continue
                row = _construir_fila_mensual(df_tipo, f"{prov} — {tipo}", cuit)
                row["categoria"] = "ABRIR"
                result.append(row)
        elif categoria == "INCLUIR":
            row = _construir_fila_mensual(df_prov, prov, cuit)
            row["categoria"] = "INCLUIR"
            result.append(row)
        else:
            row = _construir_fila_mensual(df_prov, prov, cuit)
            row["categoria"] = ""
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
