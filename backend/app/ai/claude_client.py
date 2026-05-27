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
) -> str:
    """Llamada simple sin thinking. Rápida, barata."""
    client = get_client()
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
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
