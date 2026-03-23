"""Scraper pour Indeed.fr."""

import logging
import urllib.parse

from bs4 import BeautifulSoup

from taff.models import SearchCriteria
from taff.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

INDEED_URL = "https://fr.indeed.com/jobs"


class IndeedScraper(BaseScraper):
    source = "indeed"

    async def search(self, criteria: SearchCriteria) -> list[dict]:
        offers = []
        keywords = " ".join(criteria.keywords) if criteria.keywords else "DSI"

        params = {
            "q": keywords,
            "sort": "date",
        }
        if criteria.location:
            params["l"] = criteria.location

        try:
            resp = await self.client.get(INDEED_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Indeed utilise des div avec data-jk pour chaque offre
            cards = soup.select("div.job_seen_beacon, div[data-jk], div.resultContent, td.resultContent")
            if not cards:
                cards = soup.select("div[class*='cardOutline'], div[class*='result']")

            for card in cards[:20]:
                title_el = card.select_one("h2 a, h2 span, a[data-jk], [class*='jobTitle']")
                company_el = card.select_one("[data-testid='company-name'], span[class*='company'], [class*='companyName']")
                location_el = card.select_one("[data-testid='text-location'], div[class*='companyLocation'], [class*='location']")
                salary_el = card.select_one("[class*='salary'], [class*='salaryText'], div[class*='metadata']")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                # Extraire le lien
                link_el = card.select_one("a[href*='/rc/clk'], a[data-jk], h2 a")
                href = ""
                source_id = ""
                if link_el:
                    href = link_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = f"https://fr.indeed.com{href}"
                    jk = link_el.get("data-jk", "")
                    source_id = jk if jk else href.split("jk=")[-1].split("&")[0] if "jk=" in href else ""

                if not source_id:
                    # Essayer de trouver le data-jk sur le parent
                    parent = card.find_parent(attrs={"data-jk": True})
                    if parent:
                        source_id = parent.get("data-jk", "")

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
            logger.error(f"Erreur scraping Indeed: {e}")

        logger.info(f"Indeed: {len(offers)} offres trouvées")
        return offers
