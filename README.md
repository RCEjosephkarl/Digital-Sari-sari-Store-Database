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
notebooks directly into a spreadsheet, column by column.

**`raw_inventory` — 15 rows (the *presyo* notebook)**

| product_name | category | selling_price | stock_count | supplier_name | supplier_phone | alt_suppliers |
|---|---|---|---|---|---|---|
| Nescafé 3-in-1 Original 20g | Beverages | 8.00 | 175 | Nestlé Philippines Dealer | 09221330003 | NULL |
| Milo 24g | Beverages | 9.00 | 143 | **Nestlé Philippines Dealer** | **09221330003** | NULL |
| Maggi Magic Sarap 8g | Meal Ingredients | 5.00 | 210 | Nestlé Philippines Dealer | 09221330003 | Divisoria Wholesale Center |
| **Maggi Magic Sarap 8g** | Meal Ingredients | **4.50** | 210 | **Divisoria Wholesale Center** | 09331440004 | NULL |
| Lucky Me Pancit Canton 80g | Snacks | 14.00 | 189 | Monde Nissin Distributor | 09441550005 | **Monde Nissin Distributor;Suy Sing Commercial Corporation** |

Violations: Maggi appears **twice** with no primary key to distinguish the rows; `supplier_phone` copies identically across every Nestlé product row (2NF); `alt_suppliers` packs two supplier names into one semicolon-delimited cell (1NF); `stock_count` for Argentina Corned Beef reads 99 in the notebook but the actual tally is 87 (3NF).

**`raw_sales_ledger` — 10 rows (the *utang* notebook)**

| sale_date | customer_name | customer_balance | payment_type | item1_name | item2_name | item3_name | total_amount |
|---|---|---|---|---|---|---|---|
| 2025-01-15 | Aling Maria | **0.00** | credit | Coca-Cola Mismo 300ml | Datu Puti Soy Sauce 385ml | NULL | 71.00 |
| 2025-01-15 | Aling Maria | **0.00** | credit | Maggi Magic Sarap 8g | NULL | NULL | 15.00 |
| 2025-01-17 | Mang Jose | 0.00 | credit | Lucky Me Pancit Canton 80g | 555 Sardines Tomato 155g | **Milo 24g** | 76.00 |
| 2025-01-18 | Aling Maria | **50.00** | credit | Tide Powder Detergent 66g | NULL | NULL | 20.00 |

Violations: Aling Maria's `customer_balance` is 0.00 on two consecutive credit rows, then jumps to 50.00 by the third — the notebook was updated between customers but earlier rows were never corrected (3NF). Mang Jose's sale hits all three item columns, maxing out the hard cap baked into the schema (1NF). `total_amount` can always be derived from quantities × prices, yet it is stored alongside those values (3NF).

**`raw_delivery_log` — 12 rows (delivery receipts)**

| reference_no | supplier_name | supplier_phone | product_name | product_category | qty_received | unit_cost | line_total |
|---|---|---|---|---|---|---|---|
| DR-2025-001 | Coca-Cola FEMSA Route Agent | 09171110001 | Coca-Cola Mismo 300ml | Beverages | 120 | 16.00 | **1920.00** |
| DR-2025-001 | **Coca-Cola FEMSA Route Agent** | **09171110001** | Sprite Mismo 300ml | **Beverages** | 96 | 14.50 | **1392.00** |
| DR-2025-002 | Nestlé Philippines Dealer | 09221330003 | Nescafé 3-in-1 Original 20g | **Beverages** | 200 | 6.00 | **1200.00** |
| DR-2025-002 | **Nestlé Philippines Dealer** | **09221330003** | Milo 24g | **Beverages** | 180 | 7.00 | **1260.00** |

Violations: a single delivery (DR-2025-001) repeats Coca-Cola FEMSA's full contact block on every product line (2NF); `product_category` is a fact about the product, not this delivery, and would need to be copied every time the product is restocked (3NF); `line_total` equals `qty_received × unit_cost` and is stored redundantly (3NF).

**Violations at a glance**

| Table | Violations illustrated |
|---|---|
| `raw_inventory` | No PK (Maggi appears twice); `alt_suppliers` packed into one semicolon-separated cell [1NF]; supplier contact info repeated per product [2NF]; `category_desc` depends on `category` not product [3NF]; `stock_count` goes stale [3NF] |
| `raw_sales_ledger` | No PK; `item1_/item2_/item3_` repeating groups hard-limit 3 items per sale [1NF]; `customer_balance` hand-written and stale across rows [3NF]; `total_amount` stored despite being a sum [3NF] |
| `raw_delivery_log` | No PK; supplier contact info repeated per delivery line [2NF]; `product_category/unit` depend on the product not the delivery [3NF]; `line_total` stored despite being qty × cost [3NF] |

```mermaid
erDiagram
    raw_inventory {
        TEXT product_name "NO PK — duplicates silently accepted"
        TEXT category
        TEXT category_desc "3NF — depends on category, not product"
        TEXT unit_label "3NF — depends on unit_code, not product"
        NUMERIC selling_price
        INT stock_count "3NF — hand-calculated, goes stale"
        TEXT supplier_name "2NF — repeats on every product row"
        TEXT supplier_phone "2NF — repeats on every product row"
        TEXT alt_suppliers "1NF — semicolon-packed multi-value cell"
    }
    raw_sales_ledger {
        DATE sale_date "NO PK"
        TEXT customer_name
        TEXT customer_phone "3NF — depends on customer, not the sale"
        NUMERIC customer_balance "3NF — derived running total, goes stale"
        TEXT item1_name "1NF — repeating group position 1"
        TEXT item2_name "1NF — repeating group position 2"
        TEXT item3_name "1NF — repeating group position 3 (hard cap)"
        NUMERIC total_amount "3NF — derived sum, stored anyway"
    }
    raw_delivery_log {
        TEXT reference_no "NO PK"
        TEXT supplier_name "2NF — repeats per product line"
        TEXT supplier_phone "2NF — repeats per product line"
        TEXT product_name
        TEXT product_category "3NF — depends on product, not delivery"
        TEXT product_unit "3NF — depends on product, not delivery"
        NUMERIC line_total "3NF — derived (qty × cost)"
    }
```

#### 1NF — atomic values and row identity

Every column holds one atomic value; every row has a unique identifier.

- **`nf1_inventory`**: surrogate PK added; `alt_suppliers` split into a companion
  `nf1_product_alt_suppliers` table (one row per alternate supplier).
- **`nf1_sales_header` + `nf1_sales_items`**: the `item1_/item2_/item3_` repeating
  groups are unnested via `UNION ALL` into `nf1_sales_items` — 10 header rows
  become 10 headers + 24 item rows, zero NULLs, no column-count limit.
- **`nf1_delivery_log`**: PK added only (was already atomic).

**Table count: 3 → 5.**

```mermaid
erDiagram
    nf1_inventory {
        INT product_id PK
        TEXT product_name
        TEXT category "still transitive on category_desc — 3NF to fix"
        TEXT supplier_name "still repeats per product — 2NF to fix"
        NUMERIC selling_price
        INT stock_count "still stale — 3NF to fix"
    }
    nf1_product_alt_suppliers {
        INT product_id FK
        TEXT alt_supplier_name "atomic — 1NF fixed"
    }
    nf1_sales_header {
        INT sale_id PK
        DATE sale_date
        TEXT customer_name "still partial dep on phone/nickname — 2NF to fix"
        NUMERIC customer_balance "still stored derived — 3NF to fix"
        TEXT payment_type
        NUMERIC total_amount "still stored derived — 3NF to fix"
    }
    nf1_sales_items {
        INT item_id PK
        INT sale_id FK
        TEXT product_name
        INT qty
        NUMERIC unit_price
    }
    nf1_delivery_log {
        INT delivery_item_id PK
        DATE delivery_date
        TEXT reference_no
        TEXT supplier_name "still repeats per line — 2NF to fix"
        TEXT product_name
        TEXT product_category "still transitive — 3NF to fix"
        NUMERIC line_total "still stored derived — 3NF to fix"
    }

    nf1_inventory ||--o{ nf1_product_alt_suppliers : "alt suppliers"
    nf1_sales_header ||--o{ nf1_sales_items : "contains"
```

**What was solved?**

- Every row now has a unique identifier — surrogate PKs added to all three tables.
- `alt_suppliers`, the semicolon-packed multi-value cell, is gone; each alternate supplier becomes its own row in `nf1_product_alt_suppliers` (one row per value, zero hacks).
- The `item1_`/`item2_`/`item3_` repeating groups are eliminated: 10 header rows expand into 24 item rows in `nf1_sales_items`, with no NULLs and no 3-item ceiling.
- `nf1_delivery_log` receives only a PK — it was already atomic, so no structural split was needed here.

**Still unresolved:** supplier contact info repeats across every product and delivery row (2NF); customer phone and nickname travel with every sale (2NF); `customer_balance`, `total_amount`, and `line_total` are still stored derived values (3NF).

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

```mermaid
erDiagram
    nf2_suppliers {
        INT supplier_id PK
        TEXT supplier_name
        TEXT supplier_contact
        TEXT supplier_phone
        TEXT supplier_address
    }
    nf2_products {
        INT product_id PK
        INT supplier_id FK
        TEXT product_name
        TEXT category "still transitive — 3NF to fix"
        NUMERIC selling_price
        INT stock_count "still stale — 3NF to fix"
    }
    nf2_customers {
        INT customer_id PK
        TEXT customer_name
        TEXT customer_phone
        TEXT customer_nickname
        NUMERIC customer_balance "still stored derived — 3NF to fix"
    }
    nf2_sales {
        INT sale_id PK
        INT customer_id FK
        DATE sale_date
        TEXT payment_type
        NUMERIC total_amount "still stored derived — 3NF to fix"
    }
    nf2_sale_items {
        INT item_id PK
        INT sale_id FK
        TEXT product_name "text ref, no FK yet — 3NF to fix"
        INT qty
        NUMERIC unit_price
    }
    nf2_deliveries {
        INT delivery_id PK
        INT supplier_id FK
        DATE delivery_date
        TEXT reference_no
    }
    nf2_delivery_items {
        INT delivery_item_id PK
        INT delivery_id FK
        TEXT product_name "text ref, no FK yet — 3NF to fix"
        TEXT product_category "still transitive — 3NF to fix"
        NUMERIC line_total "still stored derived — 3NF to fix"
    }

    nf2_suppliers ||--o{ nf2_products : "supplies"
    nf2_suppliers ||--o{ nf2_deliveries : "delivers to"
    nf2_customers ||--o{ nf2_sales : "makes"
    nf2_sales ||--o{ nf2_sale_items : "contains"
    nf2_deliveries ||--o{ nf2_delivery_items : "has"
```

**What was solved?**

- Supplier contact info (contact name, phone, address) now lives in exactly one row in `nf2_suppliers`; changing Nestlé's phone number is 1 UPDATE instead of 7+ scattered across product and delivery rows.
- Customer identity (phone, nickname) is extracted to `nf2_customers`; one customer maps to one row, referenced by FK wherever sales need it.
- The delivery log is formally split into a **header** (`nf2_deliveries` — one row per receipt) and **line items** (`nf2_delivery_items` — one row per product), making the structure that was implicit in the flat log explicit and enforceable.

**Still unresolved:** `category_desc` and `unit_label` are still attributes of their parent concept, not of the product (3NF); `customer_balance`, `total_amount`, and `line_total` remain stored derived values (3NF); product names in sale and delivery items are still free-text columns with no FK constraint (3NF).

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

```mermaid
erDiagram
    categories {
        INT category_id PK
        TEXT name
        TEXT description
    }
    units {
        INT unit_id PK
        TEXT code
        TEXT name
    }
    suppliers {
        INT supplier_id PK
        TEXT name
        TEXT contact_person
        TEXT phone
        TEXT address
    }
    products {
        INT product_id PK
        INT category_id FK
        INT unit_id FK
        TEXT name
        NUMERIC current_price
        INT reorder_level
    }
    customers {
        INT customer_id PK
        TEXT full_name
        TEXT nickname
        TEXT phone
    }
    credit_payments {
        INT payment_id PK
        INT customer_id FK
        NUMERIC amount
        DATE payment_date
    }
    transactions {
        INT transaction_id PK
        INT customer_id FK
        DATE transaction_date
        TEXT payment_type
    }
    transaction_items {
        INT transaction_item_id PK
        INT transaction_id FK
        INT product_id FK
        INT quantity
        NUMERIC unit_price "snapshot — price at time of sale"
    }
    restocks {
        INT restock_id PK
        INT supplier_id FK
        DATE restock_date
        TEXT reference_no
    }
    restock_items {
        INT restock_item_id PK
        INT restock_id FK
        INT product_id FK
        INT quantity
        NUMERIC unit_cost "snapshot — cost at time of delivery"
    }

    categories ||--o{ products : "classifies"
    units ||--o{ products : "measures"
    suppliers ||--o{ restocks : "delivers"
    customers ||--o{ transactions : "makes"
    customers ||--o{ credit_payments : "pays"
    transactions ||--o{ transaction_items : "contains"
    restocks ||--o{ restock_items : "has"
    products ||--o{ transaction_items : "sold in"
    products ||--o{ restock_items : "restocked in"
```

**What was solved?**

- `category_desc` and `unit_label` each live in their own tables (`categories`, `units`) — no two product rows can disagree on what "Snacks" means or what "sachet" is called.
- `products.stock_count` is dropped entirely; `customers.customer_balance` is dropped entirely. Both are replaced by views (`v_product_stock`, `v_customer_balances`) that compute the correct answer from live data on every query — no staleness possible.
- `total_amount` and `line_total` are removed; they are `SUM()` calls, not facts that belong in a row.
- `credit_payments` becomes a first-class entity — previously invisible in the raw notebook (only its net effect on the stale balance column was recorded); 3NF surfaces it as a distinct fact: who paid, how much, when.
- All free-text product name references in sale and delivery line items are replaced by `product_id` FKs — a typo in a product name is now impossible at the row level.

**Final: 10 tables + 2 views — structurally identical to `schema.sql`.**

#### The journey in brief

| Stage | Tables | Key transformation | Anomalies eliminated |
|---|---:|---|---|
| Raw | 3 | Direct notebook transcription | — |
| 1NF | 5 | PKs added; repeating groups unnested; multi-value cells split | Duplicate-row ambiguity; 3-item sale cap; non-atomic `alt_suppliers` |
| 2NF | 7 | Supplier & customer info extracted; delivery header/line split | Supplier contact repeated per row; customer info scattered across sales |
| 3NF | 10 + 2 views | Transitive deps extracted; stored derivations replaced by views; text refs → FKs | Stale stock count; stale customer balance; wrong sale totals; product-name typos |

**One rule, consistently applied:** a fact lives in exactly one place — and derived facts are never stored at all.

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

### Reporting & Visualization

Once the schema is honest, the reports almost write themselves — every derived
number already lives in a view. Two artifacts surface them, and **both read from
exactly one query layer** so the SQL is never duplicated:

```
src/sarisari/reporting.py        # ← single source of truth for every report
        │
        ├──►  notebooks/01_reporting_dashboard.ipynb   (JupyterLab, Plotly inline)
        └──►  dashboard/app.py                          (Streamlit web dashboard)
```

`reporting.py` exposes a small, composable API: a `Filters` dataclass (date
window + product groups + brands) and a function per report that returns a tidy
pandas `DataFrame`. Derived facts are always read from the **views**
(`v_customer_balances`, `v_utang_ledger`, `v_product_stock`) — the reporting
layer never re-implements balance or stock math.

**The "brand" that wasn't a column.** The brief asked for a *brand* filter, but
3NF (correctly) has no brand column — each product *name* embeds a real Filipino
brand (*"Lucky Me Pancit Canton Original 60g"*). Rather than denormalize,
`derive_brand()` recovers it with a curated **longest-prefix** match over the
188-SKU catalog, so `Lucky Me Pancit Canton Original` and `Lucky Me Instant Mami
Beef` both roll up to **Lucky Me**, while `Ginebra San Miguel Bilog` resolves to
**Ginebra San Miguel** (not **San**). Because the product dimension is tiny, the
brand is derived once in pandas and group/brand filters are pushed down to SQL
as a resolved `product_id` list.

Both artifacts present the same three report families:

| Report | Filters | Backed by |
|---|---|---|
| **Sales** — revenue / units / baskets over time, by group, by brand, cash vs. credit, top SKUs | time range · group · brand · granularity (day→year) | `transactions` + `transaction_items` |
| **Customers** — per-customer utang balance, payments, transactions & amounts, single-customer ledger drill-down with a running-balance chart | — | `v_customer_balances`, `v_utang_ledger` |
| **Stock** — on-hand levels, reorder flags, inventory value, derived-vs-maintained reconciliation | group · brand | `v_product_stock` |

The Streamlit app caches the engine (`st.cache_resource`) and every query
(`st.cache_data`) so filter changes are instant; the notebook is parameterized by
a single editable `Filters` block at the top. Launch with `make dashboard` /
`make notebook`.

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

# 4. Explore the reports:
make notebook     # JupyterLab analytics notebook (01_reporting_dashboard.ipynb)
make dashboard    # interactive Streamlit web dashboard
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
│   ├── reporting.py        #   ★ shared report query layer (notebook + dashboard)
│   └── cli.py              #   synthesize / load / verify entry points
│
├── dashboard/              # ★ Streamlit web reporting dashboard
│   └── app.py              #   sales · customers · stock — interactive filters
│
├── scripts/                # thin runnable wrappers around cli.py
├── data/csv/               # generated CSVs (gitignored)
├── notebooks/              # analytics & ML notebooks
│   └── 01_reporting_dashboard.ipynb   # ★ live query + Plotly report notebook
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
| Reporting | Streamlit, Plotly | Interactive web dashboard + inline notebook charts |
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
