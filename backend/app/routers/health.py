from fastapi import APIRouter

from .. import classifier, ocr, schemas
from ..db import now_iso

router = APIRouter(tags=["health"])


@router.get("/health", response_model=schemas.HealthResponse)
def health():
    return {
        "status": "ok",
        "modelVersion": classifier.MODEL_VERSION,
        "modelReady": True,
        "ocrReady": ocr.available(),
        "time": now_iso(),
    }
