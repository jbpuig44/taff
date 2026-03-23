"""Scraper pour HelloWork.com - parse les liens data-cy='offerTitle' + aria-label."""

import json
import logging
import re

from bs4 import BeautifulSoup

from taff.models import SearchCriteria
from taff.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

HELLOWORK_URL = "https://www.hellowork.com/fr-fr/emploi/recherche.html"


def _parse_aria_label(label: str) -> dict:
    """Extrait les infos structurées de l'aria-label HelloWork.

    Format: 'Voir offre de {title} à {location}, chez {company}, pour un {contract}, avec un salaire de {salary}, en {time}'
    """
    info = {"title": "", "company": "", "location": "", "contract_type": "", "salary": ""}

    m = re.search(r"Voir offre de (.+?) à (.+?), chez (.+?),", label)
    if m:
        info["title"] = m.group(1).strip()
        info["location"] = m.group(2).strip()
        info["company"] = m.group(3).strip()

    m = re.search(r"pour un (.+?),", label)
    if m:
        info["contract_type"] = m.group(1).strip()

    m = re.search(r"salaire de (.+?),", label)
    if m:
        info["salary"] = m.group(1).strip()

    return info


class HelloWorkScraper(BaseScraper):
    source = "hellowork"

    async def search(self, criteria: SearchCriteria) -> list[dict]:
        offers = []
        keywords = " ".join(criteria.keywords) if criteria.keywords else "DSI"

        params = {"k": keywords}
        if criteria.location:
            params["l"] = criteria.location

        try:
            resp = await self.client.get(HELLOWORK_URL, params=params)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # HelloWork utilise data-cy="offerTitle" avec aria-label riche
            links = soup.select("a[data-cy='offerTitle']")

            for link in links:
                aria = link.get("aria-label", "")
                title_attr = link.get("title", "")
                href = link.get("href", "")

                if not href:
                    continue

                if not href.startswith("http"):
                    href = f"https://www.hellowork.com{href}"

                # Extraire l'ID de l'offre depuis l'URL
                source_id = href.split("/")[-1].replace(".html", "").split("?")[0]

                # Parser l'aria-label pour les infos structurées
                if aria:
                    info = _parse_aria_label(aria)
                else:
                    info = {"title": "", "company": "", "location": "", "contract_type": "", "salary": ""}

                # Le title de l'attribut contient "Titre - Entreprise"
                title = info["title"]
                company = info["company"]
                if not title and title_attr:
                    parts = title_attr.split(" - ", 1)
                    title = parts[0].strip()
                    if len(parts) > 1:
                        company = parts[1].strip()

                if not title:
                    title = link.get_text(strip=True)
                if not title:
                    continue

                # Extraire aussi le product_id depuis les analytics
                analytics = link.get("data-analytics-values-param", "")
                if analytics:
                    try:
                        data = json.loads(analytics)
                        products = data.get("product_data", [])
                        if products:
                            source_id = products[0].get("product_id", source_id)
                    except (json.JSONDecodeError, KeyError):
                        pass

                offer = self._build_offer(
                    title=title,
                    company=company,
                    location=info["location"],
                    salary=info["salary"],
                    contract_type=info["contract_type"],
                    source_url=href,
                    source_id=source_id,
                )
                offers.append(offer)

        except Exception as e:
            logger.error(f"Erreur scraping HelloWork: {e}")

        logger.info(f"HelloWork: {len(offers)} offres trouvées")
        return offers
