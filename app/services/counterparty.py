from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.counterparty import Counterparty
from app.schemas.bank_account import BankAccountCreate
from app.schemas.counterparty import CounterpartyCreate, CounterpartyUpdate
from app.services import counterparty_bank_account as cp_ba_svc
from app.services.query_utils import apply_search_filter, apply_sort


def _has_legacy_bank_fields(
    *,
    account_number: str | None,
    sheba_number: str | None,
    card_number: str | None,
) -> bool:
    return bool(
        (account_number or "").strip()
        or (sheba_number or "").strip()
        or (card_number or "").strip()
    )


def _seed_bank_account_from_legacy(
    db: Session,
    row: Counterparty,
    *,
    account_number: str | None,
    sheba_number: str | None,
    card_number: str | None,
) -> None:
    if not _has_legacy_bank_fields(
        account_number=account_number,
        sheba_number=sheba_number,
        card_number=card_number,
    ):
        return
    existing = cp_ba_svc.list_for_counterparty(db, row.id, active_only=False)
    if existing:
        return
    cp_ba_svc.create_account(
        db,
        row.id,
        BankAccountCreate(
            label="حساب اصلی",
            account_number=account_number,
            sheba_number=sheba_number,
            card_number=card_number,
            is_default=True,
        ),
    )


def serialize_counterparty(
    db: Session, row: Counterparty, *, include_bank_accounts: bool = False
) -> dict:
    data = {
        "id": row.id,
        "name": row.name,
        "party_type": row.party_type,
        "company_name": row.company_name,
        "account_number": row.account_number,
        "sheba_number": row.sheba_number,
        "card_number": row.card_number,
        "notes": row.notes,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "bank_accounts": [],
    }
    if include_bank_accounts:
        accounts = cp_ba_svc.list_for_counterparty(db, row.id)
        data["bank_accounts"] = [
            {
                "id": a["id"],
                "label": a["label"],
                "bank_name": a.get("bankName"),
                "account_number": a.get("accountNumber"),
                "sheba_number": a.get("shebaNumber"),
                "card_number": a.get("cardNumber"),
                "is_default": a.get("isDefault", False),
                "is_active": a.get("isActive", True),
                "display_label": a.get("displayLabel"),
                "created_at": a.get("createdAt"),
                "updated_at": a.get("updatedAt"),
            }
            for a in accounts
        ]
    return data


def create_counterparty(db: Session, payload: CounterpartyCreate) -> dict:
    row = Counterparty(
        name=payload.name.strip(),
        party_type=payload.party_type,
        company_name=(payload.company_name or "").strip() or None,
        account_number=(payload.account_number or "").strip() or None,
        sheba_number=(payload.sheba_number or "").strip() or None,
        card_number=(payload.card_number or "").strip() or None,
        notes=(payload.notes or "").strip() or None,
        is_active=payload.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _seed_bank_account_from_legacy(
        db,
        row,
        account_number=row.account_number,
        sheba_number=row.sheba_number,
        card_number=row.card_number,
    )
    return serialize_counterparty(db, row, include_bank_accounts=True)


def update_counterparty(
    db: Session, counterparty_id: int, payload: CounterpartyUpdate
) -> dict | None:
    row = db.get(Counterparty, counterparty_id)
    if not row:
        return None
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.party_type is not None:
        row.party_type = payload.party_type
    if payload.company_name is not None:
        row.company_name = payload.company_name.strip() or None
    if payload.account_number is not None:
        row.account_number = payload.account_number.strip() or None
    if payload.sheba_number is not None:
        row.sheba_number = payload.sheba_number.strip() or None
    if payload.card_number is not None:
        row.card_number = payload.card_number.strip() or None
    if payload.notes is not None:
        row.notes = payload.notes.strip() or None
    if payload.is_active is not None:
        row.is_active = payload.is_active
    db.commit()
    db.refresh(row)
    _seed_bank_account_from_legacy(
        db,
        row,
        account_number=row.account_number,
        sheba_number=row.sheba_number,
        card_number=row.card_number,
    )
    return serialize_counterparty(db, row, include_bank_accounts=True)


def get_counterparty(db: Session, counterparty_id: int) -> dict | None:
    row = db.get(Counterparty, counterparty_id)
    if not row:
        return None
    return serialize_counterparty(db, row, include_bank_accounts=True)


def list_counterparties(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 50,
    sort_by: str = "id",
    sort_order: str = "desc",
    search: str | None = None,
    active_only: bool = True,
):
    query = db.query(Counterparty)
    if active_only:
        query = query.filter(Counterparty.is_active == True)  # noqa: E712
    query = apply_search_filter(
        query,
        Counterparty,
        search,
        ["name", "company_name", "account_number", "sheba_number", "card_number"],
    )
    query = apply_sort(query, Counterparty, sort_by, sort_order)
    rows = query.offset(offset).limit(limit).all()
    return [serialize_counterparty(db, r) for r in rows]


def count_counterparties(
    db: Session,
    *,
    search: str | None = None,
    active_only: bool = True,
) -> int:
    query = db.query(func.count(Counterparty.id))
    if active_only:
        query = query.filter(Counterparty.is_active == True)  # noqa: E712
    query = apply_search_filter(
        query,
        Counterparty,
        search,
        ["name", "company_name", "account_number", "sheba_number", "card_number"],
    )
    return query.scalar() or 0


def delete_counterparty(db: Session, counterparty_id: int) -> bool:
    row = db.get(Counterparty, counterparty_id)
    if not row:
        return False
    row.is_active = False
    db.commit()
    return True
