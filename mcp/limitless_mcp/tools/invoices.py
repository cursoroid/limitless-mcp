from datetime import date
from typing import Annotated, Literal

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from limitless_mcp.db import query


class Invoice(BaseModel):
    id: int
    customer_id: int
    customer_name: str
    amount: float
    date: date
    due_date: date
    status: str
    days_overdue: int


class InvoicesResult(BaseModel):
    total: int
    invoices: list[Invoice]


def read_invoices(
    customer_id: int | None = None,
    status: Literal["paid", "unpaid"] | None = None,
    date_from: Annotated[date | None, Field(description="Invoice date on/after, YYYY-MM-DD")] = None,
    overdue_only: Annotated[bool, Field(description="Unpaid and past due_date")] = False,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> InvoicesResult:
    """Invoices with customer name, due date and days overdue (0 unless unpaid and past due).
    Amounts in INR, 1 lakh = 100000. Most overdue first. total = all matches."""
    if customer_id is not None and not query("SELECT 1 FROM customers WHERE id = %s", (customer_id,)):
        raise ToolError(f"NOT_FOUND: customer {customer_id} does not exist")
    rows = query(
        """
        SELECT i.id, i.customer_id, c.name AS customer_name, i.amount::float8 AS amount,
               i.date, i.due_date, i.status,
               CASE WHEN i.status = 'unpaid' THEN GREATEST(CURRENT_DATE - i.due_date, 0) ELSE 0 END AS days_overdue,
               COUNT(*) OVER () AS total
        FROM invoices i JOIN customers c ON c.id = i.customer_id
        WHERE (%(cid)s::int IS NULL OR i.customer_id = %(cid)s)
          AND (%(status)s::text IS NULL OR i.status = %(status)s)
          AND (%(from)s::date IS NULL OR i.date >= %(from)s)
          AND (NOT %(overdue)s OR (i.status = 'unpaid' AND i.due_date < CURRENT_DATE))
        ORDER BY days_overdue DESC, i.due_date
        LIMIT %(limit)s
        """,
        {"cid": customer_id, "status": status, "from": date_from, "overdue": overdue_only, "limit": limit},
    )
    return InvoicesResult(total=rows[0]["total"] if rows else 0, invoices=rows)
