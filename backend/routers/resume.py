import io
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Setting
from llm.resume_summariser import summarise_resume
import pdfplumber

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resume", tags=["resume"])

MAX_BYTES = 3 * 1024 * 1024  # 3 MB
ALLOWED_MIME = {"application/pdf"}


def _extract_text(file_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pdfplumber."""
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t.strip())
    return "\n\n".join(text_parts)


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # --- Security checks ---
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Only PDF files are accepted. Got: {file.content_type}",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is 3 MB, got {len(file_bytes) / 1024 / 1024:.1f} MB.",
        )

    # Verify the bytes actually start with the PDF magic number %PDF
    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=415,
            detail="File does not appear to be a valid PDF.",
        )

    # --- Extract text ---
    try:
        resume_text = _extract_text(file_bytes)
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        raise HTTPException(status_code=422, detail="Could not extract text from PDF. Is it a scanned image?")

    if len(resume_text.strip()) < 200:
        raise HTTPException(
            status_code=422,
            detail="Extracted text is too short. The PDF may be image-based or empty.",
        )

    # Store raw extracted text
    _upsert_setting(db, "resume_raw_text", resume_text)
    _upsert_setting(db, "resume_filename", file.filename or "resume.pdf")
    _upsert_setting(db, "resume_summary", "")  # clear any old summary

    return {
        "message": "Resume uploaded and text extracted successfully.",
        "filename": file.filename,
        "char_count": len(resume_text),
        "preview": resume_text[:300] + "..." if len(resume_text) > 300 else resume_text,
    }


@router.post("/summarise")
async def summarise(db: Session = Depends(get_db)):
    raw = _get_setting(db, "resume_raw_text")
    if not raw:
        raise HTTPException(status_code=404, detail="No resume uploaded yet. Please upload a PDF first.")

    try:
        summary = await summarise_resume(raw)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Resume summarisation failed: {e}")
        raise HTTPException(status_code=502, detail=f"Groq API error: {str(e)}")

    _upsert_setting(db, "resume_summary", summary)

    return {
        "message": "Resume summarised successfully.",
        "summary": summary,
    }


@router.get("/status")
def resume_status(db: Session = Depends(get_db)):
    filename = _get_setting(db, "resume_filename")
    summary = _get_setting(db, "resume_summary")
    raw = _get_setting(db, "resume_raw_text")
    return {
        "has_resume": bool(raw),
        "has_summary": bool(summary),
        "filename": filename or None,
        "summary": summary or None,
    }


# --- Helpers ---

def _upsert_setting(db: Session, key: str, value: str):
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def _get_setting(db: Session, key: str) -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row else ""
