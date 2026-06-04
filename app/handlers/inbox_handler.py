from app.models.inbox import InboxItem
from app.services.role_resolver import resolve_user_by_role


def on_workflow_approved(event):
    instance_id = event["instance_id"]

    user_id = resolve_user_by_role(event["role_id"])

    inbox = InboxItem(
        user_id=user_id,
        ref_id=instance_id,
        ref_type="workflow",
        title="Approval Required",
        is_read=False,
    )

    db.add(inbox)
    db.commit()
