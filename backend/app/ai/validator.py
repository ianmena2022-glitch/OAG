"""
Capa de validación con IA: revisa resultados de cada paso y flagea anomalías.
"""
import json
import re
from typing import List, Dict
from .claude_client import chat


SYSTEM_VALIDADOR = """Eres un auditor contable senior con experiencia en sistemas argentinos.
Tu tarea es revisar el resultado de un paso de auditoría y detectar inconsistencias
o anomalías que un auditor humano debería revisar.

Reglas críticas de coherencia:
1. Conservación: Total ARCA = (OK + Diferencias + Solo_ARCA). Si no cierra, ALGO ESTÁ MAL.
2. Conservación: Total Gestión = (OK + Diferencias + Solo_Gestión). Si no cierra, ALGO ESTÁ MAL.
3. Match 0 con miles de registros sugiere que las claves no matchean bien (formato distinto).
4. Diferencia 10x entre montos USD de dos fuentes sugiere problema de conversión de moneda.
5. Ratio razonable: si 80%+ de registros son SOLO_ARCA o SOLO_GESTION, sugiere desincronización.
6. Montos negativos en facturas comunes (no NC) son sospechosos.
7. Fechas fuera del año analizado son sospechosas.

Devolvé ÚNICAMENTE un JSON con el formato:
{
  "ok": true|false,
  "severidad": "info" | "warning" | "error",
  "alertas": [
    {
      "nivel": "info" | "warning" | "error",
      "titulo": "Título corto",
      "detalle": "Explicación específica con números",
      "sugerencia": "Qué revisar o hacer"
    }
  ]
}
Si todo está bien, devolvé ok=true y alertas=[]. NO inventes problemas que no estén respaldados por los datos."""


def validar_paso(paso_num: int, resumen: dict, muestra: list = None) -> dict:
    """
    Valida el resultado de un paso. Retorna {ok, severidad, alertas}.
    muestra: opcional, primeras N filas de la tabla principal para contexto.
    """
    muestra_str = ""
    if muestra:
        muestra_str = f"\n\nMuestra primeras filas:\n{json.dumps(muestra[:5], ensure_ascii=False, default=str)[:1500]}"

    user_msg = f"""Paso {paso_num} ejecutado. Resumen:
{json.dumps(resumen, ensure_ascii=False, default=str, indent=2)}
{muestra_str}

Revisá si hay inconsistencias o anomalías. Sé específico con los números."""

    try:
        raw = chat(SYSTEM_VALIDADOR, user_msg, max_tokens=2048)
    except Exception as e:
        return {"ok": True, "severidad": "info", "alertas": [], "error_validacion": str(e)}

    # Extraer JSON
    txt = raw.strip()
    if "```" in txt:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", txt)
        if m:
            txt = m.group(1)
    m = re.search(r"\{[\s\S]*\}", txt)
    if m:
        txt = m.group(0)

    try:
        data = json.loads(txt)
        # Normalizar estructura
        if "alertas" not in data:
            data["alertas"] = []
        if "ok" not in data:
            data["ok"] = len(data.get("alertas", [])) == 0
        if "severidad" not in data:
            niveles = [a.get("nivel", "info") for a in data.get("alertas", [])]
            if "error" in niveles:
                data["severidad"] = "error"
            elif "warning" in niveles:
                data["severidad"] = "warning"
            else:
                data["severidad"] = "info"
        return data
    except (json.JSONDecodeError, TypeError):
        return {"ok": True, "severidad": "info", "alertas": [], "raw_response": raw[:500]}
