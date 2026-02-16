PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:.

.PHONY: test

test:
	PYTHONPATH=$(PYTHONPATH) python3 -m pytest

.PHONY: run-orchestrator
run-orchestrator:
	PYTHONPATH=$(PYTHONPATH) python services/orchestrator-api/app.py
