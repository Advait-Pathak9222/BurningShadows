PYTHON ?= python

.PHONY: install data demo report sensitivity attention pii-probe judge-probe loadtest toxicchat api console mlflow-ui test lint typecheck check clean

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
	$(PYTHON) -m mypy controlplane

check: lint typecheck test

clean:
	$(PYTHON) -m controlplane.cli clean
