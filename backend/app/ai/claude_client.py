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
    client = get_client()
    response = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text
