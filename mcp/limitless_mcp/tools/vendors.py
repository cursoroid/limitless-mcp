from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from limitless_mcp.db import query


class Vendor(BaseModel):
    id: int
    name: str
    payment_status: str
    amount_due: float
    due_date: date | None
    days_overdue: int


class VendorsResult(BaseModel):
    total: int
    total_amount_due: float
    vendors: list[Vendor]


def read_vendors(
    payment_status: Literal["paid", "pending"] | None = None,
    min_days_overdue: Annotated[int | None, Field(ge=0, description="Pending and at least this many days past due_date")] = None,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> VendorsResult:
    """Vendors we owe money to, with amount due and days past due (0 unless pending and past due).
    Amounts in INR, 1 lakh = 100000. Most overdue first. total / total_amount_due cover all matches."""
    rows = query(
        """
        SELECT id, name, payment_status, amount_due::float8 AS amount_due, due_date,
               CASE WHEN payment_status = 'pending' THEN GREATEST(CURRENT_DATE - due_date, 0) ELSE 0 END AS days_overdue,
               COUNT(*) OVER () AS total, SUM(amount_due) OVER ()::float8 AS total_amount_due
        FROM vendors
        WHERE (%(status)s::text IS NULL OR payment_status = %(status)s)
          AND (%(min)s::int IS NULL OR (payment_status = 'pending' AND CURRENT_DATE - due_date >= %(min)s))
        ORDER BY days_overdue DESC, amount_due DESC
        LIMIT %(limit)s
        """,
        {"status": payment_status, "min": min_days_overdue, "limit": limit},
    )
    head = rows[0] if rows else {"total": 0, "total_amount_due": 0}
    return VendorsResult(total=head["total"], total_amount_due=head["total_amount_due"], vendors=rows)
