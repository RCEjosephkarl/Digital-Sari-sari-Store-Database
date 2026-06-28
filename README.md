# Digital Sari-Sari Store — Data Engineering, Analytics & ML

> *Bridging a decade of handwritten ledgers into a relational database — then a
> reproducible data platform for analytics and machine learning.*

A neighborhood **sari-sari** (Filipino corner store) has tracked a decade of
pricing, inventory, restocks, cash sales and **utang** (customer credit) in
handwritten notebooks. This repo digitizes that world into:

1. A **3NF PostgreSQL schema** ([`schema.sql`](./schema.sql)).
2. A **reproducible Python pipeline** that synthesizes **~676,767 rows** of
   realistic, *specific-Filipino-brand* data across six product groups, writes
   them to **CSV**, and bulk-loads them into PostgreSQL.
3. A foundation ready for **data analytics & ML** (the latter phase).

---

## Table of contents
- [Quickstart](#quickstart)
- [Project structure](#project-structure)
- [The dataset (~676,767 rows)](#the-dataset-676767-rows)
- [Prologue: The Decade of Ink and Paper](#prologue-the-decade-of-ink-and-paper)
- [Architecture Decisions: The Path to 3NF](#architecture-decisions-the-path-to-3nf)
- [The Schema Overview](#the-schema-overview)
- [The Data Engineering Pipeline](#the-data-engineering-pipeline)
- [Analytics & ML Roadmap](#analytics--ml-roadmap)
- [Conclusion & Future Recommendations](#conclusion--future-recommendations)
- [Appendix — verifying it yourself](#appendix--verifying-it-yourself)

---

## Quickstart

```bash
# 1. Create the reproducible environment (.venv) and install everything
make setup
#    └─ equivalent to:
#       python3 -m venv .venv
#       ./.venv/bin/pip install -r requirements.txt
#       ./.venv/bin/pip install -e . --no-deps

# 2. (optional) configure — defaults work out of the box
cp .env.example .env

# 3. Run the whole pipeline:  synthesize → load → verify
make pipeline
#    └─ make synth   : ~676,767 rows  →  data/csv/*.csv
#       make load    : create schema  +  COPY all CSVs into PostgreSQL
#       make verify  : row counts + stock/utang sanity checks
```

**No PostgreSQL installed?** No problem. If `DATABASE_URL` is empty, the loader
spins up a self-contained local PostgreSQL via [`pgserver`](https://pypi.org/project/pgserver/)
under `./.pgdata` — zero Docker, zero `sudo` (ideal on WSL). To point at a real
server (Docker / cloud) for dashboards, set `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/sarisari
```

---

## Project structure

```
DE_SariSari_Store_Inventory/
├── schema.sql              # 3NF PostgreSQL DDL (tables, triggers, indexes, views)
├── database_erd.md         # Mermaid ER diagram
├── requirements.txt        # pinned dependencies (reproducible)
├── pyproject.toml          # `sarisari` package (src layout) + console scripts
├── Makefile                # setup / synth / load / verify / notebook / clean
├── .env.example            # configuration template (DB URL, target rows, seed)
│
├── src/sarisari/           # the installable package
│   ├── config.py           #   env-driven settings & paths
│   ├── catalog.py          #   ★ Filipino-brand catalog: 6 groups, ~187 SKUs
│   ├── synthesize.py       #   ★ generates the ~676,767-row dataset → CSV
│   ├── db.py               #   PostgreSQL connection (DATABASE_URL or pgserver)
│   ├── loader.py           #   schema + fast COPY load + stock recompute
│   └── cli.py              #   synthesize / load / verify entry points
│
├── scripts/                # thin runnable wrappers around cli.py
│   ├── synthesize_data.py
│   ├── load_to_postgres.py
│   └── verify_db.py
│
├── data/csv/               # generated CSVs (gitignored)
├── notebooks/              # analytics & ML notebooks (latter phase)
└── models/                 # trained ML artifacts (gitignored)
```

---

## The dataset (~676,767 rows)

"~676,767 rows" is interpreted as the **grand total across all ten tables**.
The line-item table (`transaction_items`) absorbs the remainder so the total is
**exact**. Spanning **2011-01-01 → 2026-06-28**, the data is fully reproducible
from a single seed.

| Table               |     Rows | Notes                                                   |
|---------------------|---------:|---------------------------------------------------------|
| `categories`        |        6 | The six product groups                                  |
| `units`             |        8 | pc, sachet, bottle, can, pack, kg, pouch, tetra         |
| `suppliers`         |       30 | Real PH distributors (San Miguel, URC, Nestlé, …)       |
| `products`          |      187 | **Specific Filipino brands** across the 6 groups        |
| `customers`         |    2,000 | Named *suki* with nicknames (*palayaw*) & credit limits |
| `restocks`          |    6,000 | Inbound delivery headers                                |
| `restock_items`     |   36,000 | Delivery lines (cost snapshot)                          |
| `transactions`      |  180,000 | Sales headers (cash / credit)                           |
| `transaction_items` |  428,536 | Sales lines (price snapshot) — *balancing table*        |
| `credit_payments`   |   24,000 | Utang repayments                                        |
| **TOTAL**           | **676,767** |                                                      |

### The six product groups & their brands

Every product is a recognizable Philippine brand (see [`catalog.py`](./src/sarisari/catalog.py)):

| Group | Example brands |
|-------|----------------|
| **Meal Ingredients** | Datu Puti, Silver Swan, UFC, Knorr, Maggi, Ajinomoto, Baguio Oil, Mama Sita's |
| **Beverages** | Coca-Cola, Pepsi, Royal, Sprite, Nescafé, Kopiko, Great Taste, Milo, Bear Brand, Cobra, Sting |
| **Snacks** | Lucky Me, Piattos, Nova, Chippy, Oishi, Boy Bawang, Skyflakes, Rebisco, Cream-O, Cloud 9 |
| **Small Household Items** | Tide, Ariel, Surf, Joy, Downy, Safeguard, Sunsilk, Palmolive, Colgate, Close-Up |
| **Processed Meat** | Argentina, CDO, Purefoods (Tender Juicy), 555, Mega, Century Tuna, Spam, Maling |
| **Liquor** | San Miguel Pale Pilsen, Red Horse, Ginebra San Miguel, Tanduay, Emperador, Jinro |

---

## Prologue: The Decade of Ink and Paper

There is a particular kind of genius in a well-kept sari-sari store ledger.

For more than ten years, the *tindera* — the owner, the one who knows every
customer by their *palayaw* (nickname) — ran the entire business out of spiral
notebooks. One notebook for **presyo** (prices). One for **deliveries**. And the
most sacred of all: the **utang** notebook, where credit was extended one line
at a time — *"Aling Maria, 1 delata, 2 kilo bigas… 163."* A peso paid here, fifty
pesos there, the balance carried forward in a column of careful subtraction.

That notebook *worked*. But paper cannot be backed up, cannot answer *"which
items are about to run out?"* at a glance, and cannot total what you're owed
across every customer. The owner wants to scale — and to **preserve the legacy**.
The first task wasn't an app; it was getting the **data model** right, because
every feature built later is only as honest as the schema underneath it.

---

## Architecture Decisions: The Path to 3NF

The guiding rule: **a fact lives in exactly one place.** That is the spirit of
Third Normal Form — and exactly what a stack of notebooks cannot guarantee. We
isolated three classes of anomaly: **no repeating groups**, **no partial
dependencies**, **no transitive dependencies**. The result is ten tables.

### Decision 1 — "Utang" is a *running balance*, not a stored number

A stored `balance` column is a deletion/update anomaly waiting to happen. Instead
the balance is **computed**, never stored:

- A **charge** is simply a sale (`transactions`) with `payment_type = 'credit'`;
  its amount already lives, once, in `transaction_items`. No duplication.
- A **payment** is a row in `credit_payments`, applied to the customer's overall
  balance (how the store really works — *"si Aling Maria, bayad 100"*).

```
balance(customer) = SUM(credit-sale line totals) − SUM(credit_payments)
```

Two views serve it: **`v_customer_balances`** (per-customer totals + remaining
credit headroom) and **`v_utang_ledger`** (the *digital page of the notebook* —
every charge & payment on one timeline with a **running balance**).

### Decision 2 — "Restocks" use a header/line split (and remember their cost)

A delivery is two facts: the **event** (`restocks` — supplier, date, invoice) and
its **contents** (`restock_items` — product, qty, cost). The split removes the
repeating group, and `restock_items.unit_cost` is a **cost snapshot** so a decade
of margin history survives even as prices drift.

### Decision 3 — Prices are snapshotted at the moment of sale

`products.current_price` is *today's* price; `transaction_items.unit_price` is the
price **as it was when sold**. The synthesizer even deflates prices into the past
(~4%/yr), so a 2013 receipt is genuinely cheaper than a 2025 one — real
time-series signal for analytics.

### Decision 4 — Stock-on-hand, kept *both* ways (on purpose)

Stock is *derivable*, but the POS needs an instant answer. We keep **both**: a
trigger-maintained `products.stock_on_hand` column, and a strictly-derived
`v_product_stock` view that prints derived on-hand **next to** the maintained
column so drift is visible in one query.

> *Verified on the full 676,767-row load:* **0** mismatches between derived and
> maintained stock, and **0** products with negative stock.

### Decision 5 — Delete rules that protect a decade of history

Header→line is `ON DELETE CASCADE`; every FK into `products` / `customers` /
`suppliers` / `categories` / `units` is `ON DELETE RESTRICT`. To retire an item,
flip `is_active = false` (soft delete) — history is the asset.

### Decision 6 — Cash walk-ins vs. named credit customers

`transactions.customer_id` is **nullable** (NULL = cash walk-in); a `CHECK`
(`credit_requires_customer`) guarantees a credit sale must name a customer.

---

## The Schema Overview

Ten tables, three views, three layers. (See [`database_erd.md`](./database_erd.md).)

**Lookup:** `categories`, `units` · **Master:** `suppliers`, `products`,
`customers` · **Activity:** `restocks`/`restock_items`,
`transactions`/`transaction_items`, `credit_payments`.

**Views:** `v_product_stock` (stock + reorder flag), `v_customer_balances`
(utang per customer), `v_utang_ledger` (running-balance timeline).

`schema.sql` is **DDL-only** — the dataset is produced by the Python pipeline
below and bulk-loaded, rather than hand-seeded inline.

---

## The Data Engineering Pipeline

```
catalog.py ─► synthesize.py ─► data/csv/*.csv ─► loader.py ─► PostgreSQL ─► v_* views
 (brands)      (realism)        (materialized)     (COPY)       (3NF)        (analytics/ML)
```

### 1. Synthesis (`src/sarisari/synthesize.py`)

Deterministic (single seed) and *realistic*:

- **Store growth** — transaction volume rises ~7%/year (the store prospers).
- **Seasonality** — weekend, December, and payday (15th/30th) spikes; morning &
  evening rushes.
- **Bestsellers vs. slow movers** — product selection weighted by popularity.
- **Price inflation** — unit prices/costs deflate into the past.
- **An utang sub-economy** — ~22% of sales are credit; a heavy-tailed set of loyal
  *suki* customers; partial repayments.
- **Built-in integrity** — restock quantities always **cover** units sold (no
  negative stock); payments never exceed charges (no negative balances). The
  grand total is forced to **exactly 676,767**.

### 2. Materialization to CSV

All ten tables are written to `data/csv/*.csv` (NULLs preserved for cash
walk-ins and unscanned tingi items) for inspection, sharing, or loading
elsewhere. CSVs are gitignored — they regenerate identically from the seed.

### 3. Bulk load into PostgreSQL (`src/sarisari/loader.py`)

The standard high-throughput DE pattern:

1. Apply `schema.sql` (drops & recreates → empty, correct schema).
2. In **one transaction**: **disable** the stock triggers, `COPY` every CSV in
   FK-safe order, recompute `products.stock_on_hand` in a **single set-based
   UPDATE**, **re-enable** the triggers, and realign identity sequences.

Disabling per-row triggers during `COPY` turns ~428k single-row updates into one
bulk update — the full load runs in seconds — while `v_product_stock` still
*proves* the result is correct.

### Reproducibility

`requirements.txt` pins every dependency; `.env` controls the seed, target row
count, date range, and DB target. Same seed ⇒ byte-identical dataset.

---

## Analytics & ML Roadmap

The environment already includes **pandas, scikit-learn, matplotlib, seaborn and
JupyterLab** — the "latter part" is ready to begin. Launch with `make notebook`.

Read straight from the warehouse into pandas:

```python
import pandas as pd
from sarisari.db import get_engine

engine = get_engine()
sales = pd.read_sql("""
    SELECT t.transaction_date::date AS day, c.name AS category,
           SUM(ti.quantity * ti.unit_price) AS revenue
    FROM transaction_items ti
    JOIN transactions t  ON t.transaction_id = ti.transaction_id
    JOIN products p      ON p.product_id     = ti.product_id
    JOIN categories c    ON c.category_id    = p.category_id
    GROUP BY 1, 2 ORDER BY 1
""", engine)
```

Natural next analyses / models:

- **Demand forecasting** — daily/weekly sales per product (time series; the
  built-in seasonality & growth give real signal).
- **Reorder optimization** — combine `v_product_stock.needs_reorder` with forecasts.
- **Credit-risk scoring** — predict utang default/slow-payment from
  `v_customer_balances` + payment history.
- **Market-basket analysis** — association rules over `transaction_items`.
- **Customer segmentation (RFM)** — recency/frequency/monetary clustering of *suki*.

---

## Conclusion & Future Recommendations

### Building the API
- Wrap multi-line writes (sale = 1 header + N lines) in a single DB transaction;
  the stock triggers keep `stock_on_hand` correct automatically.
- **Read from the views, write to the tables** — never reimplement balance math.
- Enforce `credit_limit` at the service layer (`v_customer_balances.credit_available`).

### Preserving the legacy — cloud backups
- Nightly `pg_dump` to versioned off-site object storage; WAL archiving for PITR;
  test restores regularly; keep a human-readable CSV export too.

### UI/UX for someone who trusts a notebook
- An utang screen that *looks like the ledger page*; fast tingi entry (search by
  *palayaw*); **offline-first** (brownouts happen); gentle reorder nudges;
  Filipino-first labels (*Utang, Bayad, Presyo*).

### Future extensions
- `price_history` table · payment-to-sale allocation (invoice aging) · staff/auth
  & audit trail · multi-store (`store_id`).

---

## Appendix — verifying it yourself

This pipeline was run end-to-end against a real PostgreSQL engine:

```text
$ make pipeline
  ... synthesize ...            TOTAL  676,767   (data/csv/*.csv)
  ... load ...                  TOTAL  676,767   (loaded in ~14s)
  ... verify ...
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

Ad-hoc checks once loaded:

```sql
SELECT * FROM v_product_stock     ORDER BY needs_reorder DESC LIMIT 20;
SELECT * FROM v_customer_balances ORDER BY balance DESC      LIMIT 20;
SELECT * FROM v_utang_ledger      WHERE customer_id = 1;
```

*— The ink is safe now.*
