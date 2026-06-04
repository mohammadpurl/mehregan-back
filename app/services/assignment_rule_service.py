from sqlalchemy.orm import Session

from app.models.assignment_rule import AssignmentRule

VALID_STRATEGIES = frozenset({"random", "least_loaded", "round_robin"})


def list_rules(db: Session, *, role_id: int | None = None) -> list[AssignmentRule]:
    query = db.query(AssignmentRule).order_by(AssignmentRule.role_id, AssignmentRule.id)
    if role_id is not None:
        query = query.filter(AssignmentRule.role_id == role_id)
    return query.all()


def get_rule(db: Session, rule_id: int) -> AssignmentRule | None:
    return db.get(AssignmentRule, rule_id)


def create_rule(
    db: Session,
    *,
    role_id: int,
    strategy: str,
    is_active: bool = True,
) -> AssignmentRule:
    strategy = (strategy or "random").strip().lower()
    if strategy not in VALID_STRATEGIES:
        raise ValueError(
            f"strategy must be one of {sorted(VALID_STRATEGIES)}"
        )
    row = AssignmentRule(
        role_id=role_id,
        strategy=strategy,
        is_active=is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_rule(
    db: Session,
    rule_id: int,
    *,
    strategy: str | None = None,
    is_active: bool | None = None,
) -> AssignmentRule | None:
    row = db.get(AssignmentRule, rule_id)
    if not row:
        return None
    if strategy is not None:
        s = strategy.strip().lower()
        if s not in VALID_STRATEGIES:
            raise ValueError(
                f"strategy must be one of {sorted(VALID_STRATEGIES)}"
            )
        row.strategy = s
    if is_active is not None:
        row.is_active = is_active
    db.commit()
    db.refresh(row)
    return row


def delete_rule(db: Session, rule_id: int) -> bool:
    row = db.get(AssignmentRule, rule_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
