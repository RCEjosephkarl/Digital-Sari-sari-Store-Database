"""Command-line entry points (also wired as console scripts in pyproject.toml)."""
from __future__ import annotations

import time

from . import TABLES_IN_LOAD_ORDER
from .config import settings
from .db import get_connection
from .loader import load
from .synthesize import synthesize, write_csvs


def synthesize_main() -> None:
    print(f"Synthesizing ~{settings.target_rows:,} rows (seed={settings.seed}) ...")
    t0 = time.time()
    frames = synthesize(settings)
    sizes = write_csvs(frames, settings)
    total = sum(sizes.values())
    print(f"\nWrote {len(sizes)} CSV files to {settings.csv_dir} in {time.time()-t0:,.1f}s")
    width = max(len(n) for n in sizes)
    for name in TABLES_IN_LOAD_ORDER:
        print(f"  {name:<{width}}  {sizes[name]:>10,}")
    print(f"  {'TOTAL':<{width}}  {total:>10,}")


def load_main() -> None:
    print("Creating schema and loading CSVs into PostgreSQL ...")
    t0 = time.time()
    counts = load(settings)
    total = sum(counts.values())
    width = max(len(n) for n in counts)
    for name in TABLES_IN_LOAD_ORDER:
        print(f"  {name:<{width}}  {counts[name]:>10,}")
    print(f"  {'TOTAL':<{width}}  {total:>10,}")
    print(f"Loaded in {time.time()-t0:,.1f}s")


def verify_main() -> None:
    conn = get_connection(settings)
    try:
        with conn.cursor() as cur:
            print("Row counts:")
            grand = 0
            for table in TABLES_IN_LOAD_ORDER:
                cur.execute(f"SELECT count(*) FROM {table}")
                n = cur.fetchone()[0]
                grand += n
                print(f"  {table:<20} {n:>10,}")
            print(f"  {'TOTAL':<20} {grand:>10,}")

            cur.execute(
                "SELECT count(*) FROM v_product_stock WHERE on_hand <> maintained_on_hand"
            )
            drift = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM products WHERE stock_on_hand < 0")
            negative = cur.fetchone()[0]
            print(f"\nStock reconcile — derived vs maintained mismatches: {drift}")
            print(f"Products with negative stock: {negative}")

            cur.execute("SELECT count(*) FROM v_customer_balances WHERE balance < 0")
            neg_bal = cur.fetchone()[0]
            cur.execute("SELECT round(sum(balance), 2) FROM v_customer_balances")
            total_utang = cur.fetchone()[0]
            print(f"Customers with negative balance: {neg_bal}")
            print(f"Total outstanding utang: PHP {total_utang:,}")

            print("\nTop 5 product groups by units sold:")
            cur.execute(
                """
                SELECT c.name, SUM(ti.quantity) AS units, round(SUM(ti.quantity*ti.unit_price),2) AS sales
                FROM transaction_items ti
                JOIN products p ON p.product_id = ti.product_id
                JOIN categories c ON c.category_id = p.category_id
                GROUP BY c.name ORDER BY units DESC LIMIT 5
                """
            )
            for name, units, sales in cur.fetchall():
                print(f"  {name:<24} {units:>10,} units   PHP {sales:>14,}")
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    import sys

    {"synthesize": synthesize_main, "load": load_main, "verify": verify_main}[
        sys.argv[1]
    ]()
