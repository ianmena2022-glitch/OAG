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
from .paso1_service import (
    normalizar_tipo_comprobante,
    normalizar_monto,
    normalizar_numero_comprobante,
)


# Schema CRM Syngenta. ORDEN IMPORTANTE: los campos del DISTRIBUIDOR ("Cuenta:")
# van primero para que el parser "consuma" esas columnas antes que las del
# cliente ("Vendido a:") — así no las confunde.
CRM_SCHEMA = {
    # ── Distribuidor (la "Cuenta" de Syngenta que reporta) ──────────────────
    "cuit_distribuidor": [
        "cuenta: cuit", "cuenta cuit", "cuit cuenta",
        "cuit del distribuidor", "cuit distribuidor", "account cuit",
    ],
    "nombre_distribuidor": [
        "cuenta: nombre", "cuenta nombre", "nombre de la cuenta",
        "nombre cuenta", "razon social cuenta", "razón social cuenta",
        "nombre del distribuidor", "account name",
    ],
    # ── Cliente final del distribuidor ──────────────────────────────────────
    "cuit_cliente_crm": [
        "vendido a: cuit", "vendido a cuit",
        "cuit cliente", "cuit comprador", "cliente cuit",
    ],
    "cliente_crm": [
        "vendido a: nombre", "vendido a nombre",
        "nombre cliente", "razón social cliente",
        "cliente", "razón social", "razon social",
        "denominación", "denominacion", "comprador",
    ],
    # ── Datos del comprobante / línea ───────────────────────────────────────
    "fecha_crm": ["fecha de la factura", "fecha factura", "fecha venta", "fecha", "date"],
    "tipo_crm": ["tipo de documento", "tipo de comprobante", "tipo comprobante", "tipo"],
    "numero_crm": [
        "numero de factura", "número de factura",
        "numero factura", "número factura",
        "nro comprobante", "nro. comprobante",
        "número desde", "numero desde",
        "comprobante", "factura",
    ],
    "producto_crm": [
        "descripción homogénea", "descripcion homogenea",
        "nombre del producto", "producto de lealtad",
        "descripción producto", "descripcion producto",
        "producto", "artículo", "articulo",
        "descripción", "descripcion", "item",
    ],
    "cantidad_crm": [
        "volume in normalized", "volumen normalizado", "volumen",
        "cantidad", "cant", "qty", "unidades",
    ],
    "monto_crm": [
        "monto de la factura", "monto factura",
        "monto usd", "importe usd", "total usd",
        "monto", "importe total", "total",
    ],
}

# Exclusiones para evitar colisiones de mapeo entre columnas "Cuenta:" vs
# "Vendido a:" (distribuidor vs cliente final), y para que el número de
# factura no se confunda con un número de cuenta interno de Syngenta.
CRM_EXCLUSIONES = {
    "cuit_cliente_crm":    ["cuenta", "distribuidor"],
    "cliente_crm":         ["cuenta", "distribuidor"],
    "numero_crm":          ["cuit", "cuil", "doc", "cuenta", "vendido a"],
    "tipo_crm":            ["cuit", "cuil", "doc", "cuenta", "vendido a"],
    "cantidad_crm":        ["monto", "importe", "precio", "price"],
    "producto_crm":        ["codigo", "código", "code"],
}


def _solo_digitos(s) -> str:
    """
    Devuelve solo los dígitos de una cadena. Para comparar CUITs sin formato.

    Maneja el caso openpyxl/read_only en el que un CUIT guardado como número
    en Excel viene como float 30708563311.0 → str sería "30708563311.0" y
    los dígitos darían "307085633110" (12 cifras). Convertir a int primero
    elimina el ".0" espurio.
    """
    if s is None:
        return ""
    if isinstance(s, float):
        s = str(int(s)) if s.is_integer() else str(s)
    return "".join(c for c in str(s) if c.isdigit())


def _norm_header(s) -> str:
    """Normaliza un nombre de columna a minúsculas sin acentos para matchear."""
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(s or "").lower())
        if not unicodedata.combining(c)
    ).strip()


def _leer_crm_filtrado_streaming(path: str, cuit_distribuidor: str) -> tuple:
    """
    Lee el archivo CRM filtrando INLINE por el CUIT del distribuidor del
    expediente, en lugar de cargar las 200k+ filas en pandas. Solo quedan en
    memoria las filas del distribuidor actual (~unos miles).

    Usa python-calamine (Rust, ~5x más rápido que openpyxl) si está disponible.
    Cae a openpyxl read-only como fallback. Si ninguno aplica, devuelve
    (None, diag) y el caller usa el camino tradicional con pd.read_excel.
    """
    cuit_norm = _solo_digitos(cuit_distribuidor)
    if not cuit_norm:
        return None, {"motivo": "expediente sin CUIT configurado"}

    # ── Intento 1: calamine (rápido) ────────────────────────────────────────
    try:
        import python_calamine
        wb = python_calamine.CalamineWorkbook.from_path(path)
        sheet = wb.get_sheet_by_index(0)
        data = sheet.to_python()
        if not data:
            return None, {"motivo": "archivo vacío"}
        header = list(data[0])
        rows_iter = iter(data[1:])
        metodo = "streaming (calamine)"
    except Exception as e:
        # ── Intento 2: openpyxl como fallback ───────────────────────────────
        try:
            from openpyxl import load_workbook
            wb = load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            r_iter = ws.iter_rows(values_only=True)
            try:
                header = list(next(r_iter))
            except StopIteration:
                wb.close()
                return None, {"motivo": "archivo vacío"}
            rows_iter = r_iter
            metodo = "streaming (openpyxl)"
            # cerramos wb al final, no lo cerramos acá porque iter es perezoso
        except Exception as e2:
            return None, {"motivo": f"no se pudo leer como xlsx (calamine: {e}; openpyxl: {e2})"}

    # ── Localizar columnas de CUIT y nombre del distribuidor ───────────────
    cuit_col_idx = None
    nombre_col_idx = None
    for i, col in enumerate(header):
        cn = _norm_header(col)
        if cuit_col_idx is None and (
            ("cuenta" in cn and "cuit" in cn) or
            ("distribuidor" in cn and "cuit" in cn)
        ):
            cuit_col_idx = i
        if nombre_col_idx is None and (
            ("cuenta" in cn and ("nombre" in cn or "razon" in cn)) or
            ("nombre" in cn and "distribuidor" in cn)
        ):
            nombre_col_idx = i
    if cuit_col_idx is None:
        return None, {"motivo": "no se encontró columna Cuenta: CUIT en el header"}

    # ── Iterar filas, filtrar + enumerar distribuidores en una pasada ──────
    filtradas = []
    total = 0
    distribuidores: dict = {}
    for row in rows_iter:
        total += 1
        if cuit_col_idx >= len(row):
            continue
        val = row[cuit_col_idx]
        if val is None:
            continue
        this_cuit = _solo_digitos(val)
        if not this_cuit:
            continue
        if this_cuit not in distribuidores:
            nombre = ""
            if nombre_col_idx is not None and nombre_col_idx < len(row):
                nombre = str(row[nombre_col_idx] or "")
            distribuidores[this_cuit] = [nombre, 0]
        distribuidores[this_cuit][1] += 1
        if this_cuit == cuit_norm:
            filtradas.append(row)

    diag = {
        "filas_archivo_total": total,
        "filas_distribuidor": len(filtradas),
        "metodo_lectura": metodo,
        "distribuidores_archivo": sorted(
            [{"cuit": c, "nombre": n, "filas": f} for c, (n, f) in distribuidores.items()],
            key=lambda x: -x["filas"],
        ),
    }

    if not filtradas:
        return pd.DataFrame(columns=header), diag

    df = pd.DataFrame(filtradas, columns=header)
    return df, diag


def _numero_crm_a_estandar(valor: str) -> str:
    """
    El CRM de Syngenta usa un formato compuesto en 'Numero de factura':
        'A002226061|FC|A000600020954'
        (cuenta) | (tipo) | (numero fiscal compuesto)

    Esta función extrae la parte fiscal y la normaliza al mismo formato que
    usa Paso 1 ("PPPPP-NNNNNNNN") para que el cruce matchee.
    """
    if not valor or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    s = str(valor).strip()
    # Si tiene '|', tomar la última parte (el número fiscal compuesto)
    if "|" in s:
        s = s.split("|")[-1]
    # Extraer solo dígitos y normalizar usando la misma función de Paso 1
    digitos = _solo_digitos(s)
    if not digitos:
        return ""
    return normalizar_numero_comprobante(valor_combinado=digitos)


def leer_crm(path: str):
    """Lee reporte CRM usando smart_parser. Retorna (df_renombrado, info_parser)."""
    resultado = parsear_excel(
        path=path,
        task_id="crm",
        schema=CRM_SCHEMA,
        excluir_si_contiene=CRM_EXCLUSIONES,
        # cuit_distribuidor es crítico — sin él no podemos filtrar al distribuidor
        # del expediente cuando el CRM contiene reportes de varios distribuidores.
        columnas_criticas=["fecha_crm", "numero_crm", "producto_crm", "monto_crm",
                          "cuit_distribuidor"],
    )
    df = resultado["df"]
    mapping = resultado["mapping"]

    rename_map = {orig: std for std, orig in mapping.items() if orig}
    df = df.rename(columns=rename_map)

    print(f"[CRM] método={resultado['metodo']} conf={resultado['confianza']:.2f} "
          f"mapping={mapping} warnings={resultado['warnings']}")
    return df, resultado


def _filtrar_crm_por_distribuidor(df: pd.DataFrame, cuit_exp: str,
                                  nombre_exp: str = "") -> tuple:
    """
    Filtra el CRM dejando SOLO las filas del distribuidor del expediente.

    Estrategia:
      1. Match exacto por CUIT (dígitos puros) — determinístico, sin IA, infalible.
      2. Si no hay match por CUIT, intenta fuzzy match por nombre (substring
         insensible a mayúsculas / acentos) como fallback de seguridad.
      3. Si tampoco así, levanta un error claro listando los distribuidores
         que SÍ están en el archivo para que el auditor verifique.

    Devuelve (df_filtrado, diag) con info de qué pasó.
    """
    diag = {
        "filas_archivo_total": int(len(df)),
        "filas_distribuidor": 0,
        "metodo_filtro": None,
        "distribuidores_archivo": [],   # primeros N para el mensaje de error
    }
    if "cuit_distribuidor" not in df.columns:
        raise ValueError(
            "El archivo CRM no tiene una columna que identifique al distribuidor "
            "(se esperaba 'Cuenta: CUIT' o similar). Sin esa columna no se puede "
            "filtrar al distribuidor del expediente del CRM consolidado."
        )

    cuit_norm = _solo_digitos(cuit_exp or "")

    # ── 1. Match exacto por CUIT ─────────────────────────────────────────────
    df = df.copy()
    df["__cuit_dist_norm__"] = df["cuit_distribuidor"].astype(str).apply(_solo_digitos)

    if cuit_norm:
        sel = df[df["__cuit_dist_norm__"] == cuit_norm]
        if len(sel) > 0:
            diag["filas_distribuidor"] = int(len(sel))
            diag["metodo_filtro"] = f"CUIT exacto ({cuit_exp})"
            return sel.drop(columns=["__cuit_dist_norm__"]), diag

    # ── 2. Fallback fuzzy por nombre ─────────────────────────────────────────
    if nombre_exp and "nombre_distribuidor" in df.columns:
        import unicodedata
        def _norm(s):
            return "".join(c for c in unicodedata.normalize("NFKD", str(s).lower())
                          if not unicodedata.combining(c)).strip()
        nombre_norm = _norm(nombre_exp)
        if nombre_norm:
            df["__nom_norm__"] = df["nombre_distribuidor"].astype(str).apply(_norm)
            # Match si el nombre del expediente está contenido en el nombre del CRM
            # o viceversa (atajamos diferencias tipo "X SA" vs "X").
            sel = df[df["__nom_norm__"].str.contains(nombre_norm, na=False, regex=False)]
            if len(sel) == 0:
                # Intentar al revés: nombre del CRM contenido en el del expediente
                sel = df[df["__nom_norm__"].apply(
                    lambda v: bool(v) and v in nombre_norm
                )]
            if len(sel) > 0:
                diag["filas_distribuidor"] = int(len(sel))
                diag["metodo_filtro"] = f"nombre similar ({nombre_exp})"
                return sel.drop(columns=["__cuit_dist_norm__", "__nom_norm__"]), diag

    # ── 3. Ningún match: levantar error con la lista de distribuidores ──────
    distrib_disponibles = (
        df.groupby(["__cuit_dist_norm__", "nombre_distribuidor"], dropna=False)
          .size().reset_index(name="filas")
          .sort_values("filas", ascending=False)
          .head(15)
    ) if "nombre_distribuidor" in df.columns else (
        df.groupby("__cuit_dist_norm__").size().reset_index(name="filas")
        .sort_values("filas", ascending=False).head(15)
    )

    ejemplos = []
    for _, r in distrib_disponibles.iterrows():
        nombre = r.get("nombre_distribuidor", "(s/n)") if "nombre_distribuidor" in r.index else ""
        ejemplos.append(f"  - CUIT {r['__cuit_dist_norm__']}: {nombre} ({int(r['filas'])} filas)")
    diag["distribuidores_archivo"] = ejemplos

    raise ValueError(
        f"En el archivo CRM no hay datos del distribuidor con CUIT '{cuit_exp}' "
        f"({nombre_exp or 'sin nombre'}). El archivo contiene "
        f"{df['__cuit_dist_norm__'].nunique()} distribuidores distintos. "
        f"Los principales son:\n" + "\n".join(ejemplos[:10]) +
        "\n\nVerificá que el CUIT del expediente esté bien escrito y que el CRM "
        "incluya el período del distribuidor que estás auditando."
    )


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
    cuit_distribuidor: str = "",
    nombre_distribuidor: str = "",
) -> dict:
    """
    Cruza agroquímicos Syngenta (Paso 2) vs CRM.

    El archivo CRM de Syngenta contiene reportes de TODOS los distribuidores;
    se filtra al distribuidor del expediente por CUIT antes de cruzar.
    """
    # Cargar datos
    df_agro = pd.read_excel(path_agroquimicos_syngenta, dtype=str)

    # ── Lectura del CRM con FILTRO INLINE (streaming) ───────────────────────
    # El CRM puede tener 200k+ filas (todos los distribuidores). Leer todo
    # con pd.read_excel y filtrar después tumba el worker por memoria/tiempo.
    # Estrategia: openpyxl read_only + iter_rows, descartando inline las filas
    # que no son del distribuidor del expediente. Solo cargamos en memoria las
    # filas relevantes (~6k de 188k en el caso real).
    df_crm_stream, stream_diag = _leer_crm_filtrado_streaming(path_crm, cuit_distribuidor)

    # Si streaming corrió OK pero no encontró filas para este CUIT, levantar
    # error claro con la lista de distribuidores presentes (todo desde la
    # MISMA pasada de streaming, sin volver a leer el archivo).
    if df_crm_stream is not None and df_crm_stream.empty:
        ejemplos = stream_diag.get("distribuidores_archivo", [])[:10]
        lista = "\n".join(
            f"  - CUIT {d['cuit']}: {d['nombre'] or '(sin nombre)'} ({d['filas']:,} filas)"
            for d in ejemplos
        )
        raise ValueError(
            f"En el archivo CRM no hay datos del distribuidor con CUIT "
            f"'{cuit_distribuidor}' ({nombre_distribuidor or 'sin nombre'}). "
            f"El archivo tiene {len(stream_diag.get('distribuidores_archivo', []))} "
            f"distribuidores distintos en {stream_diag.get('filas_archivo_total', 0):,} "
            f"filas. Los principales son:\n" + lista +
            "\n\nVerificá que el CUIT del expediente esté bien escrito (editalo "
            "con el botón ✏️ del Dashboard) y que el CRM incluya el período del "
            "distribuidor que estás auditando."
        )

    if df_crm_stream is not None and not df_crm_stream.empty:
        # Streaming OK y encontró filas → seguir con el df filtrado.
        # Aplicamos detección de columnas con keywords sobre el df ya pequeño.
        from ..ai.smart_parser import detectar_por_keywords
        mapping = detectar_por_keywords(
            [str(c) for c in df_crm_stream.columns], CRM_SCHEMA, CRM_EXCLUSIONES,
        )
        rename_map = {orig: std for std, orig in mapping.items() if orig}
        df_crm = df_crm_stream.rename(columns=rename_map)
        crm_info = {
            "metodo": "streaming",
            "confianza": 1.0,
            "mapping": mapping,
            "columnas_archivo": [str(c) for c in df_crm_stream.columns],
            "columnas_faltantes": [c for c in CRM_SCHEMA if not mapping.get(c)],
            "columnas_no_mapeadas": [c for c in df_crm_stream.columns if c not in mapping.values()],
            "warnings": [],
        }
        filtro_diag = {
            "filas_archivo_total": stream_diag["filas_archivo_total"],
            "filas_distribuidor": stream_diag["filas_distribuidor"],
            "metodo_filtro": f"CUIT exacto streaming ({cuit_distribuidor})",
            "distribuidores_archivo": [],
        }
        print(f"[CRM] Streaming → {filtro_diag['filas_distribuidor']:,} de "
              f"{filtro_diag['filas_archivo_total']:,} filas (sin cargar el resto en memoria)")
    else:
        # Fallback: streaming no aplica (no es xlsx, header sin 'Cuenta: CUIT',
        # etc.) — caer al camino tradicional que carga todo y filtra después.
        # Este camino también es el que dispara el mensaje de error útil
        # listando los distribuidores presentes si el CUIT no matchea.
        motivo = (stream_diag or {}).get("motivo", "desconocido")
        print(f"[CRM] Streaming no aplicable ({motivo}) — fallback a lectura completa")
        df_crm_full, crm_info = leer_crm(path_crm)
        df_crm, filtro_diag = _filtrar_crm_por_distribuidor(
            df_crm_full, cuit_distribuidor, nombre_distribuidor,
        )
        print(f"[CRM] Filtro distribuidor: {filtro_diag['metodo_filtro']} → "
              f"{filtro_diag['filas_distribuidor']:,} de "
              f"{filtro_diag['filas_archivo_total']:,} filas")

    # Preparar DataFrame de gestión (solo Syngenta)
    df_gestion = _preparar_gestion(df_agro)
    df_crm = _preparar_crm(df_crm)

    # Cruce
    conciliacion = _cruzar_crm(df_gestion, df_crm)

    # Generar justificaciones con IA SOLO para las verdaderas DIFERENCIAS
    # (matchearon en ambos lados pero los montos no cuadran). Las SOLO_GESTION
    # y SOLO_CRM ya tienen una justificación template ("Venta sin reporte en
    # CRM" / "Reportado en CRM sin factura") — la IA no aporta nada ahí y son
    # la MAYORÍA de las filas (lo que disparaba los $13 de tokens).
    #
    # Además se ordenan por monto descendente y se capean a 200 — más que eso
    # no aporta valor y empieza a costar caro / tardar minutos. Las que sobran
    # quedan como pendientes para análisis manual.
    MAX_IA = 200
    diferencias_reales = [
        r for r in conciliacion
        if r.get("estado") == "DIFERENCIA"
        and abs(r.get("diferencia_monto") or 0) > 0.01
    ]
    diferencias_reales.sort(key=lambda r: abs(r.get("diferencia_monto") or 0), reverse=True)
    overflow = []
    if len(diferencias_reales) > MAX_IA:
        overflow = diferencias_reales[MAX_IA:]
        diferencias_reales = diferencias_reales[:MAX_IA]
        for r in overflow:
            r["justificacion"] = (
                f"Pendiente — más de {MAX_IA} diferencias para analizar con IA. "
                f"Revisar manualmente."
            )

    if diferencias_reales:
        try:
            justificaciones = generar_justificaciones(diferencias_reales)
        except Exception as e:
            print(f"[PASO 3] generar_justificaciones falló: {e}")
            justificaciones = []
        for r, j in zip(diferencias_reales, justificaciones):
            if j:
                r["justificacion"] = j

    print(f"[PASO 3] IA: {len(diferencias_reales)} diferencias procesadas"
          f"{' (+' + str(len(overflow)) + ' overflow)' if overflow else ''}, "
          f"SOLO_* con template (sin IA)")

    resumen = {
        "total_lineas": len(conciliacion),
        "sin_diferencia": sum(1 for r in conciliacion if r.get("estado") == "OK"),
        "con_diferencia": sum(1 for r in conciliacion if r.get("estado") == "DIFERENCIA"),
        "solo_gestion": sum(1 for r in conciliacion if r.get("estado") == "SOLO_GESTION"),
        "solo_crm": sum(1 for r in conciliacion if r.get("estado") == "SOLO_CRM"),
    }

    # Sumar el diagnóstico del filtro de distribuidor a los warnings del parser
    warnings_crm = list(crm_info.get("warnings", []))
    warnings_crm.insert(0,
        f"Filtro distribuidor: {filtro_diag['metodo_filtro']} — "
        f"{filtro_diag['filas_distribuidor']:,} de "
        f"{filtro_diag['filas_archivo_total']:,} filas del archivo CRM"
    )

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
            "warnings": warnings_crm,
        })

    return {
        "conciliacion": conciliacion,
        "resumen": resumen,
        "parser_diagnostico": parser_diagnostico,
        "filtro_distribuidor": filtro_diag,
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
    # cuit normalizado a dígitos puros para que matchee con el cuit del CRM
    df["cuit_cliente"] = _col_or_default("cuit_cliente", default="").astype(str).apply(_solo_digitos)
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
    cols = set(df.columns)

    def _serie(*names, default=""):
        for n in names:
            if n in cols:
                return df[n]
        return pd.Series([default] * len(df), index=df.index)

    df["fecha_crm"] = pd.to_datetime(_serie("fecha_crm", default=""), errors="coerce")
    # Normalizar el "Numero de factura" del CRM (formato "AXXX|FC|A000600020954")
    # al mismo formato que usa Paso 1 (PPPPP-NNNNNNNN), sino el cruce nunca matchea.
    df["numero_crm"] = _serie("numero_crm", default="").astype(str).apply(_numero_crm_a_estandar)
    df["cuit_cliente_crm"] = _serie("cuit_cliente_crm", default="").astype(str).apply(_solo_digitos)
    df["producto_crm"] = _serie("producto_crm", default="").astype(str).str.strip().str.upper()
    df["cantidad_crm"] = pd.to_numeric(_serie("cantidad_crm", default=0), errors="coerce").fillna(0)
    df["monto_crm"] = pd.to_numeric(_serie("monto_crm", default=0), errors="coerce").fillna(0)
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
