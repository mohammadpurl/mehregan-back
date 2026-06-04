from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.assignment_rule import (
    AssignmentRuleCreate,
    AssignmentRuleOut,
    AssignmentRuleUpdate,
)
from app.services import assignment_rule_service as ar_svc

router = APIRouter(prefix="/assignment-rules", tags=["Assignment rules"])


@router.get("/", response_model=list[AssignmentRuleOut])
def list_assignment_rules(
    role_id: int | None = Query(None, alias="roleId"),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    return ar_svc.list_rules(db, role_id=role_id)


@router.post("/", response_model=AssignmentRuleOut, status_code=status.HTTP_201_CREATED)
def create_assignment_rule(
    payload: AssignmentRuleCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        return ar_svc.create_rule(
            db,
            role_id=payload.role_id,
            strategy=payload.strategy,
            is_active=payload.is_active,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{rule_id}", response_model=AssignmentRuleOut)
def get_assignment_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    row = ar_svc.get_rule(db, rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="قانون تخصیص یافت نشد")
    return row


@router.patch("/{rule_id}", response_model=AssignmentRuleOut)
@router.put("/{rule_id}", response_model=AssignmentRuleOut)
def update_assignment_rule(
    rule_id: int,
    payload: AssignmentRuleUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        row = ar_svc.update_rule(
            db,
            rule_id,
            strategy=payload.strategy,
            is_active=payload.is_active,
        )
    except ValueError as err:
        raise_from_value_error(err)
    if not row:
        raise HTTPException(status_code=404, detail="قانون تخصیص یافت نشد")
    return row


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    if not ar_svc.delete_rule(db, rule_id):
        raise HTTPException(status_code=404, detail="قانون تخصیص یافت نشد")
