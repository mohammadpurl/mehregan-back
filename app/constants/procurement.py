"""وضعیت‌ها و ثابت‌های درخواست خرید."""

REQUEST_TYPE_PURCHASE = "purchase"
REQUEST_TYPE_INTERNAL = "internal"

# مرحله ۱: تأیید درخواست
STATUS_PENDING = "pending"
STATUS_AWAITING_PROFORMA = "awaiting_proforma"
# مرحله ۲: پیش‌فاکتور
STATUS_PROFORMA_REVIEW = "proforma_review"
STATUS_READY_FOR_PAYMENT = "ready_for_payment"
STATUS_AWAITING_INVOICE = "awaiting_invoice"
STATUS_PAYMENT_PENDING = "payment_pending"
STATUS_RECEIVING = "receiving"
STATUS_COMPLETED = "completed"

GRN_STATUS_DRAFT = "draft"
GRN_STATUS_POSTED = "posted"
GRN_STATUS_CANCELLED = "cancelled"

WORKFLOW_REF_GRN = "goods_receipt"
STATUS_REJECTED = "rejected"
STATUS_APPROVED = "approved"  # legacy

PROFORMA_STATUS_DRAFT = "draft"
PROFORMA_STATUS_SUBMITTED = "submitted"
PROFORMA_STATUS_APPROVED = "approved"
PROFORMA_STATUS_REJECTED = "rejected"

WORKFLOW_REF_REQUEST = "request"
WORKFLOW_REF_PROFORMA = "procurement_proforma"
# گردش‌کار یکپارچه درخواست خرید کالا (همه مراحل در یک instance)
WORKFLOW_REF_PURCHASE = "purchase_request"

PURCHASE_WORKFLOW_REFS = (
    WORKFLOW_REF_PURCHASE,
    WORKFLOW_REF_REQUEST,
    WORKFLOW_REF_PROFORMA,
)
