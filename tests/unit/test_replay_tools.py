from datetime import datetime, timezone

from apps.replay_tools import build_replay_payload, in_window, parse_event_time


def test_parse_event_time_with_z_suffix():
    dt = parse_event_time("2026-02-15T12:30:00Z")
    assert dt.tzinfo is not None
    assert dt == datetime(2026, 2, 15, 12, 30, 0, tzinfo=timezone.utc)


def test_in_window_inclusive_bounds():
    start = datetime(2026, 2, 15, 10, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 2, 15, 11, 0, 0, tzinfo=timezone.utc)
    probe = datetime(2026, 2, 15, 11, 0, 0, tzinfo=timezone.utc)
    assert in_window(probe, start, end)


def test_build_replay_payload_rewrites_event_id():
    src = {"event_id": "evt-1", "title": "sample", "schema_version": "1.0"}
    out = build_replay_payload(src, replay_id="abc123", index=2)
    assert out["event_id"] == "evt-1:replay:abc123:2"
    assert out["title"] == "sample"
