import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Job
from llm.groq_client import run_gap_analysis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/gap-analysis/{job_id}")
async def gap_analysis(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.description or len(job.description.strip()) < 100:
        raise HTTPException(
            status_code=422,
            detail="Job description is too short for meaningful analysis. This is likely an Indeed metadata-only job.",
        )

    try:
        result = await run_gap_analysis(
            job_title=job.job_title,
            company=job.company,
            job_description=job.description,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Groq gap analysis failed for job {job_id}: {e}")
        raise HTTPException(status_code=502, detail=f"Groq API error: {str(e)}")
