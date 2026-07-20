"""بررسی اینکه کاربر می‌تواند روی یک مرحله workflow اقدام کند."""

from app.models.workflow_step import WorkflowStep

# هنگام auto-skip مراحل پشت‌سرهم با همان تأییدکننده
AUTO_SKIP_COMMENT = "تأیید خودکار: همان تأییدکننده مرحله قبل"


def user_can_act_on_workflow_step(user, step: WorkflowStep) -> bool:
    """اگر مسئول مشخص شده فقط همان نفر؛ وگرنه هر عضو نقش مرحله."""
    if step.assigned_user_id is not None:
        return step.assigned_user_id == user.id
    user_role_ids = [r.id for r in user.get_roles()]
    return step.role_id is not None and step.role_id in user_role_ids


def is_same_approver_for_auto_skip(user, step: WorkflowStep) -> bool:
    """
    آیا تأییدکنندهٔ فعلی همان مسئول مرحلهٔ بعدی است؟
    اگر assigned_user_id مشخص باشد فقط همان نفر؛ وگرنه نقش/دسترسی.
    """
    if step.assigned_user_id is not None:
        return step.assigned_user_id == user.id
    return user_can_act_on_workflow_step(user, step)
