#!/usr/bin/env python3
"""
OGSA Test Runner — Automatiza ejecución y comparación de pasos.

USO RÁPIDO:
  # Ver todos los expedientes en la DB
  python tests/ogsa_test.py list

  # Re-ejecutar todos los pasos de un expediente y ver métricas
  python tests/ogsa_test.py rerun --exp-id 3

  # Re-ejecutar SOLO el paso 3 para todos los expedientes
  python tests/ogsa_test.py rerun --all --paso 3

  # Guardar métricas actuales como "golden" (referencia esperada)
  python tests/ogsa_test.py golden --save --exp-id 3

  # Comparar salida actual vs golden (detecta regresiones)
  python tests/ogsa_test.py diff --all

  # Comparar salida OGSA vs Excel del auditor
  python tests/ogsa_test.py compare --exp-id 3 --paso 3 --ref "C:/ruta/auditor.xlsx"

CONFIGURACIÓN (variables de entorno o editar DEFAULTS abajo):
  OGSA_URL       URL del backend  (default: http://localhost:8000)
  OGSA_EMAIL     Email del admin  (default: admin@ogsa.com)
  OGSA_PASSWORD  Contraseña       (default: cambiar abajo)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Cargar .env si existe (no bloquea si no está)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

# ── DEFAULTS (editá si no querés usar variables de entorno) ───────────────────

BASE_URL    = os.getenv("OGSA_URL",      "http://localhost:8000")
EMAIL       = os.getenv("OGSA_EMAIL",    "admin@ogsa.com")
PASSWORD    = os.getenv("OGSA_PASSWORD", "admin123")

GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_DIR.mkdir(exist_ok=True)

PASO_TIMEOUT = 600  # segundos máx por paso (clasificación IA puede tardar)

# ── ANSI colors (funcionan en Windows 10+ y Railway logs) ────────────────────

def green(s):   return f"\033[92m{s}\033[0m"
def red(s):     return f"\033[91m{s}\033[0m"
def yellow(s):  return f"\033[93m{s}\033[0m"
def cyan(s):    return f"\033[96m{s}\033[0m"
def bold(s):    return f"\033[1m{s}\033[0m"
def gray(s):    return f"\033[90m{s}\033[0m"

def fmt_usd(v):
    """Formatea un valor numérico como USD."""
    if v is None:
        return "—"
    return f"US$ {float(v):>12,.0f}"

def fmt_val(key, val):
    """Formatea un valor según su tipo (USD vs conteo)."""
    if val is None:
        return "—"
    if isinstance(val, float) and val > 999:
        return f"US$ {val:,.0f}"
    return str(val)

# ── HTTP ──────────────────────────────────────────────────────────────────────

_session = requests.Session()

def login():
    resp = _session.post(
        f"{BASE_URL}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=15,
    )
    if resp.status_code != 200:
        print(red(f"Login fallido ({resp.status_code}): {resp.text[:200]}"))
        sys.exit(1)
    token = resp.json()["access_token"]
    _session.headers.update({"Authorization": f"Bearer {token}"})
    print(gray(f"[auth] {EMAIL} @ {BASE_URL}"))

def _get(path, **kw):
    return _session.get(f"{BASE_URL}{path}", **kw)

def _post(path, **kw):
    return _session.post(f"{BASE_URL}{path}", **kw)

def list_expedientes():
    r = _get("/expedientes", timeout=15)
    r.raise_for_status()
    return r.json()

def _get_exp_map():
    """Devuelve {id: exp_dict} para lookup rápido."""
    return {e["id"]: e for e in list_expedientes()}

# ── Extracción de métricas por paso ──────────────────────────────────────────
# Cada función extrae las métricas clave del dict de resultado de la API.
# Se usan tanto para mostrar en terminal como para guardar en golden.

def extract_metrics(paso: int, resultado: dict) -> dict:
    m = {"paso": paso}

    if paso == 1:
        res = resultado.get("resumen") or {}
        m["total_arca"]         = res.get("total_arca", 0)
        m["total_gestion"]      = res.get("total_gestion", 0)
        m["solo_arca"]          = res.get("solo_arca", 0)
        m["solo_gestion"]       = res.get("solo_gestion", 0)
        m["internos"]           = res.get("internos", 0)
        m["con_diferencia"]     = res.get("con_diferencia", 0)
        m["monto_arca_usd"]     = round(float(res.get("monto_total_arca_usd") or 0))
        m["monto_gestion_usd"]  = round(float(res.get("monto_total_gestion_usd") or 0))

    elif paso == 2:
        tot = resultado.get("totales") or {}
        m["total_facturado_usd"]  = round(float(tot.get("total_facturado_usd") or 0))
        m["total_syngenta_usd"]   = round(float(tot.get("total_syngenta_usd") or 0))
        m["total_agro_usd"]       = round(float(tot.get("total_agroquimicos_usd") or 0))
        # Contar productos clasificados como Syngenta
        prods = resultado.get("ranking_productos_top10") or []
        m["clientes_count"]       = len(resultado.get("ranking_clientes_top10") or [])
        m["productos_count"]      = len(prods)

    elif paso == 3:
        res = resultado.get("resumen") or {}
        m["total"]          = res.get("total", 0)
        m["ok_cruzado"]     = res.get("ok", 0)
        m["solo_crm"]       = res.get("solo_crm", 0)
        m["solo_gestion"]   = res.get("solo_gestion", 0)
        m["monto_g_usd"]    = round(float(res.get("monto_gestion_total_usd") or 0))
        m["monto_crm_usd"]  = round(float(res.get("monto_crm_total_usd") or 0))

    elif paso == 4:
        tot = resultado.get("totales") or {}
        m["total_compras_usd"]  = round(float(tot.get("total_compras_usd") or 0))
        m["proveedores_count"]  = len(resultado.get("resumen_top20") or [])

    elif paso == 5:
        tot = resultado.get("totales") or {}
        m["total_ventas_usd"]   = round(float(tot.get("total_ventas_usd") or 0))
        m["total_compras_usd"]  = round(float(tot.get("total_compras_usd") or 0))

    # Agregar alertas de la validación como resumen
    val = resultado.get("validacion") or {}
    alertas = val.get("alertas") or []
    m["_alertas_count"]   = len(alertas)
    m["_alertas_errors"]  = sum(1 for a in alertas if a.get("nivel") == "error")
    m["_alertas_warnings"]= sum(1 for a in alertas if a.get("nivel") == "warning")
    m["_alertas_resumen"] = [
        {"nivel": a.get("nivel"), "titulo": a.get("titulo")} for a in alertas[:5]
    ]

    return m

METRICAS_DISPLAY = {
    1: ["total_arca", "total_gestion", "solo_arca", "solo_gestion", "internos",
        "con_diferencia", "monto_arca_usd", "monto_gestion_usd"],
    2: ["total_facturado_usd", "total_syngenta_usd", "total_agro_usd"],
    3: ["total", "ok_cruzado", "solo_crm", "solo_gestion",
        "monto_g_usd", "monto_crm_usd"],
    4: ["total_compras_usd", "proveedores_count"],
    5: ["total_ventas_usd", "total_compras_usd"],
}

def print_metrics(paso: int, metrics: dict, indent: int = 4):
    keys = METRICAS_DISPLAY.get(paso, [k for k in metrics if not k.startswith("_") and k != "paso"])
    sp = " " * indent
    for k in keys:
        v = metrics.get(k)
        if v is None:
            continue
        label = k.ljust(22)
        val = fmt_val(k, v)
        print(f"{sp}{gray(label)}  {cyan(val)}")
    # Alertas
    nerr  = metrics.get("_alertas_errors", 0)
    nwarn = metrics.get("_alertas_warnings", 0)
    if nerr or nwarn:
        resumen = metrics.get("_alertas_resumen", [])
        color = red if nerr else yellow
        print(f"{sp}{color(f'⚠ {nerr} error(es), {nwarn} warning(s) en validación:')}")
        for a in resumen:
            icon = red("✗") if a["nivel"] == "error" else yellow("⚠")
            print(f"{sp}  {icon} {a.get('titulo', '')}")

# ── Tolerancias para diff ─────────────────────────────────────────────────────
# (paso, metrica) → tolerancia porcentual. 0.0 = exacto.

TOLERANCIAS = {
    (1, "solo_gestion"):      0.00,   # debe ser exacto (idealmente 0)
    (1, "solo_arca"):         0.00,
    (1, "monto_arca_usd"):    0.02,   # 2%
    (1, "monto_gestion_usd"): 0.02,
    (1, "total_arca"):        0.00,
    (1, "total_gestion"):     0.02,
    (2, "total_syngenta_usd"):0.05,   # 5% — la IA puede variar
    (2, "total_facturado_usd"):0.05,
    (3, "solo_crm"):          0.00,
    (3, "solo_gestion"):      0.00,
    (3, "monto_g_usd"):       0.05,
    (4, "total_compras_usd"): 0.05,
    (5, "total_ventas_usd"):  0.05,
}
DEFAULT_TOL = 0.10  # 10% para cualquier métrica no listada

def compare_metrics(paso: int, current: dict, golden: dict) -> list[dict]:
    diffs = []
    skip = {"paso", "_alertas_count", "_alertas_errors", "_alertas_warnings",
            "_alertas_resumen"}
    all_keys = (set(current) | set(golden)) - skip

    for key in sorted(all_keys):
        cur = current.get(key)
        gld = golden.get(key)
        if cur is None or gld is None:
            continue
        if not isinstance(cur, (int, float)) or not isinstance(gld, (int, float)):
            if cur != gld:
                diffs.append({"key": key, "nivel": "info", "cur": cur, "gld": gld, "pct": "—"})
            continue

        tol = TOLERANCIAS.get((paso, key), DEFAULT_TOL)

        if gld == 0:
            if cur != 0:
                diffs.append({"key": key, "nivel": "error",
                               "cur": cur, "gld": gld, "pct": "+∞"})
            continue

        diff_pct = (cur - gld) / abs(gld)
        if abs(diff_pct) <= tol:
            continue

        nivel = "error" if abs(diff_pct) > tol * 3 else "warning"
        diffs.append({
            "key": key, "nivel": nivel,
            "cur": cur, "gld": gld,
            "pct": f"{diff_pct * 100:+.1f}%",
        })
    return diffs

# ── Golden files ──────────────────────────────────────────────────────────────

def golden_path(exp_id: int) -> Path:
    return GOLDEN_DIR / f"exp_{exp_id}.json"

def load_golden(exp_id: int) -> Optional[dict]:
    p = golden_path(exp_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

def save_golden_file(exp_id: int, nombre: str, pasos_metrics: dict):
    data = {
        "exp_id":    exp_id,
        "nombre":    nombre,
        "saved_at":  time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pasos":     pasos_metrics,
    }
    golden_path(exp_id).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(green(f"  ✓ Golden guardado → {golden_path(exp_id)}"))

# ── Paso runner ───────────────────────────────────────────────────────────────

def run_paso(exp_id: int, paso: int) -> Optional[dict]:
    """Ejecuta un paso via API y devuelve sus métricas. None si falló."""
    t0 = time.time()
    print(f"  ▶ Paso {paso}  ", end="", flush=True)

    try:
        resp = _post(
            f"/expedientes/{exp_id}/pasos/{paso}/ejecutar",
            timeout=PASO_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        print(red(f"TIMEOUT ({PASO_TIMEOUT}s)"))
        return None
    except requests.exceptions.ConnectionError as e:
        print(red(f"CONEXIÓN FALLIDA: {e}"))
        return None

    elapsed = time.time() - t0

    if resp.status_code != 200:
        err = resp.json().get("detail", resp.text[:200]) if resp.text else str(resp.status_code)
        print(red(f"FALLÓ ({resp.status_code}): {err}"))
        return None

    resultado = resp.json()
    metrics = extract_metrics(paso, resultado)

    # Línea de resumen inline
    nerr  = metrics.get("_alertas_errors", 0)
    nwarn = metrics.get("_alertas_warnings", 0)
    alert_str = ""
    if nerr:
        alert_str = red(f"  ⚠ {nerr}err")
    elif nwarn:
        alert_str = yellow(f"  ⚠ {nwarn}warn")

    print(green(f"✓ {elapsed:.1f}s") + alert_str)
    return metrics

def get_paso_result(exp_id: int, paso: int) -> Optional[dict]:
    resp = _get(f"/expedientes/{exp_id}/pasos/{paso}/resultado", timeout=30)
    if resp.status_code != 200:
        return None
    return resp.json()

# ── Comparación vs auditor ────────────────────────────────────────────────────

def compare_vs_auditor(exp_id: int, paso: int, ref_path: str):
    """
    Compara la salida OGSA de un paso con un Excel del auditor.
    Lee automáticamente las hojas relevantes según el paso.
    """
    try:
        import pandas as pd
        import openpyxl
    except ImportError:
        print(red("ERROR: pip install pandas openpyxl"))
        return

    resultado = get_paso_result(exp_id, paso)
    if not resultado:
        print(red(f"  Paso {paso} no ejecutado aún para exp {exp_id}"))
        return

    ogsa = extract_metrics(paso, resultado)
    ref  = Path(ref_path)
    if not ref.exists():
        print(red(f"  Archivo no encontrado: {ref_path}"))
        return

    xl = pd.ExcelFile(ref_path)
    sheets = xl.sheet_names
    print(gray(f"  Hojas en {ref.name}: {', '.join(sheets)}"))

    # ── Paso 1: buscar sheet CRUCE ARCA/GESTION ──────────────────────────
    if paso == 1:
        target = next((s for s in sheets if "arca" in s.lower() or "gestion" in s.lower()), None)
        if not target:
            print(yellow("  No encontré hoja ARCA/GESTION en el archivo"))
            return
        df = xl.parse(target, header=None)
        print(gray(f"  Leyendo hoja: {target}  ({len(df)} filas)"))
        # Buscar totales
        _show_numeric_summary(df, "Auditor Paso 1")
        _show_ogsa_metrics(ogsa, paso)

    # ── Paso 2: buscar sheet con facturación Syngenta ────────────────────
    elif paso == 2:
        # En el informe final suele haber "Tabla Apertura" o "Clasificacion"
        target = next((s for s in sheets
                       if "syngenta" in s.lower() or "clasif" in s.lower()
                       or "apertura" in s.lower() or "facturac" in s.lower()), None)
        if not target:
            target = sheets[0]
        df = xl.parse(target)
        print(gray(f"  Leyendo hoja: {target}  ({len(df)} filas)"))
        _show_numeric_summary(df, "Auditor Paso 2")
        _show_ogsa_metrics(ogsa, paso)

    # ── Paso 3: buscar sheet CRUCE CRM ───────────────────────────────────
    elif paso == 3:
        target = next((s for s in sheets if "crm" in s.lower() or "cruce" in s.lower()), None)
        if not target:
            print(yellow("  No encontré hoja CRM/CRUCE en el archivo"))
            return
        df = xl.parse(target)
        print(gray(f"  Leyendo hoja: {target}  ({len(df)} filas)"))

        # Contar estados si existe columna de estado
        estado_col = next((c for c in df.columns
                           if "estado" in str(c).lower() or "status" in str(c).lower()), None)
        if estado_col:
            vc = df[estado_col].value_counts()
            print(bold(f"\n  Estados en auditor ({target}):"))
            for estado, cnt in vc.items():
                print(f"    {estado:<30} {cnt:>5}")
            print()

        # Montos numéricos
        _show_numeric_summary(df, "Auditor Paso 3")
        _show_ogsa_metrics(ogsa, paso)

    # ── Paso 4: buscar sheet compras ─────────────────────────────────────
    elif paso == 4:
        target = next((s for s in sheets if "compra" in s.lower() or "proveedor" in s.lower()), None)
        if not target:
            target = sheets[0]
        df = xl.parse(target)
        print(gray(f"  Leyendo hoja: {target}  ({len(df)} filas)"))
        _show_numeric_summary(df, "Auditor Paso 4")
        _show_ogsa_metrics(ogsa, paso)

    else:
        print(yellow(f"  Comparación automática no implementada para paso {paso}"))


def _show_numeric_summary(df, label: str):
    """Muestra sumas de columnas numéricas del DataFrame."""
    import pandas as pd
    num_cols = df.select_dtypes(include="number").columns.tolist()
    if not num_cols:
        print(gray(f"  {label}: sin columnas numéricas detectadas"))
        return
    print(bold(f"\n  {label} — totales columnas numéricas:"))
    for col in num_cols[:8]:
        total = df[col].sum()
        if abs(total) > 100:
            print(f"    {str(col):<35}  {fmt_usd(total)}")


def _show_ogsa_metrics(ogsa: dict, paso: int):
    print(bold(f"\n  OGSA Paso {paso}:"))
    print_metrics(paso, ogsa, indent=4)

# ── COMMANDS ──────────────────────────────────────────────────────────────────

def cmd_list(_args):
    exps = list_expedientes()
    has_golden = lambda eid: golden_path(eid).exists()

    print(bold(f"\n  {'ID':>4}  {'Distribuidor':<35}  {'Año':>4}  {'Pasos completados':<20}  {'Golden'}"))
    print("  " + "─" * 80)
    for e in exps:
        pasos = ",".join(str(p) for p in sorted(e.get("pasos_completados") or []))
        star  = green("⭐") if has_golden(e["id"]) else gray("—")
        print(f"  {e['id']:>4}  {e['nombre_distribuidor']:<35}  "
              f"{e.get('anio_analisis') or '':>4}  {pasos:<20}  {star}")
    print()


def cmd_rerun(args):
    exp_map  = _get_exp_map()
    exp_ids  = [int(x) for x in args.exp_id.split(",")] if not args.all else list(exp_map)
    pasos    = [int(p) for p in args.paso.split(",")] if args.paso else [1, 2, 3, 4, 5]

    summary = []  # (exp_id, nombre, paso, ok, metrics)

    for exp_id in exp_ids:
        nombre = exp_map.get(exp_id, {}).get("nombre_distribuidor", f"Exp#{exp_id}")
        print(bold(f"\n{'═'*62}"))
        print(bold(f"  {nombre}  (id={exp_id})"))
        print(bold(f"{'═'*62}"))

        exp_metrics = {}
        for paso in pasos:
            metrics = run_paso(exp_id, paso)
            if metrics is None:
                summary.append((exp_id, nombre, paso, False, {}))
                if not args.continue_on_error:
                    print(yellow(f"  → Deteniendo en Paso {paso}. Usá --continue para seguir."))
                    break
                continue
            exp_metrics[paso] = metrics
            summary.append((exp_id, nombre, paso, True, metrics))

        # Mostrar métricas detalladas
        for paso, m in exp_metrics.items():
            print(bold(f"\n  Paso {paso}:"))
            print_metrics(paso, m)

        # Auto-diff vs golden
        golden = load_golden(exp_id)
        if golden and exp_metrics:
            print(bold(f"\n  Diff vs golden ({golden.get('saved_at', '?')}):"))
            any_diff = False
            for paso, m in exp_metrics.items():
                gld_paso = (golden.get("pasos") or {}).get(str(paso))
                if not gld_paso:
                    continue
                diffs = compare_metrics(paso, m, gld_paso)
                for d in diffs:
                    any_diff = True
                    icon  = red("✗") if d["nivel"] == "error" else yellow("⚠")
                    print(f"    {icon} Paso{paso}.{d['key']:<22} "
                          f"ahora={fmt_val(d['key'], d['cur'])}  "
                          f"era={fmt_val(d['key'], d['gld'])}  "
                          f"{d['pct']}")
            if not any_diff:
                print(f"    {green('✓ Sin cambios vs golden')}")

    # Tabla resumen final
    print(bold(f"\n{'═'*62}"))
    print(bold("  RESUMEN"))
    print(bold(f"{'═'*62}"))
    for exp_id, nombre, paso, ok, _ in summary:
        icon = green("✓") if ok else red("✗")
        print(f"  {icon} Exp {exp_id} ({nombre[:25]:<25})  Paso {paso}")
    print()


def cmd_golden(args):
    exp_map = _get_exp_map()
    exp_ids = [int(x) for x in args.exp_id.split(",")] if not args.all else list(exp_map)
    pasos   = [int(p) for p in args.paso.split(",")] if args.paso else [1, 2, 3, 4, 5]

    for exp_id in exp_ids:
        nombre = exp_map.get(exp_id, {}).get("nombre_distribuidor", f"Exp#{exp_id}")
        print(bold(f"\n  {nombre} (id={exp_id})"))

        pasos_metrics = {}
        for paso in pasos:
            resultado = get_paso_result(exp_id, paso)
            if not resultado:
                print(gray(f"    Paso {paso}: no ejecutado, saltando"))
                continue
            m = extract_metrics(paso, resultado)
            pasos_metrics[str(paso)] = m
            # Mini-resumen
            claves = [k for k in METRICAS_DISPLAY.get(paso, []) if k in m]
            vals_str = "  ".join(f"{k}={fmt_val(k, m[k])}" for k in claves[:3])
            print(gray(f"    Paso {paso}: {vals_str}"))

        if pasos_metrics:
            save_golden_file(exp_id, nombre, pasos_metrics)
        else:
            print(yellow("    Ningún paso ejecutado — golden no guardado"))


def cmd_diff(args):
    exp_map  = _get_exp_map()
    exp_ids  = [int(x) for x in args.exp_id.split(",")] if not args.all else list(exp_map)
    pasos    = [int(p) for p in args.paso.split(",")] if args.paso else [1, 2, 3, 4, 5]
    total_errors = 0

    for exp_id in exp_ids:
        nombre = exp_map.get(exp_id, {}).get("nombre_distribuidor", f"Exp#{exp_id}")
        golden = load_golden(exp_id)
        if not golden:
            print(yellow(f"\n  {nombre}: sin golden. "
                         f"Ejecutá: ogsa_test.py golden --save --exp-id {exp_id}"))
            continue

        print(bold(f"\n  {nombre}  (golden: {golden.get('saved_at', '?')})"))
        any_diff = False

        for paso in pasos:
            resultado = get_paso_result(exp_id, paso)
            if not resultado:
                print(gray(f"    Paso {paso}: sin datos"))
                continue

            m       = extract_metrics(paso, resultado)
            gld_m   = (golden.get("pasos") or {}).get(str(paso))
            if not gld_m:
                print(gray(f"    Paso {paso}: sin golden para este paso"))
                continue

            diffs = compare_metrics(paso, m, gld_m)
            errors = [d for d in diffs if d["nivel"] == "error"]
            warns  = [d for d in diffs if d["nivel"] == "warning"]
            total_errors += len(errors)

            if not diffs:
                print(f"    Paso {paso}:  {green('✓ OK')}")
            else:
                any_diff = True
                label = (red(f"✗ {len(errors)} error(es)") if errors
                         else yellow(f"⚠ {len(warns)} warning(s)"))
                print(f"    Paso {paso}:  {label}")
                for d in diffs:
                    icon = red("  ✗") if d["nivel"] == "error" else yellow("  ⚠")
                    print(f"    {icon} {d['key']:<22}  "
                          f"ahora={fmt_val(d['key'], d['cur'])}  "
                          f"era={fmt_val(d['key'], d['gld'])}  "
                          f"{d['pct']}")

        if not any_diff:
            print(f"    {green('✓ Sin regresiones detectadas')}")

    print()
    if total_errors == 0:
        print(green(bold("  ✓ Todos los checks dentro de tolerancia")))
    else:
        print(red(bold(f"  ✗ {total_errors} error(es) detectados")))

    return total_errors


def cmd_compare(args):
    exp_map = _get_exp_map()
    exp_id  = int(args.exp_id)
    nombre  = exp_map.get(exp_id, {}).get("nombre_distribuidor", f"Exp#{exp_id}")
    paso    = int(args.paso)

    print(bold(f"\n  Comparando: {nombre} — Paso {paso}"))
    print(bold(f"  Referencia: {args.ref}"))
    print()
    compare_vs_auditor(exp_id, paso, args.ref)
    print()

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="OGSA Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd")

    # list
    sub.add_parser("list", help="Lista expedientes con estado de pasos y golden")

    # rerun
    p = sub.add_parser("rerun", help="Re-ejecuta pasos y muestra métricas")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--exp-id", help="ID(s) separados por coma, ej: 1,3")
    g.add_argument("--all", action="store_true", help="Todos los expedientes")
    p.add_argument("--paso", help="Paso(s) a ejecutar, ej: 3  o  1,2,3. Default: 1-5")
    p.add_argument("--continue-on-error", action="store_true",
                   help="Seguir con el paso siguiente aunque uno falle")

    # golden
    p = sub.add_parser("golden", help="Guarda métricas actuales como referencia")
    p.add_argument("--save", action="store_true", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--exp-id", help="ID(s)")
    g.add_argument("--all", action="store_true")
    p.add_argument("--paso", help="Pasos a incluir. Default: 1-5")

    # diff
    p = sub.add_parser("diff", help="Compara salida actual vs golden")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--exp-id", help="ID(s)")
    g.add_argument("--all", action="store_true")
    p.add_argument("--paso", help="Pasos a comparar. Default: 1-5")

    # compare
    p = sub.add_parser("compare", help="Compara output OGSA vs Excel del auditor")
    p.add_argument("--exp-id", required=True, help="ID del expediente")
    p.add_argument("--paso", required=True, help="Número de paso (1-5)")
    p.add_argument("--ref", required=True, help="Ruta al Excel del auditor")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return

    login()

    if   args.cmd == "list":    cmd_list(args)
    elif args.cmd == "rerun":   cmd_rerun(args)
    elif args.cmd == "golden":  cmd_golden(args)
    elif args.cmd == "diff":
        errors = cmd_diff(args)
        sys.exit(1 if errors else 0)
    elif args.cmd == "compare": cmd_compare(args)


if __name__ == "__main__":
    main()
