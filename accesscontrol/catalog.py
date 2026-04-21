PERMISSION_CATALOG = [
    {
        "code": "categories",
        "name": "Menu Categories",
        "description": "Manage menu category records.",
        "permissions": [
            ("view", "View menu categories"),
            ("create", "Create menu categories"),
            ("update", "Update menu categories"),
            ("delete", "Delete menu categories"),
        ],
    },
    {
        "code": "event_bookings",
        "name": "Event Bookings",
        "description": "Manage event bookings and schedules.",
        "permissions": [
            ("view", "View event bookings"),
            ("create", "Create event bookings"),
            ("update", "Update event bookings"),
            ("delete", "Delete event bookings"),
            ("change_status", "Change event booking status"),
        ],
    },
    {
        "code": "event_booking_reports",
        "name": "Event Booking Reports",
        "description": "Access booking summaries and event reports.",
        "permissions": [
            ("view", "View booking reports"),
        ],
    },
    {
        "code": "session_ingredients",
        "name": "Session Ingredients",
        "description": "Manage ingredients linked to event sessions.",
        "permissions": [
            ("view", "View session ingredients"),
            ("create", "Create session ingredients"),
            ("update", "Update session ingredients"),
            ("delete", "Delete session ingredients"),
        ],
    },
    {
        "code": "event_item_configs",
        "name": "Event Item Configs",
        "description": "Manage event item configuration records.",
        "permissions": [
            ("view", "View event item configs"),
            ("create", "Create event item configs"),
            ("update", "Update event item configs"),
            ("delete", "Delete event item configs"),
        ],
    },
    {
        "code": "ingredient_vendor_assignments",
        "name": "Ingredient Vendor Assignments",
        "description": "Manage vendor assignments for ingredients.",
        "permissions": [
            ("view", "View ingredient vendor assignments"),
            ("create", "Create ingredient vendor assignments"),
            ("update", "Update ingredient vendor assignments"),
            ("delete", "Delete ingredient vendor assignments"),
        ],
    },
    {
        "code": "items",
        "name": "Items",
        "description": "Manage item master data.",
        "permissions": [
            ("view", "View items"),
            ("create", "Create items"),
            ("update", "Update items"),
            ("delete", "Delete items"),
        ],
    },
    {
        "code": "recipes",
        "name": "Recipes",
        "description": "Manage recipe ingredients.",
        "permissions": [
            ("view", "View recipes"),
            ("create", "Create recipes"),
            ("update", "Update recipes"),
            ("delete", "Delete recipes"),
        ],
    },
    {
        "code": "ingredient_categories",
        "name": "Ingredient Categories",
        "description": "Manage ingredient categories and ingredient items.",
        "permissions": [
            ("view", "View ingredient categories"),
            ("create", "Create ingredient categories"),
            ("update", "Update ingredient categories"),
            ("delete", "Delete ingredient categories"),
        ],
    },
    {
        "code": "ingredient_items",
        "name": "Ingredient Items",
        "description": "Manage ingredient items.",
        "permissions": [
            ("view", "View ingredient items"),
            ("create", "Create ingredient items"),
            ("update", "Update ingredient items"),
            ("delete", "Delete ingredient items"),
        ],
    },
    {
        "code": "payments",
        "name": "Payments",
        "description": "Manage payment entries.",
        "permissions": [
            ("view", "View payments"),
            ("create", "Create payments"),
            ("update", "Update payments"),
            ("delete", "Delete payments"),
        ],
    },
    {
        "code": "transactions",
        "name": "Transactions",
        "description": "View transaction reports.",
        "permissions": [
            ("view", "View transactions"),
        ],
    },
    {
        "code": "stock_categories",
        "name": "Stock Categories",
        "description": "Manage stock categories.",
        "permissions": [
            ("view", "View stock categories"),
            ("create", "Create stock categories"),
            ("update", "Update stock categories"),
            ("delete", "Delete stock categories"),
        ],
    },
    {
        "code": "stock_items",
        "name": "Stock Items",
        "description": "Manage stock items.",
        "permissions": [
            ("view", "View stock items"),
            ("create", "Create stock items"),
            ("update", "Update stock items"),
            ("delete", "Delete stock items"),
        ],
    },
    {
        "code": "stock_adjustments",
        "name": "Stock Adjustments",
        "description": "Add or remove stock quantities.",
        "permissions": [
            ("view", "View stock adjustments"),
            ("create", "Create stock adjustments"),
            ("update", "Update stock adjustments"),
        ],
    },
    {
        "code": "stock_alerts",
        "name": "Stock Alerts",
        "description": "View stock alert information.",
        "permissions": [
            ("view", "View stock alerts"),
        ],
    },
    {
        "code": "users",
        "name": "Users",
        "description": "Manage user accounts.",
        "permissions": [
            ("view", "View users"),
            ("create", "Create users"),
            ("update", "Update users"),
            ("delete", "Delete users"),
            ("change_password", "Change user passwords"),
        ],
    },
    {
        "code": "notes",
        "name": "Notes",
        "description": "Manage notes.",
        "permissions": [
            ("view", "View notes"),
            ("create", "Create notes"),
            ("update", "Update notes"),
            ("delete", "Delete notes"),
        ],
    },
    {
        "code": "business_profiles",
        "name": "Business Profiles",
        "description": "Manage business profile details.",
        "permissions": [
            ("view", "View business profiles"),
            ("create", "Create business profiles"),
            ("update", "Update business profiles"),
            ("delete", "Delete business profiles"),
        ],
    },
    {
        "code": "expense_entries",
        "name": "Expenses",
        "description": "Manage expense entries.",
        "permissions": [
            ("view", "View expenses"),
            ("create", "Create expenses"),
            ("update", "Update expenses"),
            ("delete", "Delete expenses"),
        ],
    },
    {
        "code": "expense_categories",
        "name": "Expense Categories",
        "description": "Manage expense categories.",
        "permissions": [
            ("view", "View expense categories"),
            ("create", "Create expense categories"),
            ("update", "Update expense categories"),
            ("delete", "Delete expense categories"),
        ],
    },
    {
        "code": "expense_entities",
        "name": "Expense Entities",
        "description": "Manage expense entities.",
        "permissions": [
            ("view", "View expense entities"),
            ("create", "Create expense entities"),
            ("update", "Update expense entities"),
            ("delete", "Delete expense entities"),
        ],
    },
    {
        "code": "expense_summaries",
        "name": "Expense Summaries",
        "description": "Access expense summary reports.",
        "permissions": [
            ("view", "View expense summaries"),
        ],
    },
    {
        "code": "vendor_categories",
        "name": "Vendor Categories",
        "description": "Manage vendor-facing categories.",
        "permissions": [
            ("view", "View vendor categories"),
            ("create", "Create vendor categories"),
            ("update", "Update vendor categories"),
            ("delete", "Delete vendor categories"),
        ],
    },
    {
        "code": "vendors",
        "name": "Vendors",
        "description": "Manage vendor records.",
        "permissions": [
            ("view", "View vendors"),
            ("create", "Create vendors"),
            ("update", "Update vendors"),
            ("delete", "Delete vendors"),
        ],
    },
    {
        "code": "staff_roles",
        "name": "Staff Roles",
        "description": "Manage staff role master data.",
        "permissions": [
            ("view", "View staff roles"),
            ("create", "Create staff roles"),
            ("update", "Update staff roles"),
            ("delete", "Delete staff roles"),
        ],
    },
    {
        "code": "waiter_types",
        "name": "Waiter Types",
        "description": "Manage waiter type master data.",
        "permissions": [
            ("view", "View waiter types"),
            ("create", "Create waiter types"),
            ("update", "Update waiter types"),
            ("delete", "Delete waiter types"),
        ],
    },
    {
        "code": "fixed_staff_payments",
        "name": "Fixed Staff Payments",
        "description": "Manage fixed staff salary payments.",
        "permissions": [
            ("view", "View fixed staff payments"),
            ("create", "Create fixed staff payments"),
            ("update", "Update fixed staff payments"),
            ("delete", "Delete fixed staff payments"),
        ],
    },
    {
        "code": "staff_withdrawals",
        "name": "Staff Withdrawals",
        "description": "Manage staff withdrawals.",
        "permissions": [
            ("view", "View staff withdrawals"),
            ("create", "Create staff withdrawals"),
            ("update", "Update staff withdrawals"),
            ("delete", "Delete staff withdrawals"),
        ],
    },
    {
        "code": "event_staff_assignments",
        "name": "Event Staff Assignments",
        "description": "Manage event staff assignments.",
        "permissions": [
            ("view", "View event staff assignments"),
            ("create", "Create event staff assignments"),
            ("update", "Update event staff assignments"),
            ("delete", "Delete event staff assignments"),
            ("view_summary", "View event staff summaries"),
        ],
    },
    {
        "code": "ground_categories",
        "name": "Ground Categories",
        "description": "Manage ground categories.",
        "permissions": [
            ("view", "View ground categories"),
            ("create", "Create ground categories"),
            ("update", "Update ground categories"),
            ("delete", "Delete ground categories"),
        ],
    },
    {
        "code": "ground_items",
        "name": "Ground Items",
        "description": "Manage ground items.",
        "permissions": [
            ("view", "View ground items"),
            ("create", "Create ground items"),
            ("update", "Update ground items"),
            ("delete", "Delete ground items"),
        ],
    },
    {
        "code": "invoice_setup",
        "name": "Invoice Setup",
        "description": "Manage invoice setup entries.",
        "permissions": [
            ("view", "View invoice setup"),
            ("create", "Create invoice setup"),
            ("update", "Update invoice setup"),
            ("delete", "Delete invoice setup"),
        ],
    },
    {
        "code": "party_information",
        "name": "Party Information",
        "description": "Manage party information records.",
        "permissions": [
            ("view", "View party information"),
            ("create", "Create party information"),
            ("update", "Update party information"),
            ("delete", "Delete party information"),
        ],
    },
    {
        "code": "global_configuration",
        "name": "Global Configuration",
        "description": "Manage global configuration.",
        "permissions": [
            ("view", "View global configuration"),
            ("create", "Create global configuration"),
            ("update", "Update global configuration"),
            ("delete", "Delete global configuration"),
        ],
    },
    {
        "code": "branch_items",
        "name": "Branch Items",
        "description": "Manage branch items.",
        "permissions": [
            ("view", "View branch items"),
            ("create", "Create branch items"),
            ("update", "Update branch items"),
            ("delete", "Delete branch items"),
        ],
    },
    {
        "code": "branch_bills",
        "name": "Branch Bills",
        "description": "Manage branch bills.",
        "permissions": [
            ("view", "View branch bills"),
            ("create", "Create branch bills"),
            ("update", "Update branch bills"),
            ("delete", "Delete branch bills"),
        ],
    },
]


def iter_catalog_permissions():
    for module_index, module in enumerate(PERMISSION_CATALOG, start=1):
        for permission_index, permission in enumerate(module["permissions"], start=1):
            action, name = permission
            yield {
                "module_code": module["code"],
                "module_name": module["name"],
                "module_description": module["description"],
                "module_sort_order": module_index,
                "permission_code": f"{module['code']}.{action}",
                "permission_action": action,
                "permission_name": name,
                "permission_description": f"{name} permission for {module['name'].lower()}.",
                "permission_sort_order": permission_index,
            }
