-- =============================================================================
--  03_3nf_migrate.sql  —  Third Normal Form (Final Schema)
--
--  Rules for 3NF (requires 2NF first):
--    No non-key attribute may depend on another non-key attribute.
--    Every "fact" must depend directly on the key, the whole key, and nothing
--    but the key.  Stored derived values violate this rule because they
--    functionally depend on other rows, not on the row's own key.
--
--  This file transforms the 2NF schema into the same logical structure as the
--  production schema defined in schema.sql — ten tables and two views, all
--  housed in the norm_demo schema so they sit alongside the 2NF tables for
--  easy side-by-side comparison.
--
--  Run 00_raw.sql → 01_1nf.sql → 02_2nf.sql first.
-- =============================================================================

-- Drop 3NF tables in reverse dependency order (safe to re-run).
DROP VIEW  IF EXISTS norm_demo.v_product_stock       CASCADE;
DROP VIEW  IF EXISTS norm_demo.v_customer_balances   CASCADE;
DROP TABLE IF EXISTS norm_demo.credit_payments       CASCADE;
DROP TABLE IF EXISTS norm_demo.transaction_items     CASCADE;
DROP TABLE IF EXISTS norm_demo.transactions          CASCADE;
DROP TABLE IF EXISTS norm_demo.restock_items         CASCADE;
DROP TABLE IF EXISTS norm_demo.restocks              CASCADE;
DROP TABLE IF EXISTS norm_demo.customers             CASCADE;
DROP TABLE IF EXISTS norm_demo.products              CASCADE;
DROP TABLE IF EXISTS norm_demo.suppliers             CASCADE;
DROP TABLE IF EXISTS norm_demo.units                 CASCADE;
DROP TABLE IF EXISTS norm_demo.categories            CASCADE;


-- =============================================================================
--  STEP A: Extract categories and units
--
--  Diagnosis in nf2_products:
--    product_id → category → category_desc   (transitive: desc depends on category,
--                                             not directly on product_id)
--    product_id → unit_code → unit_label     (transitive: label depends on unit_code)
--
--  Fix: give each concept its own table.  A product now stores only the FK.
-- =============================================================================

CREATE TABLE norm_demo.categories AS
SELECT DISTINCT
    ROW_NUMBER() OVER (ORDER BY category)::INT AS category_id,
    category        AS name,
    category_desc   AS description
FROM norm_demo.nf2_products;

ALTER TABLE norm_demo.categories ADD PRIMARY KEY (category_id);
ALTER TABLE norm_demo.categories ADD UNIQUE (name);

-- Verify: 6 rows — one per product group.
-- SELECT * FROM norm_demo.categories ORDER BY category_id;


CREATE TABLE norm_demo.units AS
SELECT DISTINCT
    ROW_NUMBER() OVER (ORDER BY unit_code)::INT AS unit_id,
    unit_code AS code,
    unit_label AS name
FROM norm_demo.nf2_products;

ALTER TABLE norm_demo.units ADD PRIMARY KEY (unit_id);
ALTER TABLE norm_demo.units ADD UNIQUE (code);


-- =============================================================================
--  STEP B: Extract suppliers (carried from 2NF, renamed for production parity)
-- =============================================================================

CREATE TABLE norm_demo.suppliers AS
SELECT supplier_id, supplier_name AS name, supplier_contact AS contact_person,
       supplier_phone AS phone, supplier_address AS address
FROM norm_demo.nf2_suppliers;

ALTER TABLE norm_demo.suppliers ADD PRIMARY KEY (supplier_id);
ALTER TABLE norm_demo.suppliers ADD UNIQUE (name);


-- =============================================================================
--  STEP C: Rebuild products — drop all transitive columns and stored stock
--
--  Dropped columns:
--    category, category_desc  → replaced by category_id FK
--    unit_code, unit_label    → replaced by unit_id FK
--    stock_count              → REMOVED ENTIRELY (see comment below)
--
--  Why drop stock_count?
--    stock_count is a count derived from restock and sale activity.  It depends
--    on all of the restock_items and transaction_items rows, not on the product's
--    own primary key.  Storing it here violates 3NF and creates an update anomaly:
--    every sale or restock must also update this column — and in the raw notebook,
--    it was always at least one sale behind.
--
--    The production schema (schema.sql) maintains stock_on_hand via a trigger as a
--    performance concession for fast POS reads, but it is always verified against
--    the strictly-derived v_product_stock view after any bulk load.  For the
--    tutorial data we skip that complication and rely solely on the view.
-- =============================================================================

CREATE TABLE norm_demo.products AS
SELECT
    p.product_id,
    c.category_id,       -- FK; dropped: category TEXT, category_desc TEXT
    u.unit_id,           -- FK; dropped: unit_code TEXT, unit_label TEXT
    p.product_name   AS name,
    p.barcode,
    p.selling_price  AS current_price,
    p.reorder_qty    AS reorder_level
    -- stock_count INTENTIONALLY OMITTED — derived, stored in a view instead.
FROM norm_demo.nf2_products p
JOIN norm_demo.categories c ON c.name = p.category
JOIN norm_demo.units      u ON u.code = p.unit_code;

ALTER TABLE norm_demo.products ADD PRIMARY KEY (product_id);
ALTER TABLE norm_demo.products
    ADD FOREIGN KEY (category_id) REFERENCES norm_demo.categories(category_id);
ALTER TABLE norm_demo.products
    ADD FOREIGN KEY (unit_id) REFERENCES norm_demo.units(unit_id);


-- =============================================================================
--  STEP D: Rebuild customers — drop stored balance
--
--  customer_balance stored in nf2_customers is a violation of 3NF:
--    customer_id → balance
--    but balance is actually: SUM(credit sales for this customer) − SUM(payments)
--    It therefore depends on transaction_items and credit_payments, not on
--    the customer row itself.
--
--  Fix: drop the column.  A view recalculates it correctly and always reflects
--  the actual state of the ledger without any manual update anomalies.
-- =============================================================================

CREATE TABLE norm_demo.customers AS
SELECT
    customer_id,
    customer_name     AS full_name,
    customer_nickname AS nickname,
    customer_phone    AS phone
    -- customer_balance DROPPED — derived from transaction_items and credit_payments.
    -- Removing it eliminates the anomaly shown in 00_raw.sql where Aling Maria's
    -- balance appeared as 0.00 on consecutive credit sales.
FROM norm_demo.nf2_customers;

ALTER TABLE norm_demo.customers ADD PRIMARY KEY (customer_id);


-- =============================================================================
--  STEP E: Introduce credit_payments — a new first-class entity
--
--  In the raw notebook, payments were invisible: only the running balance was
--  written down.  3NF normalization reveals that a PAYMENT is a distinct fact
--  (who paid, how much, when) that deserves its own table.
--
--  This is one of the most valuable outcomes of normalization: it forces us to
--  record events we were previously only summarizing.
--
--  For this tutorial the sample data has no payment rows — only the starting
--  stub table is created, mirroring the production schema.
-- =============================================================================

CREATE TABLE norm_demo.credit_payments (
    payment_id   INT  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  INT  NOT NULL REFERENCES norm_demo.customers(customer_id),
    amount       NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    payment_date DATE NOT NULL,
    notes        TEXT
);
-- Note: no rows inserted here because no payment events were recorded in the raw
-- notebook (only the balance was noted).  In a real migration from paper, each
-- payment date and amount would be reconstructed from the notebook margins.


-- =============================================================================
--  STEP F: Rebuild transactions — drop derived total_amount
--
--  total_amount = SUM(qty × unit_price) across all transaction_items for this
--  sale.  It depends on transaction_items, not on the transaction row.
--  Dropping it eliminates the update anomaly: a price correction on one item
--  would otherwise require also updating the total on the header row.
--
--  The credit_requires_customer constraint mirrors the production schema:
--  a credit sale must name a customer (NULL = anonymous cash walk-in is only
--  valid for cash transactions).
-- =============================================================================

CREATE TABLE norm_demo.transactions AS
SELECT
    sale_id        AS transaction_id,
    customer_id,   -- nullable FK: NULL = cash walk-in
    sale_date      AS transaction_date,
    payment_type,
    notes
    -- total_amount DROPPED — derivable from SUM(transaction_items.qty * unit_price)
FROM norm_demo.nf2_sales;

ALTER TABLE norm_demo.transactions ADD PRIMARY KEY (transaction_id);
ALTER TABLE norm_demo.transactions
    ADD FOREIGN KEY (customer_id) REFERENCES norm_demo.customers(customer_id);
ALTER TABLE norm_demo.transactions
    ADD CONSTRAINT credit_requires_customer
    CHECK (payment_type <> 'credit' OR customer_id IS NOT NULL);


-- =============================================================================
--  STEP G: Rebuild transaction_items — replace product TEXT with product FK
--
--  nf2_sale_items referenced products by name (a text column).  This provided no
--  referential integrity: a typo in a product name would silently create an orphan
--  row.  Replacing it with product_id enforces that every line item points to a
--  real, known product.
-- =============================================================================

CREATE TABLE norm_demo.transaction_items AS
SELECT
    i.item_id       AS transaction_item_id,
    i.sale_id       AS transaction_id,
    p.product_id,   -- FK replaces product_name TEXT
    i.qty           AS quantity,
    i.unit_price    -- price snapshot: what the customer paid, regardless of today's price
FROM norm_demo.nf2_sale_items i
JOIN norm_demo.products p ON p.name = i.product_name;

ALTER TABLE norm_demo.transaction_items ADD PRIMARY KEY (transaction_item_id);
ALTER TABLE norm_demo.transaction_items
    ADD FOREIGN KEY (transaction_id) REFERENCES norm_demo.transactions(transaction_id)
    ON DELETE CASCADE;
ALTER TABLE norm_demo.transaction_items
    ADD FOREIGN KEY (product_id) REFERENCES norm_demo.products(product_id);


-- =============================================================================
--  STEP H: Introduce restocks header + rebuild restock_items
--
--  nf2_deliveries becomes norm_demo.restocks (renamed for production parity).
--  nf2_delivery_items is rebuilt to:
--    • Replace product_name TEXT with product_id FK
--    • Drop product_category (transitive: product → category)
--    • Drop product_unit (transitive: product → unit)
--    • Drop line_total (derived: qty_received × unit_cost)
-- =============================================================================

CREATE TABLE norm_demo.restocks AS
SELECT
    delivery_id   AS restock_id,
    supplier_id,
    delivery_date AS restock_date,
    reference_no,
    notes
FROM norm_demo.nf2_deliveries;

ALTER TABLE norm_demo.restocks ADD PRIMARY KEY (restock_id);
ALTER TABLE norm_demo.restocks
    ADD FOREIGN KEY (supplier_id) REFERENCES norm_demo.suppliers(supplier_id);


CREATE TABLE norm_demo.restock_items AS
SELECT
    di.delivery_item_id AS restock_item_id,
    d.restock_id,
    p.product_id,       -- FK replaces product_name TEXT
    di.qty_received     AS quantity,
    di.unit_cost        -- cost snapshot: what we paid, regardless of today's price
    -- product_category DROPPED (transitive: product → category)
    -- product_unit     DROPPED (transitive: product → unit)
    -- line_total       DROPPED (derived: qty_received × unit_cost)
FROM norm_demo.nf2_delivery_items di
JOIN norm_demo.restocks d ON d.restock_id = di.delivery_id
JOIN norm_demo.products p ON p.name       = di.product_name;

ALTER TABLE norm_demo.restock_items ADD PRIMARY KEY (restock_item_id);
ALTER TABLE norm_demo.restock_items
    ADD FOREIGN KEY (restock_id) REFERENCES norm_demo.restocks(restock_id)
    ON DELETE CASCADE;
ALTER TABLE norm_demo.restock_items
    ADD FOREIGN KEY (product_id) REFERENCES norm_demo.products(product_id);


-- =============================================================================
--  STEP I: Replace stored derived values with views
--
--  Two stored values were removed:
--    stock_count      (from products)  → v_product_stock
--    customer_balance (from customers) → v_customer_balances
--
--  Views are always correct because they are computed on every query from the
--  authoritative source rows.  There is no anomaly possible: the data has one
--  owner (the transaction and restock rows), and the view is the lens.
-- =============================================================================

-- v_product_stock replaces products.stock_count
CREATE VIEW norm_demo.v_product_stock AS
SELECT
    p.product_id,
    p.name                                                   AS product,
    c.name                                                   AS category,
    u.code                                                   AS unit,
    p.reorder_level,
    COALESCE(SUM(ri.quantity), 0)                            AS total_restocked,
    COALESCE(SUM(ti.quantity), 0)                            AS total_sold,
    COALESCE(SUM(ri.quantity), 0) - COALESCE(SUM(ti.quantity), 0) AS on_hand,
    (COALESCE(SUM(ri.quantity), 0) - COALESCE(SUM(ti.quantity), 0))
        <= p.reorder_level                                   AS needs_reorder
FROM norm_demo.products       p
JOIN norm_demo.categories     c  ON c.category_id = p.category_id
JOIN norm_demo.units          u  ON u.unit_id      = p.unit_id
LEFT JOIN norm_demo.restock_items  ri ON ri.product_id = p.product_id
LEFT JOIN norm_demo.transaction_items ti ON ti.product_id = p.product_id
GROUP BY p.product_id, p.name, c.name, u.code, p.reorder_level;


-- v_customer_balances replaces customers.customer_balance
-- balance = sum of all credit sale charges − sum of all payments
CREATE VIEW norm_demo.v_customer_balances AS
SELECT
    c.customer_id,
    c.full_name,
    c.nickname,
    COALESCE(SUM(ti.quantity * ti.unit_price)
        FILTER (WHERE t.payment_type = 'credit'), 0)         AS total_utang,
    COALESCE((SELECT SUM(cp.amount)
              FROM norm_demo.credit_payments cp
              WHERE cp.customer_id = c.customer_id), 0)      AS total_paid,
    COALESCE(SUM(ti.quantity * ti.unit_price)
        FILTER (WHERE t.payment_type = 'credit'), 0)
    - COALESCE((SELECT SUM(cp.amount)
                FROM norm_demo.credit_payments cp
                WHERE cp.customer_id = c.customer_id), 0)    AS balance
FROM norm_demo.customers         c
LEFT JOIN norm_demo.transactions t  ON t.customer_id      = c.customer_id
LEFT JOIN norm_demo.transaction_items ti ON ti.transaction_id = t.transaction_id
GROUP BY c.customer_id, c.full_name, c.nickname;

-- Verify the balance view — compare to the stale values in 00_raw.sql:
-- SELECT full_name, nickname, total_utang, total_paid, balance
-- FROM norm_demo.v_customer_balances ORDER BY balance DESC;
--
-- Expected: Aling Maria = 71 + 15 + 20 = 106.00 (not the stale 0.00 or 50.00)
--           Mang Jose   = 76 + 23       =  99.00 (not the stale 0.00)
--           Ate Linda   = 186 + 40      = 226.00 (not the stale 0.00)


-- =============================================================================
--  FINAL COMPARISON: raw → 1NF → 2NF → 3NF
--  -----------------------------------------
--
--  Stage   Tables   Columns   Key properties
--  ------  -------  --------  -----------------------------------------------
--  raw          3       41    No PKs, repeating groups, NULLs, stored derived
--                             values, no referential integrity
--  1NF          5       39    PKs added, repeating groups unnested into rows,
--                             no more multi-valued cells
--  2NF          7       36    Partial dependencies removed: suppliers and
--                             customers extracted; delivery header/line split
--  3NF         10       28    Transitive deps removed (categories, units);
--                             ALL stored derived values replaced by views;
--                             all text product references become FK columns
--  + views      2        —    v_product_stock, v_customer_balances
--
--  "A fact lives in exactly one place." — that is 3NF.
--
--  The norm_demo schema is now structurally identical to the production `public`
--  schema defined in schema.sql (with sample data instead of 676,767 rows).
--  Run them side by side:
--    SELECT * FROM norm_demo.v_customer_balances;
--    SELECT * FROM public.v_customer_balances LIMIT 10;
-- =============================================================================
