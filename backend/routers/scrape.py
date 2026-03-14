import logging
from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import text
from database import SessionLocal, engine
from models import Job, SeekScrapeRequest, ScrapeResponse
from scraper.seek_scraper import scrape_seek
from scraper.iworkforsa_scraper import scrape_iworkforsa
from matcher.tfidf_matcher import score_jobs_batch

router = APIRouter(prefix="/api/scrape", tags=["scrape"])
logger = logging.getLogger(__name__)

_seek_running       = False
_iworkforsa_running = False
_seek_last:         dict = {}
_iworkforsa_last:   dict = {}


def _save_jobs(raw_jobs: list, source: str) -> tuple:
    db = SessionLocal()
    try:
        existing_urls = {r[0] for r in db.query(Job.application_url).all()}
        new_jobs = [
            j for j in raw_jobs
            if j.get("application_url")
            and not j["application_url"].lower().startswith("javascript")
            and j["application_url"] not in existing_urls
            and j.get("job_title", "").lower() not in {"job title", ""}
        ]
        if not new_jobs:
            return len(raw_jobs), 0
        scored = score_jobs_batch(new_jobs)
        # use INSERT OR IGNORE via raw SQL to be safe against any race duplicates
        with engine.connect() as conn:
            for j in scored:
                conn.execute(
                    text("""
                        INSERT OR IGNORE INTO jobs
                            (job_title, company, location, salary, description,
                             posted_date, application_url, match_score,
                             matched_skills, missing_skills, is_applied)
                        VALUES
                            (:job_title, :company, :location, :salary, :description,
                             :posted_date, :application_url, :match_score,
                             :matched_skills, :missing_skills, 0)
                    """),
                    {
                        "job_title":       j["job_title"],
                        "company":         j["company"],
                        "location":        j["location"],
                        "salary":          j.get("salary", ""),
                        "description":     j["description"],
                        "posted_date":     j.get("posted_date", ""),
                        "application_url": j["application_url"],
                        "match_score":     j.get("match_score", 0.0),
                        "matched_skills":  j.get("matched_skills", "[]"),
                        "missing_skills":  j.get("missing_skills", "[]"),
                    }
                )
            conn.commit()
        return len(raw_jobs), len(scored)
    except Exception as e:
        logger.error(f"{source} save failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


async def _run_seek(request: SeekScrapeRequest):
    global _seek_running, _seek_last
    _seek_running = True
    try:
        raw = await scrape_seek(
            keywords=request.keywords,
            location=request.location,
            max_pages=request.max_pages,
        )
        scraped, inserted = _save_jobs(raw, "seek")
        _seek_last = {"scraped": scraped, "inserted": inserted}
        logger.info(f"Seek done: {scraped} scraped, {inserted} inserted")
    except Exception as e:
        _seek_last = {"error": str(e)}
        logger.error(f"Seek scrape failed: {e}", exc_info=True)
    finally:
        _seek_running = False


async def _run_iworkforsa():
    global _iworkforsa_running, _iworkforsa_last
    _iworkforsa_running = True
    try:
        raw = await scrape_iworkforsa()
        scraped, inserted = _save_jobs(raw, "iworkforsa")
        _iworkforsa_last = {"scraped": scraped, "inserted": inserted}
        logger.info(f"iworkforsa done: {scraped} scraped, {inserted} inserted")
    except Exception as e:
        _iworkforsa_last = {"error": str(e)}
        logger.error(f"iworkforsa scrape failed: {e}", exc_info=True)
    finally:
        _iworkforsa_running = False


@router.post("/seek", response_model=ScrapeResponse)
async def trigger_seek(request: SeekScrapeRequest, background_tasks: BackgroundTasks):
    if _seek_running:
        return ScrapeResponse(scraped=0, scored=0, message="Seek scrape already in progress.")
    background_tasks.add_task(_run_seek, request)
    return ScrapeResponse(scraped=0, scored=0, message="Seek scrape started.")


@router.post("/iworkforsa", response_model=ScrapeResponse)
async def trigger_iworkforsa(background_tasks: BackgroundTasks):
    if _iworkforsa_running:
        return ScrapeResponse(scraped=0, scored=0, message="iworkforSA scrape already in progress.")
    background_tasks.add_task(_run_iworkforsa)
    return ScrapeResponse(scraped=0, scored=0, message="iworkforSA scrape started.")


@router.get("/status")
def scrape_status():
    return {
        "seek":       {"running": _seek_running,       "last_result": _seek_last},
        "iworkforsa": {"running": _iworkforsa_running, "last_result": _iworkforsa_last},
    }
