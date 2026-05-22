"""
Clasifica productos como Agroquímico SI/NO y Syngenta SI/NO usando Claude.
Trabaja en batches para eficiencia.
"""
import json
from typing import List, Dict
from .claude_client import chat

SYSTEM_CLASIFICADOR = """Eres un experto auditor en el rubro agropecuario argentino con amplio conocimiento
de productos agroquímicos y de la cartera comercial de Syngenta Argentina.

Tu tarea es clasificar productos facturados por un distribuidor agropecuario en dos dimensiones:

1. AGROQUIMICO (SI/NO): Es agroquímico si corresponde a:
   - Herbicidas (glifosato, atrazina, 2,4-D, dicamba, etc.)
   - Insecticidas (clorpirifos, lambdacialotrina, imidacloprid, etc.)
   - Fungicidas (mancozeb, tebuconazole, azoxystrobin, etc.)
   - Fertilizantes (urea, fosfatos, nitrógeno, micronutrientes, etc.)
   - Coadyuvantes / adherentes / aceites agrícolas
   - Inoculantes para semillas
   - Curasemillas
   - Acaricidas, nematicidas, rodenticidas de uso agrícola

   NO es agroquímico:
   - Semillas sin curasemilla
   - Maquinaria, repuestos, herramientas
   - Alimentos para animales (forrajes, balanceados)
   - Veterinarios (antibióticos, antiparasitarios, vacunas)
   - Combustibles, lubricantes
   - Servicios, mano de obra
   - Packaging, envases
   - Artículos de limpieza o higiene

2. SYNGENTA (SI/NO): Pertenece a la cartera de Syngenta si coincide con
   alguno de sus productos registrados. Productos conocidos de Syngenta incluyen
   (entre muchos otros): Actara, Ampligo, Amistar, Azimut, Callisto, Curzate,
   Dual Gold, Elatus, Engeo, Flint, Force, Gramoxone, Header, Herculex, Karate,
   Lannate, Laudis, Lumax, Maxim, NK Seeds, Priori, Quadris, Revus, Ridomil,
   Sencor, Sequence, Switch, Tazer, Touchdown, Trophy, Tilt, Vertimec, Voliam,
   Bontima, CruiserMaxx, Denim, Endura, Expert, Folicur (cuando es Syngenta),
   y todos sus genéricos, formulaciones y mezclas.

   Considera también principios activos exclusivos o asociados históricamente a Syngenta:
   azoxystrobin + cyproconazol (Amistar Top), tiametoxam (Actara/Engeo),
   clorantraniliprol (Altacor/Coragen), lambda-cihalotrina (Karate).

Responde ÚNICAMENTE con un JSON array válido. Para cada producto ingresado devuelve:
[
  {
    "producto": "nombre exacto del producto recibido",
    "agroquimico": "SI" | "NO",
    "syngenta": "SI" | "NO",
    "justificacion": "breve explicación de la clasificación (máx 100 chars)"
  },
  ...
]
"""


def clasificar_productos(productos: List[str], maestro_syngenta: List[str] = None) -> List[Dict]:
    """
    Clasifica una lista de productos. Retorna lista de dicts con clasificación.
    Trabaja en batches de 50 para no exceder tokens.
    """
    if not productos:
        return []

    resultados = []
    batch_size = 50

    maestro_context = ""
    if maestro_syngenta:
        sample = maestro_syngenta[:100]
        maestro_context = f"\n\nProductos confirmados de Syngenta (maestro oficial):\n{json.dumps(sample, ensure_ascii=False)}"

    for i in range(0, len(productos), batch_size):
        batch = productos[i: i + batch_size]
        user_msg = f"Clasificá los siguientes {len(batch)} productos:{maestro_context}\n\nProductos a clasificar:\n{json.dumps(batch, ensure_ascii=False)}"

        response = chat(SYSTEM_CLASIFICADOR, user_msg, max_tokens=4096)

        try:
            text = response.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            batch_results = json.loads(text)
            resultados.extend(batch_results)
        except (json.JSONDecodeError, KeyError):
            # Fallback: marcar todos como no clasificados
            for p in batch:
                resultados.append({
                    "producto": p,
                    "agroquimico": "REVISAR",
                    "syngenta": "REVISAR",
                    "justificacion": "Error en clasificación automática — revisar manualmente",
                })

    return resultados
