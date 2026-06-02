"""
Paso 2 — Análisis Producto Ventas
Ranking clientes, ranking productos, muestreo, clasificación agroquímicos,
tabla de apertura.
"""
import os
import random
import pandas as pd
import numpy as np
from typing import List, Dict, Optional

from ..ai.clasificador import clasificar_productos
from ..core.config import settings
from .paso1_service import normalizar_tipo_comprobante, normalizar_monto, es_articulo_no_producto

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def ejecutar_paso2(
    path_bajada_norm: str,
    maestro_syngenta: List[str],
    clientes_especiales: List[str],
    expediente_id: int,
    anio_analisis: int,
) -> dict:
    """
    Ejecuta todos los sub-reportes del Paso 2.
    """
    df = pd.read_excel(path_bajada_norm)
    df = _preparar_df(df, anio_analisis)

    # Filtrar ajustes financieros (AJUSTE DE PRECIO, INTERES, RECARGO, etc.)
    # de los análisis por producto. NO son productos vendidos — inflan los
    # rankings, la tabla de apertura y el cruce CRM.
    if not df.empty and "articulo" in df.columns:
        es_no_prod = df["articulo"].apply(es_articulo_no_producto)
        n_no_prod = int(es_no_prod.sum())
        if n_no_prod:
            print(f"[Paso 2] Excluidas {n_no_prod} líneas de ajustes financieros "
                  f"(AJUSTE/INTERES/RECARGO/etc) — no son productos")
            df = df[~es_no_prod].copy()

    upload_dir = os.path.join(settings.UPLOAD_DIR, str(expediente_id))
    os.makedirs(upload_dir, exist_ok=True)

    # 1. Ranking clientes
    ranking_clientes = _ranking_clientes(df)

    # 2. Ranking productos
    ranking_productos = _ranking_productos(df)

    # 3. Muestreo
    muestreo = _generar_muestreo(df, ranking_clientes, ranking_productos, clientes_especiales)

    # 4. Clasificación con IA
    productos_unicos = df["articulo"].dropna().unique().tolist()
    clasificaciones = clasificar_productos(productos_unicos, maestro_syngenta)
    clasificacion_map = {c["producto"]: c for c in clasificaciones}

    # 6. Filtros
    #
    # AGROQUÍMICOS — usa la clasificación de la IA (es la mejor info que
    # tenemos sobre si un producto cualquiera es agro o no). Si la IA falla
    # y el producto es Syngenta (por marca), lo marcamos agro=SI igual.
    #
    # SYNGENTA — usa el MAESTRO Syngenta como ground truth, no la clasificación
    # IA. Razones:
    #   (a) El maestro es admin-curado y deterministico — la IA tiene falsos
    #       positivos y negativos.
    #   (b) Paso 3 usa el mismo criterio (extrae marcas del CRM Syngenta) →
    #       así los totales de Paso 2 y Paso 3 coinciden.
    # Si el maestro está vacío caemos a la clasificación IA como fallback.
    productos_syngenta = _productos_syngenta_por_marca(
        productos_unicos, maestro_syngenta, clasificaciones
    )
    productos_agro = {c["producto"] for c in clasificaciones if c["agroquimico"] == "SI"}
    # Cualquier Syngenta es agroquímico por definición — override por si la
    # IA fallo o lo clasifico mal.
    productos_agro |= productos_syngenta

    df_agro = df[df["articulo"].isin(productos_agro)].copy()
    df_syngenta = df[df["articulo"].isin(productos_syngenta)].copy()

    # 5. Reporte de clasificación — la columna Syngenta refleja la decisión
    # determinística (match por marca del maestro), no la opinión de la IA.
    # La justificación textual sigue siendo la de la IA (informativa).
    reporte_clasificacion = []
    for c in clasificaciones:
        prod = c["producto"]
        es_syn = prod in productos_syngenta
        es_agro = prod in productos_agro
        reporte_clasificacion.append({
            "articulo": prod,
            "agroquimico": "SI" if es_agro else ("NO" if c["agroquimico"] in ("SI", "NO") else c["agroquimico"]),
            "syngenta": "SI" if es_syn else "NO",
            "justificacion": c.get("justificacion", ""),
        })

    # 7. Tabla de apertura
    tabla_apertura = _tabla_apertura(df_agro, clasificacion_map, anio_analisis)

    # Guardar archivos intermedios
    path_agro = os.path.join(upload_dir, "bajada_agroquimicos.xlsx")
    df_agro.to_excel(path_agro, index=False)
    # Subset Syngenta (lo que realmente usa el Paso 3 para cruzar con el CRM)
    path_syngenta = os.path.join(upload_dir, "bajada_syngenta.xlsx")
    df_syngenta.to_excel(path_syngenta, index=False)

    totales = {
        "total_facturado_usd": round(df["monto_usd"].sum(), 2),
        "total_agro_usd": round(df_agro["monto_usd"].sum(), 2),
        "total_syngenta_usd": round(df_syngenta["monto_usd"].sum(), 2),
        "cant_productos": len(productos_unicos),
        "cant_productos_agro": len(productos_agro),
        "cant_productos_syngenta": len(productos_syngenta),
        "diagnostico": df.attrs.get("diagnostico", {}),
    }

    return {
        "ranking_clientes": ranking_clientes,
        "ranking_productos": ranking_productos,
        "muestreo": muestreo,
        "clasificacion": reporte_clasificacion,
        "tabla_apertura": tabla_apertura,
        "agroquimicos_path": path_agro,
        "syngenta_path": path_syngenta,
        "totales": totales,
        # Guardas determinísticas (no dependen de IA) para mostrar como alertas
        "guardas": _guardas_paso2(df, totales),
    }


def _productos_syngenta_por_marca(productos_unicos: list, maestro: list,
                                  clasificaciones_ia: list) -> set:
    """
    Decide qué productos de la gestión son Syngenta usando el MAESTRO Syngenta
    como ground truth (substring match de marca, mismo criterio que Paso 3
    contra el CRM). La IA queda solo como fallback cuando no hay maestro.

    Estrategia:
      - Extraer las marcas únicas del maestro (primera palabra significativa
        + el nombre completo).
      - Marcar producto como Syngenta si su nombre contiene alguna marca del
        maestro.
      - Si el maestro está vacío → fallback a la clasificación IA.
    """
    if not maestro:
        return {c["producto"] for c in clasificaciones_ia if c.get("syngenta") == "SI"}

    marcas = set()
    for nombre in maestro:
        if not nombre:
            continue
        s = str(nombre).strip().upper()
        if not s:
            continue
        marcas.add(s)
        primera = s.split()[0]
        if len(primera) > 2 and primera.isalpha():
            marcas.add(primera)
    GENERICAS = {"PRODUCTO", "ARTICULO", "ITEM", "DESC", "VARIOS", "OTROS"}
    marcas -= GENERICAS

    if not marcas:
        return {c["producto"] for c in clasificaciones_ia if c.get("syngenta") == "SI"}

    resultado = set()
    for prod in productos_unicos:
        if not prod:
            continue
        p_upper = str(prod).upper()
        if any(m in p_upper for m in marcas):
            resultado.add(prod)
    return resultado


def _guardas_paso2(df: pd.DataFrame, totales: dict) -> list:
    """
    Controles determinísticos del Paso 2. Mensajes simples y con la ubicación
    del problema (qué archivo / qué columna mirar). Devuelve lista de alertas.
    """
    alertas = []
    total = sum(abs(x) for x in df["monto_usd"]) or 0.0

    def _archivos_de(mask) -> str:
        if "archivo" not in df.columns:
            return ""
        vals = [a for a in df.loc[mask, "archivo"].dropna().unique().tolist() if str(a).strip()]
        return ", ".join(map(str, vals))

    # 1. Ventas sin cliente identificado
    mask_sn = df["cliente"] == "SIN NOMBRE"
    monto_sn = df.loc[mask_sn, "monto_usd"].abs().sum()
    if total and monto_sn / total > 0.20:
        arch = _archivos_de(mask_sn)
        alertas.append({
            "nivel": "warning",
            "titulo": "Hay ventas sin cliente identificado",
            "detalle": (
                f"El {monto_sn / total * 100:.0f}% de lo facturado (US$ {monto_sn:,.0f}) está en filas "
                f"sin nombre de cliente." + (f" Archivo(s): {arch}." if arch else "")
            ),
            "sugerencia": "Revisá la columna de cliente en ese archivo: puede faltar o estar vacía en algunas filas.",
        })

    # 2. Ventas sin producto identificado
    mask_sd = df["articulo"] == "SIN DESCRIPCIÓN"
    monto_sd = df.loc[mask_sd, "monto_usd"].abs().sum()
    if total and monto_sd / total > 0.30:
        arch = _archivos_de(mask_sd)
        alertas.append({
            "nivel": "warning",
            "titulo": "Hay ventas sin producto identificado",
            "detalle": (
                f"El {monto_sd / total * 100:.0f}% de lo facturado (US$ {monto_sd:,.0f}) no tiene producto "
                f"asignado." + (f" Archivo(s): {arch}." if arch else "")
                + " (Las notas de crédito/débito no tienen detalle de producto y caen acá; eso es normal.)"
            ),
            "sugerencia": "Si el porcentaje es alto por facturas de venta, revisá la columna de producto en ese archivo.",
        })

    # 3. Año pedido distinto al de los datos
    diag = totales.get("diagnostico") or {}
    if str(diag.get("filtro_aplicado", "")).startswith("SIN FILTRO"):
        anios = diag.get("anios_presentes") or []
        pedido = diag.get("anio_pedido")
        alertas.append({
            "nivel": "info",
            "titulo": "El año pedido no coincide con los datos",
            "detalle": (
                f"Pediste analizar el año {pedido}, pero los archivos tienen datos de "
                f"{', '.join(map(str, anios)) or 'otro año'}. Se analizaron todos los datos disponibles."
            ),
            "sugerencia": f"Si el período correcto es {', '.join(map(str, anios)) or 'otro'}, cambiá el año del expediente.",
        })

    return alertas


def _preparar_df(df: pd.DataFrame, anio: int) -> pd.DataFrame:
    """Normaliza tipos y filtra por año. Tolera nombres de columna variables.

    Adjunta diagnóstico en df.attrs["diagnostico"] para surface en los totales:
      filas_archivo, filas_anio, anios_presentes, anio_pedido, filtro_aplicado.
    """
    df = df.copy()
    diag = {"filas_archivo": int(len(df))}

    # ── fecha ── buscar columna con nombre estándar o variantes (exacto → parcial)
    col_fecha = next(
        (c for c in df.columns if str(c).strip().lower() in (
            "fecha", "date", "fecha_emision", "fecha emision", "fecha_comprobante",
            "fecha comprobante", "fecha de emision", "fecha de emisión",
        )),
        None
    )
    if col_fecha is None:
        col_fecha = next(
            (c for c in df.columns
             if "fecha" in str(c).strip().lower() or str(c).strip().lower() == "date"),
            None
        )
    if col_fecha is None:
        raise KeyError(
            f"No se encontró columna 'fecha' en la bajada normalizada. "
            f"Columnas disponibles: {list(df.columns)}. "
            "Re-ejecutá el Paso 1 para regenerar el archivo normalizado."
        )
    df["fecha"] = pd.to_datetime(df[col_fecha], errors="coerce")

    # Años efectivamente presentes (descarta NaT)
    anios_presentes = sorted(
        int(a) for a in df["fecha"].dt.year.dropna().unique().tolist()
    )
    diag["anios_presentes"] = anios_presentes
    diag["anio_pedido"] = int(anio) if anio else None

    # ── filtro por año NO destructivo ──
    # Solo se filtra cuando el año pedido EXISTE en los datos. En cualquier otro
    # caso (año no presente, o fechas que no parsean) se conservan TODAS las filas
    # para que los rankings de clientes/productos siempre tengan datos. La tabla
    # de apertura mensual igual se arma solo con las filas que tengan fecha válida.
    if anio and anio in anios_presentes:
        df = df[df["fecha"].dt.year == anio]
        diag["filtro_aplicado"] = f"año {anio}"
    elif anio and anios_presentes:
        diag["filtro_aplicado"] = (
            f"SIN FILTRO — no hay datos del año {anio}; "
            f"se usan todos los años presentes: {anios_presentes}"
        )
    elif anio:
        diag["filtro_aplicado"] = (
            f"SIN FILTRO — ninguna fecha del archivo se pudo interpretar "
            f"(revisar columna de fecha en la bajada). Año pedido: {anio}"
        )
    else:
        diag["filtro_aplicado"] = "sin año configurado — se usan todas las filas"

    diag["filas_anio"] = int(len(df))
    df.attrs["diagnostico"] = diag
    df["mes"] = df["fecha"].dt.month

    # ── monto_usd ──
    if "monto_usd" in df.columns:
        df["monto_usd"] = pd.to_numeric(df["monto_usd"], errors="coerce").fillna(0)
    elif "monto_total" in df.columns:
        df["monto_usd"] = pd.to_numeric(df["monto_total"], errors="coerce").fillna(0)
    else:
        df["monto_usd"] = 0.0

    # ── articulo ── buscar variantes (match exacto primero, luego parcial)
    _ART_EXACT = {
        "articulo", "artículo", "producto", "descripcion", "descripción",
        "description", "item", "detalle", "concepto",
    }
    _ART_SUBSTR = (
        "articulo", "artículo", "producto", "descripcion", "descripción",
        "detalle", "item", "concepto", "description", "product",
    )
    _ART_EXCL = (
        "cliente", "razon", "cuit", "cuil", "numero", "número", "nro",
        "comprobante", "tipo", "fecha", "moneda", "total", "importe", "monto",
        "subtotal", "iva",
    )
    col_art = next(
        (c for c in df.columns if str(c).strip().lower() in _ART_EXACT),
        None
    )
    if col_art is None:
        col_art = next(
            (c for c in df.columns
             if any(k in str(c).strip().lower() for k in _ART_SUBSTR)
             and not any(excl in str(c).strip().lower() for excl in _ART_EXCL)),
            None
        )
    df["articulo"] = (
        df[col_art].fillna("SIN DESCRIPCIÓN").astype(str).str.strip().str.upper()
        if col_art else "SIN DESCRIPCIÓN"
    )

    # ── cliente ──
    _CLI_EXACT = {
        "cliente", "razon_social", "razon social", "client", "nombre_cliente",
        "nombre cliente", "denominacion", "denominación",
    }
    _CLI_SUBSTR = ("cliente", "razon", "receptor", "comprador", "denominacion", "denominación")
    _CLI_EXCL = (
        "cuit", "cuil", "numero", "número", "nro", "comprobante",
        "tipo", "fecha", "moneda", "total", "importe", "monto", "articulo",
    )
    col_cli = next(
        (c for c in df.columns if str(c).strip().lower() in _CLI_EXACT),
        None
    )
    if col_cli is None:
        col_cli = next(
            (c for c in df.columns
             if any(k in str(c).strip().lower() for k in _CLI_SUBSTR)
             and not any(excl in str(c).strip().lower() for excl in _CLI_EXCL)),
            None
        )
    df["cliente"] = (
        df[col_cli].fillna("SIN NOMBRE").astype(str).str.strip().str.upper()
        if col_cli else "SIN NOMBRE"
    )

    # ── numero/tipo comprobante ── (opcionales, usados en muestreo)
    col_nro = next(
        (c for c in df.columns if str(c).strip().lower() in (
            "numero_comprobante", "numero comprobante", "nro", "nro.", "numero", "número"
        )), None
    )
    col_tipo = next(
        (c for c in df.columns if str(c).strip().lower() in (
            "tipo_comprobante", "tipo comprobante", "tipo", "type"
        )), None
    )
    if col_nro and "numero_comprobante" not in df.columns:
        df["numero_comprobante"] = df[col_nro].astype(str)
    if col_tipo and "tipo_comprobante" not in df.columns:
        df["tipo_comprobante"] = df[col_tipo].astype(str)

    return df


def _ranking_clientes(df: pd.DataFrame) -> List[Dict]:
    grouped = (
        df.groupby("cliente")["monto_usd"]
        .sum()
        .reset_index()
        .rename(columns={"monto_usd": "total_usd"})
        .sort_values("total_usd", ascending=False)
    )
    total = grouped["total_usd"].sum()
    grouped["porcentaje"] = (grouped["total_usd"] / total * 100).round(2) if total else 0
    grouped["total_usd"] = grouped["total_usd"].round(2)
    return grouped.to_dict(orient="records")


def _ranking_productos(df: pd.DataFrame) -> List[Dict]:
    grouped = (
        df.groupby("articulo")["monto_usd"]
        .sum()
        .reset_index()
        .rename(columns={"monto_usd": "total_usd"})
        .sort_values("total_usd", ascending=False)
    )
    total = grouped["total_usd"].sum()
    grouped["porcentaje"] = (grouped["total_usd"] / total * 100).round(2) if total else 0
    grouped["total_usd"] = grouped["total_usd"].round(2)
    return grouped.to_dict(orient="records")


def _generar_muestreo(
    df: pd.DataFrame,
    ranking_clientes: List[Dict],
    ranking_productos: List[Dict],
    clientes_especiales: List[str],
    n_muestras: int = 70,
) -> List[Dict]:
    """
    Selecciona 70 comprobantes de forma aleatoria ponderada entre
    principales clientes y productos. Incluye forzados de clientes_especiales.
    """
    # Top 10 clientes y top 10 productos (80% de la selección)
    top_clientes = {r["cliente"] for r in ranking_clientes[:10]}
    top_productos = {r["articulo"] for r in ranking_productos[:10]}

    # Normalizar clientes especiales
    especiales = {c.upper().strip() for c in clientes_especiales}

    # Pool principal: registros de top clientes o top productos
    mask_principal = (
        df["cliente"].isin(top_clientes) |
        df["articulo"].isin(top_productos) |
        df["cliente"].isin(especiales)
    )
    df_pool = df[mask_principal].copy()

    if len(df_pool) == 0:
        df_pool = df.copy()

    # Comprobantes únicos del pool (agrupar por número de comprobante)
    comp_cols = ["numero_comprobante", "tipo_comprobante", "fecha", "cliente", "monto_usd"]
    available_cols = [c for c in comp_cols if c in df_pool.columns]
    df_comp = df_pool[available_cols].drop_duplicates(
        subset=[c for c in ["numero_comprobante", "tipo_comprobante"] if c in available_cols]
    )

    # Forzar clientes especiales
    df_especiales = df_comp[df_comp.get("cliente", pd.Series(dtype=str)).isin(especiales)]
    df_resto = df_comp[~df_comp.index.isin(df_especiales.index)]

    # Muestra aleatoria del resto
    n_resto = max(0, n_muestras - len(df_especiales))
    if len(df_resto) > n_resto:
        df_muestra = pd.concat([df_especiales, df_resto.sample(n=n_resto, random_state=42)])
    else:
        df_muestra = pd.concat([df_especiales, df_resto])

    df_muestra = df_muestra.head(n_muestras)

    result = []
    for _, row in df_muestra.iterrows():
        result.append({
            "fecha": str(row.get("fecha", ""))[:10],
            "tipo_comprobante": str(row.get("tipo_comprobante", "")),
            "numero_comprobante": str(row.get("numero_comprobante", "")),
            "cliente": str(row.get("cliente", "")),
            "monto_usd": round(float(row.get("monto_usd", 0)), 2),
            "es_especial": str(row.get("cliente", "")) in especiales,
        })

    return result


def _tabla_apertura(df_agro: pd.DataFrame, clasificacion_map: dict, anio: int) -> List[Dict]:
    """
    Genera tabla de apertura: producto | Syngenta SI/NO | 12 meses | Total
    Solo agroquímicos, montos netos en USD.
    """
    if df_agro.empty:
        return []

    # monto_usd ya es el neto convertido a USD (lo calcula el Paso 1 al construir
    # la bajada normalizada). No usar monto_neto crudo: ese estaría en ARS.
    df_agro = df_agro.copy()
    df_agro["monto_apertura"] = pd.to_numeric(df_agro["monto_usd"], errors="coerce").fillna(0)

    pivot = df_agro.pivot_table(
        index="articulo",
        columns="mes",
        values="monto_apertura",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()

    result = []
    for _, row in pivot.iterrows():
        producto = str(row["articulo"])
        clasif = clasificacion_map.get(producto, {})
        es_syngenta = clasif.get("syngenta", "NO")

        meses_vals = {}
        for m in range(1, 13):
            meses_vals[MESES[m - 1]] = round(float(row.get(m, 0)), 2)

        total = round(sum(meses_vals.values()), 2)

        result.append({
            "articulo": producto,
            "syngenta": es_syngenta,
            **meses_vals,
            "Total": total,
        })

    # Ordenar por Total descendente
    result.sort(key=lambda x: x["Total"], reverse=True)
    return result
