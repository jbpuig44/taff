"""Scraper pour LinkedIn Jobs (page publique, sans auth)."""

import logging

from bs4 import BeautifulSoup

from taff.models import SearchCriteria
from taff.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

LINKEDIN_URL = "https://www.linkedin.com/jobs/search/"


class LinkedInScraper(BaseScraper):
    source = "linkedin"

    async def search(self, criteria: SearchCriteria) -> list[dict]:
        offers = []
        keywords = " ".join(criteria.keywords) if criteria.keywords else "DSI"

        params = {
            "keywords": keywords,
            "sortBy": "DD",  # Date décroissante
            "location": "France",
        }
        if criteria.location:
            params["location"] = criteria.location

        try:
            resp = await self.client.get(LINKEDIN_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("div.base-card, li.result-card, div[class*='job-search-card']")
            if not cards:
                cards = soup.select("ul.jobs-search__results-list li")

            for card in cards[:20]:
                title_el = card.select_one("h3, [class*='base-search-card__title'], [class*='title']")
                company_el = card.select_one("h4, [class*='base-search-card__subtitle'], a[class*='company']")
                location_el = card.select_one("[class*='job-search-card__location'], span[class*='location']")
                date_el = card.select_one("time, [class*='date'], [class*='listed']")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                href = ""
                source_id = ""
                link_el = card.select_one("a[href*='/jobs/view/'], a[class*='base-card__full-link']")
                if link_el:
                    href = link_el.get("href", "").split("?")[0]
                    source_id = href.rstrip("/").split("/")[-1] if href else ""

                published = ""
                if date_el:
                    published = date_el.get("datetime", date_el.get_text(strip=True))

                offer = self._build_offer(
                    title=title,
                    company=company_el.get_text(strip=True) if company_el else "",
                    location=location_el.get_text(strip=True) if location_el else "",
                    source_url=href,
                    source_id=source_id or title[:50],
                    published_at=published,
                )
                offers.append(offer)

        except Exception as e:
            logger.error(f"Erreur scraping LinkedIn: {e}")

        logger.info(f"LinkedIn: {len(offers)} offres trouvées")
        return offers
