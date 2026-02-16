from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from redis import asyncio as redis

from apps.replay_tools import build_replay_payload, in_window, parse_event_time
from common_types import AppSettings, Streams

app = FastAPI(title="crypto-news-trading orchestrator", version="0.3.0")
settings = AppSettings()
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

STREAMS = [
    Streams.NEWS_RAW,
    Streams.NEWS_ENTITY,
    Streams.SIGNAL_RAW,
    Streams.SIGNAL_TRADEABLE,
    Streams.SIGNAL_UNIVERSE,
    Streams.ORDER_INTENT,
    Streams.ORDER_APPROVED,
    Streams.ORDER_REJECTED,
    Streams.EXECUTION_REPORT,
    Streams.PNL_SNAPSHOT,
]

MAX_REPLAY_TASKS = 200
REPLAY_TASK_INDEX_KEY = "replay:tasks:index"
REPLAY_TASK_KEY_PREFIX = "replay:task:"

replay_tasks: dict[str, "ReplayTask"] = {}
replay_workers: dict[str, asyncio.Task] = {}


class ConfigUpdate(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class ReplayTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class ReplayWindowRequest(BaseModel):
    start: datetime
    end: datetime
    source_stream: str = Streams.NEWS_RAW
    target_stream: str = Streams.NEWS_RAW
    max_scan: int = Field(default=5000, ge=1, le=50000)
    max_publish: int = Field(default=1000, ge=1, le=10000)
    dry_run: bool = False
    async_mode: bool = True


class ReplayTask(BaseModel):
    task_id: str
    replay_id: str
    status: ReplayTaskStatus
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    start: datetime
    end: datetime
    source_stream: str
    target_stream: str
    max_scan: int
    max_publish: int
    dry_run: bool

    scanned: int = 0
    matched: int = 0
    published: int = 0


class ReplayRetryRequest(BaseModel):
    async_mode: bool = True


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _task_key(task_id: str) -> str:
    return f"{REPLAY_TASK_KEY_PREFIX}{task_id}"


async def _persist_replay_task(task: ReplayTask) -> None:
    replay_tasks[task.task_id] = task
    payload = json.dumps(task.model_dump(mode="json"))
    await redis_client.set(_task_key(task.task_id), payload)
    await redis_client.zadd(REPLAY_TASK_INDEX_KEY, {task.task_id: task.submitted_at.timestamp()})


async def _load_replay_task(task_id: str) -> ReplayTask | None:
    task = replay_tasks.get(task_id)
    if task is not None:
        return task

    raw = await redis_client.get(_task_key(task_id))
    if not raw:
        return None

    parsed = ReplayTask.model_validate(json.loads(raw))
    replay_tasks[task_id] = parsed
    return parsed


async def _trim_replay_tasks() -> None:
    count = await redis_client.zcard(REPLAY_TASK_INDEX_KEY)
    if count <= MAX_REPLAY_TASKS:
        return

    to_remove = count - MAX_REPLAY_TASKS
    remove_ids = await redis_client.zrange(REPLAY_TASK_INDEX_KEY, 0, to_remove - 1)
    if not remove_ids:
        return

    await redis_client.zrem(REPLAY_TASK_INDEX_KEY, *remove_ids)
    remove_keys = [_task_key(task_id) for task_id in remove_ids]
    await redis_client.delete(*remove_keys)
    for task_id in remove_ids:
        replay_tasks.pop(task_id, None)
        replay_workers.pop(task_id, None)


async def _list_replay_tasks(limit: int) -> list[ReplayTask]:
    task_ids = await redis_client.zrevrange(REPLAY_TASK_INDEX_KEY, 0, limit - 1)
    if not task_ids:
        tasks = sorted(replay_tasks.values(), key=lambda item: item.submitted_at, reverse=True)
        return tasks[:limit]

    raws = await redis_client.mget([_task_key(task_id) for task_id in task_ids])
    tasks: list[ReplayTask] = []
    for task_id, raw in zip(task_ids, raws):
        if not raw:
            continue
        task = ReplayTask.model_validate(json.loads(raw))
        replay_tasks[task_id] = task
        tasks.append(task)

    tasks.sort(key=lambda item: item.submitted_at, reverse=True)
    return tasks[:limit]


def _task_duration_sec(task: ReplayTask) -> float | None:
    if task.started_at is None or task.completed_at is None:
        return None
    return max(0.0, (task.completed_at - task.started_at).total_seconds())


async def _schedule_replay_task(task_id: str) -> None:
    async def _runner() -> None:
        try:
            await _run_replay_task(task_id)
        finally:
            replay_workers.pop(task_id, None)

    replay_workers[task_id] = asyncio.create_task(_runner())


async def _scan_news_window(source_stream: str, start: datetime, end: datetime, max_scan: int) -> tuple[int, list[dict]]:
    cursor = "-"
    scanned = 0
    matched: list[dict] = []

    while scanned < max_scan:
        batch = await redis_client.xrange(source_stream, min=cursor, max="+", count=min(500, max_scan - scanned))
        if not batch:
            break

        for item_id, fields in batch:
            scanned += 1
            raw_payload = fields.get("payload")
            if not raw_payload:
                continue

            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                continue

            published_at_raw = payload.get("published_at")
            if not published_at_raw:
                continue

            try:
                published_at = parse_event_time(str(published_at_raw))
            except ValueError:
                continue

            if in_window(published_at, start, end):
                matched.append(payload)

        last_id = batch[-1][0]
        ms, seq = last_id.split("-")
        cursor = f"{ms}-{int(seq) + 1}"

    return scanned, matched


async def _run_replay_task(task_id: str) -> None:
    task = await _load_replay_task(task_id)
    if task is None:
        return

    task.status = ReplayTaskStatus.RUNNING
    task.started_at = _now_utc()
    await _persist_replay_task(task)

    try:
        scanned, matched = await _scan_news_window(task.source_stream, task.start, task.end, task.max_scan)
        selected = matched[: task.max_publish]

        published = 0
        if not task.dry_run:
            for idx, payload in enumerate(selected, start=1):
                replay_payload = build_replay_payload(payload, task.replay_id, idx)
                await redis_client.xadd(task.target_stream, {"payload": json.dumps(replay_payload)})
                published += 1

        task.scanned = scanned
        task.matched = len(matched)
        task.published = published
        task.status = ReplayTaskStatus.COMPLETED
        task.completed_at = _now_utc()
    except asyncio.CancelledError:
        task.status = ReplayTaskStatus.CANCELED
        task.error = "Task canceled"
        task.completed_at = _now_utc()
        await _persist_replay_task(task)
        raise
    except Exception as exc:  # pragma: no cover - runtime IO
        task.status = ReplayTaskStatus.FAILED
        task.error = str(exc)
        task.completed_at = _now_utc()

    await _persist_replay_task(task)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await redis_client.aclose()


@app.get("/health")
async def health() -> dict:
    pong = await redis_client.ping()
    return {"status": "ok", "redis": bool(pong), "env": settings.env}


@app.post("/strategy/start")
async def strategy_start() -> dict:
    await redis_client.set("strategy:active", "1")
    return {"active": True}


@app.post("/strategy/stop")
async def strategy_stop() -> dict:
    await redis_client.set("strategy:active", "0")
    return {"active": False}


@app.post("/config/update")
async def config_update(req: ConfigUpdate) -> dict:
    if req.values:
        await redis_client.hset("runtime:config", mapping={k: str(v) for k, v in req.values.items()})
    values = await redis_client.hgetall("runtime:config")
    return {"updated": True, "values": values}


@app.get("/metrics/summary")
async def metrics_summary() -> dict:
    lengths = {}
    for stream in STREAMS:
        lengths[stream] = await redis_client.xlen(stream)
    return {
        "stream_lengths": lengths,
        "strategy_active": await redis_client.get("strategy:active") == "1",
    }


@app.post("/replay/news-window")
async def replay_news_window(req: ReplayWindowRequest) -> dict:
    if req.end < req.start:
        raise HTTPException(status_code=400, detail="end must be greater than or equal to start")

    task_id = uuid4().hex[:12]
    replay_id = uuid4().hex[:12]
    task = ReplayTask(
        task_id=task_id,
        replay_id=replay_id,
        status=ReplayTaskStatus.PENDING,
        submitted_at=_now_utc(),
        start=req.start,
        end=req.end,
        source_stream=req.source_stream,
        target_stream=req.target_stream,
        max_scan=req.max_scan,
        max_publish=req.max_publish,
        dry_run=req.dry_run,
    )
    await _persist_replay_task(task)
    await _trim_replay_tasks()

    if req.async_mode:
        await _schedule_replay_task(task_id)
        return {
            "accepted": True,
            "async_mode": True,
            "task_id": task_id,
            "replay_id": replay_id,
            "status": ReplayTaskStatus.PENDING,
        }

    await _run_replay_task(task_id)
    done = await _load_replay_task(task_id)
    if done is None:
        raise HTTPException(status_code=500, detail="replay task was not persisted")
    return {
        "accepted": True,
        "async_mode": False,
        "task": done.model_dump(mode="json"),
    }


@app.get("/replay/tasks/{task_id}")
async def get_replay_task(task_id: str) -> dict:
    task = await _load_replay_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.model_dump(mode="json")


@app.get("/replay/tasks")
async def list_replay_tasks(limit: int = Query(default=20, ge=1, le=200)) -> list[dict]:
    tasks = await _list_replay_tasks(limit)
    return [task.model_dump(mode="json") for task in tasks]


@app.post("/replay/tasks/{task_id}/cancel")
async def cancel_replay_task(task_id: str) -> dict:
    task = await _load_replay_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    if task.status not in {ReplayTaskStatus.PENDING, ReplayTaskStatus.RUNNING}:
        raise HTTPException(status_code=409, detail=f"task is not cancellable in status={task.status}")

    worker = replay_workers.get(task_id)
    if worker is not None and not worker.done():
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
    else:
        if task.status == ReplayTaskStatus.RUNNING:
            raise HTTPException(
                status_code=409,
                detail="task is marked running but no local worker exists (likely after restart); cannot cancel safely",
            )
        task.status = ReplayTaskStatus.CANCELED
        task.error = "Task canceled before worker start"
        task.completed_at = _now_utc()
        await _persist_replay_task(task)

    done = await _load_replay_task(task_id)
    return {"canceled": True, "task": done.model_dump(mode="json") if done else None}


@app.post("/replay/tasks/{task_id}/retry")
async def retry_replay_task(task_id: str, req: ReplayRetryRequest) -> dict:
    old = await _load_replay_task(task_id)
    if old is None:
        raise HTTPException(status_code=404, detail="task not found")
    if old.status in {ReplayTaskStatus.PENDING, ReplayTaskStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="task is still active; cancel or wait before retry")

    new_task_id = uuid4().hex[:12]
    replay_id = uuid4().hex[:12]
    task = ReplayTask(
        task_id=new_task_id,
        replay_id=replay_id,
        status=ReplayTaskStatus.PENDING,
        submitted_at=_now_utc(),
        start=old.start,
        end=old.end,
        source_stream=old.source_stream,
        target_stream=old.target_stream,
        max_scan=old.max_scan,
        max_publish=old.max_publish,
        dry_run=old.dry_run,
    )
    await _persist_replay_task(task)
    await _trim_replay_tasks()

    if req.async_mode:
        await _schedule_replay_task(new_task_id)
        return {
            "accepted": True,
            "async_mode": True,
            "task_id": new_task_id,
            "replay_id": replay_id,
            "status": ReplayTaskStatus.PENDING,
            "retry_of": task_id,
        }

    await _run_replay_task(new_task_id)
    done = await _load_replay_task(new_task_id)
    return {
        "accepted": True,
        "async_mode": False,
        "retry_of": task_id,
        "task": done.model_dump(mode="json") if done else None,
    }


@app.get("/replay/metrics")
async def replay_metrics(limit: int = Query(default=200, ge=1, le=1000)) -> dict:
    tasks = await _list_replay_tasks(limit)
    total = len(tasks)
    counts = {status.value: 0 for status in ReplayTaskStatus}
    durations: list[float] = []
    terminal = 0
    completed = 0

    for task in tasks:
        counts[task.status.value] = counts.get(task.status.value, 0) + 1
        duration = _task_duration_sec(task)
        if duration is not None:
            durations.append(duration)
        if task.status in {ReplayTaskStatus.COMPLETED, ReplayTaskStatus.FAILED, ReplayTaskStatus.CANCELED}:
            terminal += 1
        if task.status == ReplayTaskStatus.COMPLETED:
            completed += 1

    avg_duration = sum(durations) / len(durations) if durations else 0.0
    success_rate = (completed / terminal) if terminal else 0.0
    return {
        "sample_size": total,
        "counts": counts,
        "avg_duration_sec": avg_duration,
        "success_rate": success_rate,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)
