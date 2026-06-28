# =============================================================================
#  Digital Sari-Sari Store — developer task runner
# =============================================================================
# Usage:  make <target>
#
#   make setup      create .venv and install everything (DE + ML stack)
#   make synth      synthesize ~676,767 rows -> data/csv/*.csv
#   make load       create the PostgreSQL schema and bulk-load the CSVs
#   make verify     print row counts + stock/utang sanity checks
#   make pipeline   synth + load + verify
#   make notebook   launch JupyterLab for analytics / ML
#   make clean      remove generated CSVs and the local pgserver data dir
# =============================================================================

VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.PHONY: setup synth load verify pipeline notebook clean clean-csv

setup:
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

clean-csv:
	rm -rf data/csv/*.csv

clean: clean-csv
	rm -rf .pgdata
	@echo "Removed generated CSVs and local pgserver data."
