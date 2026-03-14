import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from models import Job, JobUpdate, StatsOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _deserialize_job(job: Job) -> dict:
    d = {c.name: getattr(job, c.name) for c in job.__table__.columns}
    d["matched_skills"] = json.loads(job.matched_skills) if job.matched_skills else []
    d["missing_skills"] = json.loads(job.missing_skills) if job.missing_skills else []
    return d


@router.get("")
def list_jobs(
    db:         Session       = Depends(get_db),
    min_score:  float         = Query(0.0),
    location:   Optional[str] = None,
    is_applied: Optional[bool]= None,
    search:     Optional[str] = None,
    sort_by:    str           = Query("match_score", enum=["match_score", "scraped_at", "posted_date"]),
    sort_order: str           = Query("desc", enum=["asc", "desc"]),
    page:       int           = Query(1, ge=1),
    page_size:  int           = Query(20, ge=1, le=100),
):
    q = db.query(Job)
    if min_score > 0:
        q = q.filter(Job.match_score >= min_score)
    if location:
        q = q.filter(Job.location.ilike(f"%{location}%"))
    if is_applied is not None:
        q = q.filter(Job.is_applied == is_applied)
    if search:
        q = q.filter(Job.job_title.ilike(f"%{search}%") | Job.company.ilike(f"%{search}%"))

    total = q.count()
    col   = getattr(Job, sort_by, Job.match_score)
    q     = q.order_by(col.desc() if sort_order == "desc" else col.asc())
    q     = q.offset((page - 1) * page_size).limit(page_size)

    return {"total": total, "page": page, "page_size": page_size, "jobs": [_deserialize_job(j) for j in q.all()]}


@router.get("/stats", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)):
    total   = db.query(Job).count()
    avg     = db.query(func.avg(Job.match_score)).scalar() or 0.0
    applied = db.query(Job).filter(Job.is_applied == True).count()
    high    = db.query(Job).filter(Job.match_score >= 0.7).count()
    return StatsOut(total_jobs=total, avg_score=round(float(avg), 4), applied_count=applied, high_match=high)


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _deserialize_job(job)


@router.patch("/{job_id}")
def update_job(job_id: int, update: JobUpdate, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if update.is_applied is not None:
        job.is_applied = update.is_applied
        if update.is_applied:
            from datetime import datetime
            job.applied_date = datetime.utcnow()
    if update.notes is not None:
        job.notes = update.notes
    db.commit()
    db.refresh(job)
    return _deserialize_job(job)


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    return {"message": f"Job {job_id} deleted"}
