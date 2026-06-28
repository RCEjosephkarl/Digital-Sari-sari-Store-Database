# Digital Sari-Sari Store — Data Engineering, Analytics & ML

> *Bridging a decade of handwritten ledgers into a relational database — then a
> reproducible data platform for analytics and machine learning.*

---

## Abstract

This project digitizes a decade of handwritten records from a Filipino neighborhood
sari-sari (corner store) — pricing notebooks, delivery receipts, and an *utang*
(credit) ledger — into a reproducible, production-ready PostgreSQL database. It
demonstrates the full normalization journey from three flat, denormalized raw tables
(simulating direct notebook transcription) through First, Second, and Third Normal
Form, arriving at a 10-table 3NF schema housing ~676,767 rows of realistic,
specific-Filipino-brand synthetic data. A Python pipeline synthesizes the dataset,
bulk-loads it into PostgreSQL, and verifies structural integrity; the environment
is pre-wired for analytics and machine learning with pandas, scikit-learn, and
JupyterLab.

---

## Motivation

There is a particular kind of genius in a well-kept sari-sari store ledger.

For more than ten years, the *tindera* — the owner, the one who knows every
customer by their *palayaw* (nickname) — ran the entire business out of spiral
notebooks. One notebook for **presyo** (prices). One for **deliveries**. And the
most sacred of all: the **utang** notebook, where credit was extended one line
at a time — *"Aling Maria, 1 delata, 2 kilo bigas… 163."* A peso paid here,
fifty pesos there, the balance carried forward in a column of careful subtraction.

That notebook *worked*. But consider what happens the first time someone tries to
digitize it into a spreadsheet. They type each row exactly as it was written: the
customer's name, phone, and running balance alongside the items bought, all on one
line. The result is a `customer_balance` column that is hand-copied and static. The
moment Aling Maria makes a second purchase and someone forgets to update the earlier
rows, the ledger now contains two contradictory balances for the same customer — on
paper, the owner could see the full page; in a flat table, there is no such context.
Paper cannot be backed up, cannot answer *"which items are about to run out?"* at a
glance, and cannot guarantee that a stored balance is the correct one.

The owner wants to scale — and to **preserve the legacy**. The first task was not
an app; it was getting the **data model right**, because every query, every report,
and every machine-learning feature built later is only as honest as the schema
underneath it.

---

## Methodologies

### Normalization: 1NF → 2NF → 3NF

The `normalization/` directory contains a self-contained four-file SQL walkthrough
that starts where any honest digitization attempt starts — three messy flat tables —
and normalizes them step by step into the production schema.

```
normalization/
├── 00_raw.sql          # 3 tables + ~37 sample rows; every violation annotated
├── 01_1nf.sql          # Fix: add PKs, unnest repeating groups → 5 tables
├── 02_2nf.sql          # Fix: remove partial dependencies → 7 tables
└── 03_3nf_migrate.sql  # Fix: remove transitive deps, drop stored derivations → 10 tables + 2 views
```

All files operate in a `norm_demo` PostgreSQL schema so they run alongside the
production pipeline in the same database without conflict.

#### The raw starting point (3 tables)

The three raw tables simulate what a store owner produces when they type their
notebooks directly into a spreadsheet, column by column:

| Table | Violations illustrated |
|---|---|
| `raw_inventory` | No PK (Maggi appears twice); `alt_suppliers` packed into one semicolon-separated cell [1NF]; supplier contact info repeated per product [2NF]; `category_desc` depends on `category` not product [3NF]; `stock_count` goes stale [3NF] |
| `raw_sales_ledger` | No PK; `item1_/item2_/item3_` repeating groups hard-limit 3 items per sale [1NF]; `customer_balance` hand-written and stale across rows [3NF]; `total_amount` stored despite being a sum [3NF] |
| `raw_delivery_log` | No PK; supplier contact info repeated per delivery line [2NF]; `product_category/unit` depend on the product not the delivery [3NF]; `line_total` stored despite being qty × cost [3NF] |

#### 1NF — atomic values and row identity

Every column holds one atomic value; every row has a unique identifier.

- **`nf1_inventory`**: surrogate PK added; `alt_suppliers` split into a companion
  `nf1_product_alt_suppliers` table (one row per alternate supplier).
- **`nf1_sales_header` + `nf1_sales_items`**: the `item1_/item2_/item3_` repeating
  groups are unnested via `UNION ALL` into `nf1_sales_items` — 10 header rows
  become 10 headers + 24 item rows, zero NULLs, no column-count limit.
- **`nf1_delivery_log`**: PK added only (was already atomic).

**Table count: 3 → 5.**

#### 2NF — remove partial dependencies

No non-key attribute may depend on only *part* of the natural composite key.

- **`nf2_suppliers`** extracted from inventory: changing Nestlé's phone number is
  now 1 UPDATE instead of 7.
- **`nf2_customers`** extracted from sales: customer phone and nickname live in one
  row, referenced by FK.
- **`nf2_deliveries`** (header) + **`nf2_delivery_items`** (lines): the delivery
  header/line split formalizes what was implicit in the flat log.
- `nf2_products` and `nf2_sales` rebuilt to reference the new tables by FK.

**Table count: 5 → 7.**

#### 3NF — remove transitive dependencies and stored derivations

No non-key attribute may depend on another non-key attribute. Stored derived values
— balances, totals, stock counts — are the most common 3NF violation in accounting
ledgers.

- **`categories`** and **`units`** extracted from products: `category_desc` and
  `unit_label` are facts about their parent concept, not about the product.
- **`products`** rebuilt: 4 text columns (category, category_desc, unit_code,
  unit_label) → 2 FK columns; `stock_count` dropped entirely.
- **`customers`** rebuilt: `customer_balance` dropped — it was always one sale
  behind.
- **`credit_payments`** introduced as a first-class entity: in the raw notebook,
  payments existed only as adjustments to the balance; 3NF reveals they are a
  distinct fact (who paid, how much, when).
- **`transactions`** and **`transaction_items`**: `total_amount` dropped; product
  text reference replaced by `product_id` FK.
- **`restocks`** and **`restock_items`**: delivery tables renamed and `line_total`,
  `product_category`, `product_unit` dropped; product FK added.
- **`v_product_stock`** and **`v_customer_balances`** created as views: they
  replace every stored derived value with a computation that is always correct.

**Final: 10 tables + 2 views — structurally identical to `schema.sql`.**

---

### Pipeline Design

```
catalog.py ─► synthesize.py ─► data/csv/*.csv ─► loader.py ─► PostgreSQL ─► v_* views
 (brands)      (realism)        (materialized)     (COPY)       (3NF)        (analytics/ML)
```

#### Synthesis (`src/sarisari/synthesize.py`)

Deterministic (single seed) and *realistic*:

- **Store growth** — transaction volume rises ~7%/year (the store prospers).
- **Seasonality** — weekend, December, and payday (15th/30th) spikes; morning &
  evening rushes.
- **Bestsellers vs. slow movers** — product selection weighted by popularity.
- **Price inflation** — unit prices/costs deflate into the past (~4%/yr), so a 2013
  receipt is genuinely cheaper than a 2025 one.
- **An utang sub-economy** — ~22% of sales are credit; heavy-tailed loyal *suki*
  customers; partial repayments.
- **Built-in integrity** — restock quantities always cover units sold; payments never
  exceed charges. Grand total is forced to exactly 676,767.

#### Materialization to CSV

All ten tables are written to `data/csv/*.csv` (NULLs preserved for cash walk-ins
and unscanned tingi items). CSVs are gitignored — they regenerate identically from
the seed.

#### Bulk Load (`src/sarisari/loader.py`)

1. Apply `schema.sql` (drops & recreates → empty, correct schema).
2. In **one transaction**: disable stock triggers, `COPY` every CSV in FK-safe order,
   recompute `products.stock_on_hand` in a single set-based `UPDATE`, re-enable
   triggers, realign identity sequences.

Disabling per-row triggers during `COPY` turns ~428 k single-row updates into one
bulk update — the full load runs in ~14 seconds — while `v_product_stock` proves the
result is correct.

---

### Setup and Tools

#### Quick start

```bash
# 1. Create the reproducible environment (.venv) and install everything
make setup

# 2. (optional) configure — defaults work out of the box
cp .env.example .env

# 3. Run the whole pipeline:  synthesize → load → verify
make pipeline
```

**No PostgreSQL installed?** No problem. If `DATABASE_URL` is empty, the loader
spins up a self-contained local PostgreSQL via [`pgserver`](https://pypi.org/project/pgserver/)
under `./.pgdata` — zero Docker, zero `sudo` (ideal on WSL). To point at a real
server, set `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/sarisari
```

#### Repository layout

```
DE_SariSari_Store_Inventory/
├── schema.sql              # 3NF PostgreSQL DDL (tables, triggers, indexes, views)
├── database_erd.md         # Mermaid ER diagram
├── walkthrough.md          # Step-by-step guide to launch PostgreSQL and run pipeline
├── requirements.txt        # pinned dependencies (reproducible)
├── pyproject.toml          # `sarisari` package (src layout) + console scripts
├── Makefile                # setup / synth / load / verify / notebook / clean
├── .env.example            # configuration template (DB URL, target rows, seed)
│
├── normalization/          # ★ SQL normalization walkthrough (raw → 1NF → 2NF → 3NF)
│   ├── 00_raw.sql          #   3 denormalized tables + sample data + annotated violations
│   ├── 01_1nf.sql          #   First Normal Form transformation
│   ├── 02_2nf.sql          #   Second Normal Form transformation
│   └── 03_3nf_migrate.sql  #   Third Normal Form migration → final schema
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
├── data/csv/               # generated CSVs (gitignored)
├── notebooks/              # analytics & ML notebooks (latter phase)
└── models/                 # trained ML artifacts (gitignored)
```

#### Tools

| Layer | Tool | Rationale |
|---|---|---|
| Language | Python 3.10+ | Readable, widely available on WSL |
| Database | PostgreSQL 13+ | Full SQL, triggers, views, psycopg3 COPY |
| Zero-install DB | pgserver | Embeds real PostgreSQL, no `sudo`, great on WSL |
| Data synthesis | NumPy / Faker | Deterministic seeded generation |
| Analytics | pandas, JupyterLab | Standard ML stack, `read_sql` → `get_engine()` |
| ML | scikit-learn, seaborn | Ready but not yet implemented |

---

## Findings

### Schema Decisions

The guiding rule: **a fact lives in exactly one place.** That is the spirit of
Third Normal Form — and exactly what a stack of notebooks cannot guarantee.

#### Decision 0 — Normalize before building

Starting with the normalization walkthrough was not gold-plating. The anomalies
visible in `00_raw.sql` — Aling Maria's balance reading as 0.00 on consecutive credit
sales, Argentina Corned Beef's `stock_count` 12 units off, Maggi appearing as two
indistinguishable rows — are exactly the bugs that surface when a flat spreadsheet
is treated as an operational database. The ten-table schema is the direct answer
to each category of anomaly.

#### Decision 1 — "Utang" is a *running balance*, not a stored number

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

#### Decision 2 — "Restocks" use a header/line split (and remember their cost)

A delivery is two facts: the **event** (`restocks` — supplier, date, invoice) and
its **contents** (`restock_items` — product, qty, cost). The split removes the
repeating group, and `restock_items.unit_cost` is a **cost snapshot** so a decade
of margin history survives even as prices drift.

#### Decision 3 — Prices are snapshotted at the moment of sale

`products.current_price` is *today's* price; `transaction_items.unit_price` is the
price **as it was when sold**. The synthesizer deflates prices into the past (~4%/yr),
so a 2013 receipt is genuinely cheaper than a 2025 one — real time-series signal for
analytics.

#### Decision 4 — Stock-on-hand, kept *both* ways (on purpose)

Stock is *derivable*, but the POS needs an instant answer. We keep **both**: a
trigger-maintained `products.stock_on_hand` column for fast reads, and a strictly-derived
`v_product_stock` view that prints derived on-hand **next to** the maintained column
so drift is visible in one query.

> *Verified on the full 676,767-row load:* **0** mismatches between derived and
> maintained stock, and **0** products with negative stock.

#### Decision 5 — Delete rules that protect a decade of history

Header→line is `ON DELETE CASCADE`; every FK into `products` / `customers` /
`suppliers` / `categories` / `units` is `ON DELETE RESTRICT`. To retire an item,
flip `is_active = false` (soft delete) — history is the asset.

#### Decision 6 — Cash walk-ins vs. named credit customers

`transactions.customer_id` is **nullable** (NULL = cash walk-in); a `CHECK`
(`credit_requires_customer`) guarantees a credit sale must name a customer.

---

### Dataset Characteristics

"~676,767 rows" is the **grand total across all ten tables**. Spanning
**2011-01-01 → 2026-06-28**, the data is fully reproducible from a single seed.

| Table | Rows | Notes |
|---|---:|---|
| `categories` | 6 | The six product groups |
| `units` | 8 | pc, sachet, bottle, can, pack, kg, pouch, tetra |
| `suppliers` | 30 | Real PH distributors (San Miguel, URC, Nestlé, …) |
| `products` | 187 | **Specific Filipino brands** across the 6 groups |
| `customers` | 2,000 | Named *suki* with nicknames (*palayaw*) & credit limits |
| `restocks` | 6,000 | Inbound delivery headers |
| `restock_items` | 36,000 | Delivery lines (cost snapshot) |
| `transactions` | 180,000 | Sales headers (cash / credit) |
| `transaction_items` | 428,536 | Sales lines (price snapshot) — *balancing table* |
| `credit_payments` | 24,000 | Utang repayments |
| **TOTAL** | **676,767** | |

#### The six product groups & their brands

| Group | Example brands |
|---|---|
| **Meal Ingredients** | Datu Puti, Silver Swan, UFC, Knorr, Maggi, Ajinomoto, Baguio Oil, Mama Sita's |
| **Beverages** | Coca-Cola, Pepsi, Royal, Sprite, Nescafé, Kopiko, Great Taste, Milo, Bear Brand, Cobra, Sting |
| **Snacks** | Lucky Me, Piattos, Nova, Chippy, Oishi, Boy Bawang, Skyflakes, Rebisco, Cream-O, Cloud 9 |
| **Small Household Items** | Tide, Ariel, Surf, Joy, Downy, Safeguard, Sunsilk, Palmolive, Colgate, Close-Up |
| **Processed Meat** | Argentina, CDO, Purefoods (Tender Juicy), 555, Mega, Century Tuna, Spam, Maling |
| **Liquor** | San Miguel Pale Pilsen, Red Horse, Ginebra San Miguel, Tanduay, Emperador, Jinro |

---

### Data Integrity Verification

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

---

## Conclusion and Recommendations

### Building the API

- Wrap multi-line writes (sale = 1 header + N lines) in a single DB transaction;
  the stock triggers keep `stock_on_hand` correct automatically.
- **Read from the views, write to the tables** — never reimplement balance math.
- Enforce `credit_limit` at the service layer (`v_customer_balances.credit_available`).

### Preserving the Legacy — Cloud Backups

- Nightly `pg_dump` to versioned off-site object storage; WAL archiving for PITR;
  test restores regularly; keep a human-readable CSV export too.

### UI/UX for Someone Who Trusts a Notebook

- An utang screen that *looks like the ledger page*; fast tingi entry (search by
  *palayaw*); **offline-first** (brownouts happen); gentle reorder nudges;
  Filipino-first labels (*Utang, Bayad, Presyo*).

### Future Analytics and ML

The environment already includes **pandas, scikit-learn, matplotlib, seaborn and
JupyterLab** — ready to begin. Launch with `make notebook`.

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

Natural next analyses and models:

- **Demand forecasting** — daily/weekly sales per product (time series; the
  built-in seasonality & growth give real signal).
- **Reorder optimization** — combine `v_product_stock.needs_reorder` with forecasts.
- **Credit-risk scoring** — predict utang default/slow-payment from
  `v_customer_balances` + payment history.
- **Market-basket analysis** — association rules over `transaction_items`.
- **Customer segmentation (RFM)** — recency/frequency/monetary clustering of *suki*.

### Future Schema Extensions

- `price_history` table — record every price change with effective date.
- Payment-to-sale allocation (invoice aging) — link payments to specific transactions.
- Staff/auth & audit trail — `created_by` columns, change log table.
- Multi-store (`store_id`) — the same schema scales horizontally.

---

*— The ink is safe now.*
