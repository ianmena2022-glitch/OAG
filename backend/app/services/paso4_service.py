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
    # Columnas para calcular monto NETO (sin IVA) — el auditor humano usa neto,
    # no total. Si están presentes, se prefieren sobre monto_total.
    # ARCA típicamente trae: "Imp. Neto Gravado Total" (suma de todos los
    # netos por tasa de IVA) + columnas adicionales por cada tasa
    # ("Imp. Neto Gravado IVA 21%", "Imp. Neto Gravado IVA 10,5%", etc.) —
    # SIEMPRE preferimos el "Total" porque la per-tasa no abarca todos los
    # comprobantes del proveedor.
    "monto_neto_gravado": ["imp. neto gravado total", "neto gravado total",
                            "importe neto gravado total",
                            "imp. neto gravado", "neto gravado",
                            "importe neto gravado", "imp. neto"],
    "monto_neto_no_gravado": ["imp. neto no gravado", "imp neto no gravado",
                               "neto no gravado", "importe neto no gravado"],
    "monto_op_exentas": ["imp. op. exentas", "imp op exentas", "op. exentas",
                          "operaciones exentas", "imp. exentas", "exentas"],
    "monto_iva": ["total iva", "iva total", "imp. total iva", "importe total iva",
                   "imp. iva", "importe iva", "iva"],
}

RECIBIDOS_EXCLUSIONES = {
    # En comprobantes RECIBIDOS, el "receptor" es el propio distribuidor → lo excluimos del CUIT del emisor
    "numero_comprobante": ["cuit", "cuil", "receptor", "doc receptor", "denominacion"],
    "cuit_proveedor": ["receptor"],
    "nombre_proveedor": ["receptor"],
    "fecha": ["vencimiento", "vto"],
    # Para los netos: excluir las columnas per-tasa (IVA 0%, 2.5%, 5%, 10.5%,
    # 21%, 27%) que ARCA pone al lado del Total. Solo queremos el Total.
    "monto_neto_gravado": ["no gravado", "exenta", "iva 0%", "iva 2,5%", "iva 2.5%",
                            "iva 5%", "iva 10,5%", "iva 10.5%", "iva 21%", "iva 27%",
                            "percep", "retenc"],
    "monto_iva": ["neto", "percep", "retenc",
                   "iva 0%", "iva 2,5%", "iva 2.5%", "iva 5%",
                   "iva 10,5%", "iva 10.5%", "iva 21%", "iva 27%"],
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
        "lista":       [{"cuit": cuit_n, "nombre": nombre_u, "accion": ...}, ...]
      }
    El caller intenta match por CUIT primero (más robusto), después por nombre.
    'lista' preserva la asociación cuit↔nombre↔accion para los proveedores
    que no aparecen en los recibidos (hay que mostrarlos con $0 en el resumen).
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
    lista = []

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

        cuit_n = _digits(row.get(col_cuit)) if col_cuit else ""

        nombre = ""
        if col_nombre:
            nombre_raw = row.get(col_nombre)
            if nombre_raw is not None and not (isinstance(nombre_raw, float) and pd.isna(nombre_raw)):
                nombre_s = str(nombre_raw).strip().upper()
                if nombre_s and nombre_s != "NAN":
                    nombre = nombre_s

        if not cuit_n and not nombre:
            continue   # fila vacía

        if cuit_n:
            por_cuit[cuit_n] = accion
        if nombre:
            por_nombre[nombre] = accion
        lista.append({"cuit": cuit_n, "nombre": nombre, "accion": accion})

    print(f"[PROVEEDORES] Cargados {len(lista)} proveedores: "
          f"{sum(1 for x in lista if x['accion']=='ABRIR')} ABRIR + "
          f"{sum(1 for x in lista if x['accion']=='INCLUIR')} INCLUIR. "
          f"Accion={'columna detectada' if col_accion else 'sin columna (default ABRIR)'}")
    return {"por_cuit": por_cuit, "por_nombre": por_nombre, "lista": lista}


def ejecutar_paso4(
    path_recibidos: str,
    proveedores_config: dict,
    anio_analisis: int,
    db=None,
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

    Los tipos de cambio se leen del maestro global (Administración → Tipos de Cambio).
    """
    tc_map = leer_tipos_cambio(db=db)
    df, recibidos_info = _leer_comprobantes_recibidos(path_recibidos)
    df = _procesar_recibidos(df, tc_map, anio_analisis, recibidos_info["mapping"])

    resumen = _generar_resumen_compras(df, proveedores_config or {})
    # total_proveedores cuenta nombres únicos en el resumen final (incluye los
    # de "PROVEEDORES COMPETENCIA" con $0). El conteo SIN $0 va aparte para
    # el reporte.
    nombres_unicos = {r.get("nombre_proveedor","") for r in resumen if r.get("nombre_proveedor")}
    con_compras = {r.get("nombre_proveedor","") for r in resumen
                   if r.get("nombre_proveedor") and abs(r.get("Total",0)) > 0}
    # Usar .get() implícito vía .sum() con fallback por si df está vacío
    total_compras_usd = round(float(df["monto_usd"].sum()), 2) if "monto_usd" in df.columns else 0.0
    totales = {
        "total_compras_usd": total_compras_usd,
        "total_proveedores": len(nombres_unicos),
        "proveedores_con_compras": len(con_compras),
        "proveedores_sin_compras": len(nombres_unicos) - len(con_compras),
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
    """
    Normaliza y convierte a USD los comprobantes recibidos.

    El monto que se usa para Anexo I es el NETO (sin IVA), no el total — el
    auditor humano reporta los netos. Se calcula con esta cascada:
      1) Si hay netos en ARCA: neto_gravado + neto_no_gravado + op_exentas
      2) Si hay IVA pero no netos: total - iva
      3) Fallback: total (mismo comportamiento legacy — útil si el archivo no
         trae netos discriminados, ej. fuentes no-ARCA).
    """
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
    col_neto_g = mapping.get("monto_neto_gravado")
    col_neto_ng = mapping.get("monto_neto_no_gravado")
    col_exentas = mapping.get("monto_op_exentas")
    col_iva = mapping.get("monto_iva")

    # Diagnóstico: una sola vez por archivo, decir qué estrategia se va a usar
    if col_neto_g or col_neto_ng:
        print(f"[Recibidos] Usando NETO de columnas: gravado={col_neto_g} "
              f"no_gravado={col_neto_ng} exentas={col_exentas}")
    elif col_iva and col_total:
        print(f"[Recibidos] Usando NETO = total - iva (iva={col_iva}, total={col_total})")
    else:
        print(f"[Recibidos] ATENCION: no se detectaron columnas de neto ni IVA → "
              f"usando TOTAL como monto. Esto sobreestima compras en ~21% si "
              f"los comprobantes son IVA gravado. Verifica el archivo (col total={col_total}).")

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

            # ── Cascada para calcular el NETO (sin IVA) ──────────────────
            monto = 0.0
            if col_neto_g or col_neto_ng:
                neto_g  = normalizar_monto(row.get(col_neto_g, 0))  if col_neto_g  else 0
                neto_ng = normalizar_monto(row.get(col_neto_ng, 0)) if col_neto_ng else 0
                exentas = normalizar_monto(row.get(col_exentas, 0)) if col_exentas else 0
                monto = neto_g + neto_ng + exentas
                # Si todo dio 0 (NC sin neto discriminado), usar total como fallback
                if monto == 0 and monto_total != 0:
                    monto = monto_total
            elif col_iva and col_total:
                iva = normalizar_monto(row.get(col_iva, 0))
                monto = monto_total - iva
            else:
                monto = monto_total

            monto_usd = _convertir_a_usd(monto, moneda, tc_val, fecha, tc_map)

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

    Los proveedores en el archivo de proveedores que NO tienen compras
    igual aparecen en el resumen con $0 en todos los meses — el archivo
    "PROVEEDORES COMPETENCIA" lista competidores y plataformas que el
    auditor quiere ver en el informe aunque el distribuidor no les haya
    comprado nada (análisis comparativo).
    """
    por_cuit = (proveedores_config or {}).get("por_cuit", {})
    por_nombre = (proveedores_config or {}).get("por_nombre", {})

    def _digits(s):
        return "".join(c for c in str(s or "") if c.isdigit())

    def _categoria(cuit_raw, nombre):
        cuit_n = _digits(cuit_raw)
        if cuit_n and cuit_n in por_cuit:
            return por_cuit[cuit_n]
        nombre_u = str(nombre or "").strip().upper()
        if nombre_u and nombre_u in por_nombre:
            return por_nombre[nombre_u]
        return ""

    result = []
    cuits_procesados = set()        # cuits que ya generaron filas (con compras)
    nombres_procesados = set()      # idem por nombre (cuando no hay cuit en data)

    # ── 1. Procesar proveedores que SÍ tienen compras en los recibidos ─────
    if not df.empty:
        proveedores = df["nombre_proveedor"].unique()
        for prov in proveedores:
            df_prov = df[df["nombre_proveedor"] == prov]
            cuit = df_prov["cuit_proveedor"].iloc[0] if not df_prov.empty else ""
            cuit_n = _digits(cuit)
            if cuit_n:
                cuits_procesados.add(cuit_n)
            nombres_procesados.add(str(prov or "").strip().upper())
            categoria = _categoria(cuit, prov)

            if categoria == "ABRIR":
                # Una fila por FC/ND/NC SIEMPRE — incluso si un tipo no tiene
                # movimientos (queda en $0). El auditor pidió ver las tres
                # categorías para todos los proveedores ABRIR.
                for tipo in ["FC", "ND", "NC"]:
                    df_tipo = df_prov[df_prov["tipo_comprobante"] == tipo]
                    if df_tipo.empty:
                        row = _fila_vacia(f"{prov} — {tipo}", cuit, "ABRIR")
                    else:
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

    # ── 2. Agregar proveedores del archivo que NO tuvieron compras ─────────
    # Aparecen con $0 en todos los meses. Esencial para "PROVEEDORES
    # COMPETENCIA": el auditor quiere ver listados a todos los competidores
    # y plataformas marcados, aunque el distribuidor no les haya comprado.
    lista = (proveedores_config or {}).get("lista", [])
    sin_compras_count = 0
    for entry in lista:
        cuit_n = entry.get("cuit", "")
        nombre = entry.get("nombre", "")
        accion = entry.get("accion", "ABRIR")
        # Saltear si ya quedó cubierto por una fila con compras
        if cuit_n and cuit_n in cuits_procesados:
            continue
        if not cuit_n and nombre and nombre in nombres_procesados:
            continue
        nombre_show = nombre or f"(CUIT {cuit_n})"
        if accion == "ABRIR":
            # Tres filas FC/ND/NC en $0
            for tipo in ["FC", "ND", "NC"]:
                result.append(_fila_vacia(f"{nombre_show} — {tipo}", cuit_n, "ABRIR"))
        else:
            result.append(_fila_vacia(nombre_show, cuit_n, accion))
        if cuit_n:
            cuits_procesados.add(cuit_n)
        if nombre:
            nombres_procesados.add(nombre)
        sin_compras_count += 1

    if sin_compras_count:
        print(f"[Paso 4] {sin_compras_count} proveedor(es) del archivo sin "
              f"compras en los recibidos → aparecen con $0 en el resumen")

    # Ordenar por total descendente, MANTENIENDO juntas las filas FC/ND/NC
    # de un mismo proveedor ABRIR. La clave de grupo es el CUIT (si existe) o
    # el nombre base (sin "— FC/ND/NC"). El total del grupo es la suma de los
    # totales absolutos de sus filas. Dentro del grupo se mantiene FC → ND → NC.
    def _base_nombre(n: str) -> str:
        s = str(n or "")
        for suf in (" — FC", " — ND", " — NC"):
            if s.endswith(suf):
                return s[: -len(suf)]
        return s

    def _grupo_key(r: dict) -> str:
        c = str(r.get("cuit_proveedor") or "").strip()
        return c if c else _base_nombre(r.get("nombre_proveedor", ""))

    def _orden_tipo(r: dict) -> int:
        n = str(r.get("nombre_proveedor") or "")
        if n.endswith(" — FC"): return 0
        if n.endswith(" — ND"): return 1
        if n.endswith(" — NC"): return 2
        return 0

    grupos: Dict[str, List[Dict]] = {}
    for r in result:
        grupos.setdefault(_grupo_key(r), []).append(r)

    grupos_ordenados = sorted(
        grupos.items(),
        key=lambda kv: sum(abs(r.get("Total", 0)) for r in kv[1]),
        reverse=True,
    )
    result_ordenado: List[Dict] = []
    for _, filas in grupos_ordenados:
        filas.sort(key=_orden_tipo)
        result_ordenado.extend(filas)
    return result_ordenado


def _fila_vacia(nombre: str, cuit: str, categoria: str) -> Dict:
    """Fila de resumen para un proveedor sin compras (todos los meses en 0)."""
    fila = {
        "nombre_proveedor": nombre,
        "cuit_proveedor": cuit,
    }
    for m in MESES:
        fila[m] = 0.0
    fila["Total"] = 0.0
    fila["categoria"] = categoria
    return fila


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
