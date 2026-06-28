"""Synthesize a realistic ~676,767-row sari-sari dataset and write it to CSV.

Design goals
------------
* **Deterministic** — one master seed reproduces the exact dataset.
* **Realistic** — store growth over the years, weekend & payday spikes,
  bestsellers vs. slow movers, decade-long price inflation, and an "utang"
  credit sub-economy.
* **Consistent** — quantities restocked always cover quantities sold, so
  on-hand stock is never negative; utang payments never exceed charges, so
  balances are never negative.
* **Sized to a target** — the grand total of rows across all tables lands on
  ``settings.target_rows`` (default 676,767). The line-item table absorbs the
  remainder so the total is exact.

Row-count interpretation: "~676,767 rows" = the SUM of row counts across all
ten tables. ``transaction_items`` is the balancing table.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from faker import Faker

from . import catalog
from .config import Settings

DEFAULT_TARGET = 676_767

# Baseline table sizes calibrated for the default target; they scale linearly
# with ``settings.target_rows``. ``transaction_items`` is computed as the
# remainder so the grand total is exact.
_BASE_COUNTS = {
    "customers": 2_000,
    "restocks": 6_000,
    "restock_items": 36_000,
    "transactions": 180_000,
    "credit_payments": 24_000,
}

P_CREDIT = 0.22            # share of sales taken "on utang"
P_CASH_NAMED = 0.18        # cash sales that still name a (suki) customer
INFLATION_RATE = 0.04      # ~4% annual drift; prices deflate into the past
HONORIFICS = ["Aling", "Mang", "Ate", "Kuya", "Tita", "Tito", "Lola", "Lolo", "Nanay", "Tatay"]
CREDIT_LIMIT_TIERS = np.array([300, 500, 800, 1000, 1500, 2000, 3000])
CREDIT_LIMIT_WEIGHTS = np.array([0.22, 0.24, 0.20, 0.15, 0.10, 0.06, 0.03])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _round_quarter(x: np.ndarray) -> np.ndarray:
    """Round to the nearest ₱0.25 (typical sari-sari pricing granularity)."""
    return np.maximum(np.round(x * 4.0) / 4.0, 0.25)


def _inflation(years: np.ndarray, end_year: int) -> np.ndarray:
    """Multiplicative price factor: 1.0 at end_year, <1 for earlier years."""
    return (1.0 + INFLATION_RATE) ** (years - end_year)


def _day_weights(days: pd.DatetimeIndex, start_year: int) -> np.ndarray:
    """Per-day sampling weight encoding business growth + seasonality."""
    yrs = days.year.to_numpy()
    growth = 1.0 + 0.07 * (yrs - start_year)                 # store prospers over time
    dow = np.where(days.dayofweek.to_numpy() >= 4, 1.35, 1.0)  # Fri/Sat/Sun busier
    dec = np.where(days.month.to_numpy() == 12, 1.4, 1.0)      # Christmas season
    dom = days.day.to_numpy()
    payday = np.where(np.isin(dom, [15, 16, 30, 31, 1]), 1.3, 1.0)  # sahod / payday
    w = growth * dow * dec * payday
    return w / w.sum()


def _allocate_counts(weights: np.ndarray, total: int, min_each: int = 0) -> np.ndarray:
    """Split ``total`` into integer counts ∝ weights, summing exactly to total."""
    weights = np.asarray(weights, dtype=float)
    if weights.sum() <= 0:
        weights = np.ones_like(weights)
    base = np.full(len(weights), min_each, dtype=np.int64)
    remaining = total - base.sum()
    if remaining < 0:
        raise ValueError("min_each * n exceeds total")
    share = weights / weights.sum() * remaining
    floor = np.floor(share).astype(np.int64)
    base += floor
    # distribute the rounding remainder to the largest fractional parts
    short = remaining - floor.sum()
    if short > 0:
        order = np.argsort(-(share - floor))
        base[order[:short]] += 1
    return base


# ---------------------------------------------------------------------------
# main synthesis
# ---------------------------------------------------------------------------
def synthesize(settings: Settings) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(settings.seed)
    fake = _make_faker(settings.seed)

    scale = settings.target_rows / DEFAULT_TARGET
    counts = {k: max(1, int(round(v * scale))) for k, v in _BASE_COUNTS.items()}

    cats = _build_categories()
    units = _build_units()
    suppliers = _build_suppliers(fake)
    products = _build_products(rng)

    n_customers = counts["customers"]
    customers, cust_weight = _build_customers(rng, fake, n_customers)

    n_tx = counts["transactions"]
    transactions, tx_year = _build_transactions(rng, settings, n_tx, customers, cust_weight)

    # transaction_items absorbs the remainder so the grand total is exact.
    fixed_total = (
        len(cats) + len(units) + len(suppliers) + len(products) + len(customers)
        + counts["restocks"] + counts["restock_items"] + n_tx + counts["credit_payments"]
    )
    n_items = settings.target_rows - fixed_total
    if n_items < n_tx:
        raise ValueError(f"target_rows too small: need >= {fixed_total + n_tx}")

    txn_items, sold_per_product = _build_transaction_items(
        rng, n_items, transactions, products, tx_year
    )

    restocks = _build_restocks(rng, settings, counts["restocks"], len(suppliers))
    restock_items = _build_restock_items(
        rng, counts["restock_items"], products, sold_per_product, restocks
    )

    credit_payments = _build_credit_payments(
        rng, settings, counts["credit_payments"], transactions, txn_items
    )

    return {
        "categories": cats,
        "units": units,
        "suppliers": suppliers,
        "products": products,
        "customers": customers,
        "restocks": restocks,
        "restock_items": restock_items,
        "transactions": transactions,
        "transaction_items": txn_items,
        "credit_payments": credit_payments,
    }


def _make_faker(seed: int) -> Faker:
    try:
        fake = Faker("fil_PH")
    except Exception:  # pragma: no cover - locale fallback
        fake = Faker()
    Faker.seed(seed)
    return fake


# --- dimension builders -----------------------------------------------------
def _build_categories() -> pd.DataFrame:
    return pd.DataFrame(
        [(i + 1, name, desc) for i, (name, desc) in enumerate(catalog.CATEGORIES)],
        columns=["category_id", "name", "description"],
    )


def _build_units() -> pd.DataFrame:
    return pd.DataFrame(
        [(i + 1, code, name) for i, (code, name) in enumerate(catalog.UNITS)],
        columns=["unit_id", "code", "name"],
    )


def _build_suppliers(fake: Faker) -> pd.DataFrame:
    rows = []
    for i, name in enumerate(catalog.SUPPLIER_NAMES, start=1):
        rows.append(
            (
                i,
                name,
                fake.name(),
                _ph_phone(fake),
                fake.address().replace("\n", ", "),
            )
        )
    return pd.DataFrame(
        rows, columns=["supplier_id", "name", "contact_person", "phone", "address"]
    )


def _build_products(rng: np.random.Generator) -> pd.DataFrame:
    cat_id = {name: i + 1 for i, (name, _) in enumerate(catalog.CATEGORIES)}
    unit_id = {code: i + 1 for i, (code, _) in enumerate(catalog.UNITS)}
    rows = []
    for i, p in enumerate(catalog.PRODUCTS, start=1):
        # tingi staples sold loose (rice per kilo) are typically unscanned
        barcode = None if p.unit == "kg" else f"48{i:011d}"
        rows.append(
            (
                i,
                cat_id[p.category],
                unit_id[p.unit],
                p.name,
                p.category,                      # description doubles as group label
                barcode,
                round(float(p.base_price), 2),   # current_price = present-day price
                int(p.reorder_level),
                True,
            )
        )
    df = pd.DataFrame(
        rows,
        columns=[
            "product_id", "category_id", "unit_id", "name", "description",
            "barcode", "current_price", "reorder_level", "is_active",
        ],
    )
    df["barcode"] = df["barcode"].astype("string")
    return df


def _build_customers(rng, fake, n: int) -> tuple[pd.DataFrame, np.ndarray]:
    first_names = [fake.first_name() for _ in range(n)]
    rows = []
    for i in range(n):
        full = fake.name()
        nick = f"{rng.choice(HONORIFICS)} {first_names[i]}"
        rows.append(
            (
                i + 1,
                full,
                nick,
                _ph_phone(fake),
                fake.address().replace("\n", ", "),
                int(rng.choice(CREDIT_LIMIT_TIERS, p=CREDIT_LIMIT_WEIGHTS)),
                True,
            )
        )
    df = pd.DataFrame(
        rows,
        columns=[
            "customer_id", "full_name", "nickname", "phone", "address",
            "credit_limit", "is_active",
        ],
    )
    # loyalty weights: a heavy tail of frequent "suki" customers
    weight = rng.gamma(shape=1.6, scale=1.0, size=n)
    weight /= weight.sum()
    return df, weight


def _ph_phone(fake: Faker) -> str:
    return "09" + "".join(str(d) for d in fake.random_choices(range(10), length=9))


# --- fact builders ----------------------------------------------------------
def _build_transactions(rng, settings, n, customers, cust_weight):
    days = pd.date_range(settings.start_date, settings.end_date, freq="D")
    p = _day_weights(days, settings.start_date.year)
    chosen = rng.choice(len(days), size=n, p=p)
    base = days.to_numpy()[chosen]
    # time of day: weighted toward morning (7-9) and evening (17-20)
    hours = rng.choice(
        np.arange(6, 22),
        size=n,
        p=_hour_weights(),
    )
    secs = (hours * 3600 + rng.integers(0, 3600, size=n)).astype("timedelta64[s]")
    ts = base + secs

    is_credit = rng.random(n) < P_CREDIT
    cust_ids = customers["customer_id"].to_numpy()
    customer = np.full(n, -1, dtype=np.int64)

    idx_credit = np.flatnonzero(is_credit)
    customer[idx_credit] = rng.choice(cust_ids, size=idx_credit.size, p=cust_weight)

    idx_cash = np.flatnonzero(~is_credit)
    named = rng.random(idx_cash.size) < P_CASH_NAMED
    customer[idx_cash[named]] = rng.choice(cust_ids, size=int(named.sum()), p=cust_weight)

    df = pd.DataFrame(
        {
            "transaction_id": np.arange(1, n + 1, dtype=np.int64),
            "customer_id": pd.array(np.where(customer == -1, pd.NA, customer), dtype="Int64"),
            "transaction_date": ts,
            "payment_type": np.where(is_credit, "credit", "cash"),
            "notes": pd.array([pd.NA] * n, dtype="string"),
        }
    )
    tx_year = pd.DatetimeIndex(ts).year.to_numpy()
    return df, tx_year


def _hour_weights() -> np.ndarray:
    base = np.array(
        # 6  7   8   9  10 11 12 13 14 15 16 17  18  19  20 21
        [2, 6, 7, 5, 4, 4, 5, 4, 3, 3, 4, 6, 7, 6, 4, 2],
        dtype=float,
    )
    return base / base.sum()


def _build_transaction_items(rng, n_items, transactions, products, tx_year):
    n_tx = len(transactions)
    # every sale has >=1 line; distribute the rest so the basket-size has a
    # believable right tail (mostly 1-4 items).
    counts = np.ones(n_tx, dtype=np.int64)
    extra = n_items - n_tx
    if extra > 0:
        counts += rng.multinomial(extra, np.full(n_tx, 1.0 / n_tx))

    txn_id = np.repeat(transactions["transaction_id"].to_numpy(), counts)
    line_year = np.repeat(tx_year, counts)

    prod_ids = products["product_id"].to_numpy()
    # products are built in catalog order, so popularity aligns positionally
    weights = np.array([p.popularity for p in catalog.PRODUCTS], dtype=float)
    weights /= weights.sum()
    chosen_pos = rng.choice(len(prod_ids), size=n_items, p=weights)
    product = prod_ids[chosen_pos]

    qty_choices = np.array([1, 2, 3, 4, 5, 6, 8, 10, 12])
    qty_probs = np.array([0.50, 0.22, 0.12, 0.06, 0.04, 0.03, 0.015, 0.01, 0.005])
    qty_probs /= qty_probs.sum()
    quantity = rng.choice(qty_choices, size=n_items, p=qty_probs)

    base_price = products["current_price"].to_numpy()[chosen_pos]
    end_year = transactions["transaction_date"].max().year
    factor = _inflation(line_year, end_year)
    unit_price = _round_quarter(base_price * factor)

    df = pd.DataFrame(
        {
            "transaction_item_id": np.arange(1, n_items + 1, dtype=np.int64),
            "transaction_id": txn_id,
            "product_id": product,
            "quantity": quantity.astype(np.int64),
            "unit_price": np.round(unit_price, 2),
        }
    )
    sold = (
        df.groupby("product_id")["quantity"].sum()
        .reindex(prod_ids, fill_value=0)
        .to_numpy()
    )
    return df, sold


def _build_restocks(rng, settings, n, n_suppliers):
    days = pd.date_range(settings.start_date, settings.end_date, freq="D")
    # restocks grow with the business too, but no intra-week seasonality
    yrs = days.year.to_numpy()
    w = 1.0 + 0.07 * (yrs - settings.start_date.year)
    w /= w.sum()
    chosen = rng.choice(len(days), size=n, p=w)
    base = days.to_numpy()[chosen]
    secs = (rng.integers(6 * 3600, 18 * 3600, size=n)).astype("timedelta64[s]")
    ts = base + secs
    df = pd.DataFrame(
        {
            "restock_id": np.arange(1, n + 1, dtype=np.int64),
            "supplier_id": rng.integers(1, n_suppliers + 1, size=n),
            "restock_date": ts,
            "reference_no": [f"DR-{x:06d}" for x in rng.integers(100000, 999999, size=n)],
            "notes": pd.array([pd.NA] * n, dtype="string"),
        }
    )
    return df


def _build_restock_items(rng, n_lines, products, sold_per_product, restocks):
    prod_ids = products["product_id"].to_numpy()
    reorder = products["reorder_level"].to_numpy()
    base_price = products["current_price"].to_numpy()
    categories = products["description"].to_numpy()  # we stored group in description
    n_prod = len(prod_ids)

    # Total to restock per product must COVER everything sold, plus a buffer so
    # the final on-hand is a believable positive number.
    buffer = (reorder * rng.integers(2, 7, size=n_prod)).astype(np.int64) + rng.integers(
        1, 20, size=n_prod
    )
    needed = sold_per_product.astype(np.int64) + buffer

    # spread the fixed number of lines across products ∝ how much they move
    line_weights = needed.astype(float) + 1.0
    lines_per_product = _allocate_counts(line_weights, n_lines, min_each=1)

    restock_ids = restocks["restock_id"].to_numpy()
    restock_year = pd.DatetimeIndex(restocks["restock_date"]).year.to_numpy()
    year_by_restock = dict(zip(restock_ids, restock_year))
    end_year = int(restock_year.max())

    out_product = np.empty(n_lines, dtype=np.int64)
    out_qty = np.empty(n_lines, dtype=np.int64)
    pos = 0
    for i in range(n_prod):
        k = int(lines_per_product[i])
        if k == 0:
            continue
        # split this product's needed quantity across its k lines (>=1 each)
        q = max(int(needed[i]), k)
        base_q = q // k
        rem = q - base_q * k
        line_q = np.full(k, base_q, dtype=np.int64)
        line_q[:rem] += 1
        out_product[pos : pos + k] = prod_ids[i]
        out_qty[pos : pos + k] = np.maximum(line_q, 1)
        pos += k

    assigned_restock = rng.choice(restock_ids, size=n_lines)
    yrs = np.array([year_by_restock[r] for r in assigned_restock])
    # cost per line = wholesale cost deflated to that restock's year
    pos_index = {pid: idx for idx, pid in enumerate(prod_ids)}
    prod_pos = np.array([pos_index[p] for p in out_product])
    cost_now = np.array(
        [catalog.cost_for(categories[j], base_price[j]) for j in prod_pos]
    )
    unit_cost = np.round(cost_now * _inflation(yrs, end_year), 2)

    df = pd.DataFrame(
        {
            "restock_item_id": np.arange(1, n_lines + 1, dtype=np.int64),
            "restock_id": assigned_restock,
            "product_id": out_product,
            "quantity": out_qty,
            "unit_cost": unit_cost,
        }
    )
    return df


def _build_credit_payments(rng, settings, n_payments, transactions, txn_items):
    # line totals -> per-transaction totals
    line_total = txn_items["quantity"].to_numpy() * txn_items["unit_price"].to_numpy()
    tx_total = (
        pd.Series(line_total, index=txn_items["transaction_id"].to_numpy())
        .groupby(level=0)
        .sum()
    )

    tx = transactions.copy()
    tx["total"] = tx["transaction_id"].map(tx_total).fillna(0.0)
    credit = tx[(tx["payment_type"] == "credit") & tx["customer_id"].notna()]

    charge = credit.groupby("customer_id")["total"].sum()
    first_date = credit.groupby("customer_id")["transaction_date"].min()
    cust = charge.index.to_numpy().astype(np.int64)
    charge_v = charge.to_numpy()

    if len(cust) == 0:
        return pd.DataFrame(
            columns=["payment_id", "customer_id", "amount", "payment_date", "notes"]
        )

    # allocate the fixed number of payment rows across credit customers ∝ charge
    pay_counts = _allocate_counts(charge_v, n_payments, min_each=0)

    end = np.datetime64(settings.end_date)
    out_cust, out_amt, out_date = [], [], []
    for i in range(len(cust)):
        k = int(pay_counts[i])
        if k == 0:
            continue
        total = float(charge_v[i])
        target_paid = total * rng.uniform(0.50, 0.95)
        # split into k positive parts that sum to target_paid
        parts = rng.random(k) + 0.05
        parts = parts / parts.sum() * target_paid
        amounts = np.maximum(np.round(parts, 2), 1.0)
        # never let payments exceed the charge (keep balance >= 0)
        if amounts.sum() > total:
            amounts = amounts / amounts.sum() * (total * 0.95)
            amounts = np.round(np.maximum(amounts, 0.5), 2)

        start = np.datetime64(first_date.loc[cust[i]])
        span = max((end - start) / np.timedelta64(1, "s"), 1)
        offs = np.sort(rng.random(k)) * span
        dates = start + offs.astype("timedelta64[s]")

        out_cust.extend([int(cust[i])] * k)
        out_amt.extend(amounts.tolist())
        out_date.extend(pd.to_datetime(dates).tolist())

    df = pd.DataFrame(
        {
            "payment_id": np.arange(1, len(out_cust) + 1, dtype=np.int64),
            "customer_id": np.array(out_cust, dtype=np.int64),
            "amount": np.array(out_amt, dtype=float),
            "payment_date": out_date,
            "notes": pd.array([pd.NA] * len(out_cust), dtype="string"),
        }
    )
    return df


# ---------------------------------------------------------------------------
# CSV materialization
# ---------------------------------------------------------------------------
def write_csvs(frames: dict[str, pd.DataFrame], settings: Settings) -> dict[str, int]:
    settings.ensure_dirs()
    sizes: dict[str, int] = {}
    for name, df in frames.items():
        path = settings.csv_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        sizes[name] = len(df)
    return sizes
