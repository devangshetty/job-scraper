import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Job, ScrapeRequest, ScrapeResponse
from scraper.seek_scraper import scrape_seek
from matcher.tfidf_matcher import score_jobs_batch

router = APIRouter(prefix="/api/scrape", tags=["scrape"])
logger = logging.getLogger(__name__)
_scrape_running = False


async def _run_scrape(db: Session, request: ScrapeRequest):
    global _scrape_running
    _scrape_running = True
    try:
        raw_jobs = await scrape_seek(
            keywords=request.keywords,
            location=request.location,
            max_pages=request.max_pages,
        )

        existing_urls = {r[0] for r in db.query(Job.application_url).all()}
        new_jobs      = [j for j in raw_jobs if j["application_url"] not in existing_urls]

        if not new_jobs:
            return len(raw_jobs), 0

        scored_jobs = score_jobs_batch(new_jobs)

        db_objects = [
            Job(
                job_title       = j["job_title"],
                company         = j["company"],
                location        = j["location"],
                salary          = j.get("salary", ""),
                description     = j["description"],
                posted_date     = j.get("posted_date", ""),
                application_url = j["application_url"],
                match_score     = j.get("match_score"),
                matched_skills  = j.get("matched_skills", "[]"),
                missing_skills  = j.get("missing_skills", "[]"),
            )
            for j in scored_jobs
        ]

        db.bulk_save_objects(db_objects)
        db.commit()
        return len(raw_jobs), len(db_objects)

    except Exception as e:
        logger.error(f"Scrape failed: {e}", exc_info=True)
        raise
    finally:
        _scrape_running = False


@router.post("", response_model=ScrapeResponse)
async def trigger_scrape(request: ScrapeRequest, db: Session = Depends(get_db)):
    global _scrape_running
    if _scrape_running:
        return ScrapeResponse(scraped=0, scored=0, message="Scrape already in progress.")
    scraped, inserted = await _run_scrape(db, request)
    return ScrapeResponse(scraped=scraped, scored=inserted, message=f"Scraped {scraped} jobs, inserted {inserted} new.")


@router.get("/status")
def scrape_status():
    return {"running": _scrape_running}
