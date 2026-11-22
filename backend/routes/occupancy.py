from fastapi import APIRouter, Depends

from .. import services
from ..auth import require_any

router = APIRouter()


@router.get("/occupancy/floors", tags=["occupancy"], dependencies=[Depends(require_any)])
def get_occupancy_floors():
    """Ketersediaan slot per lantai (UNKNOWN dihitung terpisah dari available)."""
    return {"floors": services.floor_summary(), "generatedAt": services.generated_at()}
