"""
Clasifica productos como Agroquímico SI/NO y Syngenta SI/NO usando Claude.

Optimización: trabaja en DOS etapas para ahorrar tokens y tiempo.
  Etapa 1 — clasifica TODOS los productos como agroquímico SI/NO (prompt corto,
            sin contexto Syngenta).
  Etapa 2 — SOLO para los que dieron agroquímico=SI, decide si son Syngenta
            (prompt enfocado, con el maestro Syngenta como contexto).

Para los productos con agroquímico=NO, syngenta queda automáticamente en "NO"
y se conserva la justificación de la Etapa 1.
"""
import json
from typing import List, Dict
from .claude_client import chat
from ..core.config import settings


def _chat_cheap(system: str, user_msg: str, max_tokens: int = 8192) -> str:
    """
    Llama al modelo barato. Si falla (nombre invalido, no disponible, etc.)
    cae automaticamente al modelo principal (mas caro pero seguro) y deja
    el error visible en los logs.
    """
    try:
        return chat(system, user_msg, max_tokens=max_tokens,
                    model=settings.CLAUDE_MODEL_CHEAP)
    except Exception as e:
        print(f"[CLASIFICADOR] Modelo cheap '{settings.CLAUDE_MODEL_CHEAP}' fallo "
              f"({type(e).__name__}: {e}). Cayendo a '{settings.CLAUDE_MODEL}'.")
        return chat(system, user_msg, max_tokens=max_tokens,
                    model=settings.CLAUDE_MODEL)


# ─── Etapa 1: ¿es agroquímico? ─────────────────────────────────────────────────

SYSTEM_AGROQUIMICO = """Eres un experto en productos agropecuarios argentinos.

Tu tarea: para cada producto, decidir si es un AGROQUÍMICO de uso agrícola.

ES agroquímico:
  - Herbicidas (glifosato, atrazina, 2,4-D, dicamba, etc.)
  - Insecticidas (clorpirifos, lambdacialotrina, imidacloprid, etc.)
  - Fungicidas (mancozeb, tebuconazole, azoxystrobin, etc.)
  - Fertilizantes (urea, fosfatos, nitrógeno, micronutrientes, etc.)
  - Coadyuvantes / adherentes / aceites agrícolas
  - Inoculantes (productos para inocular semillas, NO semillas inoculadas)
  - Curasemillas vendidos como producto independiente (ej. Maxim, Cruiser,
    Vibrance) — el producto en sí es el principio activo
  - Acaricidas, nematicidas, rodenticidas de uso agrícola
  - Bioestimulantes / reguladores de crecimiento

NO es agroquímico (categoría separada en el informe ejecutivo):
  - SEMILLAS de cualquier tipo, incluso tratadas, curadas, inoculadas o
    con tratamiento de fábrica. La SEMILLA TRATADA es una SEMILLA, no un
    agroquímico — el principio activo va incluido pero el producto vendido
    es la semilla. Ejemplos típicos que son SEMILLA (no agroquímico):
      - "MAIZ NIDERA AX7761VT3P TRATADO 80MIL SEMILLA" → NO
      - "GIRASOL NIDERA NS1113CL TRATADO 180MIL SEM" → NO
      - "SEM SOJA NS 3220 STS PRIMU BIG BAG" → NO
      - "MAÍZ DK 7210 VT3P TRATADO" → NO
      - "SOJA RR2 TRATADA CON CRUISER" → NO (la semilla es lo principal)
    Palabras clave que indican SEMILLA: "MAIZ", "MAÍZ", "SOJA", "GIRASOL",
    "TRIGO", "SORGO", "CEBADA", "SEMILLA", "SEM ", "SEM.", "BOLSA",
    "BIG BAG", "MIL SEM", "MIL SEMILLA", combinados con "TRATADO/A".
  - Maquinaria, repuestos, herramientas, bolsas silo
  - Alimentos para animales (forrajes, balanceados)
  - Veterinarios (antibióticos, antiparasitarios, vacunas)
  - Combustibles, lubricantes
  - Servicios, mano de obra, fletes
  - Packaging, envases
  - Artículos de limpieza, higiene, oficina

Responde ÚNICAMENTE un JSON array. Para cada producto:
[
  {
    "producto": "nombre exacto recibido",
    "agroquimico": "SI" | "NO",
    "justificacion": "breve explicación (máx 100 chars)"
  },
  ...
]
"""


# ─── Etapa 2: ¿es Syngenta? (solo agroquímicos) ────────────────────────────────

SYSTEM_SYNGENTA = """Eres un experto en la cartera comercial de Syngenta Argentina.

Todos los productos que recibís YA son agroquímicos. Tu única tarea es decidir
si pertenecen a la cartera de Syngenta.

Marcas y productos de Syngenta (lista no exhaustiva — incluye históricas y
modernas que actualmente comercializa Syngenta Argentina):

Herbicidas: Gramoxone, Touchdown (Sulfosato Touchdown), Dual Gold, Callisto,
Lumax, Camix, Halex GT, Axial, Axial Plus, Acuron (Acuron Uno), Boxer,
Reflex, Sequence, Peak, Lambolt, Nuvoxl, Traspect, Voleris, Spirit,
Pack Gold, Trophy, Adengo, Banvel, Gesaprim, Gesagard, Bicep,
Atrazina Syngenta, Flontus, Eforia, Borja, Enelan, Festio, Chikara,
Clearsol, Carexo.

Fungicidas: Amistar, Amistar Top, Priori, Priori Xtra, Quadris, Tilt,
Bravo, Cherokee, Score, Daconil, Folicur (cuando es Syngenta), Elatus,
Elatus Ace, Mazen, Mazen Ace, Miravis, Miravis Duo, Miravis Top,
Miravis Neo, Vibrance, Vibrance Gold, Vibrance Integral, Vesdua,
Vesdua P, Helios, Helios Max, Artea, Bontima, Revus.

Insecticidas: Actara, Engeo, Engeo Pleno, Karate, Karate Zeon, Ampligo,
Voliam, Voliam Flexi, Voliam Targo, Force, Match, Polo, Plenum, Curyom,
Goten, Proclaim, Demand, Atabron, Lannate (cuando Syngenta).

Curasemillas (seed treatments): Maxim, Maxim XL, Maxim Quattro, Maxim Evolution,
CruiserMaxx, Cruiser, Vibrance Gold, Vibrance Integral, Apron, Apron XL,
Apron Maxx, Dividend, Force CS.

Bioestimulantes y nutricionales (Valagro, adquirida por Syngenta en 2020):
Megafol, Viva, Sweet, Maxifruit, Brexil, Erger, Kendal, YieldOn,
Talete, Kiem, Top Set, Sumitec.

Otros: Rainbow (cuando es Syngenta), Heliosulf, Inscalis.

Productos detectados en distribuidores argentinos 2025 (agregados por
validación contra archivos de auditores):
  - Bice Pack (paquete Syngenta — Bice es insecticida+fungicida Syngenta)
  - Verdavis (herbicida Syngenta, principio activo aclonifen+oxifluorfén)
  - Prime+ / Prime Plus (herbicida Syngenta graminicida, pinoxaden+cletodim)
  - Virantra (insecticida Syngenta, tiametoxam+lambda-cihalotrina)
  - Topas (fungicida Syngenta, penconazol)
  - Nogred (herbicida Syngenta, nicosulfurón)
  - Tekarium (fungicida Syngenta, isofetamida)
  - Norbiza Extra (fungicida Syngenta, azoxystrobin+tebuconazol)
  - Oderis (fungicida Syngenta, benzovindiflupyr)
  - Perdure (fungicida Syngenta)
  - Zavobia (fungicida Syngenta)
  - Onduty Plus (herbicida Syngenta, oxasulfurón)
  - Imatron (herbicida Syngenta, imazapic+glifosato)
  - Dash MSO Max (coadyuvante Syngenta)

Principios activos asociados a Syngenta: azoxystrobin (Amistar), benzovindiflupyr
(Elatus/Oderis), pydiflumetofen (Miravis), mefentrifluconazol, isofetamida (Tekarium),
fluindapyr, tiametoxam (Actara/Engeo/Virantra), lambda-cihalotrina (Karate/Virantra),
clorantraniliprol + abamectina (Voliam Targo), mesotrione (Callisto), pinoxaden (Axial/Prime+),
S-metolaclor (Dual Gold), bicyclopirona + s-metolaclor + atrazina (Acuron),
aclonifen (Verdavis), penconazol (Topas), nicosulfurón (Nogred).

Regla práctica: Si el nombre contiene una de las marcas listadas como
subcadena (case-insensitive), es Syngenta. Ej: "AXIAL PLUS 4X5 L ARA" → SI.
"VIBRANCE GOLD 1000L ARA" → SI. "VOLERIS X 20 LTS" → SI.

Responde ÚNICAMENTE un JSON array. Para cada producto:
[
  {
    "producto": "nombre exacto recibido",
    "syngenta": "SI" | "NO",
    "justificacion": "breve explicación (máx 100 chars)"
  },
  ...
]
"""


def _parse_json_array(response: str) -> list:
    """Extrae un JSON array de la respuesta de Claude, tolerante a bloques markdown."""
    text = response.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return json.loads(text)


def _clasificar_agroquimicos(productos: List[str], batch_size: int = 50) -> List[Dict]:
    """Etapa 1: clasifica cada producto como agroquímico SI/NO."""
    resultados = []
    for i in range(0, len(productos), batch_size):
        batch = productos[i: i + batch_size]
        user_msg = (
            f"Clasificá los siguientes {len(batch)} productos:\n\n"
            f"{json.dumps(batch, ensure_ascii=False)}"
        )
        try:
            response = _chat_cheap(SYSTEM_AGROQUIMICO, user_msg)
            batch_results = _parse_json_array(response)
            resultados.extend(batch_results)
        except Exception as e:
            print(f"[CLASIFICADOR] Etapa1 batch {i}-{i+len(batch)} fallo "
                  f"({type(e).__name__}: {e}). Productos quedan en REVISAR.")
            for p in batch:
                resultados.append({
                    "producto": p,
                    "agroquimico": "REVISAR",
                    "justificacion": f"Error en clasificación automática — {type(e).__name__}: "
                                     f"{str(e)[:100]}",
                })
    return resultados


def _clasificar_syngenta(productos_agro: List[str], maestro_syngenta: List[str] = None,
                         batch_size: int = 50, aprendizajes_texto: str = "") -> Dict[str, Dict]:
    """
    Etapa 2: para los productos ya marcados como agroquímico, decide si son Syngenta.
    Devuelve un dict {producto: {syngenta, justificacion}} para fácil mezcla.
    """
    if not productos_agro:
        return {}

    maestro_context = ""
    if maestro_syngenta:
        sample = maestro_syngenta[:100]
        maestro_context = (
            f"\n\nProductos confirmados de Syngenta (maestro oficial):\n"
            f"{json.dumps(sample, ensure_ascii=False)}"
        )

    aprendizajes_ctx = ""
    if aprendizajes_texto:
        aprendizajes_ctx = (
            f"\n\nAprendizajes previos (correcciones aplicadas en otros expedientes — "
            f"tenelos en cuenta):\n{aprendizajes_texto}"
        )

    mapa: Dict[str, Dict] = {}
    for i in range(0, len(productos_agro), batch_size):
        batch = productos_agro[i: i + batch_size]
        user_msg = (
            f"Decidí si cada uno pertenece a la cartera de Syngenta "
            f"({len(batch)} productos):{maestro_context}{aprendizajes_ctx}\n\n"
            f"{json.dumps(batch, ensure_ascii=False)}"
        )
        try:
            response = _chat_cheap(SYSTEM_SYNGENTA, user_msg)
            batch_results = _parse_json_array(response)
            for item in batch_results:
                nombre = item.get("producto")
                if nombre:
                    mapa[nombre] = {
                        "syngenta": item.get("syngenta", "REVISAR"),
                        "justificacion": item.get("justificacion", ""),
                    }
        except Exception as e:
            print(f"[CLASIFICADOR] Etapa2 (Syngenta) batch {i}-{i+len(batch)} fallo "
                  f"({type(e).__name__}: {e}). Productos quedan en REVISAR.")
            for p in batch:
                mapa[p] = {
                    "syngenta": "REVISAR",
                    "justificacion": f"Error en clasificación Syngenta — {type(e).__name__}: "
                                     f"{str(e)[:100]}",
                }
    return mapa


# ─── Orquestador público (firma sin cambios para no romper paso2_service) ──────

def clasificar_productos(productos: List[str], maestro_syngenta: List[str] = None,
                         aprendizajes_texto: str = "") -> List[Dict]:
    """
    Clasifica una lista de productos en dos etapas:
      1. agroquímico SI/NO sobre TODOS los productos
      2. Syngenta SI/NO SOLO sobre los que dieron agroquímico=SI

    Para los no-agroquímicos, syngenta se fuerza a "NO" y se conserva la
    justificación de la etapa 1 ("es semilla", "es lubricante", etc.).

    Devuelve la MISMA estructura que antes — la app muestra todo igual:
    [{producto, agroquimico, syngenta, justificacion}, ...]
    """
    if not productos:
        return []

    # Etapa 1: ¿agroquímico?
    etapa1 = _clasificar_agroquimicos(productos)

    # Etapa 2: solo para los SI
    productos_agro = [r["producto"] for r in etapa1 if r.get("agroquimico") == "SI"]
    mapa_syngenta = _clasificar_syngenta(productos_agro, maestro_syngenta,
                                          aprendizajes_texto=aprendizajes_texto)

    # Mezclar y devolver con la estructura clásica
    resultados: List[Dict] = []
    for r in etapa1:
        nombre = r.get("producto")
        agro = r.get("agroquimico", "REVISAR")
        if agro == "SI":
            syng = mapa_syngenta.get(nombre, {})
            resultados.append({
                "producto": nombre,
                "agroquimico": "SI",
                "syngenta": syng.get("syngenta", "REVISAR"),
                # Para agroquímicos la justificación que importa es la de Syngenta
                "justificacion": syng.get("justificacion") or r.get("justificacion", ""),
            })
        elif agro == "NO":
            resultados.append({
                "producto": nombre,
                "agroquimico": "NO",
                "syngenta": "NO",   # no-agroquímico → no puede ser Syngenta
                "justificacion": r.get("justificacion", ""),
            })
        else:   # REVISAR
            resultados.append({
                "producto": nombre,
                "agroquimico": "REVISAR",
                "syngenta": "REVISAR",
                "justificacion": r.get("justificacion", "Revisar manualmente"),
            })

    return resultados
