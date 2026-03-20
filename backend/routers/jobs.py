import json
import logging
import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from database import SessionLocal
from models import Job
from matcher.tfidf_matcher import score_job
from typing import Optional

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)

ALLOWED_SOURCES = {"seek", "iworkforsa", "indeed"}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def list_jobs(
    min_score:  float          = Query(0.0),
    search:     Optional[str]  = Query(None),
    is_applied: Optional[bool] = Query(None),
    sort_by:    str            = Query("match_score"),
    sort_order: str            = Query("desc"),
    source:     Optional[str]  = Query(None),
    page:       int            = Query(1, ge=1),
    page_size:  int            = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(Job).filter(Job.match_score >= min_score)
    if search:
        like = f"%{search}%"
        q = q.filter((Job.job_title.ilike(like)) | (Job.company.ilike(like)))
    if is_applied is not None:
        q = q.filter(Job.is_applied == is_applied)
    if source:
        q = q.filter(Job.source == source)

    sort_col = getattr(Job, sort_by, Job.match_score)
    primary_order = sort_col.desc() if sort_order == "desc" else sort_col.asc()
    # Secondary sort by id ensures stable ordering within ties (e.g. same scraped_at timestamp)
    q = q.order_by(primary_order, Job.id.desc())

    total = q.count()
    jobs  = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "jobs": jobs}


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total     = db.query(func.count(Job.id)).scalar()
    applied   = db.query(func.count(Job.id)).filter(Job.is_applied == True).scalar()
    avg_score = db.query(func.avg(Job.match_score)).scalar()
    top_jobs  = (
        db.query(Job)
        .filter(Job.match_score >= 0.5)
        .order_by(Job.match_score.desc())
        .limit(5)
        .all()
    )
    return {
        "total_jobs":   total,
        "applied_jobs": applied,
        "avg_score":    round(avg_score or 0, 3),
        "top_jobs":     top_jobs,
    }


@router.post("/rescore/{source}")
def rescore_by_source(source: str, db: Session = Depends(get_db)):
    """Re-run TF-IDF scoring on all jobs from a source that have a non-empty description."""
    if source not in ALLOWED_SOURCES:
        return {"error": f"Unknown source '{source}'."}
    jobs = (
        db.query(Job)
        .filter(Job.source == source)
        .filter(Job.description != None)
        .filter(Job.description != "")
        .all()
    )
    rescored = 0
    for job in jobs:
        result = score_job(job.description)
        job.match_score    = result["score"]
        job.matched_skills = json.dumps(result["matched_skills"])
        job.missing_skills = json.dumps(result["missing_skills"])
        rescored += 1
    db.commit()
    logger.info(f"Rescored {rescored} jobs for source '{source}'")
    return {"rescored": rescored, "source": source}


@router.delete("/source/{source}")
def delete_by_source(source: str, db: Session = Depends(get_db)):
    if source not in ALLOWED_SOURCES:
        return {"error": f"Unknown source '{source}'. Allowed: {sorted(ALLOWED_SOURCES)}"}
    result = db.execute(
        text("DELETE FROM jobs WHERE source = :source"),
        {"source": source}
    )
    db.commit()
    deleted = result.rowcount
    logger.info(f"Deleted {deleted} jobs from source '{source}'")
    return {"deleted": deleted, "source": source}


@router.get("/debug/{job_id}")
def debug_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"error": "not found"}
    desc = job.description or ""
    loc  = job.location or ""
    return {
        "id":               job.id,
        "title":            job.job_title,
        "source":           job.source,
        "location":         loc,
        "location_length":  len(loc),
        "desc_length":      len(desc),
        "desc_first_500":   desc[:500],
        "looks_like_html":  "<" in desc and ">" in desc,
    }


@router.post("/fix-descriptions")
def fix_descriptions(db: Session = Depends(get_db)):
    jobs = db.query(Job).filter(Job.source == "iworkforsa").all()
    fixed = 0
    for job in jobs:
        changed = False
        if job.location and len(job.location) > 100:
            match = re.search(r"(\d{4}\s*[-\u2013]\s*[A-Z][A-Z ]+)", job.description or "", re.IGNORECASE)
            job.location = match.group(1).strip() if match else "Adelaide SA"
            changed = True
        if job.description:
            cleaned = re.sub(r"<[^>]+>", " ", job.description)
            cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
            cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
            cleaned = cleaned.strip()
            if cleaned != job.description:
                job.description = cleaned
                changed = True
        if changed:
            fixed += 1
    db.commit()
    return {"fixed": fixed, "total_iworkforsa": len(jobs)}


@router.delete("/purge/duplicates")
def purge_duplicates(db: Session = Depends(get_db)):
    result = db.execute(text("""
        DELETE FROM jobs
        WHERE id NOT IN (
            SELECT MIN(id) FROM jobs
            GROUP BY LOWER(TRIM(job_title)), LOWER(TRIM(company))
        )
    """))
    db.commit()
    deleted = result.rowcount
    logger.info(f"purge-duplicates: removed {deleted} duplicate jobs")
    return {"deleted": deleted}


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    return db.query(Job).filter(Job.id == job_id).first()


@router.patch("/{job_id}/apply")
def mark_applied(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        job.is_applied = True
        db.commit()
    return {"ok": True}


@router.patch("/{job_id}")
def update_job(job_id: int, update: dict, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job:
        for key, value in update.items():
            if hasattr(job, key):
                setattr(job, key, value)
        db.commit()
    return job


@router.delete("/purge/non-ict")
def purge_non_ict(db: Session = Depends(get_db)):
    result = db.execute(text("""
        DELETE FROM jobs
        WHERE source = 'iworkforsa'
        AND match_score < 0.05
        AND (description NOT LIKE '%software%'
             AND description NOT LIKE '%developer%'
             AND description NOT LIKE '%ICT%'
             AND description NOT LIKE '%technology%'
             AND description NOT LIKE '%data%'
             AND description NOT LIKE '%system%'
             AND description NOT LIKE '%analyst%'
             AND description NOT LIKE '%engineer%')
    """))
    db.commit()
    return {"deleted": result.rowcount}
