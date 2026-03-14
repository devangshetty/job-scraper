import asyncio
import logging
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from models import Job, ScrapeRequest, ScrapeResponse
from scraper.seek_scraper import scrape_seek
from scraper.iworkforsa_scraper import scrape_iworkforsa
from matcher.tfidf_matcher import score_jobs_batch

router = APIRouter(prefix="/api/scrape", tags=["scrape"])
logger = logging.getLogger(__name__)

_scrape_running = False
_last_result: dict = {}


async def _run_scrape_background(request: ScrapeRequest):
    global _scrape_running, _last_result
    _scrape_running = True
    db = SessionLocal()
    try:
        seek_jobs = await scrape_seek(
            keywords=request.keywords,
            location=request.location,
            max_pages=request.max_pages,
        )

        iworkforsa_jobs = []
        if request.include_iworkforsa:
            try:
                iworkforsa_jobs = await scrape_iworkforsa()
            except Exception as e:
                logger.error(f"iworkforsa scrape failed: {e}", exc_info=True)

        raw_jobs = seek_jobs + iworkforsa_jobs

        existing_urls = {r[0] for r in db.query(Job.application_url).all()}
        new_jobs      = [j for j in raw_jobs if j["application_url"] not in existing_urls]

        if not new_jobs:
            _last_result = {"scraped": len(raw_jobs), "inserted": 0}
            return

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
        _last_result = {"scraped": len(raw_jobs), "inserted": len(db_objects)}
        logger.info(f"Scrape done: {len(raw_jobs)} scraped, {len(db_objects)} inserted")

    except Exception as e:
        logger.error(f"Scrape failed: {e}", exc_info=True)
        _last_result = {"scraped": 0, "inserted": 0, "error": str(e)}
    finally:
        db.close()
        _scrape_running = False


@router.post("", response_model=ScrapeResponse)
async def trigger_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    global _scrape_running
    if _scrape_running:
        return ScrapeResponse(scraped=0, scored=0, message="Scrape already in progress.")
    background_tasks.add_task(_run_scrape_background, request)
    return ScrapeResponse(scraped=0, scored=0, message="Scrape started. Check status at /api/scrape/status.")


@router.get("/status")
def scrape_status():
    return {"running": _scrape_running, "last_result": _last_result}
