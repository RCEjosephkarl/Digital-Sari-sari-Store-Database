-- =============================================================================
--  02_2nf.sql  —  Second Normal Form
--
--  Rules for 2NF (requires 1NF first):
--    Every non-key attribute must depend on the WHOLE primary key, not just
--    part of it.  In tables with composite natural keys, attributes that
--    depend only on one part of that key must be extracted into their own
--    table.  Even with a surrogate PK, we reason about the *natural* key
--    (what uniquely identifies the real entity) to find partial dependencies.
--
--  Run 00_raw.sql then 01_1nf.sql first.
-- =============================================================================

-- Drop in reverse dependency order (safe to re-run).
DROP TABLE IF EXISTS norm_demo.nf2_delivery_items CASCADE;
DROP TABLE IF EXISTS norm_demo.nf2_deliveries     CASCADE;
DROP TABLE IF EXISTS norm_demo.nf2_sale_items     CASCADE;
DROP TABLE IF EXISTS norm_demo.nf2_sales          CASCADE;
DROP TABLE IF EXISTS norm_demo.nf2_customers      CASCADE;
DROP TABLE IF EXISTS norm_demo.nf2_products       CASCADE;
DROP TABLE IF EXISTS norm_demo.nf2_suppliers      CASCADE;


-- =============================================================================
--  STEP A: Extract nf2_suppliers
--
--  Diagnosis: in nf1_inventory the natural composite key (if we remove the
--  surrogate) is (product_name, supplier_name) — a product+supplier pair.
--  supplier_contact, supplier_phone, and supplier_address depend ONLY on
--  supplier_name, not on the full (product_name, supplier_name) pair.
--  That is a PARTIAL DEPENDENCY — a 2NF violation.
--
--  Fix: extract supplier info into its own table, keyed by supplier_name.
--  Result: changing Nestlé's phone number is now ONE UPDATE, not seven.
-- =============================================================================

CREATE TABLE norm_demo.nf2_suppliers AS
SELECT DISTINCT
    ROW_NUMBER() OVER (ORDER BY supplier_name)::INT AS supplier_id,
    supplier_name,
    supplier_contact,
    supplier_phone,
    supplier_address
FROM norm_demo.nf1_inventory;

ALTER TABLE norm_demo.nf2_suppliers ADD PRIMARY KEY (supplier_id);
ALTER TABLE norm_demo.nf2_suppliers ADD UNIQUE (supplier_name);

-- Verify: one row per distinct supplier.
-- SELECT supplier_id, supplier_name FROM norm_demo.nf2_suppliers ORDER BY supplier_id;
-- Before: each of 8 rows in nf1_inventory carried full supplier contact data.
-- After: 6 rows here, each supplier's info stored exactly once.


-- =============================================================================
--  STEP B: Rebuild nf2_products with supplier_id FK
--
--  The four supplier text columns are replaced by a single integer FK.
--  category_desc, unit_label, and stock_count remain — they are 3NF issues.
-- =============================================================================

CREATE TABLE norm_demo.nf2_products AS
SELECT
    i.product_id,
    i.product_name,
    i.barcode,
    i.category,
    i.category_desc,   -- [3NF] still transitive: category → category_desc
    i.unit_code,
    i.unit_label,      -- [3NF] still transitive: unit_code → unit_label
    i.selling_price,
    i.reorder_qty,
    i.stock_count,     -- [3NF] still a stored derived value
    s.supplier_id      -- FK replaces: supplier_name, supplier_contact, supplier_phone, supplier_address
FROM norm_demo.nf1_inventory i
JOIN norm_demo.nf2_suppliers s ON s.supplier_name = i.supplier_name;

ALTER TABLE norm_demo.nf2_products ADD PRIMARY KEY (product_id);
ALTER TABLE norm_demo.nf2_products
    ADD FOREIGN KEY (supplier_id) REFERENCES norm_demo.nf2_suppliers(supplier_id);

-- Update anomaly eliminated:
--   Before: UPDATE nf1_inventory SET supplier_phone = '09221330099'
--           WHERE supplier_name = 'Nestlé Philippines Dealer';  → touches 3 rows
--   After:  UPDATE nf2_suppliers SET supplier_phone = '09221330099'
--           WHERE supplier_name = 'Nestlé Philippines Dealer';  → touches 1 row


-- =============================================================================
--  STEP C: Extract nf2_customers
--
--  Diagnosis: in nf1_sales_header the natural key is (sale_date, customer_name).
--  customer_phone and customer_nickname depend only on customer_name, not on the
--  full (sale_date, customer_name) pair.  Partial dependency → 2NF violation.
--  customer_balance also depends only on customer_name (it is the accumulated
--  utang for that customer) — but it is additionally a DERIVED value, so it
--  will be removed entirely in 3NF.  We keep it here to show the 2NF step
--  clearly.
-- =============================================================================

CREATE TABLE norm_demo.nf2_customers AS
SELECT DISTINCT
    ROW_NUMBER() OVER (ORDER BY customer_name)::INT AS customer_id,
    customer_name,
    customer_phone,
    customer_nickname,
    customer_balance   -- [3NF] stored derived — will be dropped in 03_3nf_migrate.sql
FROM norm_demo.nf1_sales_header
WHERE customer_name IS NOT NULL;   -- cash walk-ins (NULL) have no customer record

ALTER TABLE norm_demo.nf2_customers ADD PRIMARY KEY (customer_id);
ALTER TABLE norm_demo.nf2_customers ADD UNIQUE (customer_name);


-- =============================================================================
--  STEP D: Rebuild nf2_sales with customer_id FK
--
--  total_amount remains (still a stored derived value — 3NF fix).
--  Cash walk-in rows (customer_name IS NULL) keep NULL for customer_id.
-- =============================================================================

CREATE TABLE norm_demo.nf2_sales AS
SELECT
    h.sale_id,
    h.sale_date,
    c.customer_id,   -- FK replaces: customer_name, customer_phone, customer_nickname, customer_balance
    h.payment_type,
    h.total_amount,  -- [3NF] still a stored derived value
    h.notes
FROM norm_demo.nf1_sales_header h
LEFT JOIN norm_demo.nf2_customers c ON c.customer_name = h.customer_name;

ALTER TABLE norm_demo.nf2_sales ADD PRIMARY KEY (sale_id);
ALTER TABLE norm_demo.nf2_sales
    ADD FOREIGN KEY (customer_id) REFERENCES norm_demo.nf2_customers(customer_id);
-- Note: customer_id is nullable (NULL = cash walk-in, no customer record needed).


-- =============================================================================
--  STEP E: Carry nf1_sales_items forward as nf2_sale_items (unchanged in 2NF)
--
--  The sale items table has no 2NF issue: every column (product_name, qty,
--  unit_price) depends on the full (sale_id, item_id) key.  product_name is
--  still a text reference without referential integrity — that is a 3NF fix.
-- =============================================================================

CREATE TABLE norm_demo.nf2_sale_items AS
SELECT item_id, sale_id, product_name, qty, unit_price
FROM norm_demo.nf1_sales_items;

ALTER TABLE norm_demo.nf2_sale_items ADD PRIMARY KEY (item_id);
ALTER TABLE norm_demo.nf2_sale_items
    ADD FOREIGN KEY (sale_id) REFERENCES norm_demo.nf2_sales(sale_id);


-- =============================================================================
--  STEP F: Formalize the delivery header/line split
--
--  Diagnosis: in nf1_delivery_log the natural composite key is
--  (reference_no, product_name).  supplier_contact/phone/address depend only
--  on supplier_name (and supplier_name depends on reference_no, not on
--  product_name).  This is again a partial dependency.
--
--  Fix: extract a delivery header table and a delivery items table.
--  The supplier FK is placed on the header (one supplier per delivery DR).
-- =============================================================================

-- Delivery headers: one row per delivery receipt (DR number).
CREATE TABLE norm_demo.nf2_deliveries AS
SELECT DISTINCT
    ROW_NUMBER() OVER (ORDER BY delivery_date, reference_no)::INT AS delivery_id,
    delivery_date,
    reference_no,
    s.supplier_id,   -- FK replaces supplier_name + contact + phone + address
    notes
FROM norm_demo.nf1_delivery_log dl
JOIN norm_demo.nf2_suppliers s ON s.supplier_name = dl.supplier_name;

ALTER TABLE norm_demo.nf2_deliveries ADD PRIMARY KEY (delivery_id);
ALTER TABLE norm_demo.nf2_deliveries
    ADD FOREIGN KEY (supplier_id) REFERENCES norm_demo.nf2_suppliers(supplier_id);


-- Delivery items: one row per product received per delivery.
CREATE TABLE norm_demo.nf2_delivery_items AS
SELECT
    dl.delivery_item_id,
    d.delivery_id,
    dl.product_name,      -- still text; 3NF will add a product_id FK
    dl.product_category,  -- [3NF] still transitive: product_name → category
    dl.product_unit,      -- [3NF] still transitive: product_name → unit
    dl.qty_received,
    dl.unit_cost,
    dl.line_total         -- [3NF] still a stored derived value (qty × cost)
FROM norm_demo.nf1_delivery_log dl
JOIN norm_demo.nf2_deliveries d ON d.reference_no = dl.reference_no;

ALTER TABLE norm_demo.nf2_delivery_items ADD PRIMARY KEY (delivery_item_id);
ALTER TABLE norm_demo.nf2_delivery_items
    ADD FOREIGN KEY (delivery_id) REFERENCES norm_demo.nf2_deliveries(delivery_id);


-- =============================================================================
--  WHAT CHANGED IN 2NF
--  -------------------
--  Before (5 tables from 1NF):
--    nf1_inventory, nf1_product_alt_suppliers,
--    nf1_sales_header, nf1_sales_items, nf1_delivery_log
--
--  After (7 tables):
--    nf2_suppliers        — new; 6 rows (each supplier stored exactly once)
--    nf2_products         — rebuilt; 15 rows, 4 supplier columns → 1 FK column
--    nf2_customers        — new; 3 rows (Aling Maria, Mang Jose, Ate Linda)
--    nf2_sales            — rebuilt; 10 rows, customer columns → 1 FK column
--    nf2_sale_items       — carried forward; 24 rows
--    nf2_deliveries       — new; 3 rows (one per DR number)
--    nf2_delivery_items   — rebuilt; 12 rows, 4 supplier columns → delivery_id FK
--
--  What 2NF bought us:
--    • Nestlé's phone number is now in one place (nf2_suppliers, 1 row).
--    • "Aling Maria"'s phone is in one place (nf2_customers, 1 row).
--    • Adding a new supplier or customer no longer requires touching product/sale rows.
--
--  Remaining violations:
--    • nf2_products: category_desc, unit_label (transitive on category/unit_code)
--    • nf2_products: stock_count (stored derived)
--    • nf2_customers: customer_balance (stored derived — and the wrong tool for the job)
--    • nf2_sales: total_amount (stored derived)
--    • nf2_delivery_items: product_category, product_unit (transitive on product_name)
--    • nf2_delivery_items: line_total (stored derived)
--    • nf2_sale_items, nf2_delivery_items: product referenced by TEXT, not FK
--
--  Those are 3NF violations.  Next: 03_3nf_migrate.sql.
-- =============================================================================
