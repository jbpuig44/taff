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

    # Identifiants APEC
    apec_email: str = ""
    apec_password: str = ""

    # Identifiants Indeed
    indeed_email: str = ""
    indeed_password: str = ""

    # Identifiants Cadremploi
    cadremploi_email: str = ""
    cadremploi_password: str = ""

    # Playwright
    browser_headless: bool = True
    browser_slow_mo: int = 0  # ms entre chaque action (utile pour debug)

    model_config = {"env_prefix": "TAFF_"}


settings = Settings()
