REF_TYPE = "mission_request"

STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_REPORT_PENDING_APPROVAL = "REPORT_PENDING_APPROVAL"  # گزارش ثبت شد؛ در تأیید
STATUS_COMPLETED = "COMPLETED"

# گردش‌کار تأیید گزارش ماموریت: مدیر مستقیم → مدیرعامل
WORKFLOW_REF_MISSION_REPORT = "mission_report"

MISSION_REPORT_STEPS = [
    {
        "order": 1,
        "label": "تأیید گزارش — مدیر مستقیم",
        "role_aliases": ["manager", "project_manager", "مدیر مستقیم", "مدیر واحد"],
        "assignee_strategy": "submitter_manager",
        "step_action": "approval",
    },
    {
        "order": 2,
        "label": "تأیید گزارش — مدیرعامل",
        "role_aliases": ["ceo", "managing_director", "مدیرعامل"],
        "assignee_strategy": "role_pool",
        "step_action": "approval",
    },
]
