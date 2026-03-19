# ============================================================
# config.py — Paramètres centraux de l'application
# ============================================================
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Base de données
    database_url: str  # postgresql://user:pass@host:port/dbname

    # JWT Auth
    secret_key: str    # générer avec : openssl rand -hex 32
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24h

    # Brevo (emails)
    brevo_api_key: str = ""
    email_from: str = "portfolio@investir.blog"
    email_from_name: str = "Investir.blog — Portefeuille Modèle"

    # App
    environment: str = "development"
    base_currency: str = "USD"
    portfolio_start_value: float = 100_000.0

    # Cron secret (pour le scheduler externe)
    cron_secret: str = "changeme"

    # Financial Modeling Prep API
    fmp_api_key: str = ""

    # CORS
    allowed_origins: str = "http://localhost:3000,https://investir.blog"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
