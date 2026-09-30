from typing import Annotated

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from limitless_mcp.db import query


class StockItem(BaseModel):
    sku: str
    quantity: int
    reorder_level: int
    warehouse: str
    plant: str
    action_needed: str


class InventoryResult(BaseModel):
    total: int
    items: list[StockItem]


def read_inventory(
    plant: Annotated[str | None, Field(description="e.g. 'Plant A'")] = None,
    warehouse_id: int | None = None,
    sku: Annotated[str | None, Field(description="Exact SKU, e.g. 'BEARING_6205'")] = None,
    below_reorder_only: Annotated[bool, Field(description="Only items needing reorder (critical)")] = False,
    limit: Annotated[int, Field(ge=1, le=200)] = 50,
) -> InventoryResult:
    """Stock per SKU and warehouse with reorder advice, most urgent first. Use for low-stock / critical SKUs.
    action_needed by shortfall (reorder_level - quantity): >= 3 ORDER IMMEDIATELY, 1-2 ORDER TODAY, else OK."""
    if plant is not None and not query("SELECT 1 FROM warehouses WHERE plant ILIKE %s", (plant,)):
        known = ", ".join(r["plant"] for r in query("SELECT DISTINCT plant FROM warehouses ORDER BY plant"))
        raise ToolError(f"NOT_FOUND: plant '{plant}' does not exist (known: {known})")
    if warehouse_id is not None and not query("SELECT 1 FROM warehouses WHERE id = %s", (warehouse_id,)):
        raise ToolError(f"NOT_FOUND: warehouse {warehouse_id} does not exist")
    if sku is not None and not query("SELECT 1 FROM inventory WHERE sku ILIKE %s", (sku,)):
        raise ToolError(f"NOT_FOUND: SKU '{sku}' does not exist")
    rows = query(
        """
        SELECT i.sku, i.quantity, i.reorder_level, w.name AS warehouse, w.plant,
               CASE WHEN i.reorder_level - i.quantity >= 3 THEN 'ORDER IMMEDIATELY'
                    WHEN i.reorder_level - i.quantity >= 1 THEN 'ORDER TODAY'
                    ELSE 'OK' END AS action_needed,
               COUNT(*) OVER () AS total
        FROM inventory i JOIN warehouses w ON w.id = i.warehouse_id
        WHERE (%(plant)s::text IS NULL OR w.plant ILIKE %(plant)s)
          AND (%(wid)s::int IS NULL OR w.id = %(wid)s)
          AND (%(sku)s::text IS NULL OR i.sku ILIKE %(sku)s)
          AND (NOT %(below)s OR i.quantity < i.reorder_level)
        ORDER BY i.reorder_level - i.quantity DESC, i.sku
        LIMIT %(limit)s
        """,
        {"plant": plant, "wid": warehouse_id, "sku": sku, "below": below_reorder_only, "limit": limit},
    )
    return InventoryResult(total=rows[0]["total"] if rows else 0, items=rows)
