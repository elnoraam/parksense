from fastapi import APIRouter, Depends

from .. import ai_adapter, services
from ..auth import require_bearer
from ..errors import ApiError

router = APIRouter()


@router.get("/ai/predictions/occupancy", tags=["ai"], dependencies=[Depends(require_bearer)])
def get_occupancy_prediction(fromHour: int, toHour: int):
    """Prediksi okupansi per jam per lantai pada rentang jam (inklusif) beserta advisory."""
    if not (0 <= fromHour < toHour <= 23):
        raise ApiError(400, "INVALID_TIME_WINDOW", "fromHour harus lebih kecil dari toHour dan berada di rentang 0-23")
    try:
        predictions = ai_adapter.predict_occupancy((fromHour, toHour), ai_adapter.load_history())
    except ValueError as exc:
        raise ApiError(400, "INVALID_TIME_WINDOW", str(exc))
    floors = [
        {"floorNumber": f["floorNumber"], "isOpen": f["isOpen"], "total": f["total"]}
        for f in services.floor_summary()
    ]
    return {
        "fromHour": fromHour,
        "toHour": toHour,
        "predictions": predictions,
        "advisory": ai_adapter.make_advisory(predictions, floors),
    }
