"""
Genera justificaciones automáticas para diferencias en el cruce CRM.
"""
import json
from typing import List, Dict
from .claude_client import chat
from ..core.config import settings

SYSTEM_JUSTIFICADOR = """Sos auditor de ventas de distribuidores agroquímicos argentinos.

Recibís diferencias entre lo facturado por el distribuidor (gestión) y lo
reportado al CRM de Syngenta. Asigná UNA categoría a cada una.

Categorías:
- "Diferencia de timing" — distinto período de reporte
- "Nota de crédito asociada" — NC reduce el monto
- "Error de carga CRM" — error humano en carga manual
- "Conversión de moneda" — diferencia por TC distinto
- "Cantidad parcial reportada" — solo parte fue reportada
- "Comprobante anulado" — anulado después
- "Sin diferencia significativa" — < 5% o < USD 100
- "Requiere respaldo" — sin justificación clara

Respondé ÚNICAMENTE un JSON array (sin nada más, sin ```):
[{"indice": N, "justificacion": "categoría: explicación breve (máx 100 chars)"}, ...]
"""


def generar_justificaciones(diferencias: List[Dict]) -> List[Dict]:
    """
    Genera justificaciones para una lista de diferencias del cruce CRM.
    Cada dict debe tener: producto, fecha, tipo_comprobante, numero,
    cuit_cliente, cant_gestion, cant_crm, monto_gestion, monto_crm.
    """
    if not diferencias:
        return []

    resultados = []
    batch_size = 30

    for i in range(0, len(diferencias), batch_size):
        batch = diferencias[i: i + batch_size]
        indexed = [{"indice": i + j, **row} for j, row in enumerate(batch)]

        user_msg = f"""Analizá las siguientes {len(batch)} diferencias del cruce CRM y generá una justificación para cada una:

{json.dumps(indexed, ensure_ascii=False, default=str)}"""

        try:
            # Sonnet alcanza para esta clasificación categórica (5x más barato).
            # Si el modelo cheap falla, fallback automático al modelo principal
            # — la visibilidad del error queda en stdout y los logs.
            # max_tokens=8192 con sobra para 30 items × ~150 tokens cada uno.
            # Subido desde 1500 que truncaba la respuesta a mitad del JSON.
            try:
                response = chat(SYSTEM_JUSTIFICADOR, user_msg,
                                max_tokens=8192, model=settings.CLAUDE_MODEL_CHEAP)
            except Exception as e_cheap:
                print(f"[JUSTIFICADOR] Modelo cheap '{settings.CLAUDE_MODEL_CHEAP}' "
                      f"fallo ({type(e_cheap).__name__}: {e_cheap}). "
                      f"Cayendo a '{settings.CLAUDE_MODEL}'.")
                response = chat(SYSTEM_JUSTIFICADOR, user_msg,
                                max_tokens=8192, model=settings.CLAUDE_MODEL)
            text = response.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            batch_results = json.loads(text)
            resultados.extend(batch_results)
        except Exception as e:
            # Cualquier falla de la IA (timeout, rate limit, JSON inválido, etc.)
            # NO debe bloquear el Paso 3 — se marca como pendiente y listo.
            print(f"[JUSTIFICADOR] Batch {i}-{i+len(batch)} falló: {e}")
            for j in range(len(batch)):
                resultados.append({
                    "indice": i + j,
                    "justificacion": "Pendiente — generación automática no disponible",
                })

    # Ordenar por índice y retornar solo justificaciones
    resultados.sort(key=lambda x: x.get("indice", 0))
    return [r.get("justificacion", "") for r in resultados]


def mapear_glosario(productos: List[str], glosario: List[Dict]) -> List[Dict]:
    """
    Mapea productos a nombres estandarizados del glosario usando Claude.
    glosario: lista de dicts con {nombre_original, nombre_estandar}
    """
    if not productos or not glosario:
        return [{"producto": p, "nombre_glosario": p} for p in productos]

    SYSTEM_GLOSARIO = """Eres un experto en productos agroquímicos argentinos.
Tu tarea es mapear nombres de productos facturados al nombre estandarizado del glosario.

Criterios de matching:
- Ignorar diferencias de mayúsculas/minúsculas
- Ignorar presentaciones (litros, kg, etc.) si el producto base coincide
- Considerar nombres comerciales alternativos y abreviaturas
- Si no hay match claro en el glosario, usar el nombre original

Responde ÚNICAMENTE con un JSON array:
[
  {"producto": "nombre_original", "nombre_glosario": "nombre_estandarizado_del_glosario"},
  ...
]
"""

    batch_size = 50
    resultados = []

    glosario_nombres = [g["nombre_estandar"] for g in glosario[:200]]

    for i in range(0, len(productos), batch_size):
        batch = productos[i: i + batch_size]

        user_msg = f"""Glosario disponible (nombres estandarizados):
{json.dumps(glosario_nombres, ensure_ascii=False)}

Productos a mapear:
{json.dumps(batch, ensure_ascii=False)}"""

        response = chat(SYSTEM_GLOSARIO, user_msg, max_tokens=4096)

        try:
            text = response.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            batch_results = json.loads(text)
            resultados.extend(batch_results)
        except json.JSONDecodeError:
            for p in batch:
                resultados.append({"producto": p, "nombre_glosario": p})

    return resultados
