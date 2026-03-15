import logging
import re
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from database import SessionLocal
from models import Job
from typing import Optional

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


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
    q = q.order_by(sort_col.desc() if sort_order == "desc" else sort_col.asc())

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
    """
    Bulk-fix existing iworkforsa jobs:
    - Clears location if it's longer than 100 chars (it's been contaminated with full page text)
    - Extracts a clean postcode/suburb from description if possible
    - Collapses whitespace in description
    """
    jobs = db.query(Job).filter(Job.source == "iworkforsa").all()
    fixed = 0
    for job in jobs:
        changed = False

        # Fix bad location - if it's longer than 100 chars it's definitely page content, not a suburb
        if job.location and len(job.location) > 100:
            # Try to extract postcode + suburb from description e.g. "5000 - ADELAIDE"
            match = re.search(r"(\d{4}\s*[-–]\s*[A-Z ]+)", job.description or "", re.IGNORECASE)
            job.location = match.group(1).strip() if match else "Adelaide SA"
            changed = True

        # Clean description - strip HTML tags and collapse whitespace
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
    logger.info(f"fix-descriptions: fixed {fixed} iworkforsa jobs")
    return {"fixed": fixed, "total_iworkforsa": len(jobs)}


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
