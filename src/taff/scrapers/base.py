"""Base scraper interfaces."""

import abc
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from taff.config import settings
from taff.models import SearchCriteria

logger = logging.getLogger(__name__)

# Répertoire pour stocker les états de session Playwright
SESSION_DIR = Path.home() / ".taff" / "sessions"

# Vérifier si Playwright est disponible
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright  # noqa: F401
    # Vérifier qu'un navigateur est installé
    import subprocess
    result = subprocess.run(
        ["python3", "-c", "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True, args=['--no-sandbox']); b.close(); p.stop()"],
        capture_output=True, timeout=10,
    )
    if result.returncode == 0:
        PLAYWRIGHT_AVAILABLE = True
    else:
        logger.info("Playwright installé mais navigateur non disponible. Mode httpx uniquement.")
except Exception:
    logger.info("Playwright non disponible. Mode httpx uniquement.")


class BaseScraper(abc.ABC):
    """Interface commune pour les scrapers HTTP (httpx)."""

    source: str = ""

    def __init__(self):
        self.client = httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
            timeout=30.0,
        )

    async def close(self):
        await self.client.aclose()

    @abc.abstractmethod
    async def search(self, criteria: SearchCriteria) -> list[dict]:
        """Rechercher des offres selon les critères. Retourne une liste de dicts prêts pour la DB."""
        ...

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _build_offer(
        self,
        title: str,
        company: str,
        location: str = "",
        description: str = "",
        salary: str = "",
        contract_type: str = "",
        source_url: str = "",
        source_id: str = "",
        published_at: str = "",
    ) -> dict:
        return {
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "salary": salary,
            "contract_type": contract_type,
            "source": self.source,
            "source_url": source_url,
            "source_id": source_id,
            "published_at": published_at,
            "scraped_at": self._now(),
        }


class BrowserScraper(BaseScraper):
    """Base pour les scrapers qui utilisent Playwright quand dispo, sinon httpx."""

    def __init__(self):
        super().__init__()
        self._playwright = None
        self._browser = None
        self._use_browser = PLAYWRIGHT_AVAILABLE

    async def _get_browser(self):
        """Lance Playwright et retourne le navigateur (lazy init)."""
        if not self._use_browser:
            return None
        if self._browser is None:
            from playwright.async_api import async_playwright
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=settings.browser_headless,
                    slow_mo=settings.browser_slow_mo,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
            except Exception as e:
                logger.warning(f"Playwright launch failed: {e}. Fallback httpx.")
                self._use_browser = False
                return None
        return self._browser

    async def _get_context(self):
        """Retourne un contexte avec session persistante (cookies sauvegardés)."""
        browser = await self._get_browser()
        if browser is None:
            return None
        storage_path = SESSION_DIR / f"{self.source}.json"

        if storage_path.exists():
            logger.info(f"{self.source}: restauration session depuis {storage_path}")
            context = await browser.new_context(
                storage_state=str(storage_path),
                user_agent=settings.user_agent,
            )
        else:
            context = await browser.new_context(
                user_agent=settings.user_agent,
            )
        return context

    async def _save_session(self, context):
        """Sauvegarder l'état de session (cookies, localStorage)."""
        if context is None:
            return
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        storage_path = SESSION_DIR / f"{self.source}.json"
        await context.storage_state(path=str(storage_path))
        logger.info(f"{self.source}: session sauvegardée dans {storage_path}")

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        await super().close()
