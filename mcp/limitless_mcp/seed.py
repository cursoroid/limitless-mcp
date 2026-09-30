# Fake ERP data, seeded so every run is identical. Dates are relative to today.
# python -m limitless_mcp.seed [--if-empty]
import random
import sys
from datetime import date, timedelta

import psycopg
from faker import Faker

from limitless_mcp.db import DATABASE_URL

WAREHOUSES = [
    ("Pune Main Store", "Plant A"), ("Pune Spares Yard", "Plant A"),
    ("Chennai Main Store", "Plant B"), ("Chennai Tool Crib", "Plant B"),
    ("Ahmedabad Main Store", "Plant C"), ("Ahmedabad Spares Yard", "Plant C"),
]
# The only Plant A items below reorder level, i.e. the demo's "critical SKUs in Plant A".
CRITICAL = [("BEARING_6205", 2, 1, 5), ("PUMP_320", 1, 1, 3)]  # sku, qty, warehouse_id, reorder
PARTS = ["BEARING", "PUMP", "VALVE", "MOTOR", "GASKET", "BELT", "FILTER", "SEAL", "BOLT", "CABLE", "SENSOR", "RELAY"]
BIG_DEBTORS = 7  # customers 1..7 get large unpaid invoices (> 10 lakh total)


def seed(conn: psycopg.Connection) -> None:
    fake, rng, today = Faker("en_IN"), random.Random(42), date.today()
    Faker.seed(42)
    conn.execute("TRUNCATE customers, invoices, warehouses, inventory, vendors RESTART IDENTITY CASCADE")
    cur = conn.cursor()

    cur.executemany(
        "INSERT INTO customers (name, address, credit_limit) VALUES (%s, %s, %s)",
        [(fake.unique.company(), fake.address().replace("\n", ", "), rng.randrange(5, 51) * 100_000) for _ in range(120)],
    )

    invoices = []
    for n in range(600):
        big = n < BIG_DEBTORS * 5
        cid = n // 5 + 1 if big else rng.randint(BIG_DEBTORS + 1, 120)
        issued = today - timedelta(days=rng.randint(0, 365))
        due = issued + timedelta(days=30)
        amount = rng.randint(250_000, 600_000) if big else rng.randint(5_000, 80_000)
        unpaid = big or rng.random() < (0.3 if due < today else 0.8)
        invoices.append((cid, amount, issued, due, "unpaid" if unpaid else "paid"))
    cur.executemany("INSERT INTO invoices (customer_id, amount, date, due_date, status) VALUES (%s, %s, %s, %s, %s)", invoices)

    cur.executemany("INSERT INTO warehouses (name, plant) VALUES (%s, %s)", WAREHOUSES)
    taken = {sku for sku, *_ in CRITICAL}
    skus = rng.sample([s for p in PARTS for n in range(100, 1000) if (s := f"{p}_{n}") not in taken], 1200 - len(CRITICAL))
    stock = [(sku, qty, wid, reorder) for sku, qty, wid, reorder in CRITICAL]
    for sku in skus:
        wid, reorder = rng.randint(1, len(WAREHOUSES)), rng.randint(10, 200)
        low = WAREHOUSES[wid - 1][1] != "Plant A" and rng.random() < 0.15
        stock.append((sku, rng.randint(0, reorder - 1) if low else rng.randint(reorder, reorder * 4), wid, reorder))
    cur.executemany("INSERT INTO inventory (sku, quantity, warehouse_id, reorder_level) VALUES (%s, %s, %s, %s)", stock)

    vendors = []
    for n in range(40):
        if n < 10:
            vendors.append((fake.unique.company(), "paid", 0, today - timedelta(days=rng.randint(1, 90))))
        else:
            late = rng.randint(35, 120) if n < 22 else rng.randint(-30, 25)  # 12 vendors > 30 days past due
            vendors.append((fake.unique.company(), "pending", rng.randint(20_000, 1_500_000), today - timedelta(days=late)))
    cur.executemany("INSERT INTO vendors (name, payment_status, amount_due, due_date) VALUES (%s, %s, %s, %s)", vendors)


def main() -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        if "--if-empty" in sys.argv and conn.execute("SELECT EXISTS (SELECT 1 FROM customers)").fetchone()[0]:
            print("seed: data present, skipping", file=sys.stderr)
            return
        seed(conn)
    print("seed: done", file=sys.stderr)


if __name__ == "__main__":
    main()
