# Walkthrough: Launching the Sari-Sari Store Database

This guide takes you from a fresh clone to a running PostgreSQL database with
676,767 rows of synthesized Filipino store data, shows the **three ways to
explore it** — raw SQL, the JupyterLab notebook, and the Streamlit dashboard
(Section 6) — and walks through the normalization that shows how the schema was
designed.

---

## 1. Prerequisites

**Required:**
- **Python 3.10 or newer** — check with `python3 --version`
- **git** — check with `git --version`

**Optional (PostgreSQL):**
You do not need to install PostgreSQL globally. The project includes a
zero-install embedded option via `pgserver` that manages its own PostgreSQL
process under `.pgdata/`. If you have an existing PostgreSQL server (local,
Docker, or cloud) you can point the pipeline at it instead.

**WSL2 note:** All three connection options below work on WSL2. The `pgserver`
option (Option A) is the recommended choice because it avoids WSL networking
complexity entirely.

---

## 2. Clone and Environment Setup

```bash
git clone https://github.com/RCEjosephkarl/DE_SariSari_Store_Inventory.git
cd DE_SariSari_Store_Inventory
```

Create the environment and install all dependencies (pins exact versions for
reproducibility). `make setup` builds the `.venv` for you — it auto-detects
[uv](https://docs.astral.sh/uv/) for a 10–100× faster install and falls back to
`python3 -m venv` + `pip` when uv isn't installed:

```bash
make setup
```

Then activate the environment:

```bash
# Linux / macOS / WSL
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

**Prefer uv explicitly?** Install it once (`curl -LsSf https://astral.sh/uv/install.sh | sh`,
or `pip install uv`), and `make setup` will use it automatically. The equivalent
manual commands are:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
uv pip install --python .venv/bin/python -e . --no-deps
```

If `make` is unavailable (Windows without Git Bash), run the pip path directly:

```bash
python -m venv .venv
pip install -r requirements.txt
pip install -e . --no-deps
```

---

## 3. Configuration

```bash
cp .env.example .env
```

Open `.env` in any editor. The defaults work out of the box (Option A below).
Here is what each variable controls:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(empty)* | PostgreSQL connection string. Empty = use pgserver automatically. |
| `PGDATA_DIR` | `.pgdata` | Where pgserver stores its PostgreSQL cluster. |
| `SARISARI_TARGET_ROWS` | `676767` | Total rows across all 10 tables. Reduce to `50000` for faster dev runs. |
| `SARISARI_SEED` | `20110628` | Master random seed. Same seed → byte-identical dataset. |
| `SARISARI_START_DATE` | `2011-01-01` | Start of the store's business history window. |
| `SARISARI_END_DATE` | `2026-06-28` | End of the business history window. |
| `SARISARI_CSV_DIR` | `data/csv` | Where synthesized CSVs are written. |

---

## 4. Three Ways to Connect to PostgreSQL

### Option A: pgserver (recommended — zero install, great for WSL)

Leave `DATABASE_URL` empty in `.env`. The loader detects this and automatically
starts a self-contained PostgreSQL process under `.pgdata/`. First run initializes
the cluster (~20 s); subsequent runs reuse it (~2 s).

`pgserver` bundles actual PostgreSQL binaries — it is not a mock or emulator. You
can connect to it with `psql` or any GUI tool:

```bash
# Get the connection URL for external tools (psql, DBeaver, etc.)
python3 -c "
from sarisari.db import _libpq_url
from sarisari.config import settings
print(_libpq_url(settings))
"
# Prints something like: postgresql://postgres@/tmp/pgserver-xxx/sarisari
```

No `.env` change needed. Run `make pipeline` and the cluster starts automatically.

---

### Option B: Docker

Start a PostgreSQL container:

```bash
docker run -d --name sarisari-pg \
  -e POSTGRES_USER=sarisari \
  -e POSTGRES_PASSWORD=sarisari \
  -e POSTGRES_DB=sarisari \
  -p 5432:5432 \
  postgres:16
```

Set `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgresql+psycopg://sarisari:sarisari@localhost:5432/sarisari
```

**WSL caveat:** if your Docker runs on Windows and WSL cannot reach `localhost:5432`,
replace `localhost` with `host.docker.internal` or the Docker bridge IP
(`172.17.0.1`).

---

### Option C: Cloud PostgreSQL (Supabase, Neon, Render, AWS RDS)

Obtain the connection string from your provider's dashboard. It typically looks like:

```
postgresql+psycopg://user:password@host:5432/dbname?sslmode=require
```

Set it as `DATABASE_URL` in `.env`. The `?sslmode=require` suffix is mandatory for
Supabase and Neon.

The `get_engine()` function in `src/sarisari/db.py` works identically for all three
options — analytics notebooks do not need to change connection code.

---

## 5. Running the Full Pipeline

### All at once

```bash
make pipeline
```

### Step by step (useful for understanding each phase)

```bash
# Phase 1: synthesize ~676,767 rows to data/csv/*.csv  (~25–35 s)
make synth

# Phase 2: apply schema.sql + COPY all CSVs into PostgreSQL  (~10–20 s)
make load

# Phase 3: print row counts + integrity checks
make verify
```

### Expected output

```text
─── Synthesize ───────────────────────────────────────
categories             6
units                  8
suppliers             30
products             187
customers          2,000
restocks           6,000
restock_items     36,000
transactions     180,000
transaction_items 428,536
credit_payments   24,000
TOTAL            676,767   data/csv/*.csv written

─── Load ─────────────────────────────────────────────
Applying schema … done
Loading CSVs (COPY) … done
Recomputing stock … done
TOTAL  676,767   loaded in ~14 s

─── Verify ───────────────────────────────────────────
Stock reconcile — derived vs maintained mismatches: 0
Products with negative stock: 0
Customers with negative balance: 0
Total outstanding utang: PHP 1,611,821.34

Top product groups by units sold:
  Snacks                 169,689 units   PHP 1,680,996.75
  Beverages              169,336 units   PHP 2,385,797.25
  Meal Ingredients       165,002 units   PHP 4,651,160.25
  Small Household Items  163,203 units   PHP 2,265,104.50
  Processed Meat         152,210 units   PHP 5,605,234.75
```

The verify step specifically confirms the 3NF integrity guarantees: stock computed
from scratch via `v_product_stock` must equal the trigger-maintained
`products.stock_on_hand`, and no customer balance is negative.

---

## 6. Exploring the Project — Three Endpoints

Once `make pipeline` has loaded the warehouse, there are **three ways to look at
the same data**, from most raw to most visual. They all read from the identical
PostgreSQL database — pick whichever fits what you want to do.

| # | Endpoint | Best for | Launch |
|---|---|---|---|
| 1 | **Database (SQL)** | Ad-hoc queries, learning the schema, full control | `psql "$DB_URL"` |
| 2 | **JupyterLab notebook** | Step-by-step analysis you can edit and re-run | `make notebook` |
| 3 | **Streamlit dashboard** | Click-and-filter reports, no code needed | `make dashboard` |

> All three are **read-only** views over the same tables and views — nothing you
> do in the notebook or dashboard changes the data. The notebook and dashboard
> share one query layer (`src/sarisari/reporting.py`), so they always agree.

---

### 6.1 · Endpoint 1 — The Database (SQL via `psql`)

The lowest-level view: query PostgreSQL directly. Get your connection URL
(see Section 4), then:

```bash
# Option A (pgserver):
DB_URL=$(python3 -c "from sarisari.db import _libpq_url; from sarisari.config import settings; print(_libpq_url(settings))")

# Options B or C:
DB_URL="postgresql+psycopg://sarisari:sarisari@localhost:5432/sarisari"

psql "$DB_URL"
```

Useful queries:

```sql
-- Products close to running out
SELECT product, category, on_hand, reorder_level
FROM v_product_stock
WHERE needs_reorder
ORDER BY on_hand ASC
LIMIT 10;

-- Top customers by outstanding utang
SELECT full_name, nickname, balance, credit_available
FROM v_customer_balances
ORDER BY balance DESC
LIMIT 10;

-- Aling Maria's full utang ledger (replace 1 with her actual customer_id)
SELECT entry_date, entry_type, debit, credit, running_balance
FROM v_utang_ledger
WHERE customer_id = 1
ORDER BY entry_date;

-- Daily revenue for the last 30 days
SELECT t.transaction_date::date AS day,
       SUM(ti.quantity * ti.unit_price) AS revenue
FROM transaction_items ti
JOIN transactions t ON t.transaction_id = ti.transaction_id
GROUP BY 1
ORDER BY 1 DESC
LIMIT 30;

-- Revenue by product group (all time)
SELECT c.name AS category,
       SUM(ti.quantity)                    AS units_sold,
       SUM(ti.quantity * ti.unit_price)    AS revenue
FROM transaction_items ti
JOIN products p    ON p.product_id    = ti.product_id
JOIN categories c  ON c.category_id  = p.category_id
GROUP BY c.name
ORDER BY revenue DESC;
```

---

### 6.2 · Endpoint 2 — JupyterLab Notebook

```bash
make notebook
# Opens JupyterLab in your browser at http://localhost:8888
```

In the JupyterLab **file browser** (left panel), open
**`notebooks/01_reporting_dashboard.ipynb`**. This notebook queries the live
database and renders the project's three reports with inline Plotly charts:

1. **Sales** — revenue / units / baskets over time, by product group and by brand.
2. **Customers** — utang (credit) balances, payments, and a per-customer ledger.
3. **Stock** — on-hand levels, reorder flags and inventory value.

**How to use it (beginner steps):**

1. From the menu, choose **Run → Run All Cells** (or step through with
   <kbd>Shift</kbd>+<kbd>Enter</kbd> from the top).
2. Find the cell titled **"1 · Filters"** near the top and edit the variables —
   every chart below reacts to them:
   ```python
   START      = lo               # or e.g. date(2020, 1, 1)
   END        = hi
   CATEGORIES = ["Liquor"]       # one or more of the 6 groups; [] = all
   BRANDS     = ["Tanduay"]      # specific brands; [] = all
   FREQ       = "Monthly"        # Daily | Weekly | Monthly | Quarterly | Yearly
   ```
3. Re-run the cells below to refresh the charts with your new slice.

You can also write your own query in any empty cell:

```python
import pandas as pd
from sarisari.db import get_engine

engine = get_engine()
df = pd.read_sql("SELECT * FROM v_customer_balances ORDER BY balance DESC", engine)
df.head(10)
```

Stop the notebook server with <kbd>Ctrl</kbd>+<kbd>C</kbd> in the terminal.

---

### 6.3 · Endpoint 3 — Streamlit Dashboard

```bash
make dashboard
# Opens the dashboard in your browser at http://localhost:8501
```

The most beginner-friendly view — a point-and-click web app, **no code required**.
If a browser tab does not open automatically, copy the **Local URL** Streamlit
prints in the terminal (usually `http://localhost:8501`) into your browser.

**Sidebar (left) — global filters** that apply to every chart:

- **Time range** — a quick preset (All time / Last 12 months / Year to date / …)
  or a custom date picker.
- **Granularity** — how the time charts are bucketed (Daily → Yearly).
- **Product group** — restrict to one or more of the 6 groups.
- **Brand** — restrict to specific Filipino brands (the list narrows to whatever
  groups you picked).

**Three tabs (top) — one per report:**

- **📈 Sales** — headline KPIs, a revenue trend you can switch to units or
  transactions, revenue by group, the cash-vs-credit split, and the top brands
  and products.
- **👥 Customers** — total outstanding utang and the top debtors; open the
  **🔍 Single customer** sub-tab to pick a customer and see their running-balance
  ledger and recent transactions.
- **📦 Stock** — inventory value by group, the lowest-stock items, and a full
  stock table with optional *reorder-only* and *derived-vs-maintained drift*
  toggles.

Most tables have a **⬇️ Download CSV** button. Stop the dashboard with
<kbd>Ctrl</kbd>+<kbd>C</kbd> in the terminal.

> **WSL tip:** if `http://localhost:8501` will not load from a Windows browser,
> try the **Network URL** Streamlit prints, or `http://127.0.0.1:8501`.

---

## 7. Normalization Walkthrough

The `normalization/` directory contains four SQL files that show the full
journey from denormalized raw tables to the production schema:

```
normalization/00_raw.sql         ← 3 flat tables with annotated violations
normalization/01_1nf.sql         ← First Normal Form
normalization/02_2nf.sql         ← Second Normal Form
normalization/03_3nf_migrate.sql ← Third Normal Form (final schema)
```

All files use a `norm_demo` schema so they run in the same database as the
production pipeline without any conflict.

### Running the walkthrough

```bash
# Get your connection URL
DB_URL=$(python3 -c "from sarisari.db import _libpq_url; from sarisari.config import settings; print(_libpq_url(settings))")

psql "$DB_URL" -f normalization/00_raw.sql
psql "$DB_URL" -f normalization/01_1nf.sql
psql "$DB_URL" -f normalization/02_2nf.sql
psql "$DB_URL" -f normalization/03_3nf_migrate.sql
```

### Verifying the walkthrough

```sql
-- List all tables in the norm_demo schema
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'norm_demo'
ORDER BY table_name;
-- Expected: 10 tables + the nf1_/nf2_ intermediate tables

-- Check that v_customer_balances computes correct balances
-- (compare to the stale values hard-coded in 00_raw.sql)
SELECT full_name, nickname, total_utang, total_paid, balance
FROM norm_demo.v_customer_balances
ORDER BY balance DESC;
-- Expected:
--   Ate Linda    226.00  (raw notebook said 0.00 twice)
--   Mang Jose     99.00  (raw notebook said 0.00 twice)
--   Aling Maria  106.00  (raw notebook said 0.00, then 50.00 — both wrong)

-- Compare norm_demo.products to public.products (should be structurally identical)
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'norm_demo' AND table_name = 'products'
ORDER BY ordinal_position;
```

---

## 8. Troubleshooting

### "Port 5432 already in use"

- **Option A (pgserver):** No issue — pgserver uses a Unix socket under `.pgdata/`,
  not port 5432. You can always use it alongside a running PostgreSQL service.
- **Option B (Docker):** Check `lsof -i :5432` to find the process holding the port.
  Either stop it or map Docker to a different port:
  ```bash
  docker run -d -p 5433:5432 ... postgres:16
  # Then set DATABASE_URL=postgresql+psycopg://sarisari:sarisari@localhost:5433/sarisari
  ```

### "Connection refused" on WSL

- **Option A:** Use the URL printed by the Python snippet in Section 4 — not
  `localhost:5432`. pgserver's socket is inside WSL and does not bind to a TCP port
  by default.
- **Option B (Docker on Windows):** Replace `localhost` with `host.docker.internal`
  or `$(hostname).local`.

### "Permission denied" on `.pgdata/`

PostgreSQL requires the data directory to be owned exclusively by the current user
(mode 0700):

```bash
chmod 700 .pgdata/
```

On WSL, if `.pgdata/` was created from the Windows side, the permissions may be
wrong. Delete it and let pgserver reinitialize:

```bash
rm -rf .pgdata/
make load  # pgserver creates a fresh cluster
```

### "Missing CSV: data/csv/categories.csv"

The synthesizer must run before the loader:

```bash
make synth   # generates data/csv/*.csv
make load    # then loads them
# Or: make pipeline  (runs both in sequence)
```

### Slow first run (30–60 s)

pgserver initializes a fresh PostgreSQL cluster on the first call to `make load`.
Subsequent runs in the same directory reuse the cluster and start in ~2 s. The
`.pgdata/` directory persists between sessions.

### Python version error (pyarrow / numpy)

`pyarrow` requires Python 3.10+. Check your version:

```bash
python3 --version
```

On Ubuntu 20.04 (common in WSL), upgrade via the deadsnakes PPA:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt install python3.11 python3.11-venv
python3.11 -m venv .venv
source .venv/bin/activate
make setup
```

### "`make setup` fails: python3 not found" (Windows without WSL)

Replace `python3` with `python` in the Makefile, or run the pip commands directly:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e . --no-deps
```

---

*See `README.md` for the full technical journal: motivation, schema design decisions,
dataset characteristics, and analytics/ML roadmap.*
