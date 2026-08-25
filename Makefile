PYTHON ?= python

.PHONY: install data demo report sensitivity attention pii-probe judge-probe loadtest slo-sweep chaos replay api console mlflow-ui test lint typecheck check clean

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

# Runtime lane targets. Placed here so the runtime lane never has to edit this file:
# two agents appending rules to one Makefile is a merge conflict waiting to happen.
slo-sweep:
	$(PYTHON) -m controlplane.cli slo-sweep

chaos:
	$(PYTHON) -m controlplane.cli chaos

replay:
	$(PYTHON) -m controlplane.cli replay

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
