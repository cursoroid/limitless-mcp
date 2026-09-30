-- Loaded once by postgres on first start (docker-entrypoint-initdb.d).
CREATE TABLE customers (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    address      TEXT,
    credit_limit NUMERIC(14,2) NOT NULL DEFAULT 0
);

CREATE TABLE invoices (
    id          SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id),
    amount      NUMERIC(14,2) NOT NULL,
    date        DATE NOT NULL,
    due_date    DATE NOT NULL,  -- added: date + 30, needed for days_overdue
    status      TEXT NOT NULL CHECK (status IN ('paid', 'unpaid'))
);
CREATE INDEX ON invoices (customer_id);

CREATE TABLE warehouses (  -- added: maps "Plant A" to warehouses
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL,
    plant TEXT NOT NULL
);

CREATE TABLE inventory (
    sku           TEXT NOT NULL,
    quantity      INT NOT NULL,
    warehouse_id  INT NOT NULL REFERENCES warehouses(id),
    reorder_level INT NOT NULL,
    PRIMARY KEY (sku, warehouse_id)
);

CREATE TABLE vendors (
    id             SERIAL PRIMARY KEY,
    name           TEXT NOT NULL,
    payment_status TEXT NOT NULL CHECK (payment_status IN ('paid', 'pending')),
    amount_due     NUMERIC(14,2) NOT NULL DEFAULT 0,  -- added: what we owe
    due_date       DATE                               -- added: for "pending > 30 days"
);
