"""ثابت‌های اسناد مالی."""

WORKFLOW_REF_FINANCIAL_DOCUMENT = "financial_document"

DOCUMENT_TYPE_CHECK = "check"
DOCUMENT_TYPE_OTHER = "other"

DOCUMENT_TYPES = frozenset({DOCUMENT_TYPE_CHECK, DOCUMENT_TYPE_OTHER})

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
