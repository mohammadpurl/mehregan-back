"""Permission codes grouped for route guards (aligned with nav_menu + reset_rbac)."""

# Dashboard
DASHBOARD_READ = ("dashboard.read",)

# Ad-hoc: مسیر API با get_current_active_user باز است؛ این کدها فقط برای inbox/پیوست
AD_HOC_TASK_ACCESS = DASHBOARD_READ

# Workflow
WORKFLOW_READ = ("workflow.read",)
WORKFLOW_INBOX = ("workflow.inbox.read",)
WORKFLOW_TRACKING = (
    "workflow.tracking.read",
    "workflow.all.read",
    "workflow.read",
)
WORKFLOW_ALL = ("workflow.all.read",)
WORKFLOW_APPROVE = ("workflow.approve",)
WORKFLOW_CORRECTION = ("workflow.correction",)
WORKFLOW_VIEW = (
    "workflow.read",
    "workflow.inbox.read",
    "workflow.tracking.read",
    "workflow.all.read",
)

# Financial
PAYMENT_ACCESS = ("payment.create", "payment.approve")
PAYMENT_WRITE = ("payment.create",)
PAYMENT_APPROVE = ("payment.approve",)

# Admin
ADMIN_MANAGE = ("admin.manage",)

# Procurement
PROCUREMENT_READ = ("procurement.read",)
PROCUREMENT_WRITE = ("procurement.write",)

# Inventory / warehouse forms
INVENTORY_READ = ("inventory.read",)
INVENTORY_WRITE = ("inventory.transfer",)
WAREHOUSE_FORMS = ("inventory.read", "inventory.transfer")

# Secure attachment download (route guard; entity-level check in attachment_service)
ATTACHMENT_DOWNLOAD = (
    *PAYMENT_ACCESS,
    *PROCUREMENT_READ,
    *INVENTORY_READ,
    *WORKFLOW_APPROVE,
    *WORKFLOW_VIEW,
    *AD_HOC_TASK_ACCESS,
)

# Master data
MASTERDATA_MANAGE = ("masterdata.manage",)
MASTERDATA_VIEW = ("masterdata.manage", "item.read", "item.*", "inventory.read")

# Admin lookups used from payment forms
COUNTERPARTY_LOOKUP = ("admin.manage", "payment.create", "payment.approve")
COMPANY_ACCOUNT_LOOKUP = ("admin.manage", "payment.create", "payment.approve")

# Inbox API — workflow approvers + anyone who can receive ad-hoc assignments
INBOX_READ = WORKFLOW_INBOX + AD_HOC_TASK_ACCESS

# Notifications (inbox-related)
NOTIFICATIONS = INBOX_READ + WORKFLOW_VIEW
