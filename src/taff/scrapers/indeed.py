"""Scraper pour Indeed.fr - httpx par défaut, Playwright si disponible."""

import logging
import urllib.parse

from bs4 import BeautifulSoup

from taff.config import settings
from taff.models import SearchCriteria
from taff.scrapers.base import BrowserScraper

logger = logging.getLogger(__name__)

INDEED_URL = "https://fr.indeed.com"
INDEED_LOGIN_URL = "https://secure.indeed.com/account/login"


class IndeedScraper(BrowserScraper):
    source = "indeed"

    # ── Playwright login ──

    async def _login(self, page) -> bool:
        """Se connecter à Indeed si les identifiants sont configurés."""
        if not settings.indeed_email or not settings.indeed_password:
            logger.info("Indeed: pas d'identifiants configurés, navigation anonyme")
            return False

        try:
            await page.goto(INDEED_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            email_input = page.locator("input[type='email'], input[name='__email'], #ifl-InputFormField-3")
            if await email_input.count() > 0:
                await email_input.first.fill(settings.indeed_email)
                submit = page.locator("button[type='submit']")
                if await submit.count() > 0:
                    await submit.first.click()
                    await page.wait_for_timeout(3000)

            pw_input = page.locator("input[type='password']")
            if await pw_input.count() > 0:
                await pw_input.first.fill(settings.indeed_password)
                submit = page.locator("button[type='submit']")
                if await submit.count() > 0:
                    await submit.first.click()
                    await page.wait_for_timeout(3000)

            if "secure.indeed.com" not in page.url:
                logger.info("Indeed: connexion réussie")
                return True
            else:
                logger.warning("Indeed: connexion échouée (peut nécessiter un CAPTCHA/2FA)")
                return False
        except Exception as e:
            logger.warning(f"Indeed login: {e}")
            return False

    # ── Playwright search ──

    async def _search_browser(self, keywords: str, criteria: SearchCriteria) -> list[dict]:
        """Recherche via Playwright."""
        offers = []
        context = await self._get_context()
        if context is None:
            return []
        page = await context.new_page()

        await self._login(page)

        search_url = f"{INDEED_URL}/jobs?q={urllib.parse.quote(keywords)}&sort=date"
        if criteria.location:
            search_url += f"&l={urllib.parse.quote(criteria.location)}"

        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        try:
            await page.wait_for_selector(
                "div.job_seen_beacon, div[data-jk], td.resultContent, [class*='jobCard']",
                timeout=10000,
            )
        except Exception:
            logger.warning("Indeed browser: aucun résultat visible (possible CAPTCHA)")
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
        search_url = f"{INDEED_URL}/jobs?q={urllib.parse.quote(keywords)}&sort=date"
        if criteria.location:
            search_url += f"&l={urllib.parse.quote(criteria.location)}"

        resp = await self.client.get(search_url)
        if resp.status_code != 200:
            logger.warning(f"Indeed HTTP {resp.status_code}")
            return []

        return self._parse_html(resp.text)

    # ── Parser commun ──

    def _parse_html(self, html: str) -> list[dict]:
        """Parse le HTML de résultats Indeed (commun browser/httpx)."""
        offers = []
        soup = BeautifulSoup(html, "lxml")

        cards = soup.select("div.job_seen_beacon, div[data-jk], td.resultContent")

        for card in cards[:25]:
            title_el = card.select_one("h2 a span, h2 span, [class*='jobTitle'] span, [class*='jobTitle']")
            company_el = card.select_one("[data-testid='company-name'], [class*='companyName'], span[class*='company']")
            location_el = card.select_one("[data-testid='text-location'], [class*='companyLocation']")
            salary_el = card.select_one("[class*='salary'], [class*='salaryText'], [class*='estimated-salary']")
            snippet_el = card.select_one("[class*='job-snippet'], [class*='underShelfFooter']")

            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            href = ""
            source_id = ""
            link_el = card.select_one("a[href*='/rc/clk'], a[data-jk], h2 a, a[href*='viewjob']")
            if link_el:
                href = link_el.get("href", "")
                if href and not href.startswith("http"):
                    href = f"{INDEED_URL}{href}"
                jk = link_el.get("data-jk", "")
                if not jk:
                    parent = card.find_parent(attrs={"data-jk": True})
                    jk = parent.get("data-jk", "") if parent else ""
                source_id = jk or (href.split("jk=")[-1].split("&")[0] if "jk=" in href else "")

            offer = self._build_offer(
                title=title,
                company=company_el.get_text(strip=True) if company_el else "",
                location=location_el.get_text(strip=True) if location_el else "",
                salary=salary_el.get_text(strip=True) if salary_el else "",
                description=snippet_el.get_text(strip=True) if snippet_el else "",
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
                logger.info(f"Indeed (Playwright): {len(offers)} offres trouvées")
                return offers
            except Exception as e:
                logger.warning(f"Indeed Playwright failed: {e}, fallback httpx")

        # Fallback httpx
        try:
            offers = await self._search_http(keywords, criteria)
            logger.info(f"Indeed (httpx): {len(offers)} offres trouvées")
            return offers
        except Exception as e:
            logger.error(f"Indeed httpx: {e}")
            return []
