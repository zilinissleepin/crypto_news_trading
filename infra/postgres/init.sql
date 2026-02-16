CREATE TABLE IF NOT EXISTS news_events (
  event_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  lang TEXT NOT NULL,
  url TEXT,
  dedup_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS execution_reports (
  order_id TEXT PRIMARY KEY,
  intent_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  side INTEGER NOT NULL,
  filled_qty DOUBLE PRECISION NOT NULL,
  avg_price DOUBLE PRECISION NOT NULL,
  fee DOUBLE PRECISION NOT NULL,
  status TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS execution_report_events (
  id BIGSERIAL PRIMARY KEY,
  order_id TEXT NOT NULL,
  intent_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  side INTEGER NOT NULL,
  status TEXT NOT NULL,
  filled_qty DOUBLE PRECISION NOT NULL,
  avg_price DOUBLE PRECISION NOT NULL,
  fee DOUBLE PRECISION NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(order_id, status, filled_qty, avg_price, fee, ts)
);

CREATE INDEX IF NOT EXISTS idx_execution_report_events_order_ts
  ON execution_report_events(order_id, ts DESC);

CREATE TABLE IF NOT EXISTS order_intents (
  intent_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  market TEXT NOT NULL,
  side INTEGER NOT NULL,
  qty_usd DOUBLE PRECISION NOT NULL,
  max_slippage_bps INTEGER NOT NULL,
  reason TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS risk_decisions (
  intent_id TEXT PRIMARY KEY,
  allow BOOLEAN NOT NULL,
  reason_code TEXT NOT NULL,
  capped_qty_usd DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pnl_snapshots (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  account TEXT NOT NULL,
  unrealized DOUBLE PRECISION NOT NULL,
  realized DOUBLE PRECISION NOT NULL,
  exposure DOUBLE PRECISION NOT NULL,
  drawdown DOUBLE PRECISION NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
