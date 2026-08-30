PYTHON ?= python

.PHONY: install data demo report sensitivity attention relearn pii-probe judge-probe loadtest toxicchat benchmarks api console mlflow-ui test lint typecheck check clean

install:
	$(PYTHON) -m pip install -e ".[dev]"

data:
	$(PYTHON) -m controlplane.cli data

demo: data
	$(PYTHON) -m controlplane.cli demo

report: data
	$(PYTHON) -m controlplane.cli report

sensitivity:
	$(PYTHON) -m controlplane.cli sensitivity

attention:
	$(PYTHON) -m controlplane.cli attention

# Refit the calibration maps from reviewer labels in the audit chain, and refuse to
# release one that is thinner, more degenerate or worse calibrated than what serves now.
# Needs `make report` first, which is what writes reviews into the chain.
relearn:
	$(PYTHON) -m controlplane.cli relearn

pii-probe:
	$(PYTHON) -m controlplane.cli pii-probe

judge-probe:
	$(PYTHON) -m controlplane.cli judge-probe

loadtest:
	$(PYTHON) -m controlplane.cli loadtest

# Real-traffic evaluation. Downloads ToxicChat on first run (~16MB) and caches it
# under data/external/. Never on the demo path: `make demo` stays fully offline.
toxicchat:
	$(PYTHON) -m controlplane.cli toxicchat

# Aegis (Pre-registration 9) and OR-Bench (Pre-registration 10). Downloads on first run.
benchmarks:
	$(PYTHON) -m controlplane.cli benchmarks

api:
	$(PYTHON) -m uvicorn controlplane.gateway.app:app --host 127.0.0.1 --port 8000

console: report
	$(PYTHON) -m streamlit run console/streamlit_app.py

mlflow-ui:
	$(PYTHON) -m mlflow ui --backend-store-uri ./mlruns

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check controlplane tests console

typecheck:
	$(PYTHON) -m mypy --strict controlplane

check: lint typecheck test

clean:
	$(PYTHON) -m controlplane.cli clean
