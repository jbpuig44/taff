"""Scraper pour APEC.fr - auth API avec identifiants."""

import logging

import httpx

from taff.config import settings
from taff.models import SearchCriteria
from taff.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

APEC_AUTH_URL = "https://login.apec.fr/auth/realms/apec/protocol/openid-connect/token"
APEC_SEARCH_URL = "https://api.apec.fr/portail-offre/api/v1/offres"


class ApecScraper(BaseScraper):
    source = "apec"

    def __init__(self):
        super().__init__()
        self._token: str | None = None

    async def _authenticate(self) -> bool:
        """Obtenir un token d'accès via les identifiants APEC."""
        if not settings.apec_email or not settings.apec_password:
            logger.warning("APEC: identifiants non configurés (TAFF_APEC_EMAIL / TAFF_APEC_PASSWORD)")
            return False

        try:
            # APEC utilise Keycloak/OpenID Connect
            resp = await self.client.post(
                APEC_AUTH_URL,
                data={
                    "grant_type": "password",
                    "client_id": "portail-offre",
                    "username": settings.apec_email,
                    "password": settings.apec_password,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("access_token")
                logger.info("APEC: authentification réussie")
                return True
            else:
                logger.warning(f"APEC auth échouée ({resp.status_code}): {resp.text[:200]}")
                return False
        except Exception as e:
            logger.warning(f"APEC auth erreur: {e}")
            return False

    async def _search_api(self, keywords: str, criteria: SearchCriteria) -> list[dict]:
        """Recherche via l'API avec ou sans token."""
        offers = []

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": "https://www.apec.fr/candidat/recherche-emploi.html/emploi",
            "Origin": "https://www.apec.fr",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        payload = {
            "motsCles": keywords,
            "lieux": [],
            "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
            "pagination": {"startIndex": 0, "range": 30},
            "typesContrat": [],
            "niveauxExperience": [],
        }

        if criteria.location:
            payload["lieux"].append({"libelle": criteria.location})

        resp = await self.client.post(APEC_SEARCH_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("resultats", []):
            numero = item.get("numeroOffre", "")
            offer = self._build_offer(
                title=item.get("intitule", ""),
                company=item.get("nomEntreprise", "Entreprise confidentielle"),
                location=(item.get("lieux", [{}])[0].get("libelle", "")
                          if item.get("lieux") else ""),
                description=item.get("texteHtml", item.get("texte", "")),
                salary=item.get("salaireTexte", ""),
                contract_type=item.get("typeContrat", ""),
                source_url=f"https://www.apec.fr/candidat/recherche-emploi.html/offre/{numero}",
                source_id=str(numero),
                published_at=item.get("datePublication", ""),
            )
            offers.append(offer)

        return offers

    async def search(self, criteria: SearchCriteria) -> list[dict]:
        keywords = " ".join(criteria.keywords) if criteria.keywords else "DSI"

        # Tenter sans auth d'abord
        try:
            offers = await self._search_api(keywords, criteria)
            if offers:
                logger.info(f"APEC (sans auth): {len(offers)} offres trouvées")
                return offers
        except Exception:
            pass

        # Tenter avec authentification
        if await self._authenticate():
            try:
                offers = await self._search_api(keywords, criteria)
                logger.info(f"APEC (auth): {len(offers)} offres trouvées")
                return offers
            except Exception as e:
                logger.error(f"APEC API avec auth: {e}")

        logger.warning("APEC: aucune méthode d'accès n'a fonctionné. Configurez TAFF_APEC_EMAIL et TAFF_APEC_PASSWORD.")
        return []
