from __future__ import annotations

from datetime import datetime, timezone


def parse_event_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def in_window(dt: datetime, start: datetime, end: datetime) -> bool:
    start_utc = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
    end_utc = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
    dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return start_utc <= dt_utc <= end_utc


def build_replay_payload(payload: dict, replay_id: str, index: int) -> dict:
    cloned = dict(payload)
    original_event_id = str(payload.get("event_id", ""))
    cloned["event_id"] = f"{original_event_id}:replay:{replay_id}:{index}"
    cloned["schema_version"] = payload.get("schema_version", "1.0")
    return cloned
