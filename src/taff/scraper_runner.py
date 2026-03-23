"""Orchestrateur de scraping : lance tous les scrapers en parallèle."""

import asyncio
import logging

from taff.db import init_db, upsert_offers
from taff.models import SearchCriteria
from taff.scrapers import ALL_SCRAPERS

logger = logging.getLogger(__name__)


async def run_all_scrapers(criteria: SearchCriteria | None = None) -> dict:
    """Lance tous les scrapers et stocke les résultats. Retourne les stats."""
    from taff.config import settings

    if criteria is None:
        criteria = SearchCriteria(
            keywords=settings.default_keywords,
            location=settings.default_location,
            contract_types=settings.default_contract_types,
        )

    await init_db()

    scrapers = [cls() for cls in ALL_SCRAPERS]
    results = {}

    try:
        tasks = [scraper.search(criteria) for scraper in scrapers]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        for scraper, result in zip(scrapers, all_results):
            source = scraper.source
            if isinstance(result, Exception):
                logger.error(f"Erreur {source}: {result}")
                results[source] = {"scraped": 0, "new": 0, "error": str(result)}
            else:
                new_count = await upsert_offers(result)
                results[source] = {"scraped": len(result), "new": new_count, "error": None}
                logger.info(f"{source}: {len(result)} scrappées, {new_count} nouvelles")
    finally:
        for scraper in scrapers:
            await scraper.close()

    return results


async def run_single_scraper(source_name: str, criteria: SearchCriteria | None = None) -> dict:
    """Lance un seul scraper par nom."""
    from taff.config import settings

    if criteria is None:
        criteria = SearchCriteria(
            keywords=settings.default_keywords,
            location=settings.default_location,
        )

    await init_db()

    scraper_cls = None
    for cls in ALL_SCRAPERS:
        if cls.source == source_name:  # type: ignore
            scraper_cls = cls
            break

    if scraper_cls is None:
        return {"error": f"Scraper inconnu: {source_name}"}

    scraper = scraper_cls()
    try:
        offers = await scraper.search(criteria)
        new_count = await upsert_offers(offers)
        return {"scraped": len(offers), "new": new_count, "error": None}
    except Exception as e:
        return {"scraped": 0, "new": 0, "error": str(e)}
    finally:
        await scraper.close()
