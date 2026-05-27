"""
Paso 1 — Cruce de Base de Datos
Compara bajada de gestión vs comprobantes emitidos (ARCA).
Salida: conciliación por comprobante con diferencias.
"""
import os
import re
from datetime import date
import pandas as pd
import numpy as np

from ..ai.smart_parser import parsear_excel
from ..core.config import settings

# Tipos de comprobante reconocidos
TIPOS_FC = {"FC", "FACTURA", "FAC", "F"}
TIPOS_NC = {"NC", "NOTA DE CREDITO", "NOTA DE CRÉDITO", "NCD", "N/C"}
TIPOS_ND = {"ND", "NOTA DE DEBITO", "NOTA DE DÉBITO", "NDD", "N/D"}


# Códigos numéricos AFIP/ARCA → tipo estándar
CODIGOS_ARCA = {
    # Notas de Crédito (todos los tipos)
    3: "NC", 8: "NC", 13: "NC", 53: "NC",
    203: "NC", 208: "NC", 213: "NC",
    # Notas de Débito
    2: "ND", 7: "ND", 12: "ND", 52: "ND",
    202: "ND", 207: "ND", 212: "ND",
    # Facturas (1, 6, 11, 51, 201, 206, 211 y resto)
    1: "FC", 6: "FC", 11: "FC", 51: "FC",
    201: "FC", 206: "FC", 211: "FC",
}


def normalizar_tipo_comprobante(tipo) -> str:
    if tipo is None or (isinstance(tipo, float) and pd.isna(tipo)):
        return "FC"
    # Primero intentar como código numérico AFIP/ARCA
    try:
        codigo = int(float(str(tipo).strip()))
        if codigo in CODIGOS_ARCA:
            return CODIGOS_ARCA[codigo]
    except (ValueError, TypeError):
        pass
    # Fallback: match por texto
    tipo_upper = str(tipo).upper().strip()
    if any(t in tipo_upper for t in TIPOS_NC):
        return "NC"
    if any(t in tipo_upper for t in TIPOS_ND):
        return "ND"
    return "FC"


def normalizar_numero_comprobante(valor_combinado=None, pv=None, num=None) -> str:
    """
    Normaliza al formato PPPPP-NNNNNNNN (5 dígitos PV, 8 dígitos número).
    Acepta:
      - pv y num por separado
      - string "0002-00001063"
      - string "200001063" (los últimos 8 dígitos son NUM, el resto PV)
      - string "1063"
    Esto unifica el formato entre Gestión y ARCA para que matcheen.
    """
    def _digits(s):
        return ''.join(c for c in str(s or '') if c.isdigit())

    if pv is not None or num is not None:
        pv_d = _digits(pv) or "0"
        num_d = _digits(num) or "0"
        return f"{pv_d.zfill(5)}-{num_d.zfill(8)}"

    s = str(valor_combinado or '').strip()
    if '-' in s:
        parts = s.split('-')
        if len(parts) == 2:
            pv_d = _digits(parts[0]) or "0"
            num_d = _digits(parts[1]) or "0"
            return f"{pv_d.zfill(5)}-{num_d.zfill(8)}"

    digits = _digits(s)
    if len(digits) > 8:
        num_d = digits[-8:]
        pv_d = digits[:-8]
        return f"{pv_d.zfill(5)}-{num_d.zfill(8)}"
    return f"00000-{digits.zfill(8)}"


def obtener_tipo_cambio_fecha(tc_map: dict, fecha: date, moneda: str) -> float:
    """Retorna el tipo de cambio para una fecha dada. Si no existe exacto, usa el más cercano anterior.
    Retorna 0 si no se puede determinar (importante: NUNCA retornar 1.0 para ARS porque infla los totales).
    """
    if str(moneda).upper() in ("USD", "U$S", "DOLAR", "DÓLAR", "DOL"):
        return 1.0

    if not tc_map:
        return 0  # Sin datos → no inventar

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

    # Usar primera disponible como fallback (la más antigua)
    if fechas_disponibles:
        return tc_map[fechas_disponibles[0]]

    return 0  # NUNCA 1.0 — eso inflaba los totales x10


TC_SCHEMA = {
    "fecha": ["fecha", "date", "dia", "día", "fec"],
    "cotizacion": ["cotizacion", "cotización", "cambio", "tc", "t/c", "dolar", "dólar",
                   "usd", "valor", "precio", "venta", "tipo de cambio"],
}

ARCA_SCHEMA = {
    "tipo_comprobante": ["tipo de comprobante", "tipo comprobante", "tipo"],
    "punto_venta": ["punto de venta", "pto. vta", "pto vta", "pto venta", "pv"],
    "numero_comprobante": [
        # Específicos de ARCA — van primero para ganar ante keywords genéricos
        "número desde", "numero desde", "nro desde",
        "desde",           # captura "NÃºmero Desde" con encoding roto (→ "namero desde")
        "nro comprobante", "nro. comprobante", "número comprobante",
        "comprobante", "factura", "número", "numero", "nro",
    ],
    "fecha": ["fecha de emisión", "fecha emisión", "fecha emision",
              "fecha comprobante", "fecha"],
    "moneda": ["moneda", "mon"],
    "tipo_cambio": ["tipo de cambio", "t/c", "tc", "cambio"],
    # Keywords ordenados de más a menos específico: primero buscar la columna
    # TOTAL del neto (suma de todos los tramos de IVA), no la columna parcial.
    # "neto gravado total" NO es substring de "imp. neto gravado" → no hay falso positivo.
    "monto_neto": [
        "neto gravado total", "imp. neto gravado total", "importe neto gravado total",
        "gravado total",
        "neto gravado", "imp. neto gravado", "importe neto gravado",
        "importe neto", "neto", "gravado", "base imponible",
    ],
    "monto_total": ["importe total", "imp. total", "imp total", "total"],
}

ARCA_EXCLUSIONES = {
    # No queremos que estos campos se confundan con datos del receptor
    "numero_comprobante": [
        "cuit", "receptor", "comprador", "doc receptor", "denominacion", "denominación",
        "tipo",   # evitar que "Tipo de Comprobante" se mapee como número
        "hasta",  # evitar "Número Hasta" — solo queremos "Número Desde"
    ],
    "tipo_comprobante": ["cuit", "receptor", "doc receptor", "doc. receptor"],
    "punto_venta": ["cuit", "receptor"],
    "fecha": ["vencimiento", "vto"],
}

# ── Schema Gestión ERP (altamente heterogéneo) ─────────────────────────────────
# Cubre sistemas: Tango/Restô, SAP B1, Dynamics, Bejerman, Evolution,
# Sap Hana, Oracle, Odoo, Flexxus y exportaciones ad-hoc de distribuidores.
GESTION_SCHEMA = {
    "fecha": [
        "fecha comprobante", "fecha de comprobante", "fecha emision", "fecha emisión",
        "fecha de emision", "fecha de emisión", "fecha factura", "fecha fc",
        "fecha doc", "fecha documento", "fecha operacion", "fecha operación",
        "fecha venta", "fecha movimiento", "fecha", "fec comp", "fec. comp",
        "fec comprobante", "fec. comprobante", "date", "fec", "fecha registro",
    ],
    "tipo_comprobante": [
        "tipo de comprobante", "tipo comprobante", "tipo documento", "tipo doc",
        "tipo de documento", "clase comprobante", "clase de comprobante",
        "tcomp", "t comp", "t. comp", "tipo", "clase", "cod tipo",
        "código tipo", "letra comprobante", "letra", "tipo fc",
        "tipo de factura", "descripcion tipo",
    ],
    "punto_venta": [
        "punto de venta", "pto. de venta", "pto de venta", "pto venta",
        "pto. venta", "pto vta", "pto. vta", "punto venta",
        "p.v.", "p. v.", "pv", "sucursal", "suc.", "suc",
        "local", "sede", "punto emision", "punto de emisión",
    ],
    "numero_comprobante": [
        "numero comprobante", "número comprobante", "nro. comprobante",
        "nro comprobante", "número de comprobante", "numero de comprobante",
        "nro factura", "numero factura", "número factura",
        "nro. factura", "número de factura", "numero de factura",
        "nro.", "nro", "numero", "número", "num", "num.",
        "comprobante nro", "comprobante número", "id comprobante",
        "doc nro", "nro doc", "numero doc", "número doc",
        "documento", "id doc", "numero de documento",
        "fc nro", "nro fc", "fact nro", "nro fact",
    ],
    "cliente": [
        "razon social", "razón social", "nombre cliente", "cliente",
        "denominacion cliente", "denominación cliente", "denominacion",
        "denominación", "nombre receptor", "receptor", "nombre",
        "empresa cliente", "rs cliente", "rs", "nombre rs",
        "nombre empresa", "empresa", "comprador", "nombre comprador",
    ],
    "cuit_cliente": [
        "cuit cliente", "cuit del cliente", "cuit receptor", "cuit comprador",
        "cuit", "cuil", "cuit/cuil", "nro cuit", "número cuit",
        "documento receptor", "doc. receptor", "nro doc receptor",
        "cuit_cliente", "id fiscal", "rut", "identificacion fiscal",
    ],
    "moneda": [
        "moneda", "divisa", "currency", "tipo moneda", "cod moneda",
        "código moneda", "mon", "moneda comprobante", "divisa comprobante",
    ],
    "tipo_cambio": [
        "tipo de cambio", "tipo cambio", "cotizacion", "cotización",
        "cotiz", "tc", "t/c", "cambio", "valor dolar", "dolar",
        "dólar", "tc comprobante", "tipo cambio comprobante",
        "cotizacion dolar", "cotización dólar",
    ],
    "monto_total": [
        "importe total", "total comprobante", "total con iva", "total c/iva",
        "total general", "total factura", "monto total", "valor total",
        "total bruto", "importe bruto", "imp. total", "imp total",
        "total c/ iva", "neto mas iva", "neto + iva",
        "monto", "importe", "total",
    ],
    "monto_neto": [
        "importe neto gravado", "neto gravado", "importe neto",
        "monto neto", "base imponible", "subtotal", "gravado",
        "neto sin iva", "importe sin iva", "sin iva",
        "neto", "imp neto", "base", "importe base",
        "neto+nograv", "neto + nograv", "neto+no grav",
    ],
    # Columna explícita en USD (algunos ERP exportan total ARS y total USD por separado)
    "monto_total_usd": [
        "total u$s", "total usd", "total dolares", "total dólares",
        "total en dolares", "total en dólares", "importe usd", "importe u$s",
        "monto usd", "monto dólares", "usd", "u$s", "dolares total",
        "dólares total", "total dol", "imp usd", "total $u",
    ],
}

GESTION_EXCLUSIONES = {
    # El número de comprobante NO debe confundirse con CUIT ni nombre de cliente
    "numero_comprobante": [
        "cuit", "cuil", "receptor", "comprador", "doc receptor",
        "denominacion", "denominación", "nombre", "cliente", "razon",
    ],
    # tipo_cambio NO debe confundirse con tipo de comprobante
    "tipo_cambio": [
        "tipo comprobante", "tipo doc", "tcomp", "tipo de comprobante",
        "clase", "letra",
    ],
    # punto_venta NO debe confundirse con cuit, moneda, etc.
    "punto_venta": ["cuit", "cuil", "tipo", "moneda", "divisa", "cliente"],
    # fecha del comprobante, no de vencimiento
    "fecha": ["vencimiento", "vto", "venc", "pago", "cobro"],
}


def leer_tipos_cambio(path: str) -> dict:
    """Lee archivo de tipos de cambio usando smart_parser. Retorna {fecha_str: cotizacion}"""
    resultado = parsear_excel(
        path=path,
        task_id="tipos_cambio",
        schema=TC_SCHEMA,
        columnas_criticas=["fecha", "cotizacion"],
    )
    df = resultado["df"]
    mapping = resultado["mapping"]
    col_fecha = mapping.get("fecha") or df.columns[0]
    col_tc = mapping.get("cotizacion") or (df.columns[1] if len(df.columns) > 1 else df.columns[0])

    print(f"[TC] método={resultado['metodo']} conf={resultado['confianza']:.2f} "
          f"fecha={col_fecha} tc={col_tc} warnings={resultado['warnings']}")

    tc_map = {}
    for _, row in df.iterrows():
        try:
            fecha = pd.to_datetime(row[col_fecha])
            tc = normalizar_monto(row[col_tc])
            if tc <= 0:
                continue
            tc_map[fecha.strftime("%Y-%m-%d")] = tc
        except (ValueError, TypeError):
            continue
    return tc_map


def leer_bajada_gestion(path: str):
    """
    Lee bajada de gestión (formato altamente variable — distintos ERP por DS).
    Usa smart_parser con IA + extended thinking para detectar columnas.
    Retorna (df_raw, mapping, info_parser).
    Las columnas críticas incluyen monto_total_usd como alternativa a monto_total.
    """
    resultado = parsear_excel(
        path=path,
        task_id="bajada_gestion",
        schema=GESTION_SCHEMA,
        excluir_si_contiene=GESTION_EXCLUSIONES,
        columnas_criticas=["fecha", "numero_comprobante"],  # monto_total es opcional si hay monto_total_usd
    )
    print(f"[GESTION] método={resultado['metodo']} conf={resultado['confianza']:.2f} "
          f"mapping={resultado['mapping']} warnings={resultado['warnings']}")
    return resultado["df"], resultado["mapping"], resultado


def leer_comprobantes_emitidos_arca(path: str):
    """
    Lee archivo de comprobantes emitidos de ARCA usando smart_parser.
    Retorna (df, mapping, info_parser).
    """
    resultado = parsear_excel(
        path=path,
        task_id="arca_emitidos",
        schema=ARCA_SCHEMA,
        excluir_si_contiene=ARCA_EXCLUSIONES,
        columnas_criticas=["tipo_comprobante", "numero_comprobante", "fecha", "monto_total"],
    )
    print(f"[ARCA] método={resultado['metodo']} conf={resultado['confianza']:.2f} "
          f"mapping={resultado['mapping']} warnings={resultado['warnings']}")
    return resultado["df"], resultado["mapping"], resultado


def normalizar_monto(valor) -> float:
    """
    Normalización inteligente de montos monetarios.

    Detecta automáticamente el formato:
    - Argentino  (punto=miles, coma=decimal): 1.234,56  → 1234.56
    - Internacional (coma=miles, punto=decimal): 1,234.56 → 1234.56
    - Sin separadores:  1234.56 o 1234,56  →  1234.56
    - Negativos: -1234.56 o (1234.56)  →  -1234.56
    - Símbolos de moneda eliminados: $, U$S, USD, ARS

    Para un solo punto con exactamente 3 dígitos tras él y ≤3 dígitos antes
    (ej: 1.234, 12.345) se trata como separador de miles (formato argentino).
    Cualquier otro único punto se trata como decimal (ej: 1234.56, 0.50).
    """
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        v = float(valor)
        return 0.0 if (v != v) else v   # nan check sin importar numpy

    s = str(valor).strip()

    # Eliminar símbolos de moneda y espacios
    for sym in ("U$S", "USD", "ARS", "$", "%"):
        s = s.replace(sym, "").strip()
    if not s:
        return 0.0

    # Detectar negativo: -1234 o (1234)
    negativo = False
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
        negativo = True
    if s.startswith("-"):
        s = s[1:].strip()
        negativo = True

    # Conservar solo dígitos, punto y coma
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not any(c.isdigit() for c in s):
        return 0.0

    n_dots   = s.count(".")
    n_commas = s.count(",")

    if n_dots >= 1 and n_commas >= 1:
        # Ambos presentes: el último es el separador decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # AR: 1.234,56 → 1234.56
        else:
            s = s.replace(",", "")                      # US: 1,234.56 → 1234.56
    elif n_dots > 1:
        # Múltiples puntos = separadores de miles: 1.234.567 → 1234567
        s = s.replace(".", "")
    elif n_commas > 1:
        # Múltiples comas = separadores de miles: 1,234,567 → 1234567
        s = s.replace(",", "")
    elif n_dots == 1:
        idx    = s.index(".")
        before = s[:idx]
        after  = s[idx + 1:]
        if len(after) == 3 and 1 <= len(before) <= 3:
            # Patrón X.YYY con pocos dígitos antes → miles AR: 1.234 → 1234
            s = s.replace(".", "")
        # else: decimal estándar: 1234.56 queda igual
    elif n_commas == 1:
        # Una sola coma → decimal argentino: 1234,56 → 1234.56
        s = s.replace(",", ".")

    try:
        result = float(s)
    except ValueError:
        return 0.0

    return -result if negativo else result


# ── Filtro universal de filas basura en bajadas de ERP ─────────────────────────

# Palabras que indican que una fila es un totalizador/resumen, no un comprobante real
_RESUMEN_KEYWORDS = frozenset([
    "total", "subtotal", "sub total", "gran total", "grand total",
    "suma", "total general", "total comprobante", "total periodo",
    "totales", "suma total", "resumen", "acumulado",
])

# Prefijos en el campo cliente que delatan filas de descripción de producto
_PRODUCTO_PREFIJOS = (
    "producto:", "artículo:", "articulo:", "item:", "descripcion:",
    "descripción:", "detalle:", "referencia:",
)

# Umbral de monto: ninguna factura de un DS debería superar USD 50 M
# (atrapa totales acumulados sin separadores como 1190034980620155)
_MONTO_USD_MAX = 50_000_000


def _es_fila_basura_gestion(
    numero_raw: str,
    numero_normalizado: str,
    cliente_raw: str,
    monto_usd: float,
) -> bool:
    """
    Detecta filas que NO son comprobantes reales en bajadas de ERP.
    Retorna True si la fila debe ser omitida.

    Causas universales de filas basura:
    1. Número normalizado todo ceros → fila sin comprobante identificable
    2. Texto de totalizador en número o cliente ("Total", "Gran Total", etc.)
    3. Filas de descripción de producto intercaladas por algunos ERP
    4. Monto absurdamente alto → total acumulado leído sin separadores de miles
    """
    numero_lower  = str(numero_raw or "").lower().strip()
    cliente_lower = str(cliente_raw or "").lower().strip()

    # 1. Número vacío o todo ceros
    if numero_normalizado in ("00000-00000000", ""):
        return True

    # 2. Palabra de resumen en número o en cliente
    for text in (numero_lower, cliente_lower):
        if any(k in text for k in _RESUMEN_KEYWORDS):
            return True

    # 3. Fila de descripción de producto (ERP que mezcla con comprobantes)
    if any(cliente_lower.startswith(p) for p in _PRODUCTO_PREFIJOS):
        return True

    # 4. Monto astronómico → captado por total acumulado / error de formato
    if abs(monto_usd) > _MONTO_USD_MAX:
        return True

    return False


def _deduplicar_gestion(registros: list) -> list:
    """
    Elimina duplicados inter-archivo cuando el mismo comprobante aparece en
    múltiples archivos ERP.

    Caso típico: el "Reporte Facturas" exporta FC + NC + ND todos juntos,
    y el usuario TAMBIÉN subió archivos separados de NC y ND.
    Resultado: cada NC aparece dos veces con keys distintas:
      - NC-00000-XXXXXXXX  (del archivo Facturas, sin columna PV)
      - NC-00001-XXXXXXXX  (del archivo NC, con PV real)

    Regla: solo se deduplica cuando coexisten PV=00000 Y PV real para el mismo
    (tipo, num_part). En ese caso el PV=00000 es el mismo comprobante visto desde
    un archivo sin columna PV → se descarta y se conserva el de PV real.

    Casos que NO se tocan:
    - PVs reales distintos (00001 y 00002, mismo número): comprobantes genuinamente
      diferentes → se mantienen ambos.
    - Todos PV=00000: pueden ser distintos PVs sin columna, o líneas de producto
      del mismo comprobante → se dejan pasar, _agregar_por_comprobante los une.
    """
    from collections import defaultdict

    # Agrupar por (tipo, num_part)
    por_tipo_num: dict = defaultdict(list)
    for r in registros:
        pv_part, num_part = r["numero"].split("-", 1)
        por_tipo_num[(r["tipo"], num_part)].append((pv_part, r))

    resultado = []
    eliminados = 0
    for (_tipo, _num), entries in por_tipo_num.items():
        if len(entries) == 1:
            resultado.append(entries[0][1])
            continue

        con_pv_real = [(pv, r) for pv, r in entries if pv != "00000"]
        sin_pv      = [(pv, r) for pv, r in entries if pv == "00000"]

        if con_pv_real and sin_pv:
            # Coexisten versiones con PV real y sin PV:
            # → las sin PV son el mismo comprobante visto desde un archivo sin columna PV
            # → conservar solo las de PV real
            resultado.extend(r for _, r in con_pv_real)
            eliminados += len(sin_pv)
        else:
            # Todos PV real (distintos PVs) → comprobantes genuinamente distintos → mantener todos
            # Todos PV=00000 → pueden ser PVs distintos sin columna, o líneas del mismo
            #   comprobante → NO deduplicar, _agregar_por_comprobante los maneja
            resultado.extend(r for _, r in entries)

    if eliminados:
        print(f"[GESTION] Deduplicación inter-archivo: {eliminados} duplicado(s) eliminado(s) "
              f"(mismo comprobante en múltiples archivos ERP)")
    return resultado


def _agregar_por_comprobante(registros: list) -> list:
    """
    Agrupa registros de Gestión por clave (tipo+numero) y suma los montos.

    Necesario cuando el ERP exporta una fila por línea de producto en lugar
    de una por comprobante (caso típico en Tango, SAP B1, Dynamics, etc.).

    Ejemplo:
      FC-00000-00002154  $500  (Roundup)    ┐
      FC-00000-00002154  $300  (Glifosato)  ├→  FC-00000-00002154  $1.200
      FC-00000-00002154  $400  (Herbicida)  ┘

    Para NC los montos son negativos — se suman igual (se preserva el signo).
    Metadatos (fecha, cliente, cuit) se toman del primer registro del grupo;
    si el primero tiene cliente vacío se busca el primer no vacío.
    """
    from collections import defaultdict as _dd2
    grupos: dict = _dd2(list)
    for r in registros:
        grupos[r["key"]].append(r)

    agregados = []
    for key, rows in grupos.items():
        if len(rows) == 1:
            agregados.append(rows[0])
            continue
        base = dict(rows[0])
        base["monto_usd"]      = round(sum(r["monto_usd"]      for r in rows), 2)
        base["monto_original"] = round(sum(r["monto_original"] for r in rows), 2)
        # Cliente: preferir el primero no vacío
        for r in rows:
            if r.get("cliente", "").strip():
                base["cliente"] = r["cliente"]
                break
        agregados.append(base)

    return agregados


def ejecutar_paso1(
    paths_bajada: list,   # lista de (path, nombre_original) tuples
    path_emitidos: str,
    path_tc: str,
    expediente_id: int,
) -> dict:
    """
    Ejecuta el cruce completo del Paso 1.
    paths_bajada puede contener múltiples archivos ERP — cada uno se parsea
    individualmente con su propio schema/tipo_inferido y los registros se consolidan.
    """
    # 1. Cargar tipos de cambio
    tc_map = leer_tipos_cambio(path_tc)

    # 2. Procesar TODOS los archivos de bajada de gestión
    all_registros_gestion = []
    all_dfs_gestion = []       # para exportar bajada normalizada
    all_mappings_gestion = []  # para exportar bajada normalizada
    parser_diagnostico = []

    for path_bajada, nombre_archivo in paths_bajada:
        df_gestion, gestion_mapping, gestion_info = leer_bajada_gestion(path_bajada)
        metadata = gestion_info.get("metadata_reporte", {})
        tipo_inferido = metadata.get("tipo_inferido")

        registros = _procesar_gestion(
            df_gestion, tc_map, mapping=gestion_mapping, tipo_inferido=tipo_inferido
        )
        all_registros_gestion.extend(registros)
        all_dfs_gestion.append(df_gestion)
        all_mappings_gestion.append(gestion_mapping)

        gestion_warnings = list(gestion_info.get("warnings", []))
        if tipo_inferido:
            gestion_warnings.insert(
                0, f"Tipo inferido del título del reporte: todos los registros son {tipo_inferido}"
            )

        parser_diagnostico.append({
            "archivo": nombre_archivo,
            "metodo": gestion_info["metodo"],
            "confianza": gestion_info["confianza"],
            "mapping": gestion_info["mapping"],
            "columnas_archivo": gestion_info.get("columnas_archivo", []),
            "columnas_faltantes": gestion_info.get("columnas_faltantes", []),
            "columnas_no_mapeadas": gestion_info.get("columnas_no_mapeadas", []),
            "warnings": gestion_warnings,
            "registros_procesados": len(registros),
            "filas_en_archivo": len(df_gestion),
        })

    # Deduplicar registros inter-archivo (mismo comprobante en Facturas + NC/ND separados)
    all_registros_gestion = _deduplicar_gestion(all_registros_gestion)

    # Agregar líneas de producto → un registro por comprobante
    filas_gestion_raw = len(all_registros_gestion)
    registros_gestion = _agregar_por_comprobante(all_registros_gestion)
    if filas_gestion_raw != len(registros_gestion):
        print(f"[GESTION] Agregación: {filas_gestion_raw} líneas → "
              f"{len(registros_gestion)} comprobantes únicos")

    # 3. Cargar comprobantes ARCA (smart_parser)
    df_arca_raw, arca_mapping, arca_info = leer_comprobantes_emitidos_arca(path_emitidos)
    registros_arca = _procesar_arca(df_arca_raw, tc_map, mapping=arca_mapping)

    if arca_info:
        parser_diagnostico.append({
            "archivo": "Comprobantes Emitidos (ARCA)",
            "metodo": arca_info["metodo"],
            "confianza": arca_info["confianza"],
            "mapping": arca_info["mapping"],
            "columnas_archivo": arca_info.get("columnas_archivo", []),
            "columnas_faltantes": arca_info.get("columnas_faltantes", []),
            "columnas_no_mapeadas": arca_info.get("columnas_no_mapeadas", []),
            "warnings": arca_info.get("warnings", []),
        })

    # 4. Cruce / Conciliación
    conciliacion = _cruzar_comprobantes(registros_gestion, registros_arca)

    # 5. Guardar bajada normalizada consolidada (para Paso 2)
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(expediente_id))
    os.makedirs(upload_dir, exist_ok=True)
    path_normalizada = os.path.join(upload_dir, "bajada_gestion_normalizada.xlsx")
    if all_dfs_gestion:
        # Exportar el primero (o concatenar si hay varios)
        if len(all_dfs_gestion) == 1:
            _exportar_bajada_normalizada(
                all_dfs_gestion[0], tc_map, path_normalizada, mapping=all_mappings_gestion[0]
            )
        else:
            # Para múltiples archivos: concatenar y exportar
            df_concat = pd.concat(all_dfs_gestion, ignore_index=True)
            df_concat.to_excel(path_normalizada, index=False)

    # 6. Calcular resumen
    solo_arca = [r for r in conciliacion if r["estado"] == "SOLO_ARCA"]
    solo_gestion = [r for r in conciliacion if r["estado"] == "SOLO_GESTION"]
    diferencia = [r for r in conciliacion if r["estado"] == "DIFERENCIA"]
    ok = [r for r in conciliacion if r["estado"] == "OK"]

    resumen = {
        "total_arca": len(registros_arca),
        "total_gestion": len(registros_gestion),       # comprobantes únicos
        "filas_gestion_raw": filas_gestion_raw,         # líneas antes de agregar
        "archivos_gestion": len(paths_bajada),
        "ok": len(ok),
        "solo_arca": len(solo_arca),
        "solo_gestion": len(solo_gestion),
        "con_diferencia": len(diferencia),
        "monto_total_arca_usd": sum(r["monto_usd_arca"] for r in registros_arca),
        "monto_total_gestion_usd": sum(r["monto_usd"] for r in registros_gestion),
    }

    # Validación con IA
    from ..ai.validator import validar_paso
    validacion = validar_paso(1, resumen, muestra=conciliacion[:5])

    return {
        "conciliacion": conciliacion,
        "resumen": resumen,
        "bajada_normalizada_path": path_normalizada,
        "parser_diagnostico": parser_diagnostico,
        "validacion": validacion,
    }


def _inferir_moneda_por_valor(montos: list) -> str:
    """
    Infiere si los montos están en ARS o USD basándose en los valores.
    Lógica de mercado agroquímico argentino 2024-2025:
    - Facturas en ARS: típicamente > 100.000 (con TC ~1000 ARS/USD)
    - Facturas en USD: típicamente entre 100 y 500.000
    - Si la mediana supera 100.000 → muy probablemente ARS
    - Si la mediana es < 50.000 → probablemente USD
    """
    montos_validos = [m for m in montos if m and m > 0]
    if not montos_validos:
        return "ARS"
    mediana = sorted(montos_validos)[len(montos_validos) // 2]
    # Umbral: si la mediana > 100.000 → ARS (ningún producto agroquímico vale 100k USD)
    return "ARS" if mediana > 100_000 else "USD"


def _procesar_gestion(df: pd.DataFrame, tc_map: dict, mapping: dict = None,
                      tipo_inferido: str = None) -> list:
    """
    Procesa la bajada de gestión usando el mapping detectado por smart_parser.
    El df tiene columnas con sus nombres ORIGINALES del ERP.
    El mapping indica qué columna original corresponde a cada campo estándar.

    tipo_inferido: "NC" | "ND" | None — tipo forzado si se detectó en el título del reporte.
    """
    mapping = mapping or {}

    col_tipo      = mapping.get("tipo_comprobante")
    col_pv        = mapping.get("punto_venta")
    col_num       = mapping.get("numero_comprobante")
    col_fecha     = mapping.get("fecha")
    col_cliente   = mapping.get("cliente")
    col_cuit      = mapping.get("cuit_cliente")
    col_moneda    = mapping.get("moneda")
    col_tc        = mapping.get("tipo_cambio")
    col_neto      = mapping.get("monto_neto")
    col_total     = mapping.get("monto_total")
    col_total_usd = mapping.get("monto_total_usd")  # columna explícita en USD

    # Columna de monto a usar: neto > total > total_usd
    # Neto es la base de comparación correcta para auditoría (excluye IVA)
    col_monto_base = col_neto or col_total
    if col_neto:
        print(f"[GESTION] Usando monto NETO: '{col_neto}'")
    elif col_total:
        print(f"[GESTION] Monto neto no encontrado — usando TOTAL: '{col_total}' (puede incluir IVA)")

    # Pre-calcular moneda inferida si no hay columna de moneda ni de total USD
    moneda_global = None
    if not col_moneda and not col_total_usd and col_monto_base:
        # Leer muestra de montos para inferir moneda por valor
        muestra_montos = []
        for _, row in df.head(50).iterrows():
            m = normalizar_monto(row.get(col_monto_base))
            if m > 0:
                muestra_montos.append(m)
        moneda_global = _inferir_moneda_por_valor(muestra_montos)
        print(f"[GESTION] Moneda inferida por valor (mediana de muestra): {moneda_global}")

    registros = []
    for _, row in df.iterrows():
        try:
            # Fecha — columna crítica
            fecha_raw = row.get(col_fecha) if col_fecha else None
            fecha = pd.to_datetime(fecha_raw, errors="coerce")
            if pd.isna(fecha):
                continue

            # Tipo de comprobante: prioridad → columna > título del reporte > FC por defecto
            if col_tipo:
                tipo = normalizar_tipo_comprobante(row.get(col_tipo))
            elif tipo_inferido:
                tipo = tipo_inferido
            else:
                tipo = "FC"

            numero_raw = row.get(col_num) if col_num else ""
            pv_raw = row.get(col_pv) if col_pv else None

            if pv_raw is not None and not pd.isna(pv_raw) and str(pv_raw).strip():
                numero = normalizar_numero_comprobante(pv=pv_raw, num=numero_raw)
            else:
                numero = normalizar_numero_comprobante(valor_combinado=numero_raw)

            # Monto: prioridad neto > total > columna USD explícita
            if col_total_usd and not col_monto_base:
                # Columna explícita en USD y sin neto/total → usar directamente
                monto_usd = normalizar_monto(row.get(col_total_usd))
                monto_original = monto_usd
                moneda = "USD"
            elif col_monto_base:
                monto_original = normalizar_monto(row.get(col_monto_base))
                if col_moneda:
                    moneda = str(row.get(col_moneda, "ARS")).upper().strip() or "ARS"
                else:
                    moneda = moneda_global or "ARS"
                tc = normalizar_monto(row.get(col_tc)) if col_tc else 0
                monto_usd = _convertir_a_usd(monto_original, moneda, tc, fecha, tc_map)
            else:
                monto_original = 0.0
                monto_usd = 0.0
                moneda = "ARS"

            # Signo por tipo de comprobante
            if tipo == "NC":
                monto_usd = -abs(monto_usd)
            else:
                monto_usd = abs(monto_usd)

            cliente_raw = str(row.get(col_cliente, "") if col_cliente else "")

            # ── Filtro universal de filas basura ────────────────────────────
            # Elimina: totalizadores, filas de producto, montos astronómicos
            if _es_fila_basura_gestion(
                numero_raw=str(numero_raw or ""),
                numero_normalizado=numero,
                cliente_raw=cliente_raw,
                monto_usd=monto_usd,
            ):
                continue

            registros.append({
                "tipo": tipo,
                "numero": numero,
                "fecha": fecha.strftime("%Y-%m-%d"),
                "cliente": cliente_raw,
                "cuit_cliente": str(row.get(col_cuit, "") if col_cuit else ""),
                "moneda": moneda,
                "monto_original": monto_original,
                "monto_usd": round(monto_usd, 2),
                "key": f"{tipo}-{numero}",
            })
        except Exception:
            continue
    return registros


def _procesar_arca(df: pd.DataFrame, tc_map: dict, mapping: dict = None) -> list:
    """Procesa comprobantes emitidos de ARCA usando el mapping del smart_parser."""
    registros = []
    mapping = mapping or {}

    col_tipo  = mapping.get("tipo_comprobante")
    col_pv    = mapping.get("punto_venta")
    col_num   = mapping.get("numero_comprobante")
    col_fecha = mapping.get("fecha")
    col_moneda = mapping.get("moneda")
    col_tc    = mapping.get("tipo_cambio")
    col_neto  = mapping.get("monto_neto")
    col_total = mapping.get("monto_total")

    # Neto > total — misma lógica que gestión para comparación consistente
    col_monto_base = col_neto or col_total
    if col_neto:
        print(f"[ARCA] Usando monto NETO: '{col_neto}'")
    elif col_total:
        print(f"[ARCA] Monto neto no encontrado — usando TOTAL: '{col_total}'")

    for _, row in df.iterrows():
        try:
            tipo = normalizar_tipo_comprobante(row.get(col_tipo, "FC"))
            fecha_raw = row.get(col_fecha)
            fecha = pd.to_datetime(fecha_raw, errors="coerce")
            if pd.isna(fecha):
                continue

            pv_raw = row.get(col_pv) if col_pv else None
            num_raw = row.get(col_num) if col_num else None
            numero = normalizar_numero_comprobante(pv=pv_raw, num=num_raw)

            moneda = str(row.get(col_moneda, "ARS")).upper().strip() if col_moneda else "ARS"
            tc = normalizar_monto(row.get(col_tc)) if col_tc else 0
            monto_base = normalizar_monto(row.get(col_monto_base, 0) if col_monto_base else 0)
            # NC/ND en ARCA pueden tener neto=0 en la columna gravado — fallback a total
            if monto_base == 0 and col_total and col_neto:
                monto_base = normalizar_monto(row.get(col_total, 0))

            monto_usd = _convertir_a_usd(monto_base, moneda, tc, fecha, tc_map)

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
        except Exception as e:
            continue

    return registros


def _convertir_a_usd(monto_ars: float, moneda: str, tc_row: float, fecha, tc_map: dict) -> float:
    """Convierte un monto a USD usando la moneda, el TC del row (si existe) y el mapa de TCs."""
    if not monto_ars:
        return 0.0
    moneda_norm = (moneda or "").upper().strip()
    if moneda_norm in ("USD", "U$S", "DOLAR", "DÓLAR", "DOL", "$U", "USD$"):
        return monto_ars
    # Preferir TC del comprobante si es válido (>1 para evitar 0 o 1.0 falso)
    if tc_row and tc_row > 1:
        return monto_ars / tc_row
    # Sino buscar en el mapa de tipos de cambio
    tc_fecha = obtener_tipo_cambio_fecha(tc_map, fecha.date() if hasattr(fecha, 'date') else fecha, moneda_norm)
    if tc_fecha and tc_fecha > 1:
        return monto_ars / tc_fecha
    # Si no hay TC válido, dejarlo en ARS (no inventar) — devolvemos 0 para no inflar totales
    print(f"[WARN] Sin TC para {fecha} moneda={moneda} → monto={monto_ars} se ignora en total USD")
    return 0.0



def _cruzar_comprobantes(gestion: list, arca: list) -> list:
    """
    Cruza registros Gestión vs ARCA en tres pasos:

    Paso 1 — Match exacto por key "{tipo}-{PV}-{NUM}".
              Si una key aparece N veces en cada lado se generan N pares.

    Paso 2 — Fuzzy PV matching para registros de Gestión con PV=00000.
              Ocurre cuando el ERP no exporta la columna de Punto de Venta:
              Gestión genera key "FC-00000-00002154" y ARCA tiene "FC-00001-00002154".
              Se intenta emparejar por (tipo, NUM) ignorando el PV faltante.

    Paso 3 — Sobrantes sin match → SOLO_ARCA / SOLO_GESTION.
    """
    from collections import defaultdict

    # ── Índices principales ──────────────────────────────────────────────────
    arca_groups    = defaultdict(list)
    gestion_groups = defaultdict(list)
    for r in arca:
        arca_groups[r["key"]].append(r)
    for r in gestion:
        gestion_groups[r["key"]].append(r)

    # Índice secundario ARCA: (tipo, num_only) → lista de registros
    # num_only = la parte numérica tras el guion (los 8 dígitos del número)
    arca_por_tipo_num = defaultdict(list)
    for r in arca:
        _, num_part = r["numero"].split("-", 1)
        arca_por_tipo_num[(r["tipo"], num_part)].append(r)

    conciliacion  = []
    arca_usados   = set()   # id(r_arca) ya emparejados
    gestion_usados = set()  # id(r_gest) ya emparejados

    # ── Paso 1: Match exacto ─────────────────────────────────────────────────
    all_keys = set(arca_groups.keys()) | set(gestion_groups.keys())
    for key in all_keys:
        a_list = arca_groups.get(key, [])
        g_list = gestion_groups.get(key, [])
        n = min(len(a_list), len(g_list))
        for i in range(n):
            r_arca = a_list[i]
            r_gest = g_list[i]
            diff = round(r_gest["monto_usd"] - r_arca["monto_usd_arca"], 2)
            estado = "OK" if abs(diff) <= 1.0 else "DIFERENCIA"
            arca_usados.add(id(r_arca))
            gestion_usados.add(id(r_gest))
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

    # ── Paso 2: Fuzzy PV — Gestión sin PV válido o con PV ajeno a ARCA ─────
    #
    # Dos causas frecuentes de PV incorrecto en Gestión:
    #   a) ERP no exporta PV → normalizar_numero_comprobante() pone "00000"
    #   b) ERP usa el código de tipo AFIP como prefijo del número
    #      (ej: "0003-00000204" donde 0003 = NC-A, no el PV real)
    #      → Gestión queda con PV=00003 pero ARCA tiene PV=00001
    #
    # Estrategia: si el PV del Gestión NO aparece entre los PVs reales de ARCA,
    # intentar match por (tipo, NUM) ignorando el PV.
    # Si el PV SÍ existe en ARCA pero no hubo match exacto → SOLO_GESTION genuino.

    # PVs reales de ARCA separados por tipo (FC, NC, ND)
    # Así un PV=3 de FC no bloquea el fuzzy de NC donde "0003" es código AFIP
    from collections import defaultdict as _dd
    arca_pvs_por_tipo: dict = _dd(set)
    for r in arca:
        pv, _ = r["numero"].split("-", 1)
        arca_pvs_por_tipo[r["tipo"]].add(pv)

    def _aplicar_fuzzy(r_gest: dict) -> bool:
        """Intenta match fuzzy para r_gest. Retorna True si matcheó."""
        pv_part, num_part = r_gest["numero"].split("-", 1)
        # Solo aplicar si el PV es desconocido (00000) o no existe en ARCA para ese tipo
        if pv_part != "00000" and pv_part in arca_pvs_por_tipo[r_gest["tipo"]]:
            return False
        candidatos = arca_por_tipo_num.get((r_gest["tipo"], num_part), [])
        for r_arca in candidatos:
            if id(r_arca) in arca_usados:
                continue
            diff = round(r_gest["monto_usd"] - r_arca["monto_usd_arca"], 2)
            estado = "OK" if abs(diff) <= 1.0 else "DIFERENCIA"
            arca_usados.add(id(r_arca))
            gestion_usados.add(id(r_gest))
            conciliacion.append({
                "key": r_arca["key"],
                "tipo": r_arca["tipo"],
                "numero": r_arca["numero"],
                "fecha": r_arca["fecha"],
                "cliente": r_gest.get("cliente", ""),
                "monto_usd_arca": r_arca["monto_usd_arca"],
                "monto_usd_gestion": r_gest["monto_usd"],
                "diferencia_usd": diff,
                "estado": estado,
            })
            return True
        return False

    for r_gest in gestion:
        if id(r_gest) in gestion_usados:
            continue
        _aplicar_fuzzy(r_gest)

    # ── Paso 3: Sobrantes ────────────────────────────────────────────────────
    for r_arca in arca:
        if id(r_arca) not in arca_usados:
            conciliacion.append({
                "key": r_arca["key"],
                "tipo": r_arca["tipo"],
                "numero": r_arca["numero"],
                "fecha": r_arca["fecha"],
                "cliente": "",
                "monto_usd_arca": r_arca["monto_usd_arca"],
                "monto_usd_gestion": None,
                "diferencia_usd": None,
                "estado": "SOLO_ARCA",
            })

    for r_gest in gestion:
        if id(r_gest) not in gestion_usados:
            conciliacion.append({
                "key": r_gest["key"],
                "tipo": r_gest["tipo"],
                "numero": r_gest["numero"],
                "fecha": r_gest["fecha"],
                "cliente": r_gest.get("cliente", ""),
                "monto_usd_arca": None,
                "monto_usd_gestion": r_gest["monto_usd"],
                "diferencia_usd": None,
                "estado": "SOLO_GESTION",
            })

    conciliacion.sort(key=lambda x: x["fecha"])
    return conciliacion


def _exportar_bajada_normalizada(df_norm: pd.DataFrame, tc_map: dict, path: str, mapping: dict = None):
    """Exporta la bajada de gestión normalizada con montos en USD calculados."""
    mapping = mapping or {}
    col_moneda = mapping.get("moneda")
    col_fecha  = mapping.get("fecha")
    col_tc     = mapping.get("tipo_cambio")
    col_total  = mapping.get("monto_total")
    col_tipo   = mapping.get("tipo_comprobante")

    df_export = df_norm.copy()

    # Calcular montos USD usando las columnas originales del ERP
    def calc_usd(row):
        moneda = str(row.get(col_moneda, "ARS") if col_moneda else "ARS").upper()
        if moneda in ("USD", "U$S", "DOLAR", "DÓLAR"):
            return normalizar_monto(row.get(col_total) if col_total else 0)
        fecha = pd.to_datetime(row.get(col_fecha) if col_fecha else None, errors="coerce")
        monto = normalizar_monto(row.get(col_total) if col_total else 0)
        if pd.isna(fecha):
            return monto
        tc = normalizar_monto(row.get(col_tc) if col_tc else 0) or obtener_tipo_cambio_fecha(
            tc_map, fecha.date(), moneda
        )
        return round(monto / tc, 2) if tc else 0

    df_export["monto_usd"] = df_export.apply(calc_usd, axis=1)

    # Aplicar signo NC
    def aplicar_signo(row):
        tipo = normalizar_tipo_comprobante(row.get(col_tipo) if col_tipo else None)
        val = row["monto_usd"]
        if tipo == "NC":
            return -abs(val)
        return abs(val)

    df_export["monto_usd"] = df_export.apply(aplicar_signo, axis=1)

    df_export.to_excel(path, index=False)
