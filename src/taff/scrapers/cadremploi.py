"""Scraper pour Cadremploi.fr."""

import logging
import urllib.parse

from bs4 import BeautifulSoup

from taff.models import SearchCriteria
from taff.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

CADREMPLOI_URL = "https://www.cadremploi.fr/emploi/liste_offres"


class CadremploiScraper(BaseScraper):
    source = "cadremploi"

    async def search(self, criteria: SearchCriteria) -> list[dict]:
        offers = []
        keywords = " ".join(criteria.keywords) if criteria.keywords else "DSI"

        params = {
            "motcle": keywords,
            "tri": "date",
        }
        if criteria.location:
            params["ville"] = criteria.location

        try:
            resp = await self.client.get(CADREMPLOI_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("li[class*='job-card'], div[class*='job-card'], article[class*='offer']")
            if not cards:
                # Fallback: chercher des liens d'offres
                cards = soup.select("a[href*='/emploi/offre-']")

            for card in cards[:20]:
                title_el = card.select_one("h2, h3, [class*='title']")
                company_el = card.select_one("[class*='company'], [class*='entreprise']")
                location_el = card.select_one("[class*='location'], [class*='lieu'], [class*='city']")
                salary_el = card.select_one("[class*='salary'], [class*='salaire']")
                link_el = card.select_one("a[href*='/emploi/']") or card if card.name == "a" else None

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                href = ""
                source_id = ""
                if link_el:
                    href = link_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = f"https://www.cadremploi.fr{href}"
                    source_id = href.split("/")[-1].split("?")[0] if href else ""

                offer = self._build_offer(
                    title=title,
                    company=company_el.get_text(strip=True) if company_el else "",
                    location=location_el.get_text(strip=True) if location_el else "",
                    salary=salary_el.get_text(strip=True) if salary_el else "",
                    source_url=href,
                    source_id=source_id or title[:50],
                )
                offers.append(offer)

        except Exception as e:
            logger.error(f"Erreur scraping Cadremploi: {e}")

        logger.info(f"Cadremploi: {len(offers)} offres trouvées")
        return offers
