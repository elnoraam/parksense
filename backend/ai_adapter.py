"""Adaptor modul AI: pakai ai/ bila ada, jika tidak pakai ai_fallback.

Tiap fungsi dipilih terpisah, jadi modul tersebut bisa masuk satu per satu tanpa mengubah backend.
`USING` menunjukkan mana yang sedang dipakai (terlihat di /health).
"""
from functools import lru_cache

from . import ai_fallback

USING: dict[str, str] = {}


def _pick(name: str, module: str):
    try:
        mod = __import__(module, fromlist=[name])
        fn = getattr(mod, name)
        USING[name] = "ai"
        return fn
    except (ImportError, AttributeError):
        USING[name] = "fallback"
        return getattr(ai_fallback, name)


recommend_slot = _pick("recommend_slot", "ai.recommend")
predict_occupancy = _pick("predict_occupancy", "ai.predict")
make_advisory = _pick("make_advisory", "ai.predict")
detect_anomaly = _pick("detect_anomaly", "ai.anomaly")
status_from_distance = _pick("status_from_distance", "ai.anomaly")
_load_history = _pick("load_history", "ai.seed_history")


@lru_cache(maxsize=1)
def load_history() -> list[dict]:
    return _load_history()
