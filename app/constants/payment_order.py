"""ثابت‌های دستور پرداخت — از روال مالی مشترک."""

from app.constants.financial_workflow import (  # noqa: F401
    ACTION_APPROVAL,
    ACTION_CONFIRM_SEPIDAR,
    ACTION_FINAL_PAYMENT_APPROVAL,
    ACTION_MARK_PAYMENT,
    WORKFLOW_REF_PAYMENT_ORDER,
)

PAYMENT_ORDER_KIND_INDIVIDUAL = "individual"
PAYMENT_ORDER_KIND_COLLECTIVE = "collective"
