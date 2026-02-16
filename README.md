# Crypto News Trading

Event-driven, modular crypto trading system targeting Binance Global with paper trading first.

## Architecture

Pipeline:

1. `news.raw`
2. `news.entity`
3. `signal.raw`
4. `signal.tradeable`
5. `signal.universe`
6. `order.intent`
7. `order.approved` / `order.rejected`
8. `execution.report`
9. `pnl.snapshot`

Shared libraries:

- `libs/common-types`: event models, stream names, config, event bus abstraction.
- `libs/exchange-adapters`: exchange adapter interface + simulated adapter.
- `libs/feature-store`: dedup and risk/pnl state stores.

Services:

- `services/ingest-service`
- `services/entity-service`
- `services/llm-signal-service`
- `services/signal-fusion-service`
- `services/universe-service`
- `services/portfolio-service`
- `services/risk-service`
- `services/execution-service`
- `services/position-pnl-service`
- `services/position-sync-service`
- `services/persistence-service`
- `services/orchestrator-api`
- `services/monitoring-alert-service`

## Quick Start

1. Copy env template:

```bash
cp .env.example .env
```

2. Install dependencies:

```bash
python3 -m pip install -e .
```

3. Start infra:

```bash
docker compose -f infra/docker-compose.yml up -d redis postgres
```

4. Run services (one terminal each):

```bash
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. \
python3 services/entity-service/main.py
```

5. Run tests:

```bash
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 -m pytest
```

6. Run a local in-memory demo:

```bash
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. \
python3 scripts/demo_pipeline.py
```

## Replay API

`POST /replay/news-window` now supports actual republish from a time window.

Example:

```bash
curl -X POST http://localhost:8080/replay/news-window \
  -H 'Content-Type: application/json' \
  -d '{
    "start": "2026-02-15T00:00:00Z",
    "end": "2026-02-15T23:59:59Z",
    "source_stream": "news.raw",
    "target_stream": "news.raw",
    "max_scan": 5000,
    "max_publish": 500,
    "dry_run": false,
    "async_mode": true
  }'
```

Query task status:

```bash
curl http://localhost:8080/replay/tasks/<task_id>
curl http://localhost:8080/replay/tasks
curl http://localhost:8080/replay/metrics
```

Cancel / retry task:

```bash
curl -X POST http://localhost:8080/replay/tasks/<task_id>/cancel
curl -X POST http://localhost:8080/replay/tasks/<task_id>/retry \
  -H 'Content-Type: application/json' \
  -d '{"async_mode": true}'
```

Replay task metadata is persisted in Redis, so task query survives orchestrator process restarts.

## Risk controls

In addition to symbol/total exposure, risk now supports market/side buckets:

- `MAX_SPOT_EXPOSURE_PCT`
- `MAX_PERP_EXPOSURE_PCT`
- `MAX_LONG_EXPOSURE_PCT`
- `MAX_SHORT_EXPOSURE_PCT`

## Notes

- Default execution adapter is simulated (`paper`) to avoid live capital risk.
- Live Binance mode is available via `EXECUTION_MODE=live`; by default it uses testnet when `BINANCE_USE_TESTNET=true`.
- In live mode, `execution-service` consumes Binance user-data WebSocket streams for spot/perp execution updates.
- Listen key keepalive failures and expirations now trigger reconnect plus `risk.alert` events.
- `position-sync-service` reconciles exchange positions back into risk state (symbol/market/side/total exposures).
- OpenAI is optional. Without API key, `llm-signal-service` falls back to heuristic NLP.
- Risk defaults are conservative and configurable via env vars.
