from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company_bank_account import CompanyBankAccount
from app.schemas.bank_account import BankAccountCreate, BankAccountUpdate
from app.services.bank_account_utils import bank_account_to_dict, format_bank_account_display
from app.services.query_utils import apply_search_filter, apply_sort


def _clear_other_defaults(db: Session, except_id: int | None = None) -> None:
    query = db.query(CompanyBankAccount).filter(CompanyBankAccount.is_default == True)  # noqa: E712
    if except_id is not None:
        query = query.filter(CompanyBankAccount.id != except_id)
    for row in query.all():
        row.is_default = False


def serialize_company_account(row: CompanyBankAccount) -> dict:
    data = bank_account_to_dict(row)
    data["id"] = row.id
    data["isDefault"] = row.is_default
    data["isActive"] = row.is_active
    data["createdAt"] = row.created_at
    data["updatedAt"] = row.updated_at
    return data


def create_account(db: Session, payload: BankAccountCreate) -> dict:
    if payload.is_default:
        _clear_other_defaults(db)
    row = CompanyBankAccount(
        label=payload.label.strip(),
        bank_name=(payload.bank_name or "").strip() or None,
        account_number=(payload.account_number or "").strip() or None,
        sheba_number=(payload.sheba_number or "").strip() or None,
        card_number=(payload.card_number or "").strip() or None,
        is_default=payload.is_default,
        is_active=payload.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_company_account(row)


def update_account(db: Session, account_id: int, payload: BankAccountUpdate) -> dict | None:
    row = db.get(CompanyBankAccount, account_id)
    if not row:
        return None
    if payload.label is not None:
        row.label = payload.label.strip()
    if payload.bank_name is not None:
        row.bank_name = payload.bank_name.strip() or None
    if payload.account_number is not None:
        row.account_number = payload.account_number.strip() or None
    if payload.sheba_number is not None:
        row.sheba_number = payload.sheba_number.strip() or None
    if payload.card_number is not None:
        row.card_number = payload.card_number.strip() or None
    if payload.is_active is not None:
        row.is_active = payload.is_active
    if payload.is_default is not None:
        if payload.is_default:
            _clear_other_defaults(db, except_id=row.id)
        row.is_default = payload.is_default
    db.commit()
    db.refresh(row)
    return serialize_company_account(row)


def get_account(db: Session, account_id: int) -> dict | None:
    row = db.get(CompanyBankAccount, account_id)
    return serialize_company_account(row) if row else None


def get_active_account(db: Session, account_id: int) -> CompanyBankAccount | None:
    row = db.get(CompanyBankAccount, account_id)
    if not row or not row.is_active:
        return None
    return row


def list_accounts(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 100,
    sort_by: str = "id",
    sort_order: str = "desc",
    search: str | None = None,
    active_only: bool = True,
) -> list[dict]:
    query = db.query(CompanyBankAccount)
    if active_only:
        query = query.filter(CompanyBankAccount.is_active == True)  # noqa: E712
    query = apply_search_filter(
        query,
        CompanyBankAccount,
        search,
        ["label", "bank_name", "account_number", "sheba_number", "card_number"],
    )
    query = apply_sort(query, CompanyBankAccount, sort_by, sort_order)
    return [serialize_company_account(r) for r in query.offset(offset).limit(limit).all()]


def count_accounts(
    db: Session,
    *,
    search: str | None = None,
    active_only: bool = True,
) -> int:
    query = db.query(func.count(CompanyBankAccount.id))
    if active_only:
        query = query.filter(CompanyBankAccount.is_active == True)  # noqa: E712
    query = apply_search_filter(
        query,
        CompanyBankAccount,
        search,
        ["label", "bank_name", "account_number", "sheba_number", "card_number"],
    )
    return query.scalar() or 0


def delete_account(db: Session, account_id: int) -> bool:
    row = db.get(CompanyBankAccount, account_id)
    if not row:
        return False
    row.is_active = False
    db.commit()
    return True


def resolve_payer_snapshot(db: Session, account_id: int) -> tuple[str, int]:
    row = get_active_account(db, account_id)
    if not row:
        raise ValueError("حساب بانکی شرکت یافت نشد یا غیرفعال است")
    return format_bank_account_display(row), row.id
