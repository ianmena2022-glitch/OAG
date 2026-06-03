import anthropic
from ..core.config import settings

_client: anthropic.Anthropic = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def chat(
    system: str,
    user_message: str,
    max_tokens: int = 4096,
    temperature: float = 0.1,
    model: str = None,
) -> str:
    """
    Llamada simple sin thinking. Rápida, barata.

    Para tareas tipo "clasificación categórica" o "extraer JSON" conviene pasar
    model='claude-sonnet-4-5' explícito — es 5x más barato que Opus y suficiente
    para el caso. Opus se reserva para análisis con razonamiento profundo.
    """
    client = get_client()
    response = client.messages.create(
        model=model or settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def chat_with_thinking(
    system: str,
    user_message: str,
    max_tokens: int = 8192,
    thinking_budget: int = 8000,
) -> str:
    """Llamada con extended thinking. Más lenta (15-30s) pero razona mejor en casos difíciles."""
    client = get_client()
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=1.0,  # thinking requiere temperature=1
        system=system,
        messages=[{"role": "user", "content": user_message}],
        thinking={"type": "enabled", "budget_tokens": thinking_budget},
    )
    # El último bloque es texto, los anteriores pueden ser thinking
    for block in reversed(response.content):
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


def chat_opus(
    system: str,
    user_message: str,
    max_tokens: int = 16384,
    temperature: float = 0.1,
    thinking_budget: int | None = 10000,
) -> dict:
    """
    Llamada al modelo más potente (Opus) para análisis profundo de bugs.
    Reservado para el botón "Revisar con IA" — se le pasa contexto grande
    (output OGSA + archivo del auditor + parser_diag + sample de input)
    y se le pide diagnosticar el bug y proponer un fix.

    Con extended thinking activado por default (mejor razonamiento).

    Devuelve dict con:
      - text: respuesta del modelo
      - input_tokens, output_tokens: para estimar costo
      - model: modelo efectivamente usado
    """
    client = get_client()
    kwargs = dict(
        model="claude-opus-4-5",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    if thinking_budget and thinking_budget > 0:
        kwargs["temperature"] = 1.0  # thinking requiere temperature=1
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
    else:
        kwargs["temperature"] = temperature

    response = client.messages.create(**kwargs)

    # Tomar el último bloque de texto (puede haber bloques de thinking antes)
    text = ""
    for block in reversed(response.content):
        if getattr(block, "type", None) == "text":
            text = block.text
            break

    usage = response.usage
    in_tokens = getattr(usage, "input_tokens", 0)
    out_tokens = getattr(usage, "output_tokens", 0)
    # Opus pricing aprox: $15/M input, $75/M output
    costo_est = (in_tokens * 15 / 1_000_000) + (out_tokens * 75 / 1_000_000)
    print(f"[OPUS] tokens in={in_tokens} out={out_tokens} costo_est=${costo_est:.4f}")

    return {
        "text": text,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "model": response.model,
        "costo_usd_estimado": round(costo_est, 4),
    }
