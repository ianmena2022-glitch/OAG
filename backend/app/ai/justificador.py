"""
Genera justificaciones automáticas para diferencias en el cruce CRM.
"""
import json
from typing import List, Dict
from .claude_client import chat

SYSTEM_JUSTIFICADOR = """Eres un auditor comercial experto en productos agroquímicos y en procesos de
reportes de ventas de distribuidores agropecuarios argentinos.

Tu tarea es analizar diferencias entre lo que el distribuidor reportó en el CRM de Syngenta
versus lo que surge de su bajada de gestión (facturas reales), y generar justificaciones
concisas y profesionales para cada diferencia.

Categorías de justificaciones posibles:
1. "Diferencia de timing" - el comprobante fue emitido pero reportado en período distinto
2. "Nota de crédito asociada" - existe una NC que reduce parcialmente el monto
3. "Error de carga CRM" - diferencia probablemente por error en carga manual al CRM
4. "Conversión de moneda" - diferencia atribuible a tipo de cambio utilizado
5. "Producto no reportado en CRM" - venta real sin reporte en CRM
6. "Cantidad parcial reportada" - solo parte de la cantidad fue reportada
7. "Comprobante anulado" - comprobante en gestión pero anulado posteriormente
8. "Sin diferencia significativa" - diferencia < 5% o < USD 100 (insignificante)
9. "Requiere documentación de respaldo" - diferencia significativa sin justificación clara

Para cada diferencia analiza el monto, la cantidad, el producto y el contexto para
asignar la categoría más apropiada.

Responde ÚNICAMENTE con un JSON array:
[
  {
    "indice": número de fila,
    "justificacion": "categoría: explicación breve en español (máx 150 chars)"
  },
  ...
]
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

        response = chat(SYSTEM_JUSTIFICADOR, user_msg, max_tokens=4096)

        try:
            text = response.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            batch_results = json.loads(text)
            resultados.extend(batch_results)
        except (json.JSONDecodeError, KeyError):
            for j in range(len(batch)):
                resultados.append({
                    "indice": i + j,
                    "justificacion": "Error en generación automática — revisar manualmente",
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
