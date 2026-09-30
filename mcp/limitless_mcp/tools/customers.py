from typing import Annotated

from pydantic import BaseModel, Field

from limitless_mcp.db import query


class Customer(BaseModel):
    id: int
    name: str
    credit_limit: float
    balance: float


class CustomersResult(BaseModel):
    total: int
    customers: list[Customer]


def read_customers(
    min_balance: Annotated[float | None, Field(ge=0, description="Only balances above this, INR (10 lakh = 1000000)")] = None,
    name_contains: Annotated[str | None, Field(description="Case-insensitive name match")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> CustomersResult:
    """Customers with credit limit and balance (sum of unpaid invoices), highest balance first.
    Amounts in INR, 1 lakh = 100000. total = all matches, customers = first `limit`."""
    rows = query(
        """
        SELECT c.id, c.name, c.credit_limit::float8 AS credit_limit,
               COALESCE(SUM(i.amount) FILTER (WHERE i.status = 'unpaid'), 0)::float8 AS balance,
               COUNT(*) OVER () AS total
        FROM customers c LEFT JOIN invoices i ON i.customer_id = c.id
        WHERE %(name)s::text IS NULL OR c.name ILIKE '%%' || %(name)s || '%%'
        GROUP BY c.id
        HAVING %(min)s::float8 IS NULL
            OR COALESCE(SUM(i.amount) FILTER (WHERE i.status = 'unpaid'), 0) > %(min)s
        ORDER BY balance DESC
        LIMIT %(limit)s
        """,
        {"name": name_contains, "min": min_balance, "limit": limit},
    )
    return CustomersResult(total=rows[0]["total"] if rows else 0, customers=rows)
