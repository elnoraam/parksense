from fastapi import APIRouter, Depends

from .. import services
from ..auth import require_any

router = APIRouter()


@router.get("/slots", tags=["slots"], dependencies=[Depends(require_any)])
def list_slots():
    """Pendukung (di luar spesifikasi 2.3): semua slot beserta warna LED, untuk peta slot."""
    return {"slots": services.slot_list(), "generatedAt": services.generated_at()}
