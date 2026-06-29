"""Reporting & analytics query layer for the Digital Sari-Sari Store.

This module is the single source of truth for every report the project visualizes
— shared by **both** the JupyterLab analytics notebook and the Streamlit web
dashboard, so the SQL lives in exactly one place (the same rule the schema
itself follows).

Three families of report are provided, matching the dashboard's three tabs:

1. **Sales** — revenue / units / baskets over time, sliceable by *date range*,
   *product group* (category) and *brand*.
2. **Customers** — per-customer utang (credit) balances, payment history and
   transaction activity, served from ``v_customer_balances`` / ``v_utang_ledger``.
3. **Stock** — on-hand levels, reorder flags and inventory value, served from
   ``v_product_stock``.

Every query reads from the **views** for derived facts (balances, stock) and
never re-implements the balance / stock math — `README.md`, "Read from the
views, write to the tables".

`brand` is not a stored column (each product *name* embeds a real Filipino
brand, e.g. *"Lucky Me Pancit Canton Original 60g"*). :func:`derive_brand`
recovers it with a curated longest-prefix match over the 188-SKU catalog, so
"Lucky Me Pancit Canton Original" and "Lucky Me Instant Mami Beef" both roll up
to the **Lucky Me** brand. Because the product dimension is tiny (188 rows) the
brand is derived once in pandas and brand/group filters are pushed down to SQL
as a resolved ``product_id`` list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy import Engine, text

from .db import get_engine  # re-exported for convenience

__all__ = [
    "get_engine",
    "derive_brand",
    "Filters",
    "load_dim_products",
    "list_categories",
    "list_brands",
    "date_bounds",
    "kpi_summary",
    "payment_mix",
    "sales_timeseries",
    "sales_by_category",
    "sales_by_product",
    "sales_by_brand",
    "top_products",
    "customer_balances",
    "customer_directory",
    "customer_detail",
    "customer_ledger",
    "customer_transactions",
    "stock_report",
    "FREQ",
]

# Period granularity options exposed to the UI -> Postgres date_trunc unit.
FREQ: dict[str, str] = {
    "Daily": "day",
    "Weekly": "week",
    "Monthly": "month",
    "Quarterly": "quarter",
    "Yearly": "year",
}

# -----------------------------------------------------------------------------
# Brand derivation
# -----------------------------------------------------------------------------
# Curated multi-word brand prefixes from the catalog. Single-word brands
# (Argentina, Nescafé, Tide, Oishi, ...) fall back to the first token, so only
# the multi-word / ambiguous cases need listing here. Order does not matter —
# the matcher always tries the LONGEST prefix first.
_KNOWN_BRANDS: list[str] = [
    "Ginebra San Miguel", "San Miguel", "San Mig Coffee", "San Mig Light",
    "San Marino", "Datu Puti", "Silver Swan", "Marca Piña", "Del Monte",
    "Mama Sita's", "Golden Fiesta", "Baguio Oil", "Lucky Me", "Boy Bawang",
    "Bear Brand", "Great Taste", "Red Horse", "Red Bull", "Century Tuna",
    "Cream Silk", "Curly Tops", "Cloud 9", "Magic Flakes", "Mr. Chips",
    "Roller Coaster", "Clover Chips", "Head & Shoulders", "Eight O'Clock",
    "Nature's Spring", "Young's Town", "Carlo Rossi", "Mountain Dew",
    "Star Margarine", "Tender Juicy", "Beer na Beer", "Colt 45",
    "Smirnoff Mule", "The Bar", "Royal Tru-Orange", "Maxx", "Well-Milled",
]
# Longest first so "San Miguel Pale Pilsen" matches "San Miguel", not "San".
_KNOWN_BRANDS_SORTED = sorted(_KNOWN_BRANDS, key=lambda b: (-b.count(" "), -len(b)))


def derive_brand(product_name: str) -> str:
    """Recover the brand from a product name (longest curated prefix, else 1st word)."""
    name = product_name.strip()
    low = name.lower()
    for brand in _KNOWN_BRANDS_SORTED:
        b = brand.lower()
        if low == b or low.startswith(b + " "):
            return brand
    return name.split(" ", 1)[0]


# -----------------------------------------------------------------------------
# Filters
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Filters:
    """A reusable slice across the reports: date window + group/brand selection.

    ``categories`` / ``brands`` empty == "no restriction" (all groups/brands).
    """

    start: date
    end: date
    categories: tuple[str, ...] = field(default_factory=tuple)
    brands: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_product_filter(self) -> bool:
        return bool(self.categories) or bool(self.brands)


def _resolve_product_ids(dim: pd.DataFrame, f: Filters) -> list[int] | None:
    """Translate group/brand selection into a concrete product_id list.

    Returns ``None`` when no product-level filter is active (so the SQL omits the
    clause entirely and scans everything).
    """
    if not f.has_product_filter:
        return None
    df = dim
    if f.categories:
        df = df[df["category"].isin(f.categories)]
    if f.brands:
        df = df[df["brand"].isin(f.brands)]
    return df["product_id"].tolist()


def _txn_where(f: Filters, pids: list[int] | None) -> tuple[str, dict]:
    """Build the shared WHERE clause + bound params for transaction queries."""
    clauses = ["t.transaction_date::date BETWEEN :start AND :end"]
    params: dict = {"start": f.start, "end": f.end}
    if pids is not None:
        clauses.append("ti.product_id = ANY(:pids)")
        params["pids"] = pids
    return " AND ".join(clauses), params


# -----------------------------------------------------------------------------
# Dimensions / lookups
# -----------------------------------------------------------------------------
def load_dim_products(engine: Engine) -> pd.DataFrame:
    """Product dimension (188 rows): id, name, category, unit, price + derived brand."""
    df = pd.read_sql(
        text(
            """
            SELECT p.product_id, p.name, c.name AS category, u.code AS unit,
                   p.current_price, p.reorder_level, p.is_active
            FROM products p
            JOIN categories c ON c.category_id = p.category_id
            JOIN units      u ON u.unit_id     = p.unit_id
            ORDER BY p.name
            """
        ),
        engine,
    )
    df["brand"] = df["name"].map(derive_brand)
    return df


def list_categories(engine: Engine) -> list[str]:
    df = pd.read_sql(text("SELECT name FROM categories ORDER BY name"), engine)
    return df["name"].tolist()


def list_brands(dim: pd.DataFrame) -> list[str]:
    """Distinct brands, ordered by SKU count (richest brands first)."""
    return dim["brand"].value_counts().index.tolist()


def date_bounds(engine: Engine) -> tuple[date, date]:
    """Earliest and latest transaction date in the warehouse."""
    row = pd.read_sql(
        text(
            "SELECT MIN(transaction_date)::date AS lo, "
            "MAX(transaction_date)::date AS hi FROM transactions"
        ),
        engine,
    ).iloc[0]
    return row["lo"], row["hi"]


# -----------------------------------------------------------------------------
# 1. SALES reports
# -----------------------------------------------------------------------------
def kpi_summary(engine: Engine, f: Filters, dim: pd.DataFrame) -> dict:
    """Headline numbers for the selected slice (revenue, units, baskets, credit)."""
    where, params = _txn_where(f, _resolve_product_ids(dim, f))
    row = pd.read_sql(
        text(
            f"""
            SELECT
                COALESCE(SUM(ti.quantity * ti.unit_price), 0)               AS revenue,
                COALESCE(SUM(ti.quantity), 0)                               AS units,
                COUNT(DISTINCT t.transaction_id)                            AS transactions,
                COUNT(DISTINCT t.transaction_id)
                    FILTER (WHERE t.payment_type = 'credit')                AS credit_txns,
                COALESCE(SUM(ti.quantity * ti.unit_price)
                    FILTER (WHERE t.payment_type = 'credit'), 0)            AS credit_revenue,
                COUNT(DISTINCT t.customer_id)                               AS active_customers
            FROM transaction_items ti
            JOIN transactions t ON t.transaction_id = ti.transaction_id
            WHERE {where}
            """
        ),
        engine,
        params=params,
    ).iloc[0]
    revenue = float(row["revenue"])
    txns = int(row["transactions"])
    return {
        "revenue": revenue,
        "units": int(row["units"]),
        "transactions": txns,
        "avg_basket": revenue / txns if txns else 0.0,
        "credit_txns": int(row["credit_txns"]),
        "credit_revenue": float(row["credit_revenue"]),
        "credit_share": (float(row["credit_revenue"]) / revenue) if revenue else 0.0,
        "active_customers": int(row["active_customers"]),
    }


def payment_mix(engine: Engine, f: Filters, dim: pd.DataFrame) -> pd.DataFrame:
    """Revenue and basket counts split by cash vs. credit."""
    where, params = _txn_where(f, _resolve_product_ids(dim, f))
    return pd.read_sql(
        text(
            f"""
            SELECT t.payment_type,
                   SUM(ti.quantity * ti.unit_price)   AS revenue,
                   COUNT(DISTINCT t.transaction_id)   AS transactions
            FROM transaction_items ti
            JOIN transactions t ON t.transaction_id = ti.transaction_id
            WHERE {where}
            GROUP BY t.payment_type
            ORDER BY revenue DESC
            """
        ),
        engine,
        params=params,
    )


def sales_timeseries(engine: Engine, f: Filters, dim: pd.DataFrame, freq: str = "Monthly") -> pd.DataFrame:
    """Revenue / units / baskets per period (Daily…Yearly) for the slice."""
    unit = FREQ.get(freq, "month")  # whitelist guard — never interpolate raw input
    where, params = _txn_where(f, _resolve_product_ids(dim, f))
    return pd.read_sql(
        text(
            f"""
            SELECT date_trunc('{unit}', t.transaction_date)::date AS period,
                   SUM(ti.quantity * ti.unit_price)               AS revenue,
                   SUM(ti.quantity)                               AS units,
                   COUNT(DISTINCT t.transaction_id)               AS transactions
            FROM transaction_items ti
            JOIN transactions t ON t.transaction_id = ti.transaction_id
            WHERE {where}
            GROUP BY 1
            ORDER BY 1
            """
        ),
        engine,
        params=params,
    )


def sales_by_category(engine: Engine, f: Filters, dim: pd.DataFrame) -> pd.DataFrame:
    """Revenue / units per product group (category)."""
    where, params = _txn_where(f, _resolve_product_ids(dim, f))
    return pd.read_sql(
        text(
            f"""
            SELECT c.name AS category,
                   SUM(ti.quantity * ti.unit_price)   AS revenue,
                   SUM(ti.quantity)                   AS units,
                   COUNT(DISTINCT t.transaction_id)   AS transactions
            FROM transaction_items ti
            JOIN transactions t ON t.transaction_id = ti.transaction_id
            JOIN products   p ON p.product_id   = ti.product_id
            JOIN categories c ON c.category_id  = p.category_id
            WHERE {where}
            GROUP BY c.name
            ORDER BY revenue DESC
            """
        ),
        engine,
        params=params,
    )


def sales_by_product(engine: Engine, f: Filters, dim: pd.DataFrame) -> pd.DataFrame:
    """Per-product revenue / units, enriched with category & brand (from the dim)."""
    where, params = _txn_where(f, _resolve_product_ids(dim, f))
    df = pd.read_sql(
        text(
            f"""
            SELECT ti.product_id,
                   SUM(ti.quantity * ti.unit_price)   AS revenue,
                   SUM(ti.quantity)                   AS units,
                   COUNT(DISTINCT t.transaction_id)   AS transactions
            FROM transaction_items ti
            JOIN transactions t ON t.transaction_id = ti.transaction_id
            WHERE {where}
            GROUP BY ti.product_id
            """
        ),
        engine,
        params=params,
    )
    return df.merge(
        dim[["product_id", "name", "category", "brand", "unit"]],
        on="product_id",
        how="left",
    )


def sales_by_brand(engine: Engine, f: Filters, dim: pd.DataFrame) -> pd.DataFrame:
    """Revenue / units rolled up to the brand level."""
    prod = sales_by_product(engine, f, dim)
    if prod.empty:
        return pd.DataFrame(columns=["brand", "revenue", "units", "transactions", "skus"])
    out = (
        prod.groupby("brand")
        .agg(revenue=("revenue", "sum"), units=("units", "sum"),
             transactions=("transactions", "sum"), skus=("product_id", "nunique"))
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    return out


def top_products(engine: Engine, f: Filters, dim: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    """The n best-selling SKUs by revenue for the slice."""
    prod = sales_by_product(engine, f, dim)
    cols = ["name", "category", "brand", "revenue", "units", "transactions"]
    if prod.empty:
        return pd.DataFrame(columns=cols)
    return prod.sort_values("revenue", ascending=False).head(n)[cols].reset_index(drop=True)


# -----------------------------------------------------------------------------
# 2. CUSTOMER reports  (utang / credit / activity)
# -----------------------------------------------------------------------------
def customer_balances(engine: Engine) -> pd.DataFrame:
    """Per-customer credit standing + lifetime activity.

    Joins ``v_customer_balances`` (the running-balance view) with transaction
    activity so credit risk and spend can be read together.
    """
    return pd.read_sql(
        text(
            """
            SELECT vb.customer_id, vb.full_name, vb.nickname, vb.credit_limit,
                   vb.total_utang, vb.total_paid, vb.balance, vb.credit_available,
                   COALESCE(act.n_transactions, 0)  AS n_transactions,
                   COALESCE(act.lifetime_spend, 0)  AS lifetime_spend,
                   act.last_purchase
            FROM v_customer_balances vb
            LEFT JOIN (
                SELECT t.customer_id,
                       COUNT(DISTINCT t.transaction_id)        AS n_transactions,
                       SUM(ti.quantity * ti.unit_price)        AS lifetime_spend,
                       MAX(t.transaction_date)::date           AS last_purchase
                FROM transactions t
                JOIN transaction_items ti ON ti.transaction_id = t.transaction_id
                WHERE t.customer_id IS NOT NULL
                GROUP BY t.customer_id
            ) act ON act.customer_id = vb.customer_id
            ORDER BY vb.balance DESC
            """
        ),
        engine,
    )


def customer_directory(engine: Engine) -> pd.DataFrame:
    """Lightweight (id, full_name, nickname) list for pickers/search."""
    return pd.read_sql(
        text(
            "SELECT customer_id, full_name, nickname FROM customers "
            "ORDER BY full_name"
        ),
        engine,
    )


def customer_detail(engine: Engine, customer_id: int) -> dict:
    """One customer's credit standing + activity (single row from the balances)."""
    df = pd.read_sql(
        text(
            """
            SELECT vb.customer_id, vb.full_name, vb.nickname, vb.credit_limit,
                   vb.total_utang, vb.total_paid, vb.balance, vb.credit_available,
                   COALESCE(act.n_transactions, 0) AS n_transactions,
                   COALESCE(act.lifetime_spend, 0) AS lifetime_spend,
                   act.first_purchase, act.last_purchase
            FROM v_customer_balances vb
            LEFT JOIN (
                SELECT t.customer_id,
                       COUNT(DISTINCT t.transaction_id) AS n_transactions,
                       SUM(ti.quantity * ti.unit_price) AS lifetime_spend,
                       MIN(t.transaction_date)::date    AS first_purchase,
                       MAX(t.transaction_date)::date    AS last_purchase
                FROM transactions t
                JOIN transaction_items ti ON ti.transaction_id = t.transaction_id
                WHERE t.customer_id = :cid
                GROUP BY t.customer_id
            ) act ON act.customer_id = vb.customer_id
            WHERE vb.customer_id = :cid
            """
        ),
        engine,
        params={"cid": int(customer_id)},
    )
    return {} if df.empty else df.iloc[0].to_dict()


def customer_ledger(engine: Engine, customer_id: int) -> pd.DataFrame:
    """The digital utang page: charges & payments on one timeline w/ running balance."""
    return pd.read_sql(
        text(
            """
            SELECT entry_date::date AS entry_date, entry_type, reference,
                   debit, credit, running_balance
            FROM v_utang_ledger
            WHERE customer_id = :cid
            ORDER BY entry_date, reference
            """
        ),
        engine,
        params={"cid": int(customer_id)},
    )


def customer_transactions(engine: Engine, customer_id: int, limit: int = 50) -> pd.DataFrame:
    """A customer's most recent sales (header amount + item count)."""
    return pd.read_sql(
        text(
            """
            SELECT t.transaction_id,
                   t.transaction_date::date            AS date,
                   t.payment_type,
                   SUM(ti.quantity)                    AS items,
                   SUM(ti.quantity * ti.unit_price)    AS amount
            FROM transactions t
            JOIN transaction_items ti ON ti.transaction_id = t.transaction_id
            WHERE t.customer_id = :cid
            GROUP BY t.transaction_id, t.transaction_date, t.payment_type
            ORDER BY t.transaction_date DESC
            LIMIT :lim
            """
        ),
        engine,
        params={"cid": int(customer_id), "lim": int(limit)},
    )


# -----------------------------------------------------------------------------
# 3. STOCK reports
# -----------------------------------------------------------------------------
def stock_report(engine: Engine, f: Filters | None = None, dim: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-product stock from ``v_product_stock`` + price -> inventory value.

    ``on_hand`` is the strictly-derived, point-in-time figure (it is cumulative,
    so the date window does not apply); the *group* and *brand* filters do apply
    and are resolved in pandas against the tiny 188-row report.
    """
    df = pd.read_sql(
        text(
            """
            SELECT vs.product_id, vs.product, vs.category, vs.unit,
                   vs.reorder_level, vs.total_restocked, vs.total_sold,
                   vs.on_hand, vs.maintained_on_hand, vs.needs_reorder,
                   p.current_price,
                   (vs.on_hand * p.current_price) AS stock_value
            FROM v_product_stock vs
            JOIN products p ON p.product_id = vs.product_id
            ORDER BY vs.product
            """
        ),
        engine,
    )
    df["brand"] = df["product"].map(derive_brand)
    if f is not None and f.has_product_filter:
        if f.categories:
            df = df[df["category"].isin(f.categories)]
        if f.brands:
            df = df[df["brand"].isin(f.brands)]
    return df.reset_index(drop=True)
