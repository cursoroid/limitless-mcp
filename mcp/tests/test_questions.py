"""The 5 demo questions, calling tool functions directly against the seeded db.
Asserts on data, not on Claude's wording. Run: docker compose run --rm mcp pytest"""
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from limitless_mcp.log import logged
from limitless_mcp.tools import get_outstanding_balance, read_customers, read_inventory, read_invoices, read_vendors


def test_critical_skus_in_plant_a():
    result = read_inventory(plant="Plant A", below_reorder_only=True)
    actions = {i.sku: i.action_needed for i in result.items}
    assert actions == {"BEARING_6205": "ORDER IMMEDIATELY", "PUMP_320": "ORDER TODAY"}


def test_customers_with_balance_over_10_lakh():
    result = read_customers(min_balance=1_000_000)
    assert 5 <= result.total <= 10
    assert all(c.balance > 1_000_000 for c in result.customers)


def test_vendors_pending_over_30_days():
    result = read_vendors(min_days_overdue=30)
    assert result.total > 0
    assert all(v.payment_status == "pending" and v.days_overdue >= 30 for v in result.vendors)


def test_overdue_invoices():
    result = read_invoices(overdue_only=True, limit=200)
    assert result.total > 0
    assert all(i.status == "unpaid" and i.days_overdue > 0 for i in result.invoices)


def test_unknown_customer_is_not_found():
    with pytest.raises(ToolError, match="^NOT_FOUND:"):
        logged(get_outstanding_balance)(customer_id=99999)
