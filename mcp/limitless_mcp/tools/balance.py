from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel

from limitless_mcp.db import query


class Balance(BaseModel):
    customer_id: int
    customer_name: str
    total_pending: float
    invoice_count: int
    oldest_invoice_age: int | None


def get_outstanding_balance(customer_id: int) -> Balance:
    """One customer's unpaid total (INR, 1 lakh = 100000), unpaid invoice count,
    and age in days of the oldest unpaid invoice (null if nothing is pending)."""
    rows = query(
        """
        SELECT c.id AS customer_id, c.name AS customer_name,
               COALESCE(SUM(i.amount), 0)::float8 AS total_pending,
               COUNT(i.id) AS invoice_count,
               CURRENT_DATE - MIN(i.date) AS oldest_invoice_age
        FROM customers c LEFT JOIN invoices i ON i.customer_id = c.id AND i.status = 'unpaid'
        WHERE c.id = %s
        GROUP BY c.id
        """,
        (customer_id,),
    )
    if not rows:
        raise ToolError(f"NOT_FOUND: customer {customer_id} does not exist")
    return Balance(**rows[0])
