def apply_workflow(db, entity, new_state, user, entity_name):
    current = entity.workflow_state.code

    if not can_transition(current, new_state):
        raise Exception("invalid transition")

    entity.workflow_state_id = new_state

    log_action(
        db,
        entity=entity_name,
        entity_id=entity.id,
        action="status_change",
        user_id=user.id,
        old_data={"state": current},
        new_data={"state": new_state},
    )
