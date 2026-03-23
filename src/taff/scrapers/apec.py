"""Scraper pour APEC.fr - utilise l'API JSON publique."""

import logging

from taff.models import SearchCriteria
from taff.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

APEC_SEARCH_URL = "https://api.apec.fr/portail-offre/api/v1/offres"


class ApecScraper(BaseScraper):
    source = "apec"

    async def search(self, criteria: SearchCriteria) -> list[dict]:
        offers = []
        keywords = " ".join(criteria.keywords) if criteria.keywords else "DSI"

        payload = {
            "motsCles": keywords,
            "lieux": [],
            "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
            "pagination": {"startIndex": 0, "range": 20},
            "typesContrat": [],
            "niveauxExperience": [],
        }

        if criteria.location:
            payload["lieux"].append({"libelle": criteria.location})

        try:
            resp = await self.client.post(
                APEC_SEARCH_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Referer": "https://www.apec.fr/candidat/recherche-emploi.html/emploi",
                    "Origin": "https://www.apec.fr",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("resultats", []):
                offer = self._build_offer(
                    title=item.get("intitule", ""),
                    company=item.get("nomEntreprise", "Entreprise confidentielle"),
                    location=item.get("lieux", [{}])[0].get("libelle", "") if item.get("lieux") else "",
                    description=item.get("texteHtml", item.get("texte", "")),
                    salary=item.get("salaireTexte", ""),
                    contract_type=item.get("typeContrat", ""),
                    source_url=f"https://www.apec.fr/candidat/recherche-emploi.html/offre/{item.get('numeroOffre', '')}",
                    source_id=str(item.get("numeroOffre", "")),
                    published_at=item.get("datePublication", ""),
                )
                offers.append(offer)

        except Exception as e:
            logger.warning(f"APEC API indisponible: {e}. L'API APEC nécessite parfois un navigateur (CORS). Essayez depuis l'interface web APEC directement.")

        logger.info(f"APEC: {len(offers)} offres trouvées")
        return offers
