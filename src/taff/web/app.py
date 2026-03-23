"""Application web FastAPI."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from taff.db import get_offers, get_stats, init_db, update_offer_status
from taff.models import CandidatureStatus, SearchCriteria, Source
from taff.scraper_runner import run_all_scrapers, run_single_scraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Taff - Recherche d'emploi", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Page principale - Dashboard."""
    stats = await get_stats()
    recent_offers = await get_offers(limit=10)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "recent_offers": recent_offers,
        "sources": [s.value for s in Source],
        "statuses": [s.value for s in CandidatureStatus],
    })


@app.get("/offers", response_class=HTMLResponse)
async def list_offers(
    request: Request,
    status: str | None = None,
    source: str | None = None,
    search: str | None = None,
    page: int = 1,
):
    """Liste des offres avec filtres."""
    limit = 25
    offset = (page - 1) * limit
    offers = await get_offers(status=status, source=source, search=search, limit=limit, offset=offset)
    stats = await get_stats()
    return templates.TemplateResponse("offers.html", {
        "request": request,
        "offers": offers,
        "stats": stats,
        "current_status": status,
        "current_source": source,
        "current_search": search or "",
        "page": page,
        "sources": [s.value for s in Source],
        "statuses": [s.value for s in CandidatureStatus],
    })


@app.post("/offers/{offer_id}/status")
async def change_status(offer_id: int, status: str = Form(...), notes: str = Form("")):
    """Changer le statut d'une offre."""
    await update_offer_status(offer_id, status, notes if notes else None)
    return RedirectResponse(url="/offers", status_code=303)


@app.post("/scrape")
async def scrape(request: Request, source: str = Form("all"), keywords: str = Form("")):
    """Lancer le scraping."""
    from taff.config import settings
    kw = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else settings.default_keywords
    criteria = SearchCriteria(keywords=kw)

    if source == "all":
        results = await run_all_scrapers(criteria)
    else:
        results = {source: await run_single_scraper(source, criteria)}

    stats = await get_stats()
    return templates.TemplateResponse("scrape_results.html", {
        "request": request,
        "results": results,
        "stats": stats,
        "sources": [s.value for s in Source],
        "statuses": [s.value for s in CandidatureStatus],
    })


@app.get("/scrape", response_class=HTMLResponse)
async def scrape_page(request: Request):
    """Page de lancement du scraping."""
    from taff.config import settings
    return templates.TemplateResponse("scrape.html", {
        "request": request,
        "sources": [s.value for s in Source],
        "statuses": [s.value for s in CandidatureStatus],
        "default_keywords": ", ".join(settings.default_keywords),
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Page de configuration des identifiants."""
    from taff.config import settings
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "sources": [s.value for s in Source],
        "statuses": [s.value for s in CandidatureStatus],
        "settings": settings,
    })


@app.post("/settings")
async def save_settings(
    request: Request,
    apec_email: str = Form(""),
    apec_password: str = Form(""),
    indeed_email: str = Form(""),
    indeed_password: str = Form(""),
    cadremploi_email: str = Form(""),
    cadremploi_password: str = Form(""),
):
    """Sauvegarder les identifiants dans un fichier .env."""
    from taff.config import settings
    from pathlib import Path
    import os

    # Chercher le .env dans le répertoire courant ou le home
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        env_path = Path.home() / ".taff" / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)

    # Lire le .env existant si présent
    existing = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()

    # Mettre à jour
    updates = {
        "TAFF_APEC_EMAIL": apec_email,
        "TAFF_APEC_PASSWORD": apec_password,
        "TAFF_INDEED_EMAIL": indeed_email,
        "TAFF_INDEED_PASSWORD": indeed_password,
        "TAFF_CADREMPLOI_EMAIL": cadremploi_email,
        "TAFF_CADREMPLOI_PASSWORD": cadremploi_password,
    }
    for key, value in updates.items():
        if value:  # Ne sauvegarder que les valeurs non vides
            existing[key] = value
            # Appliquer aussi en live
            os.environ[key] = value

    # Écrire
    lines = [f"{k}={v}" for k, v in existing.items()]
    env_path.write_text("\n".join(lines) + "\n")

    # Recharger les settings
    from taff.config import Settings
    import taff.config
    taff.config.settings = Settings()

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "sources": [s.value for s in Source],
        "statuses": [s.value for s in CandidatureStatus],
        "settings": taff.config.settings,
        "saved": True,
    })


def start():
    """Point d'entrée pour lancer le serveur."""
    import uvicorn
    from taff.config import settings
    uvicorn.run(app, host=settings.host, port=settings.port)
