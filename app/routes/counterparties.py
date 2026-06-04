from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import COUNTERPARTY_LOOKUP
from app.dependencies.auth import require_any_permission, require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.dependencies.pagination import MAX_PAGE_SIZE
from app.schemas.bank_account import BankAccountCreate, BankAccountUpdate
from app.schemas.counterparty import (
    CounterpartyCreate,
    CounterpartyListResponse,
    CounterpartyOut,
    CounterpartyUpdate,
)
from app.services import counterparty as cp_svc
from app.services import counterparty_bank_account as cp_ba_svc

router = APIRouter(prefix="/counterparties", tags=["Counterparties"])


@router.post("/", response_model=CounterpartyOut, status_code=status.HTTP_201_CREATED)
def create_counterparty_api(
    payload: CounterpartyCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    return cp_svc.create_counterparty(db, payload)


@router.get("/", response_model=CounterpartyListResponse)
def list_counterparties_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    search: str | None = Query(None),
    active_only: bool = Query(True, alias="activeOnly"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*COUNTERPARTY_LOOKUP)),
):
    offset = (page - 1) * page_size
    items = cp_svc.list_counterparties(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
        active_only=active_only,
    )
    total = cp_svc.count_counterparties(db, search=search, active_only=active_only)
    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


@router.get("/{counterparty_id}", response_model=CounterpartyOut)
def get_counterparty_api(
    counterparty_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*COUNTERPARTY_LOOKUP)),
):
    row = cp_svc.get_counterparty(db, counterparty_id)
    if not row:
        raise HTTPException(status_code=404, detail="طرف حساب یافت نشد")
    return row


@router.put("/{counterparty_id}", response_model=CounterpartyOut)
@router.patch("/{counterparty_id}", response_model=CounterpartyOut)
def update_counterparty_api(
    counterparty_id: int,
    payload: CounterpartyUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    row = cp_svc.update_counterparty(db, counterparty_id, payload)
    if not row:
        raise HTTPException(status_code=404, detail="طرف حساب یافت نشد")
    return row


@router.delete("/{counterparty_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_counterparty_api(
    counterparty_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    if not cp_svc.delete_counterparty(db, counterparty_id):
        raise HTTPException(status_code=404, detail="طرف حساب یافت نشد")


@router.get("/{counterparty_id}/bank-accounts")
def list_counterparty_bank_accounts(
    counterparty_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*COUNTERPARTY_LOOKUP)),
):
    return cp_ba_svc.list_for_counterparty(db, counterparty_id)


@router.post("/{counterparty_id}/bank-accounts", status_code=status.HTTP_201_CREATED)
def create_counterparty_bank_account(
    counterparty_id: int,
    payload: BankAccountCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        return cp_ba_svc.create_account(db, counterparty_id, payload)
    except ValueError as err:
        raise_from_value_error(err)


@router.put("/{counterparty_id}/bank-accounts/{account_id}")
@router.patch("/{counterparty_id}/bank-accounts/{account_id}")
def update_counterparty_bank_account(
    counterparty_id: int,
    account_id: int,
    payload: BankAccountUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    row = cp_ba_svc.update_account(db, counterparty_id, account_id, payload)
    if not row:
        raise HTTPException(status_code=404, detail="حساب بانکی یافت نشد")
    return row


@router.delete(
    "/{counterparty_id}/bank-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_counterparty_bank_account(
    counterparty_id: int,
    account_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    if not cp_ba_svc.delete_account(db, counterparty_id, account_id):
        raise HTTPException(status_code=404, detail="حساب بانکی یافت نشد")
