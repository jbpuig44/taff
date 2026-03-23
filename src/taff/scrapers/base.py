"""Base scraper interface."""

import abc
import logging
from datetime import datetime, timezone

import httpx

from taff.config import settings
from taff.models import SearchCriteria

logger = logging.getLogger(__name__)


class BaseScraper(abc.ABC):
    """Interface commune pour tous les scrapers."""

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
