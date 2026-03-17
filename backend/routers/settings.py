import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import Setting

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

AVAILABLE_MODELS = [
    {"id": "llama-3.1-8b-instant",    "label": "Llama 3.1 8B (Fastest)",        "recommended": False},
    {"id": "llama-3.3-70b-versatile",  "label": "Llama 3.3 70B (Best quality)",  "recommended": True},
    {"id": "llama-3.1-70b-versatile",  "label": "Llama 3.1 70B (Good quality)",  "recommended": False},
    {"id": "mixtral-8x7b-32768",       "label": "Mixtral 8x7B (Balanced)",       "recommended": False},
    {"id": "gemma2-9b-it",             "label": "Gemma 2 9B (Lightweight)",      "recommended": False},
]

DEFAULT_MODEL = "llama-3.1-8b-instant"


class ModelUpdate(BaseModel):
    model_id: str


@router.get("/model")
def get_model(db: Session = Depends(get_db)):
    row = db.query(Setting).filter(Setting.key == "groq_model").first()
    current = row.value if row else DEFAULT_MODEL
    return {
        "current_model": current,
        "available_models": AVAILABLE_MODELS,
    }


@router.post("/model")
def set_model(body: ModelUpdate, db: Session = Depends(get_db)):
    valid_ids = {m["id"] for m in AVAILABLE_MODELS}
    if body.model_id not in valid_ids:
        raise HTTPException(status_code=400, detail=f"Unknown model: {body.model_id}")

    row = db.query(Setting).filter(Setting.key == "groq_model").first()
    if row:
        row.value = body.model_id
    else:
        db.add(Setting(key="groq_model", value=body.model_id))
    db.commit()

    logger.info(f"Groq model updated to: {body.model_id}")
    return {"message": f"Model updated to {body.model_id}", "current_model": body.model_id}
