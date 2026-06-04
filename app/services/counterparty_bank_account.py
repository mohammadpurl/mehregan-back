from sqlalchemy.orm import Session

from app.models.counterparty import Counterparty
from app.models.counterparty_bank_account import CounterpartyBankAccount
from app.schemas.bank_account import BankAccountCreate, BankAccountUpdate
from app.services.bank_account_utils import bank_account_to_dict, format_bank_account_display


def _clear_defaults(db: Session, counterparty_id: int, except_id: int | None = None) -> None:
    query = db.query(CounterpartyBankAccount).filter(
        CounterpartyBankAccount.counterparty_id == counterparty_id,
        CounterpartyBankAccount.is_default == True,  # noqa: E712
    )
    if except_id is not None:
        query = query.filter(CounterpartyBankAccount.id != except_id)
    for row in query.all():
        row.is_default = False


def serialize_cp_account(row: CounterpartyBankAccount) -> dict:
    data = bank_account_to_dict(row)
    data["id"] = row.id
    data["counterpartyId"] = row.counterparty_id
    data["isDefault"] = row.is_default
    data["isActive"] = row.is_active
    data["createdAt"] = row.created_at
    data["updatedAt"] = row.updated_at
    return data


def list_for_counterparty(
    db: Session,
    counterparty_id: int,
    *,
    active_only: bool = True,
) -> list[dict]:
    query = db.query(CounterpartyBankAccount).filter(
        CounterpartyBankAccount.counterparty_id == counterparty_id
    )
    if active_only:
        query = query.filter(CounterpartyBankAccount.is_active == True)  # noqa: E712
    rows = query.order_by(
        CounterpartyBankAccount.is_default.desc(),
        CounterpartyBankAccount.id,
    ).all()
    return [serialize_cp_account(r) for r in rows]


def create_account(
    db: Session, counterparty_id: int, payload: BankAccountCreate
) -> dict:
    cp = db.get(Counterparty, counterparty_id)
    if not cp or not cp.is_active:
        raise ValueError("طرف حساب یافت نشد یا غیرفعال است")
    if payload.is_default:
        _clear_defaults(db, counterparty_id)
    row = CounterpartyBankAccount(
        counterparty_id=counterparty_id,
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
    return serialize_cp_account(row)


def update_account(
    db: Session, counterparty_id: int, account_id: int, payload: BankAccountUpdate
) -> dict | None:
    row = (
        db.query(CounterpartyBankAccount)
        .filter(
            CounterpartyBankAccount.id == account_id,
            CounterpartyBankAccount.counterparty_id == counterparty_id,
        )
        .first()
    )
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
            _clear_defaults(db, counterparty_id, except_id=row.id)
        row.is_default = payload.is_default
    db.commit()
    db.refresh(row)
    return serialize_cp_account(row)


def delete_account(db: Session, counterparty_id: int, account_id: int) -> bool:
    row = (
        db.query(CounterpartyBankAccount)
        .filter(
            CounterpartyBankAccount.id == account_id,
            CounterpartyBankAccount.counterparty_id == counterparty_id,
        )
        .first()
    )
    if not row:
        return False
    row.is_active = False
    db.commit()
    return True


def get_active_account(
    db: Session, counterparty_id: int, account_id: int
) -> CounterpartyBankAccount | None:
    row = (
        db.query(CounterpartyBankAccount)
        .filter(
            CounterpartyBankAccount.id == account_id,
            CounterpartyBankAccount.counterparty_id == counterparty_id,
            CounterpartyBankAccount.is_active == True,  # noqa: E712
        )
        .first()
    )
    return row


def resolve_receiver_snapshot(
    db: Session, counterparty_id: int, account_id: int
) -> tuple[str, int]:
    row = get_active_account(db, counterparty_id, account_id)
    if not row:
        raise ValueError("حساب بانکی طرف‌حساب یافت نشد یا غیرفعال است")
    return format_bank_account_display(row), row.id
