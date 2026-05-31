from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "OGSA Auditorías"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # Auth
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours

    # Anthropic
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-opus-4-5"
    # Modelo barato para tareas de clasificación simple (agroquímico SI/NO,
    # justificaciones categóricas). Si la llamada con este modelo falla
    # (ej: nombre inválido o no disponible), automáticamente cae al CLAUDE_MODEL.
    CLAUDE_MODEL_CHEAP: str = "claude-sonnet-4-5"

    # Files — usar /data en producción (Railway Volume) o /tmp en local
    UPLOAD_DIR: str = "/data/ogsa_uploads"
    MAX_FILE_SIZE_MB: int = 50

    # CORS
    FRONTEND_ORIGINS: str = "*"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
