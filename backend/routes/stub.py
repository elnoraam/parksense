"""API STUB: membalas data dummy berbentuk final.

Router ini didaftarkan paling akhir; endpoint asli yang didaftarkan lebih dulu akan menimpanya.
Dihapus pada commit terakhir saat semua endpoint sudah nyata.
"""
from fastapi import APIRouter, Depends

from ..auth import require_any, require_bearer, require_device
from ..util import iso, now

router = APIRouter()


@router.post("/gate/entry-tap", tags=["gate"], dependencies=[Depends(require_device)])
def stub_entry_tap():
    return {
        "recommendation": {"floorNumber": 2, "slotId": "F2-A17"},
        "gateAction": "OPEN_BARRIER",
        "displayMessage": "Lantai 2 - Slot F2-A17",
    }


@router.put("/slots/{slot_id}/status", tags=["slots"], dependencies=[Depends(require_device)])
def stub_update_status(slot_id: str):
    return {
        "slotId": slot_id,
        "currentStatus": "OCCUPIED",
        "ledCommand": {"color": "RED", "sent": True},
    }


@router.get("/occupancy/floors", tags=["occupancy"], dependencies=[Depends(require_any)])
def stub_occupancy():
    return {
        "floors": [
            {"floorNumber": 1, "isOpen": True, "total": 20, "available": 3, "occupied": 16, "unknown": 1},
            {"floorNumber": 2, "isOpen": False, "total": 20, "available": 20, "occupied": 0, "unknown": 0},
        ],
        "generatedAt": iso(now()),
    }


@router.get("/slots", tags=["slots"], dependencies=[Depends(require_any)])
def stub_slots():
    return {
        "slots": [
            {"slotId": "F2-A17", "floorNumber": 2, "status": "OCCUPIED", "ledColor": "RED", "lastUpdate": iso(now())},
            {"slotId": "F2-A18", "floorNumber": 2, "status": "AVAILABLE", "ledColor": "YELLOW", "lastUpdate": None},
            {"slotId": "F1-A05", "floorNumber": 1, "status": "UNKNOWN", "ledColor": "OFF", "lastUpdate": iso(now())},
        ],
        "generatedAt": iso(now()),
    }


@router.get("/ai/predictions/occupancy", tags=["ai"], dependencies=[Depends(require_bearer)])
def stub_prediction(fromHour: int = 6, toHour: int = 9):
    return {
        "fromHour": fromHour,
        "toHour": toHour,
        "predictions": [
            {"hour": h, "floorNumber": 1, "predictedOccupancyPercent": min(100.0, 30.0 + 20 * (h - fromHour))}
            for h in range(fromHour, toHour + 1)
        ],
        "advisory": "Data dummy (stub): pertimbangkan membuka lantai 2 lebih awal.",
    }
