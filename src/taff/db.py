"""Couche base de données SQLite."""

from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from taff.config import settings
from taff.models import CandidatureStatus, Source


class Base(DeclarativeBase):
    pass


class JobOfferRow(Base):
    __tablename__ = "job_offers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(sa.String(500))
    company: Mapped[str] = mapped_column(sa.String(300))
    location: Mapped[str] = mapped_column(sa.String(300), default="")
    description: Mapped[str] = mapped_column(sa.Text, default="")
    salary: Mapped[str] = mapped_column(sa.String(200), default="")
    contract_type: Mapped[str] = mapped_column(sa.String(50), default="")
    source: Mapped[str] = mapped_column(sa.String(50))
    source_url: Mapped[str] = mapped_column(sa.String(1000), default="")
    source_id: Mapped[str] = mapped_column(sa.String(200), default="")
    published_at: Mapped[str] = mapped_column(sa.String(100), default="")
    scraped_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(sa.String(50), default=CandidatureStatus.NEW.value)
    notes: Mapped[str] = mapped_column(sa.Text, default="")
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("source", "source_id", name="uq_source_offer"),
    )


def _get_engine():
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    return engine


engine = _get_engine()
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Créer les tables si elles n'existent pas."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def upsert_offers(offers: list[dict]) -> int:
    """Insérer ou ignorer des offres (dédupliquées par source+source_id). Retourne le nombre de nouvelles offres."""
    if not offers:
        return 0
    count = 0
    async with async_session() as session:
        for offer in offers:
            # Vérifier si l'offre existe déjà
            result = await session.execute(
                sa.select(JobOfferRow).where(
                    JobOfferRow.source == offer["source"],
                    JobOfferRow.source_id == offer["source_id"],
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                session.add(JobOfferRow(**offer))
                count += 1
        await session.commit()
    return count


async def get_offers(
    status: str | None = None,
    source: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Récupérer les offres avec filtres optionnels."""
    async with async_session() as session:
        query = sa.select(JobOfferRow).order_by(JobOfferRow.scraped_at.desc())
        if status:
            query = query.where(JobOfferRow.status == status)
        if source:
            query = query.where(JobOfferRow.source == source)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                sa.or_(
                    JobOfferRow.title.ilike(pattern),
                    JobOfferRow.company.ilike(pattern),
                    JobOfferRow.description.ilike(pattern),
                )
            )
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "title": r.title,
                "company": r.company,
                "location": r.location,
                "description": r.description,
                "salary": r.salary,
                "contract_type": r.contract_type,
                "source": r.source,
                "source_url": r.source_url,
                "source_id": r.source_id,
                "published_at": r.published_at,
                "scraped_at": r.scraped_at.isoformat() if r.scraped_at else "",
                "status": r.status,
                "notes": r.notes,
                "score": r.score,
            }
            for r in rows
        ]


async def update_offer_status(offer_id: int, status: str, notes: str | None = None) -> bool:
    """Mettre à jour le statut d'une offre."""
    async with async_session() as session:
        result = await session.execute(
            sa.select(JobOfferRow).where(JobOfferRow.id == offer_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return False
        row.status = status
        if notes is not None:
            row.notes = notes
        await session.commit()
        return True


async def get_stats() -> dict:
    """Statistiques globales."""
    async with async_session() as session:
        total = (await session.execute(sa.select(sa.func.count(JobOfferRow.id)))).scalar()
        by_status = {}
        result = await session.execute(
            sa.select(JobOfferRow.status, sa.func.count(JobOfferRow.id)).group_by(JobOfferRow.status)
        )
        for status, count in result.all():
            by_status[status] = count
        by_source = {}
        result = await session.execute(
            sa.select(JobOfferRow.source, sa.func.count(JobOfferRow.id)).group_by(JobOfferRow.source)
        )
        for source, count in result.all():
            by_source[source] = count
        return {"total": total, "by_status": by_status, "by_source": by_source}
