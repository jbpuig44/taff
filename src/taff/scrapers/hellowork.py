"""Scraper pour HelloWork.com."""

import logging
import urllib.parse

from bs4 import BeautifulSoup

from taff.models import SearchCriteria
from taff.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

HELLOWORK_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html"


class HelloWorkScraper(BaseScraper):
    source = "hellowork"

    async def search(self, criteria: SearchCriteria) -> list[dict]:
        offers = []
        keywords = " ".join(criteria.keywords) if criteria.keywords else "DSI"

        params = {
            "k": keywords,
            "tri": "pertinence",
        }
        if criteria.location:
            params["l"] = criteria.location

        try:
            resp = await self.client.get(HELLOWORK_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("li[class*='offer'], div[class*='offer-card'], article[class*='offer']")
            if not cards:
                cards = soup.select("a[href*='/emploi/']")

            for card in cards[:20]:
                title_el = card.select_one("h2, h3, [class*='title'], [class*='Title']")
                company_el = card.select_one("[class*='company'], [class*='Company'], [class*='entreprise']")
                location_el = card.select_one("[class*='location'], [class*='Location'], [class*='lieu']")
                salary_el = card.select_one("[class*='salary'], [class*='Salary'], [class*='salaire']")
                contract_el = card.select_one("[class*='contract'], [class*='Contract'], [class*='contrat']")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    # Si c'est un lien, prendre le texte du lien
                    if card.name == "a":
                        title = card.get_text(strip=True)
                if not title:
                    continue

                href = ""
                source_id = ""
                link_el = card.select_one("a[href*='/emploi/']") or (card if card.name == "a" else None)
                if link_el:
                    href = link_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = f"https://www.hellowork.com{href}"
                    source_id = href.split("/")[-1].split("?")[0].replace(".html", "") if href else ""

                offer = self._build_offer(
                    title=title,
                    company=company_el.get_text(strip=True) if company_el else "",
                    location=location_el.get_text(strip=True) if location_el else "",
                    salary=salary_el.get_text(strip=True) if salary_el else "",
                    contract_type=contract_el.get_text(strip=True) if contract_el else "",
                    source_url=href,
                    source_id=source_id or title[:50],
                )
                offers.append(offer)

        except Exception as e:
            logger.error(f"Erreur scraping HelloWork: {e}")

        logger.info(f"HelloWork: {len(offers)} offres trouvées")
        return offers
