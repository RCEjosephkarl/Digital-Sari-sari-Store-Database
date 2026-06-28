-- =============================================================================
--  01_1nf.sql  —  First Normal Form
--
--  Rules for 1NF:
--    1. Every column holds exactly one atomic value (no lists, no sets).
--    2. Every row has a unique identifier (primary key).
--    3. No repeating groups — a "group" of similar columns (item1_, item2_…)
--       must become separate rows in a separate table.
--
--  Run 00_raw.sql first.  This file reads from norm_demo.raw_* tables.
-- =============================================================================

-- Drop tables in reverse dependency order (safe to re-run).
DROP TABLE IF EXISTS norm_demo.nf1_product_alt_suppliers CASCADE;
DROP TABLE IF EXISTS norm_demo.nf1_sales_items           CASCADE;
DROP TABLE IF EXISTS norm_demo.nf1_sales_header          CASCADE;
DROP TABLE IF EXISTS norm_demo.nf1_delivery_log          CASCADE;
DROP TABLE IF EXISTS norm_demo.nf1_inventory             CASCADE;


-- =============================================================================
--  FIX 1: nf1_inventory
--  Change: Add surrogate primary key.  Split multi-valued alt_suppliers into
--          a separate companion table.
--
--  What we fix here    → [NO-PK] and [1NF] from 00_raw.sql
--  What remains        → [2NF] supplier_contact/phone/address still repeat;
--                        [3NF] category_desc, unit_label still transitive;
--                        [3NF] stock_count still a stored derived value.
-- =============================================================================

CREATE TABLE norm_demo.nf1_inventory AS
SELECT
    -- Surrogate PK: ROW_NUMBER assigns a stable id within this small sample set.
    ROW_NUMBER() OVER (ORDER BY product_name, supplier_name)::INT AS product_id,
    product_name,
    barcode,
    category,
    category_desc,    -- still a [3NF] transitive dependency (category → desc)
    unit_code,
    unit_label,       -- still a [3NF] transitive dependency (unit_code → label)
    selling_price,
    reorder_qty,
    stock_count,      -- still a [3NF] stored derived value
    supplier_name,
    supplier_contact, -- still a [2NF] partial dependency on supplier_name
    supplier_phone,
    supplier_address
    -- alt_suppliers intentionally excluded: it was the non-atomic column.
    -- Its contents are redistributed below into nf1_product_alt_suppliers.
FROM norm_demo.raw_inventory;

ALTER TABLE norm_demo.nf1_inventory ADD PRIMARY KEY (product_id);

-- The formerly comma/semicolon-separated list now lives as proper rows.
-- One alt supplier per row = atomic.  Query "all products from Divisoria" becomes:
--   SELECT i.* FROM nf1_inventory i
--   JOIN nf1_product_alt_suppliers a USING (product_id)
--   WHERE a.alt_supplier_name = 'Divisoria Wholesale Center';
CREATE TABLE norm_demo.nf1_product_alt_suppliers (
    product_id        INT  NOT NULL REFERENCES norm_demo.nf1_inventory(product_id),
    alt_supplier_name TEXT NOT NULL,
    PRIMARY KEY (product_id, alt_supplier_name)
);

-- Populate by splitting the semicolon-delimited string into individual rows.
INSERT INTO norm_demo.nf1_product_alt_suppliers (product_id, alt_supplier_name)
SELECT
    i.product_id,
    TRIM(part) AS alt_supplier_name
FROM norm_demo.nf1_inventory i
JOIN norm_demo.raw_inventory  r
    ON  r.product_name    = i.product_name
    AND r.supplier_name   = i.supplier_name   -- match the row we built the id from
JOIN LATERAL REGEXP_SPLIT_TO_TABLE(r.alt_suppliers, ';') AS part ON TRUE
WHERE r.alt_suppliers IS NOT NULL
  AND TRIM(part) <> '';


-- =============================================================================
--  FIX 2a: nf1_sales_header
--  Change: Add surrogate primary key.  Strip the item1_/item2_/item3_ groups —
--          they move to nf1_sales_items below.
--
--  What we fix here    → [NO-PK]
--  What remains        → [3NF] customer_phone/nickname depend on customer_name;
--                        [3NF] customer_balance is a stored derived value;
--                        [3NF] total_amount is a stored derived value.
-- =============================================================================

CREATE TABLE norm_demo.nf1_sales_header AS
SELECT
    ROW_NUMBER() OVER (ORDER BY sale_date, customer_name NULLS LAST)::INT AS sale_id,
    sale_date,
    customer_name,
    customer_phone,    -- still a [3NF] transitive dependency on customer_name
    customer_nickname, -- still a [3NF] transitive dependency on customer_name
    customer_balance,  -- still a [3NF] stored derived value
    payment_type,
    total_amount,      -- still a [3NF] stored derived value
    notes
FROM norm_demo.raw_sales_ledger;

ALTER TABLE norm_demo.nf1_sales_header ADD PRIMARY KEY (sale_id);


-- =============================================================================
--  FIX 2b: nf1_sales_items
--  This is the key 1NF transformation:
--
--  BEFORE — raw_sales_ledger (10 rows, hard limit of 3 items, many NULLs):
--    sale_date | customer_name | item1_name | item1_qty | item2_name | item2_qty | …
--    2025-01-17| Mang Jose     | Lucky Me   |    2      | 555 Sardines|    1     | Milo | 3 |
--    2025-01-16| (cash)        | Sprite     |    1      |    NULL     |   NULL   | NULL |…  |
--
--  AFTER — nf1_sales_items (24 rows, no NULLs, no column-count limit):
--    item_id | sale_id | product_name    | qty | unit_price
--          1 |       4 | Lucky Me …      |   2 |    14.00
--          2 |       4 | 555 Sardines … |   1 |    21.00
--          3 |       4 | Milo 24g        |   3 |     9.00
--          4 |       3 | Sprite …        |   1 |    20.00
--
--  Adding a 4th item to any transaction is now just an INSERT — no DDL needed.
-- =============================================================================

CREATE TABLE norm_demo.nf1_sales_items (
    item_id       INT  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_id       INT  NOT NULL REFERENCES norm_demo.nf1_sales_header(sale_id),
    product_name  TEXT NOT NULL,  -- still a text reference — [3NF] will add a proper FK
    qty           INT  NOT NULL,
    unit_price    NUMERIC(10,2) NOT NULL
);

-- Unnest each position into its own row using UNION ALL.
-- Rows where a position was NULL are filtered by the WHERE clause.
WITH raw_with_id AS (
    SELECT
        h.sale_id,
        r.item1_name, r.item1_qty, r.item1_price,
        r.item2_name, r.item2_qty, r.item2_price,
        r.item3_name, r.item3_qty, r.item3_price
    FROM norm_demo.raw_sales_ledger r
    JOIN norm_demo.nf1_sales_header h
        ON  h.sale_date      = r.sale_date
        AND h.customer_name  IS NOT DISTINCT FROM r.customer_name
        AND h.payment_type   = r.payment_type
        AND h.total_amount   = r.total_amount
)
INSERT INTO norm_demo.nf1_sales_items (sale_id, product_name, qty, unit_price)
SELECT sale_id, item1_name, item1_qty, item1_price FROM raw_with_id WHERE item1_name IS NOT NULL
UNION ALL
SELECT sale_id, item2_name, item2_qty, item2_price FROM raw_with_id WHERE item2_name IS NOT NULL
UNION ALL
SELECT sale_id, item3_name, item3_qty, item3_price FROM raw_with_id WHERE item3_name IS NOT NULL;

-- Verify the unnesting:
-- SELECT COUNT(*) FROM norm_demo.nf1_sales_items;   -- should be 24 (10 row × avg 2.4 items)
-- SELECT COUNT(*) FROM norm_demo.nf1_sales_header;  -- 10 header rows, unchanged


-- =============================================================================
--  FIX 3: nf1_delivery_log
--  Change: Add surrogate primary key.  The delivery table was already atomic —
--          each cell holds a single value.  The only 1NF fix needed is row identity.
--
--  What we fix here    → [NO-PK]
--  What remains        → [2NF] supplier_contact/phone/address still repeat;
--                        [3NF] product_category/product_unit still transitive;
--                        [3NF] line_total still a stored derived value.
-- =============================================================================

CREATE TABLE norm_demo.nf1_delivery_log AS
SELECT
    ROW_NUMBER() OVER (ORDER BY delivery_date, reference_no, product_name)::INT
        AS delivery_item_id,
    delivery_date,
    reference_no,
    supplier_name,
    supplier_contact, -- still a [2NF] partial dependency on supplier_name
    supplier_phone,
    supplier_address,
    product_name,
    product_category, -- still a [3NF] transitive dependency on product_name
    product_unit,
    qty_received,
    unit_cost,
    line_total,       -- still a [3NF] stored derived value (qty × cost)
    notes
FROM norm_demo.raw_delivery_log;

ALTER TABLE norm_demo.nf1_delivery_log ADD PRIMARY KEY (delivery_item_id);


-- =============================================================================
--  WHAT CHANGED IN 1NF
--  -------------------
--  Before (3 tables, 41 columns, many NULLs per row):
--    raw_inventory     — no PK, multi-valued alt_suppliers column
--    raw_sales_ledger  — no PK, item1_/item2_/item3_ repeating groups, NULLs
--    raw_delivery_log  — no PK, otherwise already atomic
--
--  After (5 tables):
--    nf1_inventory              — surrogate PK added; 15 rows
--    nf1_product_alt_suppliers  — alt_suppliers split into rows; 2 rows
--    nf1_sales_header           — surrogate PK added; 10 rows
--    nf1_sales_items            — repeating groups unnested; 24 rows (0 NULLs)
--    nf1_delivery_log           — surrogate PK added; 12 rows
--
--  1NF does NOT fix update anomalies from repeated supplier/customer data.
--  That is 2NF's job.  Next: 02_2nf.sql.
-- =============================================================================
