from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from common_types.models import ExecutionReport, OrderIntent

from .base import ExchangeAdapter

logger = logging.getLogger(__name__)


def _parse_status(status: str) -> str:
    normalized = status.lower()
    mapping = {
        "new": "new",
        "partially_filled": "partially_filled",
        "filled": "filled",
        "rejected": "rejected",
        "canceled": "canceled",
        "cancelled": "canceled",
        "expired": "canceled",
    }
    return mapping.get(normalized, "new")


class BinanceExchangeAdapter(ExchangeAdapter):
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        use_testnet: bool = True,
        recv_window_ms: int = 5000,
        timeout_sec: float = 10.0,
    ):
        if not api_key or not api_secret:
            raise RuntimeError("Binance API credentials are required for live execution mode.")

        self.api_key = api_key
        self.api_secret = api_secret
        self.recv_window_ms = recv_window_ms
        self.timeout_sec = timeout_sec
        self.use_testnet = use_testnet

        if use_testnet:
            self.spot_base_url = "https://testnet.binance.vision"
            self.perp_base_url = "https://testnet.binancefuture.com"
            self.spot_ws_base = "wss://testnet.binance.vision/ws"
            self.perp_ws_base = "wss://stream.binancefuture.com/ws"
        else:
            self.spot_base_url = "https://api.binance.com"
            self.perp_base_url = "https://fapi.binance.com"
            self.spot_ws_base = "wss://stream.binance.com:9443/ws"
            self.perp_ws_base = "wss://fstream.binance.com/ws"

        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            import httpx
        except ModuleNotFoundError as exc:
            raise RuntimeError("httpx is required for Binance live execution mode.") from exc

        self._client = httpx.AsyncClient(timeout=self.timeout_sec)
        return self._client

    @staticmethod
    def _timestamp_ms() -> int:
        return int(time.time() * 1000)

    def _signature(self, query: str) -> str:
        return hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()

    def _sign_params(self, params: dict[str, Any]) -> dict[str, Any]:
        signed = dict(params)
        signed["timestamp"] = self._timestamp_ms()
        signed["recvWindow"] = self.recv_window_ms
        query = urlencode(signed)
        signed["signature"] = self._signature(query)
        return signed

    async def _request(
        self,
        *,
        method: str,
        market: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = True,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        client = self._ensure_client()
        params = params or {}
        payload = self._sign_params(params) if signed else params

        base_url = self.spot_base_url if market == "spot" else self.perp_base_url
        url = f"{base_url}{path}"
        headers = {"X-MBX-APIKEY": self.api_key}

        response = await client.request(method, url, params=payload, headers=headers)
        response.raise_for_status()

        data = response.json()
        if isinstance(data, dict) and "code" in data and isinstance(data.get("code"), int) and data["code"] < 0:
            raise RuntimeError(f"Binance API error: {data}")
        return data

    async def _fetch_mark_price(self, symbol: str) -> float:
        client = self._ensure_client()
        url = f"{self.perp_base_url}/fapi/v1/ticker/price"
        resp = await client.get(url, params={"symbol": symbol})
        resp.raise_for_status()
        data = resp.json()
        return float(data["price"])

    async def _fetch_spot_price(self, symbol: str) -> float:
        client = self._ensure_client()
        url = f"{self.spot_base_url}/api/v3/ticker/price"
        resp = await client.get(url, params={"symbol": symbol})
        resp.raise_for_status()
        data = resp.json()
        return float(data.get("price", 0.0))

    async def place_order(self, intent: OrderIntent) -> ExecutionReport:
        side = "BUY" if intent.side > 0 else "SELL"
        client_order_id = intent.intent_id[:32]

        if intent.market == "spot":
            params = {
                "symbol": intent.symbol,
                "side": side,
                "type": "MARKET",
                "quoteOrderQty": f"{intent.qty_usd:.2f}",
                "newClientOrderId": client_order_id,
            }
            data = await self._request(method="POST", market="spot", path="/api/v3/order", params=params, signed=True)
            assert isinstance(data, dict)

            filled_qty = float(data.get("executedQty", 0.0))
            fills = data.get("fills", []) or []
            if fills:
                total_quote = sum(float(item.get("price", 0.0)) * float(item.get("qty", 0.0)) for item in fills)
                total_qty = sum(float(item.get("qty", 0.0)) for item in fills)
                avg_price = total_quote / total_qty if total_qty else 0.0
                fee = sum(float(item.get("commission", 0.0)) for item in fills)
            else:
                avg_price = float(data.get("cummulativeQuoteQty", 0.0)) / max(filled_qty, 1e-9)
                fee = 0.0

            order_id = f"spot:{intent.symbol}:{data.get('orderId')}"
            status = _parse_status(str(data.get("status", "new")))
        else:
            mark_price = await self._fetch_mark_price(intent.symbol)
            quantity = max(0.001, round(intent.qty_usd / max(mark_price, 1e-9), 3))
            params = {
                "symbol": intent.symbol,
                "side": side,
                "type": "MARKET",
                "quantity": f"{quantity:.3f}",
                "newClientOrderId": client_order_id,
            }
            data = await self._request(method="POST", market="perp", path="/fapi/v1/order", params=params, signed=True)
            assert isinstance(data, dict)

            filled_qty = float(data.get("executedQty", quantity))
            avg_price = float(data.get("avgPrice", 0.0)) or mark_price
            fee = 0.0
            order_id = f"perp:{intent.symbol}:{data.get('orderId')}"
            status = _parse_status(str(data.get("status", "new")))

        return ExecutionReport(
            order_id=order_id,
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            market=intent.market,
            side=intent.side,
            status=status,
            filled_qty=filled_qty,
            avg_price=avg_price,
            fee=fee,
            ts=datetime.now(timezone.utc),
        )

    async def cancel_order(self, order_id: str) -> bool:
        parts = order_id.split(":")
        if len(parts) != 3:
            raise ValueError("order_id must be in format 'market:symbol:exchange_order_id'")

        market, symbol, exchange_order_id = parts
        if market == "spot":
            await self._request(
                method="DELETE",
                market="spot",
                path="/api/v3/order",
                params={"symbol": symbol, "orderId": exchange_order_id},
                signed=True,
            )
            return True

        await self._request(
            method="DELETE",
            market="perp",
            path="/fapi/v1/order",
            params={"symbol": symbol, "orderId": exchange_order_id},
            signed=True,
        )
        return True

    async def fetch_positions(self) -> list[dict]:
        positions: list[dict] = []
        spot_price_cache: dict[str, float] = {}

        spot_account = await self._request(method="GET", market="spot", path="/api/v3/account", params={}, signed=True)
        assert isinstance(spot_account, dict)
        for bal in spot_account.get("balances", []):
            free = float(bal.get("free", 0.0))
            locked = float(bal.get("locked", 0.0))
            total = free + locked
            if total <= 0:
                continue
            asset = str(bal.get("asset", "")).upper()
            if asset in {"USDT", "BUSD", "USDC"}:
                continue
            symbol = f"{asset}USDT"
            if symbol not in spot_price_cache:
                try:
                    spot_price_cache[symbol] = await self._fetch_spot_price(symbol)
                except Exception:
                    spot_price_cache[symbol] = 0.0
            px = spot_price_cache[symbol]
            positions.append({"market": "spot", "symbol": symbol, "qty": total, "notional_usd": abs(total) * px})

        perp_positions = await self._request(method="GET", market="perp", path="/fapi/v2/positionRisk", params={}, signed=True)
        assert isinstance(perp_positions, list)
        for pos in perp_positions:
            qty = float(pos.get("positionAmt", 0.0))
            if qty == 0.0:
                continue
            positions.append(
                {
                    "market": "perp",
                    "symbol": pos.get("symbol"),
                    "qty": qty,
                    "notional_usd": abs(float(pos.get("notional", 0.0))),
                }
            )

        return positions

    async def _create_listen_key(self, market: str) -> str:
        path = "/api/v3/userDataStream" if market == "spot" else "/fapi/v1/listenKey"
        data = await self._request(method="POST", market=market, path=path, params={}, signed=False)
        assert isinstance(data, dict)
        listen_key = data.get("listenKey")
        if not listen_key:
            raise RuntimeError(f"Failed to create {market} listen key: {data}")
        return str(listen_key)

    def _parse_user_data_event(self, market: str, data: dict) -> dict | None:
        if market == "spot":
            if data.get("e") != "executionReport":
                return None
            filled_qty = float(data.get("z", 0.0) or 0.0)
            quote_filled = float(data.get("Z", 0.0) or 0.0)
            avg_price = quote_filled / filled_qty if filled_qty > 0 else 0.0
            ts_ms = int(data.get("E") or self._timestamp_ms())
            return {
                "order_id": f"spot:{data.get('s')}:{data.get('i')}",
                "intent_id": str(data.get("c", "")),
                "symbol": data.get("s"),
                "market": "spot",
                "side": 1 if data.get("S") == "BUY" else -1,
                "status": _parse_status(str(data.get("X", "new"))),
                "filled_qty": filled_qty,
                "avg_price": avg_price,
                "fee": 0.0,
                "ts": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
            }

        if data.get("e") != "ORDER_TRADE_UPDATE":
            return None
        order = data.get("o", {})
        filled_qty = float(order.get("z", 0.0) or 0.0)
        avg_price = float(order.get("ap", 0.0) or 0.0)
        ts_ms = int(data.get("E") or self._timestamp_ms())
        return {
            "order_id": f"perp:{order.get('s')}:{order.get('i')}",
            "intent_id": str(order.get("c", "")),
            "symbol": order.get("s"),
            "market": "perp",
            "side": 1 if order.get("S") == "BUY" else -1,
            "status": _parse_status(str(order.get("X", "new"))),
            "filled_qty": filled_qty,
            "avg_price": avg_price,
            "fee": 0.0,
            "ts": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
        }

    async def _build_alert(self, market: str, message: str, severity: str = "warning") -> dict:
        return {
            "event_type": "alert",
            "market": market,
            "severity": severity,
            "message": message,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    async def _keepalive_listen_key(self, market: str, listen_key: str) -> None:
        path = "/api/v3/userDataStream" if market == "spot" else "/fapi/v1/listenKey"
        while True:
            await asyncio.sleep(30 * 60)
            await self._request(method="PUT", market=market, path=path, params={"listenKey": listen_key}, signed=False)

    async def _consume_user_stream(self, market: str, queue: "asyncio.Queue[dict]") -> None:
        try:
            import websockets
        except ModuleNotFoundError as exc:
            raise RuntimeError("websockets package is required to stream Binance user data events") from exc

        base = self.spot_ws_base if market == "spot" else self.perp_ws_base

        while True:
            keepalive_task: asyncio.Task | None = None
            try:
                listen_key = await self._create_listen_key(market)
                keepalive_task = asyncio.create_task(self._keepalive_listen_key(market, listen_key))
                ws_url = f"{base}/{listen_key}"

                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20, close_timeout=5) as ws:
                    while True:
                        if keepalive_task.done():
                            exc = keepalive_task.exception()
                            msg = f"Binance {market} listenKey keepalive failed; reconnecting stream."
                            if exc is not None:
                                msg = f"{msg} error={exc}"
                            await queue.put(await self._build_alert(market, msg, severity="error"))
                            raise RuntimeError(msg)

                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=5)
                        except asyncio.TimeoutError:
                            continue

                        data = json.loads(message)
                        if data.get("e") == "listenKeyExpired":
                            msg = f"Binance {market} listenKey expired; reconnecting stream."
                            await queue.put(await self._build_alert(market, msg, severity="warning"))
                            raise RuntimeError(msg)

                        parsed = self._parse_user_data_event(market, data)
                        if parsed is not None:
                            parsed["event_type"] = "execution"
                            await queue.put(parsed)
            except Exception as exc:
                logger.warning("binance %s user stream loop error: %s", market, exc)
                await asyncio.sleep(2)
            finally:
                if keepalive_task is not None:
                    keepalive_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await keepalive_task

    async def stream_execution_events(self):
        queue: asyncio.Queue[dict] = asyncio.Queue()
        spot_task = asyncio.create_task(self._consume_user_stream("spot", queue))
        perp_task = asyncio.create_task(self._consume_user_stream("perp", queue))
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            for task in (spot_task, perp_task):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
