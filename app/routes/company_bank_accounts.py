from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import COMPANY_ACCOUNT_LOOKUP
from app.dependencies.auth import require_any_permission, require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.dependencies.pagination import MAX_PAGE_SIZE
from app.schemas.bank_account import BankAccountCreate, BankAccountUpdate
from app.services import company_bank_account as cba_svc

router = APIRouter(prefix="/company-bank-accounts", tags=["Company bank accounts"])


@router.get("/")
def list_company_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    search: str | None = Query(None),
    active_only: bool = Query(True, alias="activeOnly"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*COMPANY_ACCOUNT_LOOKUP)),
):
    offset = (page - 1) * page_size
    items = cba_svc.list_accounts(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
        active_only=active_only,
    )
    total = cba_svc.count_accounts(db, search=search, active_only=active_only)
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_company_account(
    payload: BankAccountCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        return cba_svc.create_account(db, payload)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/{account_id}")
def get_company_account(
    account_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*COMPANY_ACCOUNT_LOOKUP)),
):
    row = cba_svc.get_account(db, account_id)
    if not row:
        raise HTTPException(status_code=404, detail="حساب یافت نشد")
    return row


@router.put("/{account_id}")
@router.patch("/{account_id}")
def update_company_account(
    account_id: int,
    payload: BankAccountUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    row = cba_svc.update_account(db, account_id, payload)
    if not row:
        raise HTTPException(status_code=404, detail="حساب یافت نشد")
    return row


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company_account(
    account_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    if not cba_svc.delete_account(db, account_id):
        raise HTTPException(status_code=404, detail="حساب یافت نشد")
