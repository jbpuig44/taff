"""Scrapers pour les sites d'emploi."""

from taff.scrapers.apec import ApecScraper
from taff.scrapers.cadremploi import CadremploiScraper
from taff.scrapers.hellowork import HelloWorkScraper
from taff.scrapers.indeed import IndeedScraper
from taff.scrapers.linkedin import LinkedInScraper

ALL_SCRAPERS = [
    ApecScraper,
    CadremploiScraper,
    IndeedScraper,
    HelloWorkScraper,
    LinkedInScraper,
]

__all__ = ["ALL_SCRAPERS", "ApecScraper", "CadremploiScraper", "IndeedScraper", "HelloWorkScraper", "LinkedInScraper"]
