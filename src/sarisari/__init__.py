"""Digital Sari-Sari Store — data engineering toolkit.

Subpackages / modules:
  - config       : environment-driven settings & paths
  - catalog      : the Filipino-brand product catalog (6 product groups)
  - synthesize   : generate a realistic ~676,767-row dataset to CSV
  - db           : PostgreSQL connection helpers (DATABASE_URL or local pgserver)
  - loader       : create the schema and bulk-load the CSVs via COPY
"""

__version__ = "0.1.0"

# The canonical load order (parents before children) for FK-safe inserts.
TABLES_IN_LOAD_ORDER = [
    "categories",
    "units",
    "suppliers",
    "products",
    "customers",
    "restocks",
    "restock_items",
    "transactions",
    "transaction_items",
    "credit_payments",
]
