from __future__ import annotations

import threading
import time

from app.config import get_settings

_lock = threading.Lock()
# conversation_id -> timestamps monotonic des unités consommées
_buckets: dict[str, list[float]] = {}


def check_and_consume_ask_units(conversation_id: str, units: int = 1) -> None:
    """
    ``ValueError`` avec message utilisateur si quota dépassé.
    """
    s = get_settings()
    cap = s.dataset_ask_quota_per_conversation_per_minute
    if cap <= 0 or units <= 0:
        return
    key = (conversation_id or "default")[:200]
    now = time.monotonic()
    window = 60.0
    with _lock:
        prev = [t for t in _buckets.get(key, []) if now - t < window]
        if len(prev) + units > cap:
            raise ValueError(
                f"Quota atteint : maximum {cap} unités par minute pour cette conversation. Réessaie dans un instant."
            )
        prev.extend([now] * units)
        _buckets[key] = prev
