"""Scraper pour Cadremploi.fr - httpx par défaut, Playwright si disponible."""

import logging
import urllib.parse

from bs4 import BeautifulSoup

from taff.config import settings
from taff.models import SearchCriteria
from taff.scrapers.base import BrowserScraper

logger = logging.getLogger(__name__)

CADREMPLOI_URL = "https://www.cadremploi.fr"
CADREMPLOI_LOGIN_URL = "https://www.cadremploi.fr/mon-compte/connexion"


class CadremploiScraper(BrowserScraper):
    source = "cadremploi"

    # ── Playwright login ──

    async def _login(self, page) -> bool:
        """Se connecter à Cadremploi si les identifiants sont configurés."""
        if not settings.cadremploi_email or not settings.cadremploi_password:
            logger.info("Cadremploi: pas d'identifiants configurés, navigation anonyme")
            return False

        try:
            await page.goto(CADREMPLOI_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            cookie_btn = page.locator("button[id*='accept'], button[class*='accept'], #didomi-notice-agree-button")
            if await cookie_btn.count() > 0:
                await cookie_btn.first.click()
                await page.wait_for_timeout(1000)

            email_input = page.locator("input[type='email'], input[name='email'], input[id*='email']")
            if await email_input.count() > 0:
                await email_input.first.fill(settings.cadremploi_email)

            pw_input = page.locator("input[type='password']")
            if await pw_input.count() > 0:
                await pw_input.first.fill(settings.cadremploi_password)

            submit = page.locator("button[type='submit'], input[type='submit']")
            if await submit.count() > 0:
                await submit.first.click()
                await page.wait_for_timeout(3000)

            if "connexion" not in page.url.lower():
                logger.info("Cadremploi: connexion réussie")
                return True
            else:
                logger.warning("Cadremploi: connexion échouée")
                return False
        except Exception as e:
            logger.warning(f"Cadremploi login: {e}")
            return False

    # ── Playwright search ──

    async def _search_browser(self, keywords: str, criteria: SearchCriteria) -> list[dict]:
        """Recherche via Playwright."""
        context = await self._get_context()
        if context is None:
            return []
        page = await context.new_page()

        await self._login(page)

        search_url = f"{CADREMPLOI_URL}/emploi/liste_offres?motcle={urllib.parse.quote(keywords)}&tri=date"
        if criteria.location:
            search_url += f"&ville={urllib.parse.quote(criteria.location)}"

        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        cookie_btn = page.locator("#didomi-notice-agree-button, button[id*='accept']")
        if await cookie_btn.count() > 0:
            try:
                await cookie_btn.first.click(timeout=2000)
                await page.wait_for_timeout(1000)
            except Exception:
                pass

        try:
            await page.wait_for_selector(
                "[class*='job-card'], [class*='offer'], article, [data-testid*='offer']",
                timeout=10000,
            )
        except Exception:
            logger.warning("Cadremploi browser: aucun résultat visible")
            await self._save_session(context)
            await context.close()
            return []

        content = await page.content()
        offers = self._parse_html(content)

        await self._save_session(context)
        await context.close()
        return offers

    # ── httpx search (fallback) ──

    async def _search_http(self, keywords: str, criteria: SearchCriteria) -> list[dict]:
        """Recherche via httpx (mode dégradé, pas de JS)."""
        search_url = f"{CADREMPLOI_URL}/emploi/liste_offres?motcle={urllib.parse.quote(keywords)}&tri=date"
        if criteria.location:
            search_url += f"&ville={urllib.parse.quote(criteria.location)}"

        resp = await self.client.get(search_url)
        if resp.status_code != 200:
            logger.warning(f"Cadremploi HTTP {resp.status_code}")
            return []

        return self._parse_html(resp.text)

    # ── Parser commun ──

    def _parse_html(self, html: str) -> list[dict]:
        """Parse le HTML de résultats Cadremploi (commun browser/httpx)."""
        offers = []
        soup = BeautifulSoup(html, "lxml")

        cards = soup.select(
            "[class*='job-card'], [class*='offer-card'], "
            "article[class*='offer'], li[class*='offer'], "
            "[data-testid*='offer']"
        )

        if not cards:
            cards = soup.select("a[href*='/emploi/offre-'], a[href*='/candidat/offre/']")

        for card in cards[:25]:
            title_el = card.select_one("h2, h3, [class*='title'], [class*='Title']")
            company_el = card.select_one("[class*='company'], [class*='Company'], [class*='entreprise']")
            location_el = card.select_one("[class*='location'], [class*='Location'], [class*='lieu'], [class*='city']")
            salary_el = card.select_one("[class*='salary'], [class*='Salary'], [class*='salaire']")
            contract_el = card.select_one("[class*='contract'], [class*='Contract'], [class*='contrat']")
            desc_el = card.select_one("[class*='description'], [class*='snippet'], [class*='resume']")

            title = title_el.get_text(strip=True) if title_el else ""
            if not title and card.name == "a":
                title = card.get_text(strip=True)
            if not title:
                continue

            href = ""
            source_id = ""
            link_el = card.select_one("a[href*='/emploi/']") or (card if card.name == "a" else None)
            if link_el:
                href = link_el.get("href", "")
                if href and not href.startswith("http"):
                    href = f"{CADREMPLOI_URL}{href}"
                source_id = href.split("/")[-1].split("?")[0] if href else ""

            offer = self._build_offer(
                title=title,
                company=company_el.get_text(strip=True) if company_el else "",
                location=location_el.get_text(strip=True) if location_el else "",
                salary=salary_el.get_text(strip=True) if salary_el else "",
                contract_type=contract_el.get_text(strip=True) if contract_el else "",
                description=desc_el.get_text(strip=True) if desc_el else "",
                source_url=href,
                source_id=source_id or title[:50],
            )
            offers.append(offer)

        return offers

    # ── Point d'entrée ──

    async def search(self, criteria: SearchCriteria) -> list[dict]:
        keywords = " ".join(criteria.keywords) if criteria.keywords else "DSI"

        # Tenter Playwright si disponible
        if self._use_browser:
            try:
                offers = await self._search_browser(keywords, criteria)
                logger.info(f"Cadremploi (Playwright): {len(offers)} offres trouvées")
                return offers
            except Exception as e:
                logger.warning(f"Cadremploi Playwright failed: {e}, fallback httpx")

        # Fallback httpx
        try:
            offers = await self._search_http(keywords, criteria)
            logger.info(f"Cadremploi (httpx): {len(offers)} offres trouvées")
            return offers
        except Exception as e:
            logger.error(f"Cadremploi httpx: {e}")
            return []
