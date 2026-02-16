# Crypto News Trading

面向 Binance Global 的事件驱动数字货币量化交易系统（首期以仿真盘优先）。

## 架构概览

核心事件流：

1. `news.raw`
2. `news.entity`
3. `signal.raw`
4. `signal.tradeable`
5. `signal.universe`
6. `order.intent`
7. `order.approved` / `order.rejected`
8. `execution.report`
9. `pnl.snapshot`

共享库：

- `libs/common-types`：事件模型、流名称、配置、事件总线抽象。
- `libs/exchange-adapters`：交易所适配器接口与仿真实现。
- `libs/feature-store`：去重与风险/PnL 状态存储。

服务列表：

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

## 快速开始

1. 复制环境变量模板：

```bash
cp .env.example .env
```

2. 创建虚拟环境并安装依赖（推荐）：

```bash
make uv-install
```

3. 启动基础设施：

```bash
docker compose -f infra/docker-compose.yml up -d redis postgres
```

4. 运行服务（示例）：

```bash
source .venv/bin/activate
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python services/entity-service/main.py
```

5. 运行测试：

```bash
make uv-test
```

6. 运行本地内存模式演示：

```bash
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. \
python3 scripts/demo_pipeline.py
```

### 使用 UV 虚拟环境运行

仓库已支持 `uv` 创建和使用虚拟环境（Python 3.12）：

```bash
make uv-install
source .venv/bin/activate
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python -m pytest -q
```

也可以直接：

```bash
make uv-test
```

如果你不使用 `uv`，也可以执行：

```bash
make install
```

## 运行与配置（部署指南）

### 1）启动方式

#### 方式 A：Docker Compose（推荐）

1. 准备配置文件：

```bash
cp .env.example .env
```

2. 启动全套服务（包含 Redis、Postgres 和全部业务服务）：

```bash
docker compose -f infra/docker-compose.yml up -d
```

3. 查看服务状态：

```bash
docker compose -f infra/docker-compose.yml ps
```

4. 停止服务：

```bash
docker compose -f infra/docker-compose.yml down
```

#### 方式 B：本地 Python 多进程运行（开发调试）

1. 安装依赖：

```bash
python3 -m pip install -e .
```

2. 启动基础设施：

```bash
docker compose -f infra/docker-compose.yml up -d redis postgres
```

3. 在多个终端分别启动服务（示例）：

```bash
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/ingest-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/entity-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/llm-signal-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/signal-fusion-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/universe-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/portfolio-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/risk-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/execution-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/position-pnl-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/position-sync-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/persistence-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/monitoring-alert-service/main.py
PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:. python3 services/orchestrator-api/app.py
```

4. 健康检查：

```bash
curl http://localhost:8080/health
curl http://localhost:8080/metrics/summary
```

### 2）配置参数说明（`.env`）

执行 `cp .env.example .env` 后按需修改。以下为完整参数清单：

#### 基础运行参数（建议保持默认）

- `ENV`：运行环境标识，例如 `dev`。
- `LOG_LEVEL`：日志级别，默认 `INFO`。
- `REDIS_URL`：Redis 连接地址。
- `POSTGRES_DSN`：PostgreSQL 连接串。
- `BUS_BACKEND`：事件总线后端，`redis` 或 `memory`。

#### LLM 与通知

- `OPENAI_API_KEY`：LLM API Key（默认按 Qwen 兼容 OpenAI 接口接入）。为空时，LLM 服务自动降级为规则启发式分析。
- `OPENAI_MODEL`：模型名，默认 `qwen-plus`。
- `OPENAI_BASE_URL`：兼容 OpenAI 的网关地址，默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- `TELEGRAM_BOT_TOKEN`：Telegram 机器人 Token（可选）。
- `TELEGRAM_CHAT_ID`：Telegram 接收频道/用户 ID（可选）。

#### Binance 交易接入

- `EXECUTION_MODE`：`paper`（仿真，默认）或 `live`（实盘/测试网）。
- `BINANCE_API_KEY`：`live` 模式必填。
- `BINANCE_API_SECRET`：`live` 模式必填。
- `BINANCE_USE_TESTNET`：`true/false`，`live` 模式是否使用测试网。
- `BINANCE_RECV_WINDOW_MS`：Binance 请求参数 `recvWindow`。

#### 策略与风控

- `ACCOUNT_EQUITY_USD`：账户权益基准（用于风险比例换算）。
- `RISK_PER_TRADE_PCT`：单笔风险比例。
- `MAX_SYMBOL_EXPOSURE_PCT`：单币最大暴露比例。
- `MAX_TOTAL_EXPOSURE_PCT`：总暴露上限比例。
- `MAX_SPOT_EXPOSURE_PCT`：现货总暴露上限比例。
- `MAX_PERP_EXPOSURE_PCT`：合约总暴露上限比例。
- `MAX_LONG_EXPOSURE_PCT`：多头暴露上限比例。
- `MAX_SHORT_EXPOSURE_PCT`：空头暴露上限比例。
- `MAX_DAILY_DRAWDOWN_PCT`：日内回撤阈值（触发停机）。
- `MIN_SIGNAL_CONFIDENCE`：最小信号置信度阈值。
- `DEFAULT_EVENT_TTL_SEC`：事件/信号默认生存时间（秒）。
- `MAX_SLIPPAGE_BPS`：下单允许最大滑点（基点）。
- `UNIVERSE_SYMBOLS`：可交易标的池（逗号分隔）。

#### 持仓同步

- `POSITION_SYNC_INTERVAL_SEC`：持仓同步周期（秒）。
- `POSITION_SYNC_DRIFT_ALERT_PCT`：风险状态漂移告警阈值（相对 `ACCOUNT_EQUITY_USD`）。

### 3）推荐最小配置组合

#### 仅跑通仿真闭环（最快）

- 必填：`REDIS_URL`、`POSTGRES_DSN`。
- 建议：保持 `EXECUTION_MODE=paper`。
- 可空：`OPENAI_API_KEY`、`TELEGRAM_*`、`BINANCE_*`。

#### 测试网/实盘运行

- 必填：`EXECUTION_MODE=live` + `BINANCE_API_KEY` + `BINANCE_API_SECRET`。
- 建议：先使用 `BINANCE_USE_TESTNET=true`，稳定后再切换生产网。

## Replay API

`POST /replay/news-window` 支持按时间窗口重放新闻事件。

示例：

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

查询任务状态：

```bash
curl http://localhost:8080/replay/tasks/<task_id>
curl http://localhost:8080/replay/tasks
curl http://localhost:8080/replay/metrics
```

取消/重试任务：

```bash
curl -X POST http://localhost:8080/replay/tasks/<task_id>/cancel
curl -X POST http://localhost:8080/replay/tasks/<task_id>/retry \
  -H 'Content-Type: application/json' \
  -d '{"async_mode": true}'
```

Replay 任务元数据会持久化到 Redis，因此 orchestrator 进程重启后仍可查询任务状态。

## 风控说明

除单币/总暴露外，系统还支持按市场与方向维度限仓：

- `MAX_SPOT_EXPOSURE_PCT`
- `MAX_PERP_EXPOSURE_PCT`
- `MAX_LONG_EXPOSURE_PCT`
- `MAX_SHORT_EXPOSURE_PCT`

## 备注

- 默认执行适配器为 `paper` 仿真模式，不触发真实资金风险。
- `live` 模式可接 Binance；默认 `BINANCE_USE_TESTNET=true` 使用测试网。
- `live` 模式下，`execution-service` 会消费 Binance 现货/合约用户数据 WebSocket 事件。
- listenKey 续期失败或过期会触发自动重连，并发布 `risk.alert` 事件。
- `position-sync-service` 会把交易所持仓纠偏回本地风控状态（symbol/market/side/total exposures）。
- `OPENAI_API_KEY` 可选；为空时 `llm-signal-service` 自动降级为启发式规则分析。
- 默认模型为 Qwen（`OPENAI_MODEL=qwen-plus`），如需切回 OpenAI 可改 `OPENAI_BASE_URL` 与 `OPENAI_MODEL`。
- 风控参数均可通过 `.env` 调整。
