import asyncio

from feature_store import MemoryTradingStateStore


def test_memory_state_replace_snapshot_clears_old_values():
    state = MemoryTradingStateStore()

    asyncio.run(state.add_symbol_exposure("BTCUSDT", 1000))
    asyncio.run(state.add_market_exposure("spot", 1000))
    asyncio.run(state.add_side_exposure(1, 1000))
    asyncio.run(state.add_total_exposure(1000))

    asyncio.run(
        state.replace_exposure_snapshot(
            symbol_exposure={"ETHUSDT": 500},
            market_exposure={"perp": 500},
            side_exposure={"short": 500, "long": 0},
            total_exposure=500,
        )
    )

    assert asyncio.run(state.get_symbol_exposure("BTCUSDT")) == 0.0
    assert asyncio.run(state.get_symbol_exposure("ETHUSDT")) == 500
    assert asyncio.run(state.get_market_exposure("spot")) == 0.0
    assert asyncio.run(state.get_market_exposure("perp")) == 500
    assert asyncio.run(state.get_side_exposure(1)) == 0.0
    assert asyncio.run(state.get_side_exposure(-1)) == 500
    assert asyncio.run(state.get_total_exposure()) == 500
