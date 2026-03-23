"""Configuration de l'application."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Paramètres de l'application."""

    db_path: str = str(Path.home() / ".taff" / "taff.db")
    host: str = "127.0.0.1"
    port: int = 8000

    # Critères de recherche par défaut
    default_keywords: list[str] = ["DSI", "Directeur des Systèmes d'Information", "IT Director", "CIO", "Chief Information Officer", "Directeur Informatique", "Directeur SI"]
    default_location: str = ""
    default_contract_types: list[str] = ["CDI"]

    # User-Agent pour le scraping
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    model_config = {"env_prefix": "TAFF_"}


settings = Settings()
