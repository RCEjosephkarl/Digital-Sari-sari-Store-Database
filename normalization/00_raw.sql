-- =============================================================================
--  00_raw.sql  —  The notebooks before normalization
--
--  These three tables simulate what a sari-sari store owner might produce if
--  they simply typed their handwritten notebooks into a spreadsheet, column by
--  column, without any database design.
--
--  Every violation is annotated inline.  The goal is to make the PROBLEM
--  visible before the solution.
--
--  Schema: norm_demo (isolated from the main `public` schema so this walkthrough
--  can run in the same database as the production pipeline).
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS norm_demo;

-- Drop in reverse dependency order so re-running is safe.
DROP TABLE IF EXISTS norm_demo.raw_delivery_log  CASCADE;
DROP TABLE IF EXISTS norm_demo.raw_sales_ledger  CASCADE;
DROP TABLE IF EXISTS norm_demo.raw_inventory     CASCADE;


-- =============================================================================
--  TABLE 1: raw_inventory
--  Source: the "presyo" notebook — the owner's price list and supplier contacts.
--
--  VIOLATIONS
--  ----------
--  [NO-PK]    No primary key: Maggi Magic Sarap appears twice (two suppliers)
--             and there is no way to tell the rows apart by identity.
--  [1NF]      alt_suppliers stores multiple values in one cell, separated by
--             semicolons.  You cannot query "give me all products from Divisoria"
--             without a LIKE '%Divisoria%' hack.
--  [2NF]      supplier_contact, supplier_phone, supplier_address all depend only
--             on supplier_name, not on the product.  Changing Nestlé's phone
--             number requires updating every row from that supplier.
--  [3NF]      category_desc depends on category, not on the product.
--  [3NF]      unit_label depends on unit_code, not on the product.
--  [3NF]      stock_count is a hand-calculated running total: it diverges from
--             reality the moment any sale or restock happens.
-- =============================================================================

CREATE TABLE norm_demo.raw_inventory (
    -- [NO-PK] no PRIMARY KEY clause — duplicates are silently accepted
    product_name     TEXT,
    barcode          TEXT,
    category         TEXT,
    category_desc    TEXT,          -- [3NF] depends on category, not on product
    unit_code        TEXT,
    unit_label       TEXT,          -- [3NF] depends on unit_code, not on product
    selling_price    NUMERIC(10,2),
    reorder_qty      INT,
    stock_count      INT,           -- [3NF] stored derived — goes stale immediately
    supplier_name    TEXT,
    supplier_contact TEXT,          -- [2NF] depends only on supplier_name
    supplier_phone   TEXT,          -- [2NF] depends only on supplier_name
    supplier_address TEXT,          -- [2NF] depends only on supplier_name
    alt_suppliers    TEXT           -- [1NF] semicolon-separated list (not atomic)
);

INSERT INTO norm_demo.raw_inventory VALUES
--  product_name                    barcode        category               category_desc                           unit_code  unit_label  price   reorder  stock  supplier_name                   contact          phone       address            alt_suppliers
    ('Coca-Cola Mismo 300ml',        '4800019117117','Beverages',          'Soft drinks, juices & energy drinks',  'bottle',  'Bottle',   22.00,  24,      87,    'Coca-Cola FEMSA Route Agent',  'Juan Santos',   '09171110001','123 Quezon Ave', NULL),
    ('Sprite Mismo 300ml',           '4800019119104','Beverages',          'Soft drinks, juices & energy drinks',  'bottle',  'Bottle',   20.00,  24,      64,    'Coca-Cola FEMSA Route Agent',  'Juan Santos',   '09171110001','123 Quezon Ave', NULL),
    ('Pepsi-Cola 330ml Can',         '4800063100006','Beverages',          'Soft drinks, juices & energy drinks',  'can',     'Can',      20.00,  24,      52,    'PepsiCo PH Distributor',       'Ana Reyes',     '09181220002','45 EDSA Ortigas',NULL),
    ('Royal Tru-Orange 330ml',       '4800063101003','Beverages',          'Soft drinks, juices & energy drinks',  'can',     'Can',      18.00,  24,      48,    'PepsiCo PH Distributor',       'Ana Reyes',     '09181220002','45 EDSA Ortigas',NULL),
    ('Nescafé 3-in-1 Original 20g',  '4800361102019','Beverages',          'Soft drinks, juices & energy drinks',  'sachet',  'Sachet',    8.00,  50,     175,    'Nestlé Philippines Dealer',    'Maria Cruz',    '09221330003','78 Ortigas Ave', NULL),
    ('Milo 24g',                     '4800361200012','Beverages',          'Soft drinks, juices & energy drinks',  'sachet',  'Sachet',    9.00,  48,     143,    'Nestlé Philippines Dealer',    'Maria Cruz',    '09221330003','78 Ortigas Ave', NULL),
    -- [2NF] supplier_contact/phone/address for Nestlé repeat identically above and below
    -- One phone number change requires editing every Nestlé row.
    ('Bear Brand Adult Plus 33g',    '4800361300018','Beverages',          'Soft drinks, juices & energy drinks',  'sachet',  'Sachet',   11.00,  36,      98,    'Nestlé Philippines Dealer',    'Maria Cruz',    '09221330003','78 Ortigas Ave', NULL),
    -- [NO-PK] Maggi Magic Sarap appears TWICE — different supplier, different price.
    -- Without a primary key there is no way to enforce that this is intentional.
    ('Maggi Magic Sarap 8g',         '4800361400011','Meal Ingredients',   'Cooking condiments, oils & spices',    'sachet',  'Sachet',    5.00,  60,     210,    'Nestlé Philippines Dealer',    'Maria Cruz',    '09221330003','78 Ortigas Ave', 'Divisoria Wholesale Center'),
    ('Maggi Magic Sarap 8g',         '4800361400011','Meal Ingredients',   'Cooking condiments, oils & spices',    'sachet',  'Sachet',    4.50,  60,     210,    'Divisoria Wholesale Center',   'Pedro Reyes',   '09331440004','9 Divisoria St', NULL),
    -- [1NF] alt_suppliers for Lucky Me packs multiple values into one cell:
    -- you cannot do: WHERE alt_suppliers = 'Suy Sing Commercial Corporation'
    ('Lucky Me Pancit Canton 80g',   '4800016012007','Snacks',             'Noodles, chips & confectionery',       'pack',    'Pack',     14.00,  48,     189,    'Monde Nissin Distributor',     'Carlo Lim',     '09441550005','22 C.M. Recto', 'Monde Nissin Distributor;Suy Sing Commercial Corporation'),
    ('Piattos Cheese 40g',           '4800016900013','Snacks',             'Noodles, chips & confectionery',       'pack',    'Pack',     15.00,  36,      77,    'URC Snack Foods Direct',       'Rose Tan',      '09551660006','56 Shaw Blvd',  NULL),
    ('Datu Puti Soy Sauce 385ml',    '4800149530009','Meal Ingredients',   'Cooking condiments, oils & spices',    'bottle',  'Bottle',   27.00,  24,      61,    'NutriAsia Direct Delivery',    'Ben Garcia',    '09661770007','100 Aurora Blvd',NULL),
    -- [3NF] stock_count = 99, but the actual count (from restocks minus sales)
    -- is 87. The column was last updated three weeks ago and was never corrected.
    ('Argentina Corned Beef 150g',   '4800192000005','Processed Meat',     'Canned meat, fish & dairy',            'can',     'Can',      49.00,  24,      99,    'General Milling Corp',         'Tito Santos',   '09771880008','3 Buendia Ave', NULL),
    ('555 Sardines Tomato Sauce 155g','4800073100006','Processed Meat',    'Canned meat, fish & dairy',            'can',     'Can',      21.00,  36,     124,    'Century Pacific Food',         'Lita Gomez',    '09881990009','77 Pioneer St', NULL),
    ('Tide Powder Detergent 66g',    '4801000505070','Small Household Items','Cleaning, laundry & personal care',  'pack',    'Pack',     10.00,  60,     203,    'P&G Philippines Route',        'Noel Bautista', '09991000010','888 Buendia',   NULL);

-- Quick proof of the NO-PK violation: this query returns 2 rows for the same barcode.
-- SELECT product_name, barcode, supplier_name FROM norm_demo.raw_inventory
-- WHERE barcode = '4800361400011';


-- =============================================================================
--  TABLE 2: raw_sales_ledger
--  Source: the "utang" notebook — daily sales and credit running balances.
--
--  VIOLATIONS
--  ----------
--  [NO-PK]    No unique row identity: two cash sales on the same day cannot
--             be distinguished.
--  [1NF]      item1_/item2_/item3_ are repeating groups.  Adding a 4th item
--             to any transaction requires altering the table (ADD COLUMN).
--             Small transactions leave item2 and item3 entirely NULL.
--  [3NF]      customer_phone and customer_nickname depend on customer_name,
--             not on the sale.  If "Aling Maria" gets a new phone number,
--             every row mentioning her must be updated.
--  [3NF]      customer_balance is a hand-copied running total.  See rows 1–2
--             and row 5: Aling Maria's balance is shown as 0.00 on two back-
--             to-back credit sales (rows 1 and 2), then appears as 50.00 in
--             row 5 — the notebook owner wrote it down between customers and
--             it was never back-corrected.
--  [3NF]      total_amount is the sum of item quantities × prices.  If any
--             item price is corrected, total_amount must also be edited manually.
-- =============================================================================

CREATE TABLE norm_demo.raw_sales_ledger (
    -- [NO-PK] no PRIMARY KEY clause
    sale_date          DATE,
    customer_name      TEXT,           -- NULL for anonymous cash walk-ins
    customer_phone     TEXT,           -- [3NF] depends on customer_name
    customer_nickname  TEXT,           -- [3NF] depends on customer_name
    customer_balance   NUMERIC(10,2),  -- [3NF] stored derived — stale the instant any row changes
    payment_type       TEXT,
    -- [1NF] Repeating groups: positions 1, 2, 3 hard-wired as columns.
    item1_name         TEXT,
    item1_qty          INT,
    item1_price        NUMERIC(10,2),
    item2_name         TEXT,           -- NULL when fewer than 2 items
    item2_qty          INT,
    item2_price        NUMERIC(10,2),
    item3_name         TEXT,           -- NULL when fewer than 3 items
    item3_qty          INT,
    item3_price        NUMERIC(10,2),
    total_amount       NUMERIC(10,2),  -- [3NF] derived: sum of items — stored anyway
    notes              TEXT
);

INSERT INTO norm_demo.raw_sales_ledger VALUES
--  date          customer           phone          nickname  balance  type      item1                          qty1 price1  item2                   qty2 price2  item3    qty3 price3  total   notes
    ('2025-01-15','Aling Maria',     '09100000001', 'Nene',   0.00,   'credit', 'Coca-Cola Mismo 300ml',       2,   22.00, 'Datu Puti Soy Sauce 385ml',1, 27.00, NULL,   NULL,NULL,   71.00, NULL),
    -- [3NF-BALANCE] Row 2: same customer, same day — balance still shows 0.00.
    -- The credit from row 1 (PHP 71) was never posted to the balance here.
    ('2025-01-15','Aling Maria',     '09100000001', 'Nene',   0.00,   'credit', 'Maggi Magic Sarap 8g',        3,    5.00, NULL,                    NULL,NULL,   NULL,   NULL,NULL,   15.00, 'added to tab'),
    -- [1NF-NULL] Cash walk-in: customer_name is NULL, item2/item3 are NULL.
    ('2025-01-16', NULL,              NULL,          NULL,    NULL,   'cash',   'Sprite Mismo 300ml',          1,   20.00, NULL,                    NULL,NULL,   NULL,   NULL,NULL,   20.00, NULL),
    -- [1NF-MAX3] Mang Jose buys exactly 3 items — table capacity reached.
    -- A 4th item would require ALTER TABLE ADD COLUMN item4_name TEXT, etc.
    ('2025-01-17','Mang Jose',       '09200000002', 'Manong', 0.00,   'credit', 'Lucky Me Pancit Canton 80g',  2,   14.00, '555 Sardines Tomato Sauce 155g',1,21.00,'Milo 24g',3,9.00,76.00,NULL),
    -- [3NF-BALANCE] Row 5: Aling Maria shows 50.00 — this number appeared in the
    -- notebook after a partial payment, but rows 1 and 2 were never updated to
    -- reflect it, making the ledger internally inconsistent.
    ('2025-01-18','Aling Maria',     '09100000001', 'Nene',   50.00,  'credit', 'Tide Powder Detergent 66g',   2,   10.00, NULL,                    NULL,NULL,   NULL,   NULL,NULL,   20.00, NULL),
    ('2025-01-19','Ate Linda',       '09300000003', 'Linda',   0.00,  'credit', 'San Miguel Pale Pilsen 320ml',3,   52.00, 'Piattos Cheese 40g',    2,   15.00, NULL,   NULL,NULL,  186.00, NULL),
    -- [3NF-BALANCE] Row 7: Ate Linda's balance still 0.00 the next day.
    -- Row 6 charged her PHP 186 but the balance was never carried forward.
    ('2025-01-20','Ate Linda',       '09300000003', 'Linda',   0.00,  'credit', 'Nescafé 3-in-1 Original 20g', 5,   8.00, NULL,                    NULL,NULL,   NULL,   NULL,NULL,   40.00, NULL),
    -- [1NF-NULL] Cash, 2 items — item3 columns are NULL.
    ('2025-01-21', NULL,              NULL,          NULL,    NULL,   'cash',   'Argentina Corned Beef 150g',  1,   49.00, 'Datu Puti Soy Sauce 385ml',1, 27.00, NULL,   NULL,NULL,   76.00, NULL),
    ('2025-01-22', NULL,              NULL,          NULL,    NULL,   'cash',   'Pepsi-Cola 330ml Can',        2,   20.00, NULL,                    NULL,NULL,   NULL,   NULL,NULL,   40.00, NULL),
    -- [3NF-BALANCE] Row 10: Mang Jose's balance is 0.00 but he owes PHP 76 from row 4.
    ('2025-01-23','Mang Jose',       '09200000002', 'Manong', 0.00,  'credit', 'Milo 24g',                    2,    9.00, 'Maggi Magic Sarap 8g',  1,    5.00, NULL,   NULL,NULL,   23.00, NULL);


-- =============================================================================
--  TABLE 3: raw_delivery_log
--  Source: the "delivery receipt" notebook — inbound stock from suppliers.
--
--  VIOLATIONS
--  ----------
--  [NO-PK]    No row identity: a 5-item delivery has 5 rows with identical
--             reference_no but no single key to distinguish them.
--  [2NF]      supplier_contact, supplier_phone, supplier_address depend only
--             on supplier_name (partial dependency on the natural composite key
--             of (reference_no, product_name)).  A single 5-item delivery
--             from Divisoria repeats all supplier contact info 5 times.
--  [3NF]      product_category depends on product_name, not on this delivery.
--  [3NF]      product_unit depends on product_name, not on this delivery.
--  [3NF]      line_total = qty_received × unit_cost — stored despite being
--             trivially derivable; any correction to qty or cost also requires
--             correcting line_total manually.
-- =============================================================================

CREATE TABLE norm_demo.raw_delivery_log (
    -- [NO-PK] no PRIMARY KEY clause
    delivery_date    DATE,
    reference_no     TEXT,            -- DR number — same value on every item row
    supplier_name    TEXT,
    supplier_contact TEXT,            -- [2NF] depends only on supplier_name
    supplier_phone   TEXT,            -- [2NF] depends only on supplier_name
    supplier_address TEXT,            -- [2NF] depends only on supplier_name
    product_name     TEXT,
    product_category TEXT,            -- [3NF] depends on product_name, not delivery
    product_unit     TEXT,            -- [3NF] depends on product_name, not delivery
    qty_received     INT,
    unit_cost        NUMERIC(10,2),
    line_total       NUMERIC(10,2),   -- [3NF] derived: qty_received × unit_cost
    notes            TEXT
);

INSERT INTO norm_demo.raw_delivery_log VALUES
--  date          ref_no         supplier                  contact        phone           address            product                          category            unit      qty   cost   total     notes
--  DR-2025-001: Coca-Cola FEMSA (4 items — supplier info repeated 4×)
    ('2025-01-10','DR-2025-001', 'Coca-Cola FEMSA Route Agent','Juan Santos','09171110001','123 Quezon Ave',  'Coca-Cola Mismo 300ml',         'Beverages',        'bottle', 120, 16.00, 1920.00, NULL),
    ('2025-01-10','DR-2025-001', 'Coca-Cola FEMSA Route Agent','Juan Santos','09171110001','123 Quezon Ave',  'Sprite Mismo 300ml',            'Beverages',        'bottle',  96, 14.50, 1392.00, NULL),
    ('2025-01-10','DR-2025-001', 'Coca-Cola FEMSA Route Agent','Juan Santos','09171110001','123 Quezon Ave',  'Pepsi-Cola 330ml Can',          'Beverages',        'can',     72, 14.00, 1008.00, NULL),
    ('2025-01-10','DR-2025-001', 'Coca-Cola FEMSA Route Agent','Juan Santos','09171110001','123 Quezon Ave',  'Royal Tru-Orange 330ml',        'Beverages',        'can',     72, 13.50,  972.00, NULL),
--  DR-2025-002: Nestlé Philippines (3 items — supplier info repeated 3×)
    ('2025-01-11','DR-2025-002', 'Nestlé Philippines Dealer', 'Maria Cruz', '09221330003','78 Ortigas Ave',  'Nescafé 3-in-1 Original 20g',   'Beverages',        'sachet', 200,  6.00, 1200.00, NULL),
    ('2025-01-11','DR-2025-002', 'Nestlé Philippines Dealer', 'Maria Cruz', '09221330003','78 Ortigas Ave',  'Milo 24g',                      'Beverages',        'sachet', 180,  7.00, 1260.00, NULL),
    ('2025-01-11','DR-2025-002', 'Nestlé Philippines Dealer', 'Maria Cruz', '09221330003','78 Ortigas Ave',  'Bear Brand Adult Plus 33g',     'Beverages',        'sachet', 150,  8.50, 1275.00, NULL),
--  DR-2025-003: Divisoria Wholesale Center (5 items — supplier info repeated 5×)
--  [3NF] product_category and product_unit also repeat on every delivery for the
--  same product, even though they are facts about the product, not the delivery.
    ('2025-01-12','DR-2025-003', 'Divisoria Wholesale Center','Pedro Reyes','09331440004','9 Divisoria St',  'Argentina Corned Beef 150g',    'Processed Meat',   'can',     60, 38.00, 2280.00, NULL),
    ('2025-01-12','DR-2025-003', 'Divisoria Wholesale Center','Pedro Reyes','09331440004','9 Divisoria St',  '555 Sardines Tomato Sauce 155g','Processed Meat',   'can',     72, 15.00, 1080.00, NULL),
    ('2025-01-12','DR-2025-003', 'Divisoria Wholesale Center','Pedro Reyes','09331440004','9 Divisoria St',  'Lucky Me Pancit Canton 80g',    'Snacks',           'pack',   120, 10.50, 1260.00, NULL),
    ('2025-01-12','DR-2025-003', 'Divisoria Wholesale Center','Pedro Reyes','09331440004','9 Divisoria St',  'Maggi Magic Sarap 8g',          'Meal Ingredients', 'sachet', 300,  3.50, 1050.00, NULL),
    ('2025-01-12','DR-2025-003', 'Divisoria Wholesale Center','Pedro Reyes','09331440004','9 Divisoria St',  'Tide Powder Detergent 66g',     'Small Household Items','pack',96,  7.50,  720.00, NULL);

-- =============================================================================
--  SUMMARY OF VIOLATIONS
--  ----------------------
--  Table               NO-PK   1NF     2NF     3NF
--  raw_inventory         ✗              ✗       ✗
--  raw_sales_ledger      ✗       ✗              ✗
--  raw_delivery_log      ✗              ✗       ✗
--
--  3 tables, 41 columns across them, dozens of NULL cells per row.
--  Next: 01_1nf.sql — add primary keys and eliminate repeating groups.
-- =============================================================================
