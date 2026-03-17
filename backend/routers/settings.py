import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Setting

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

# Only models that are live on Groq as of March 2026
GAP_MODELS = [
    {"id": "llama-3.1-8b-instant",   "label": "Llama 3.1 8B (Fastest)",       "recommended": False},
    {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B (Best quality)", "recommended": True},
]

SUMMARISER_MODELS = [
    {"id": "llama-3.1-8b-instant",   "label": "Llama 3.1 8B (Fast, default)",  "recommended": False},
    {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B (Best quality)", "recommended": True},
]

VALID_MODEL_IDS      = {m["id"] for m in GAP_MODELS}
DEFAULT_GAP_MODEL        = "llama-3.1-8b-instant"
DEFAULT_SUMMARISER_MODEL = "llama-3.1-8b-instant"


class ModelUpdate(BaseModel):
    model_id: str


def _safe_model(value: str | None, default: str) -> str:
    """If stored value is a now-deprecated model, fall back to default silently."""
    if value and value in VALID_MODEL_IDS:
        return value
    return default


# --- Gap analysis model ---

@router.get("/model/gap")
def get_gap_model(db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == "groq_model").first()
    return {
        "current_model": _safe_model(row.value if row else None, DEFAULT_GAP_MODEL),
        "available_models": GAP_MODELS,
    }


@router.post("/model/gap")
def set_gap_model(body: ModelUpdate, db: Session = Depends(get_db)):
    _validate(body.model_id, GAP_MODELS)
    _upsert(db, "groq_model", body.model_id)
    logger.info(f"Gap analysis model updated to: {body.model_id}")
    return {"current_model": body.model_id}


# --- Summariser model ---

@router.get("/model/summariser")
def get_summariser_model(db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == "summariser_model").first()
    return {
        "current_model": _safe_model(row.value if row else None, DEFAULT_SUMMARISER_MODEL),
        "available_models": SUMMARISER_MODELS,
    }


@router.post("/model/summariser")
def set_summariser_model(body: ModelUpdate, db: Session = Depends(get_db)):
    _validate(body.model_id, SUMMARISER_MODELS)
    _upsert(db, "summariser_model", body.model_id)
    logger.info(f"Summariser model updated to: {body.model_id}")
    return {"current_model": body.model_id}


# Backwards compat - maps to gap model
@router.get("/model")
def get_model_compat(db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == "groq_model").first()
    return {
        "current_model": _safe_model(row.value if row else None, DEFAULT_GAP_MODEL),
        "available_models": GAP_MODELS,
    }

@router.post("/model")
def set_model_compat(body: ModelUpdate, db: Session = Depends(get_db)):
    _validate(body.model_id, GAP_MODELS)
    _upsert(db, "groq_model", body.model_id)
    return {"current_model": body.model_id}


def _validate(model_id: str, model_list: list):
    valid = {m["id"] for m in model_list}
    if model_id not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_id}")


def _upsert(db: Session, key: str, value: str):
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()
