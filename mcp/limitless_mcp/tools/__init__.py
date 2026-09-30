from limitless_mcp.tools.balance import get_outstanding_balance
from limitless_mcp.tools.customers import read_customers
from limitless_mcp.tools.inventory import read_inventory
from limitless_mcp.tools.invoices import read_invoices
from limitless_mcp.tools.vendors import read_vendors

# Registered by server.py. New tool = new file here + one line below.
TOOLS = [read_customers, read_invoices, read_inventory, read_vendors, get_outstanding_balance]
