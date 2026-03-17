import logging
import uuid
from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import text
from database import SessionLocal, engine
from models import Job, SeekScrapeRequest, ScrapeResponse
from scraper.seek_scraper import scrape_seek
from scraper.iworkforsa_scraper import scrape_iworkforsa
from scraper.indeed_scraper import scrape_indeed
from matcher.tfidf_matcher import score_jobs_batch
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/api/scrape", tags=["scrape"])
logger = logging.getLogger(__name__)

_seek_running       = False
_iworkforsa_running = False
_indeed_running     = False
_seek_last:         dict = {}
_iworkforsa_last:   dict = {}
_indeed_last:       dict = {}


class IndeedScrapeRequest(BaseModel):
    keywords:  List[str] = ["Software Engineer", "Full Stack Developer", "Java Developer", "React Developer"]
    location:  str       = "Adelaide SA"
    max_pages: int       = 3


def _save_jobs(raw_jobs: list, source: str) -> dict:
    """Dedup by URL, insert new jobs, return found/inserted/skipped counts."""
    session_id = str(uuid.uuid4())
    db = SessionLocal()
    try:
        # Load all existing URLs once - O(1) lookup
        existing_urls = {r[0] for r in db.query(Job.application_url).all()}

        # Filter duplicates and bad entries
        new_jobs = []
        skipped  = 0
        seen_in_batch = set()

        for j in raw_jobs:
            url = (j.get("application_url") or "").strip()

            # skip missing / javascript: URLs
            if not url or url.lower().startswith("javascript"):
                skipped += 1
                continue

            # skip placeholder titles
            if (j.get("job_title") or "").lower().strip() in {"", "job title"}:
                skipped += 1
                continue

            # skip if already in DB
            if url in existing_urls:
                skipped += 1
                continue

            # skip duplicates within this batch
            if url in seen_in_batch:
                skipped += 1
                continue

            seen_in_batch.add(url)
            j["source"] = source
            new_jobs.append(j)

        if not new_jobs:
            logger.info(f"{source}: found={len(raw_jobs)} inserted=0 skipped={skipped}")
            return {"found": len(raw_jobs), "inserted": 0, "skipped": skipped, "scrape_session_id": session_id}

        scored = score_jobs_batch(new_jobs)

        with engine.connect() as conn:
            for j in scored:
                conn.execute(
                    text("""
                        INSERT OR IGNORE INTO jobs
                            (job_title, company, location, salary, description,
                             posted_date, application_url, scrape_session_id,
                             match_score, matched_skills, missing_skills, is_applied, source)
                        VALUES
                            (:job_title, :company, :location, :salary, :description,
                             :posted_date, :application_url, :scrape_session_id,
                             :match_score, :matched_skills, :missing_skills, 0, :source)
                    """),
                    {
                        "job_title":          j["job_title"],
                        "company":            j["company"],
                        "location":           j.get("location", ""),
                        "salary":             j.get("salary", ""),
                        "description":        j.get("description", ""),
                        "posted_date":        j.get("posted_date", ""),
                        "application_url":    j["application_url"],
                        "scrape_session_id":  session_id,
                        "match_score":        j.get("match_score", 0.0),
                        "matched_skills":     j.get("matched_skills", "[]"),
                        "missing_skills":     j.get("missing_skills", "[]"),
                        "source":             j.get("source", source),
                    }
                )
            conn.commit()

        logger.info(f"{source}: found={len(raw_jobs)} inserted={len(scored)} skipped={skipped} session={session_id}")
        return {
            "found":             len(raw_jobs),
            "inserted":          len(scored),
            "skipped":           skipped,
            "scrape_session_id": session_id,
        }

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
        _seek_last = _save_jobs(raw, "seek")
        logger.info(f"Seek complete: {_seek_last}")
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
        _iworkforsa_last = _save_jobs(raw, "iworkforsa")
        logger.info(f"iworkforsa complete: {_iworkforsa_last}")
    except Exception as e:
        _iworkforsa_last = {"error": str(e)}
        logger.error(f"iworkforsa scrape failed: {e}", exc_info=True)
    finally:
        _iworkforsa_running = False


async def _run_indeed(request: IndeedScrapeRequest):
    global _indeed_running, _indeed_last
    _indeed_running = True
    try:
        raw = await scrape_indeed(
            keywords=request.keywords,
            location=request.location,
            max_pages=request.max_pages,
        )
        _indeed_last = _save_jobs(raw, "indeed")
        logger.info(f"Indeed complete: {_indeed_last}")
    except Exception as e:
        _indeed_last = {"error": str(e)}
        logger.error(f"Indeed scrape failed: {e}", exc_info=True)
    finally:
        _indeed_running = False


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


@router.post("/indeed", response_model=ScrapeResponse)
async def trigger_indeed(request: IndeedScrapeRequest, background_tasks: BackgroundTasks):
    if _indeed_running:
        return ScrapeResponse(scraped=0, scored=0, message="Indeed scrape already in progress.")
    background_tasks.add_task(_run_indeed, request)
    return ScrapeResponse(scraped=0, scored=0, message="Indeed scrape started.")


@router.get("/status")
def scrape_status():
    return {
        "seek":       {"running": _seek_running,       "last_result": _seek_last},
        "iworkforsa": {"running": _iworkforsa_running, "last_result": _iworkforsa_last},
        "indeed":     {"running": _indeed_running,     "last_result": _indeed_last},
    }
