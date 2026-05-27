"""
Paso 1 — Cruce de Base de Datos
Compara bajada de gestión vs comprobantes emitidos (ARCA).
Salida: conciliación por comprobante con diferencias.
"""
import os
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
    "numero_comprobante": ["número desde", "numero desde", "nro desde",
                            "nro comprobante", "nro. comprobante", "número comprobante",
                            "comprobante", "factura", "número", "numero", "nro"],
    "fecha": ["fecha de emisión", "fecha emisión", "fecha emision",
              "fecha comprobante", "fecha"],
    "moneda": ["moneda", "mon"],
    "tipo_cambio": ["tipo de cambio", "t/c", "tc", "cambio"],
    "monto_total": ["importe total", "imp. total", "imp total", "total"],
}

ARCA_EXCLUSIONES = {
    # No queremos que estos campos se confundan con datos del receptor
    "numero_comprobante": ["cuit", "receptor", "comprador", "doc receptor", "denominacion", "denominación"],
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
    """
    resultado = parsear_excel(
        path=path,
        task_id="bajada_gestion",
        schema=GESTION_SCHEMA,
        excluir_si_contiene=GESTION_EXCLUSIONES,
        columnas_criticas=["fecha", "numero_comprobante", "monto_total"],
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

    # 2. Cargar bajada de gestión con smart_parser (IA + thinking)
    df_gestion, gestion_mapping, gestion_info = leer_bajada_gestion(path_bajada)

    # 3. Cargar comprobantes ARCA (smart_parser)
    df_arca_raw, arca_mapping, arca_info = leer_comprobantes_emitidos_arca(path_emitidos)

    # 4. Procesar bajada de gestión usando el mapping detectado
    registros_gestion = _procesar_gestion(df_gestion, tc_map, mapping=gestion_mapping)

    # 5. Procesar comprobantes ARCA
    registros_arca = _procesar_arca(df_arca_raw, tc_map, mapping=arca_mapping)

    # 6. Cruce / Conciliación
    conciliacion = _cruzar_comprobantes(registros_gestion, registros_arca)

    # 7. Guardar bajada normalizada (para Paso 2)
    upload_dir = os.path.join(settings.UPLOAD_DIR, str(expediente_id))
    os.makedirs(upload_dir, exist_ok=True)
    path_normalizada = os.path.join(upload_dir, "bajada_gestion_normalizada.xlsx")
    _exportar_bajada_normalizada(df_gestion, tc_map, path_normalizada, mapping=gestion_mapping)

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

    # Validación con IA
    from ..ai.validator import validar_paso
    validacion = validar_paso(1, resumen, muestra=conciliacion[:5])

    # Diagnóstico estructurado de parseo por archivo
    parser_diagnostico = []
    if gestion_info:
        parser_diagnostico.append({
            "archivo": "Bajada de Gestión (ERP)",
            "metodo": gestion_info["metodo"],
            "confianza": gestion_info["confianza"],
            "mapping": gestion_info["mapping"],
            "columnas_archivo": gestion_info.get("columnas_archivo", []),
            "columnas_faltantes": gestion_info.get("columnas_faltantes", []),
            "columnas_no_mapeadas": gestion_info.get("columnas_no_mapeadas", []),
            "warnings": gestion_info.get("warnings", []),
        })
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

    return {
        "conciliacion": conciliacion,
        "resumen": resumen,
        "bajada_normalizada_path": path_normalizada,
        "mapping_columnas": gestion_mapping,
        "arca_mapping": arca_mapping,
        "parser_diagnostico": parser_diagnostico,
        "validacion": validacion,
    }


def _procesar_gestion(df: pd.DataFrame, tc_map: dict, mapping: dict = None) -> list:
    """
    Procesa la bajada de gestión usando el mapping detectado por smart_parser.
    El df tiene columnas con sus nombres ORIGINALES del ERP.
    El mapping indica qué columna original corresponde a cada campo estándar.
    """
    mapping = mapping or {}

    col_tipo    = mapping.get("tipo_comprobante")
    col_pv      = mapping.get("punto_venta")
    col_num     = mapping.get("numero_comprobante")
    col_fecha   = mapping.get("fecha")
    col_cliente = mapping.get("cliente")
    col_cuit    = mapping.get("cuit_cliente")
    col_moneda  = mapping.get("moneda")
    col_tc      = mapping.get("tipo_cambio")
    col_total   = mapping.get("monto_total")

    registros = []
    for _, row in df.iterrows():
        try:
            # Fecha — columna crítica; si no se detectó, intentamos buscarla en el row
            fecha_raw = row.get(col_fecha) if col_fecha else None
            fecha = pd.to_datetime(fecha_raw, errors="coerce")
            if pd.isna(fecha):
                continue

            tipo = normalizar_tipo_comprobante(row.get(col_tipo) if col_tipo else None)

            numero_raw = row.get(col_num) if col_num else ""
            pv_raw = row.get(col_pv) if col_pv else None

            if pv_raw is not None and not pd.isna(pv_raw) and str(pv_raw).strip():
                numero = normalizar_numero_comprobante(pv=pv_raw, num=numero_raw)
            else:
                numero = normalizar_numero_comprobante(valor_combinado=numero_raw)

            moneda = str(row.get(col_moneda, "ARS") if col_moneda else "ARS").upper().strip() or "ARS"
            tc = normalizar_monto(row.get(col_tc)) if col_tc else 0
            monto_total = normalizar_monto(row.get(col_total) if col_total else 0)

            monto_usd = _convertir_a_usd(monto_total, moneda, tc, fecha, tc_map)

            # Signo por tipo de comprobante
            if tipo == "NC":
                monto_usd = -abs(monto_usd)
            else:
                monto_usd = abs(monto_usd)

            registros.append({
                "tipo": tipo,
                "numero": numero,
                "fecha": fecha.strftime("%Y-%m-%d"),
                "cliente": str(row.get(col_cliente, "") if col_cliente else ""),
                "cuit_cliente": str(row.get(col_cuit, "") if col_cuit else ""),
                "moneda": moneda,
                "monto_original": monto_total,
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

    col_tipo = mapping.get("tipo_comprobante")
    col_pv = mapping.get("punto_venta")
    col_num = mapping.get("numero_comprobante")
    col_fecha = mapping.get("fecha")
    col_moneda = mapping.get("moneda")
    col_tc = mapping.get("tipo_cambio")
    col_total = mapping.get("monto_total")

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
            monto_total = normalizar_monto(row.get(col_total, 0))

            monto_usd = _convertir_a_usd(monto_total, moneda, tc, fecha, tc_map)

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
    """Cruza registros y retorna conciliación.

    Si una key aparece N veces en cada lado, se generan N pares (no se pisan).
    Si aparece más veces en un lado, los sobrantes quedan como SOLO_*.
    """
    from collections import defaultdict

    arca_groups = defaultdict(list)
    gestion_groups = defaultdict(list)
    for r in arca:
        arca_groups[r["key"]].append(r)
    for r in gestion:
        gestion_groups[r["key"]].append(r)

    conciliacion = []
    all_keys = set(arca_groups.keys()) | set(gestion_groups.keys())

    for key in all_keys:
        a_list = arca_groups.get(key, [])
        g_list = gestion_groups.get(key, [])

        # Emparejar uno-a-uno mientras haya en ambos
        n = min(len(a_list), len(g_list))
        for i in range(n):
            r_arca = a_list[i]
            r_gest = g_list[i]
            diff = round(r_gest["monto_usd"] - r_arca["monto_usd_arca"], 2)
            tolerancia = 1.0
            estado = "OK" if abs(diff) <= tolerancia else "DIFERENCIA"
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

        # Sobrantes en ARCA → SOLO_ARCA
        for r_arca in a_list[n:]:
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

        # Sobrantes en Gestión → SOLO_GESTION
        for r_gest in g_list[n:]:
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
