"""Modèles de données."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Source(str, Enum):
    APEC = "apec"
    CADREMPLOI = "cadremploi"
    INDEED = "indeed"
    HELLOWORK = "hellowork"
    LINKEDIN = "linkedin"


class CandidatureStatus(str, Enum):
    NEW = "new"                    # Nouvelle offre, pas encore traitée
    INTERESTED = "interested"      # Intéressé, à postuler
    APPLIED = "applied"            # Candidature envoyée
    RELAUNCHED = "relaunched"      # Relance effectuée
    INTERVIEW = "interview"        # Entretien planifié
    OFFER = "offer"                # Offre reçue
    REJECTED = "rejected"          # Refusé
    DECLINED = "declined"          # Décliné par moi
    ARCHIVED = "archived"          # Archivé


class JobOffer(BaseModel):
    """Une offre d'emploi."""

    id: int | None = None
    title: str
    company: str
    location: str = ""
    description: str = ""
    salary: str = ""
    contract_type: str = ""
    source: Source
    source_url: str = ""
    source_id: str = ""
    published_at: str = ""
    scraped_at: datetime | None = None
    status: CandidatureStatus = CandidatureStatus.NEW
    notes: str = ""
    score: float | None = None


class SearchCriteria(BaseModel):
    """Critères de recherche."""

    keywords: list[str] = []
    location: str = ""
    contract_types: list[str] = ["CDI"]
    remote_only: bool = False
    min_salary: int | None = None
