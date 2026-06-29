# =============================================================================
#  Digital Sari-Sari Store — developer task runner
# =============================================================================
# Usage:  make <target>
#
#   make setup      create .venv and install everything (DE + ML stack)
#                   (uses uv automatically if installed — much faster; else pip)
#   make synth      synthesize ~676,767 rows -> data/csv/*.csv
#   make load       create the PostgreSQL schema and bulk-load the CSVs
#   make verify     print row counts + stock/utang sanity checks
#   make pipeline   synth + load + verify
#   make notebook   launch JupyterLab for analytics / ML
#   make dashboard  launch the Streamlit reporting dashboard
#   make clean      remove generated CSVs and the local pgserver data dir
# =============================================================================

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

# Prefer uv (10-100x faster resolver/installer) when it is on PATH; else fall
# back to the stock python3 venv + pip. Both paths read the same requirements.txt
# and produce an identical .venv, so `make setup` "just works" either way.
UV := $(shell command -v uv 2>/dev/null)

.PHONY: setup setup-uv setup-pip synth load verify pipeline notebook dashboard clean clean-csv

setup:
ifeq ($(UV),)
	@$(MAKE) setup-pip
else
	@$(MAKE) setup-uv
endif

setup-uv:
	@echo ">> uv detected -> fast setup"
	uv venv --clear $(VENV)
	uv pip install --python $(PY) -r requirements.txt
	uv pip install --python $(PY) -e . --no-deps
	@echo "Done. Copy .env.example to .env and adjust if needed."

setup-pip:
	@echo ">> uv not found -> pip setup (install uv for a much faster setup)"
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	$(PIP) install -e . --no-deps
	@echo "Done. Copy .env.example to .env and adjust if needed."

synth:
	$(PY) scripts/synthesize_data.py

load:
	$(PY) scripts/load_to_postgres.py

verify:
	$(PY) scripts/verify_db.py

pipeline: synth load verify

notebook:
	$(VENV)/bin/jupyter lab

dashboard:
	$(VENV)/bin/streamlit run dashboard/app.py

clean-csv:
	rm -rf data/csv/*.csv

clean: clean-csv
	rm -rf .pgdata
	@echo "Removed generated CSVs and local pgserver data."
