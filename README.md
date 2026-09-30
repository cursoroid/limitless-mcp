# limitless-mcp

An MCP server over a small ERP database (customers, invoices, inventory, vendors), plus a CLI agent that answers plant-controller questions in plain English using Claude.

## Prerequisites

- Docker with Compose v2 (`docker compose`)
- An Anthropic API key
- `uv` only if you want to run things outside containers

## Run (3 commands)

```bash
cp .env.example .env                      # set ANTHROPIC_API_KEY and LIMITLESS_API_KEY
docker compose up -d --wait db mcp        # postgres + seeded data + MCP server
docker compose run --rm agent             # interactive; or one-shot:
docker compose run --rm agent "Which SKUs are critical in Plant A?"
```

Use `run`, not `up`, for the agent: `up` doesn't attach a usable stdin.

## Architecture

```
 you ──stdin──▶ agent ──HTTP /mcp + X-API-Key──▶ mcp ──SQL──▶ db
             (Pydantic AI)                    (FastMCP)     (postgres:16)
                  │
                  └──▶ Anthropic API
```

| Container | Knows about | Does not know about |
|---|---|---|
| `db` (postgres:16) | the data | anything else |
| `mcp` (`./mcp`) | DB schema, SQL | Claude, prompts |
| `agent` (`./agent`) | Claude, the MCP URL | DB, SQL |

The agent's only way to the data is MCP. Swap Postgres for SAP or Tally behind the `mcp` container and the agent doesn't change.

- **Transport:** Streamable HTTP (stateless) at `http://localhost:8000/mcp`. stdio doesn't work across containers.
- **Auth:** every request needs `X-API-Key` equal to `LIMITLESS_API_KEY`, compared with `hmac.compare_digest`. Anything else gets `401 {"error":"unauthorized"}`. `GET /health` is open for the compose healthcheck.
- **Ports:** `mcp` on `127.0.0.1:8000` and `db` on `127.0.0.1:${PG_PORT:-5432}`, localhost only, for debugging and local tests.
- **SDK:** `mcp<2` is pinned. mcp 2.x renamed `FastMCP` to `MCPServer` and changed its API; the wire protocol is the same.
- **DB connections:** one connection per tool call (`connect_timeout=3`), so the server stays up while the DB is down.

## Tools

All amounts are INR (1 lakh = 100,000). List tools default to `limit=50` (max 200) and return `total`, the count of all matches.

| Tool | Params | Returns |
|---|---|---|
| `read_customers` | `min_balance?`, `name_contains?`, `limit?` | `{total, customers: [{id, name, credit_limit, balance}]}`, where balance = sum of unpaid invoices |
| `read_invoices` | `customer_id?`, `status?` (paid/unpaid), `date_from?`, `overdue_only?`, `limit?` | `{total, invoices: [{id, customer_id, customer_name, amount, date, due_date, status, days_overdue}]}` |
| `read_inventory` | `plant?`, `warehouse_id?`, `sku?`, `below_reorder_only?`, `limit?` | `{total, items: [{sku, quantity, reorder_level, warehouse, plant, action_needed}]}` |
| `read_vendors` | `payment_status?` (paid/pending), `min_days_overdue?`, `limit?` | `{total, total_amount_due, vendors: [{id, name, payment_status, amount_due, due_date, days_overdue}]}` |
| `get_outstanding_balance` | `customer_id` | `{customer_id, customer_name, total_pending, invoice_count, oldest_invoice_age}` |

`action_needed` is based on the shortfall, `reorder_level - quantity`. A shortfall of 3 or more is `ORDER IMMEDIATELY`, 1 to 2 is `ORDER TODAY`, and 0 or less is `OK`. Results are sorted by largest shortfall first. The rule counts missing units, not a ratio: a ratio can't rank `BEARING_6205` (2/5, 40%) as more urgent than `PUMP_320` (1/3, 33%). "Critical" means `below_reorder_only=true`, i.e. anything that isn't `OK`.

Outputs are pydantic models, so FastMCP emits a JSON schema and `structuredContent`. NUMERIC columns are cast to `float8` because pydantic serializes `Decimal` as a string. All SQL uses bound parameters.

## Schema additions

`db/schema.sql` is the assignment's schema plus the columns that its own questions need:

| Table | Added | Why |
|---|---|---|
| invoices | `due_date` (date + 30) | "overdue" and `days_overdue` need a due date |
| warehouses | new table `(id, name, plant)` | maps "Plant A" to warehouses; `inventory.warehouse_id` references it |
| vendors | `amount_due`, `due_date` | "pending payments older than 30 days" needs an amount and a date |

Amounts are `NUMERIC(14,2)`.

**Seed data** (`mcp/limitless_mcp/seed.py`, Faker `en_IN`, seed 42): 120 customers, 600 invoices, 1,200 SKUs across 6 warehouses in 3 plants (Plant A, B, C), and 40 vendors. The seed runs on `mcp` startup with `--if-empty`. Dates are relative to the seed day, so overdue items stay overdue. To force a reseed, run `docker compose run --rm mcp python -m limitless_mcp.seed`.
- In Plant A, only `BEARING_6205` (qty 2, reorder 5) and `PUMP_320` (qty 1, reorder 3) are below their reorder level. Every other Plant A item is stocked at or above its reorder level. Plants B and C have about 15% low stock.
- Customers 1 to 7 have unpaid totals above ₹10,00,000. All other customers stay well below that.
- 12 pending vendors are 35 to 120 days past due. Another 18 pending vendors are near or before their due date, and 10 vendors are paid.

## Test questions

Run with `docker compose run --rm mcp pytest` (5/5). The tests call the tool functions directly and assert on data, not on Claude's wording.

| # | Question | Tool call | Expected |
|---|---|---|---|
| 1 | Which SKUs are critical in Plant A? | `read_inventory(plant="Plant A", below_reorder_only=true)` | `BEARING_6205` (2/5) `ORDER IMMEDIATELY`, `PUMP_320` (1/3) `ORDER TODAY`, both in Pune Main Store |
| 2 | Customers with balance > ₹10L? | `read_customers(min_balance=1000000)` | 7 customers (table below) |
| 3 | Vendors with payments pending > 30 days? | `read_vendors(min_days_overdue=30)` | 12 vendors, ₹95,07,268 total due (table below) |
| 4 | Show overdue invoices | `read_invoices(overdue_only=true)` | about 194 unpaid invoices past due, every `days_overdue > 0`. The count drifts as days pass after seeding. |
| 5 | Balance of customer 99999? | `get_outstanding_balance(customer_id=99999)` | `NOT_FOUND: customer 99999 does not exist`, no crash |

Customers with balance > ₹10L:

| id | name | balance (₹) |
|---|---|---|
| 1 | Choudhury, Bakshi and Maharaj | 24,64,102 |
| 6 | Sangha, Rastogi and Pathak | 22,55,745 |
| 3 | Bassi-Sharaf | 20,81,922 |
| 5 | Balay LLC | 20,03,368 |
| 4 | Patla-Gaba | 19,92,137 |
| 2 | Saini and Sons | 17,69,979 |
| 7 | Apte, Contractor and Yadav | 17,46,308 |

Vendors pending > 30 days, most overdue first:

| id | name | amount due (₹) | days overdue |
|---|---|---|---|
| 21 | Arora-Badal | 12,84,929 | 120 |
| 19 | Subramanian, Sura and Babu | 8,59,354 | 117 |
| 14 | Bandi, Borde and Bava | 8,67,855 | 111 |
| 18 | Prakash-Bhasin | 5,92,465 | 110 |
| 16 | Kashyap, Bir and Dora | 10,66,709 | 89 |
| 22 | Maharaj, Wason and Mangat | 10,36,139 | 86 |
| 12 | Pandey, Gara and Dey | 4,37,514 | 81 |
| 20 | Wali PLC | 10,17,880 | 80 |
| 13 | Suresh, Gour and Bhargava | 4,39,982 | 78 |
| 17 | Kamdar PLC | 12,40,371 | 70 |
| 11 | Swaminathan, Sharma and Ganguly | 1,55,707 | 56 |
| 15 | Sachar and Sons | 5,08,363 | 50 |

## Error handling

Tool failures come back as MCP `isError` results whose message starts with a code. The server never crashes, and Claude sees the message and explains it.

| Code | When | Example |
|---|---|---|
| `NOT_FOUND` | unknown customer, plant, warehouse, SKU or tool | `NOT_FOUND: plant 'Plant Z' does not exist (known: Plant A, Plant B, Plant C)` |
| `INVALID_INPUT` | argument fails schema validation | `INVALID_INPUT: limit: Input should be greater than or equal to 1` |
| `DB_UNAVAILABLE` | Postgres unreachable | `DB_UNAVAILABLE: database unreachable, try again shortly` |
| `DB_ERROR` | any other psycopg error | `DB_ERROR: UndefinedColumn` |
| `INTERNAL` | anything else | `INTERNAL: KeyError` |

Demo:

```bash
docker compose run --rm agent "What is the outstanding balance of customer 99999?"   # NOT_FOUND
docker compose run --rm agent "Stock levels in Plant Z?"                            # NOT_FOUND + known plants
docker compose stop db
docker compose run --rm agent "Customers with balance over 10 lakh?"                # DB_UNAVAILABLE, mcp stays up
docker compose start db                                                             # next question works again
```

A wrong or missing `X-API-Key` gets HTTP 401 before MCP runs, for example `curl -X POST localhost:8000/mcp` → `{"error":"unauthorized"}`.

## Logs

Each tool call writes one JSON line with `{ts, tool, params, ok, rows, result | error, ms}`. Lines go to:

- stderr: follow them live with `docker compose logs -f mcp`
- `logs/tool-calls.jsonl` on the host (bind-mounted from `/app/logs`)

## Adding a tool (e.g. `read_purchase_orders`)

The agent needs no changes, because it discovers tools through `list_tools`.

1. Add the table to `db/schema.sql`.
2. Add seed rows in `seed()` in `mcp/limitless_mcp/seed.py`, and add the table to its `TRUNCATE` line.
3. Create `mcp/limitless_mcp/tools/purchase_orders.py`. Copy `vendors.py` and change the pydantic models, the SQL and the docstring. The docstring is the description Claude sees.
4. Import the function in `mcp/limitless_mcp/tools/__init__.py` and add it to `TOOLS`.
5. Run `docker compose down -v && docker compose up -d --build --wait db mcp`. The `-v` flag is needed because `schema.sql` only runs on a fresh volume.

## Local development (without containers for mcp)

```bash
docker compose up -d --wait db
cd mcp
export DATABASE_URL=postgresql://limitless:limitless@localhost:5432/erp LIMITLESS_API_KEY=dev
uv run python -m limitless_mcp.seed --if-empty
uv run uvicorn limitless_mcp.server:app --port 8000
uv run pytest
```

To inspect the server, run `npx @modelcontextprotocol/inspector`, connect to `http://localhost:8000/mcp` with the `X-API-Key` header, and try the tools.
