"""Create the schema and bulk-load the synthesized CSVs into PostgreSQL.

Bulk-load strategy (the standard DE pattern):
  1. Apply ``schema.sql`` (drops & recreates everything → empty tables).
  2. In ONE transaction: disable the stock-maintenance triggers, ``COPY`` every
     CSV (FK-safe order), recompute ``products.stock_on_hand`` in a single set
     based UPDATE, re-enable the triggers, and realign identity sequences.

Disabling the per-row triggers during COPY turns hundreds of thousands of
single-row UPDATEs into one bulk UPDATE — orders of magnitude faster — while
the derived ``v_product_stock`` view still proves the result is correct.
"""
from __future__ import annotations

import csv
from pathlib import Path

import psycopg

from . import TABLES_IN_LOAD_ORDER
from .config import Settings, settings as default_settings
from .db import get_connection, run_script

# Column lists are read from each CSV header at load time, so they always match.
_TRUNCATE = "TRUNCATE {} RESTART IDENTITY CASCADE;"

_RECOMPUTE_STOCK = """
UPDATE products p
SET stock_on_hand = sub.on_hand
FROM (
    SELECT pr.product_id,
           COALESCE(ri.qin, 0) - COALESCE(ti.qout, 0) AS on_hand
    FROM products pr
    LEFT JOIN (SELECT product_id, SUM(quantity) AS qin
               FROM restock_items GROUP BY product_id) ri ON ri.product_id = pr.product_id
    LEFT JOIN (SELECT product_id, SUM(quantity) AS qout
               FROM transaction_items GROUP BY product_id) ti ON ti.product_id = pr.product_id
) sub
WHERE p.product_id = sub.product_id;
"""

# (table, id column) for identity-sequence realignment after explicit-id load.
_SEQUENCES = [
    ("categories", "category_id"),
    ("units", "unit_id"),
    ("suppliers", "supplier_id"),
    ("products", "product_id"),
    ("customers", "customer_id"),
    ("restocks", "restock_id"),
    ("restock_items", "restock_item_id"),
    ("transactions", "transaction_id"),
    ("transaction_items", "transaction_item_id"),
    ("credit_payments", "payment_id"),
]


def apply_schema(conn: psycopg.Connection, settings: Settings) -> None:
    sql = settings.schema_sql.read_text(encoding="utf-8")
    run_script(conn, sql)


def _copy_csv(cur: psycopg.Cursor, table: str, path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    cols = ", ".join(f'"{c}"' for c in header)
    sql = f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with cur.copy(sql) as copy:
        with path.open("rb") as fb:
            while chunk := fb.read(1 << 20):
                copy.write(chunk)
    cur.execute(f"SELECT count(*) FROM {table}")
    return cur.fetchone()[0]


def load(settings: Settings = default_settings, *, apply_ddl: bool = True) -> dict[str, int]:
    """Run the full load. Returns per-table row counts in the database."""
    counts: dict[str, int] = {}
    conn = get_connection(settings)
    try:
        if apply_ddl:
            conn.autocommit = True
            apply_schema(conn, settings)
            conn.autocommit = False

        with conn.cursor() as cur:
            # 1. silence stock triggers for the duration of the load
            cur.execute("ALTER TABLE transaction_items DISABLE TRIGGER trg_sale_stock")
            cur.execute("ALTER TABLE restock_items DISABLE TRIGGER trg_restock_stock")

            # 2. fresh tables (no-op right after apply_schema, but makes re-loads safe)
            for table in reversed(TABLES_IN_LOAD_ORDER):
                cur.execute(_TRUNCATE.format(table))

            # 3. COPY every CSV in FK-safe order
            for table in TABLES_IN_LOAD_ORDER:
                path = settings.csv_dir / f"{table}.csv"
                if not path.exists():
                    raise FileNotFoundError(f"missing CSV: {path}")
                counts[table] = _copy_csv(cur, table, path)

            # 4. set the maintained stock column from first principles (one UPDATE)
            cur.execute(_RECOMPUTE_STOCK)

            # 5. restore triggers for normal day-to-day operations
            cur.execute("ALTER TABLE transaction_items ENABLE TRIGGER trg_sale_stock")
            cur.execute("ALTER TABLE restock_items ENABLE TRIGGER trg_restock_stock")

            # 6. realign identity sequences so future inserts continue cleanly
            for table, col in _SEQUENCES:
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence(%s, %s), "
                    f"COALESCE((SELECT MAX({col}) FROM {table}), 1))",
                    (table, col),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return counts
