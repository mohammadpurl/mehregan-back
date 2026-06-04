def can_user_approve(user, step):
    user_role_ids = [r.id for r in user.roles]

    return step.required_role_id in user_role_ids
