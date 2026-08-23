PYTHON ?= python

.PHONY: install data demo report judge-probe loadtest api console mlflow-ui test lint typecheck check clean

install:
	$(PYTHON) -m pip install -e ".[dev]"

data:
	$(PYTHON) -m controlplane.cli data

demo: data
	$(PYTHON) -m controlplane.cli demo

report: data
	$(PYTHON) -m controlplane.cli report

judge-probe:
	$(PYTHON) -m controlplane.cli judge-probe

loadtest:
	$(PYTHON) -m controlplane.cli loadtest

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
