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


def start():
    """Point d'entrée pour lancer le serveur."""
    import uvicorn
    from taff.config import settings
    uvicorn.run(app, host=settings.host, port=settings.port)
