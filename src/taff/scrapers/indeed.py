"""Scraper pour Indeed.fr - scraping HTML avec fallback RSS."""

import logging

from bs4 import BeautifulSoup

from taff.models import SearchCriteria
from taff.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Indeed bloque souvent le scraping direct, on tente le flux RSS en fallback
INDEED_URL = "https://fr.indeed.com/jobs"
INDEED_RSS_URL = "https://fr.indeed.com/rss"


class IndeedScraper(BaseScraper):
    source = "indeed"

    async def search(self, criteria: SearchCriteria) -> list[dict]:
        offers = []
        keywords = " ".join(criteria.keywords) if criteria.keywords else "DSI"

        # Essayer d'abord le flux RSS (moins bloqué)
        offers = await self._try_rss(keywords, criteria.location)
        if offers:
            return offers

        # Fallback: scraping HTML
        offers = await self._try_html(keywords, criteria.location)
        return offers

    async def _try_rss(self, keywords: str, location: str) -> list[dict]:
        """Tenter le flux RSS Indeed."""
        offers = []
        params = {"q": keywords, "sort": "date"}
        if location:
            params["l"] = location

        try:
            resp = await self.client.get(INDEED_RSS_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml-xml")

            for item in soup.select("item"):
                title = item.select_one("title")
                company_el = item.select_one("source")
                link = item.select_one("link")
                description = item.select_one("description")
                pub_date = item.select_one("pubDate")

                title_text = title.get_text(strip=True) if title else ""
                if not title_text:
                    continue

                href = link.get_text(strip=True) if link else ""
                # Extraire le job key depuis l'URL
                source_id = ""
                if href and "jk=" in href:
                    source_id = href.split("jk=")[-1].split("&")[0]
                elif href:
                    source_id = href.split("/")[-1].split("?")[0]

                offer = self._build_offer(
                    title=title_text,
                    company=company_el.get_text(strip=True) if company_el else "",
                    description=description.get_text(strip=True) if description else "",
                    source_url=href,
                    source_id=source_id or title_text[:50],
                    published_at=pub_date.get_text(strip=True) if pub_date else "",
                )
                offers.append(offer)

        except Exception as e:
            logger.debug(f"Indeed RSS non disponible: {e}")

        if offers:
            logger.info(f"Indeed (RSS): {len(offers)} offres trouvées")
        return offers

    async def _try_html(self, keywords: str, location: str) -> list[dict]:
        """Fallback: scraping HTML Indeed."""
        offers = []
        params = {"q": keywords, "sort": "date"}
        if location:
            params["l"] = location

        try:
            resp = await self.client.get(INDEED_URL, params=params)
            if resp.status_code == 403:
                logger.warning("Indeed: accès bloqué (403). Indeed nécessite un navigateur ou des cookies valides.")
                return []
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("div.job_seen_beacon, div[data-jk], td.resultContent")

            for card in cards[:20]:
                title_el = card.select_one("h2 a span, h2 span, [class*='jobTitle']")
                company_el = card.select_one("[data-testid='company-name'], [class*='companyName']")
                location_el = card.select_one("[data-testid='text-location'], [class*='companyLocation']")
                salary_el = card.select_one("[class*='salary'], [class*='salaryText']")

                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                link_el = card.select_one("a[href*='/rc/clk'], a[data-jk], h2 a")
                href = ""
                source_id = ""
                if link_el:
                    href = link_el.get("href", "")
                    if href and not href.startswith("http"):
                        href = f"https://fr.indeed.com{href}"
                    jk = link_el.get("data-jk", "")
                    source_id = jk or (href.split("jk=")[-1].split("&")[0] if "jk=" in href else "")

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
            logger.warning(f"Indeed HTML: {e}")

        logger.info(f"Indeed (HTML): {len(offers)} offres trouvées")
        return offers
