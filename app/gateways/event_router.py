def route_event(event: str, payload: dict):

    # =========================
    # WORKFLOW EVENTS
    # =========================
    if event == "workflow.next_step":
        return {
            "type": "inbox.created",
            "user_id": payload["user_id"],
            "data": {
                "ref_id": payload["instance_id"],
                "step_id": payload["step_id"],
                "title": "Approval Required",
            },
        }

    if event == "workflow.approved":
        return {
            "type": "workflow.status",
            "user_id": payload["user_id"],
            "data": {"status": "approved", "instance_id": payload["instance_id"]},
        }

    if event == "sla.overdue":
        return {
            "type": "sla.alert",
            "user_id": payload["owner_id"],
            "data": {"message": "Task overdue", "instance_id": payload["instance_id"]},
        }

    # default fallback
    return {"type": "system.event", "broadcast": True, "data": payload}
