PYTHON ?= python

.PHONY: install data demo report api console test lint typecheck check clean

install:
	$(PYTHON) -m pip install -e ".[dev]"

data:
	$(PYTHON) -m controlplane.cli data

demo: data
	$(PYTHON) -m controlplane.cli demo

report: data
	$(PYTHON) -m controlplane.cli report

api:
	$(PYTHON) -m uvicorn controlplane.gateway.app:app --host 127.0.0.1 --port 8000

console: report
	$(PYTHON) -m streamlit run console/streamlit_app.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check controlplane tests console

typecheck:
	$(PYTHON) -m mypy controlplane

check: lint typecheck test

clean:
	$(PYTHON) -m controlplane.cli clean
