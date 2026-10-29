.PHONY: install probe test-print serve test lint

VENV := .venv/bin

install:
	python3 -m venv .venv
	$(VENV)/pip install --upgrade pip
	$(VENV)/pip install -e ".[dev]"

probe:
	$(VENV)/lp2443 probe

test-print:
	$(VENV)/lp2443 test-print

serve:
	$(VENV)/lp2443 serve

test:
	$(VENV)/pytest -v

lint:
	$(VENV)/ruff check src tests
