PYTHONPATH=libs/common-types/src:libs/exchange-adapters/src:libs/feature-store/src:.
PYTHON_BIN?=/Users/steven/.local/bin/python3.12
VENV=.venv
VPY=$(VENV)/bin/python

.PHONY: venv
venv:
	$(PYTHON_BIN) -m venv $(VENV)
	$(VPY) -m ensurepip --upgrade
	$(VPY) -m pip install --upgrade pip setuptools wheel

.PHONY: install
install: venv
	$(VPY) -m pip install -e ".[test]"

.PHONY: test
test:
	. $(VENV)/bin/activate && PYTHONPATH=$(PYTHONPATH) python -m pytest

.PHONY: uv-venv
uv-venv:
	UV_CACHE_DIR=/tmp/uv-cache uv venv --clear -p $(PYTHON_BIN) $(VENV)
	$(VPY) -m ensurepip --upgrade
	$(VPY) -m pip install --upgrade pip setuptools wheel

.PHONY: uv-install
uv-install: uv-venv
	$(VPY) -m pip install -e ".[test]"

.PHONY: uv-test
uv-test:
	. $(VENV)/bin/activate && PYTHONPATH=$(PYTHONPATH) python -m pytest

.PHONY: run-orchestrator
run-orchestrator:
	. $(VENV)/bin/activate && PYTHONPATH=$(PYTHONPATH) python services/orchestrator-api/app.py
