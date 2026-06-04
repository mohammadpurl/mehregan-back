from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.sla_policy import SlaPolicyCreate, SlaPolicyOut, SlaPolicyUpdate
from app.services import sla_policy_service as sla_svc

router = APIRouter(prefix="/sla-policies", tags=["SLA"])


@router.get("/", response_model=list[SlaPolicyOut])
def list_sla_policies_api(
    ref_type: str | None = Query(None, alias="refType"),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    return sla_svc.list_sla_policies(db, ref_type=ref_type)


@router.post("/", response_model=SlaPolicyOut, status_code=status.HTTP_201_CREATED)
def create_sla_policy_api(
    payload: SlaPolicyCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        return sla_svc.create_sla_policy(db, payload)
    except ValueError as err:
        raise_from_value_error(err)


@router.put("/{policy_id}", response_model=SlaPolicyOut)
@router.patch("/{policy_id}", response_model=SlaPolicyOut)
def update_sla_policy_api(
    policy_id: int,
    payload: SlaPolicyUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    row = sla_svc.update_sla_policy(db, policy_id, payload)
    if not row:
        raise HTTPException(status_code=404, detail="سیاست SLA یافت نشد")
    return row


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sla_policy_api(
    policy_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    if not sla_svc.delete_sla_policy(db, policy_id):
        raise HTTPException(status_code=404, detail="سیاست SLA یافت نشد")
