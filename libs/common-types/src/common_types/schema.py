from __future__ import annotations

from .models import STREAM_MODEL_MAP


def schema_for_stream(stream: str) -> dict:
    model = STREAM_MODEL_MAP.get(stream)
    if model is None:
        raise ValueError(f"Unknown stream: {stream}")
    return model.model_json_schema()
