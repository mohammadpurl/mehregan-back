"""بررسی اینکه کاربر می‌تواند روی یک مرحله workflow اقدام کند."""

from app.models.workflow_step import WorkflowStep


def user_can_act_on_workflow_step(user, step: WorkflowStep) -> bool:
    user_role_ids = [r.id for r in user.get_roles()]
    is_assignee = step.assigned_user_id is not None and step.assigned_user_id == user.id
    return step.role_id in user_role_ids or is_assignee
