"""اعتبارسنجی مبلغ — هم‌راستا با NUMERIC(15, 2) در PostgreSQL."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import Field, PlainValidator

# NUMERIC(15,2): حداکثر ۱۳ رقم صحیح → کمتر از 10^13
MAX_MONEY_AMOUNT = Decimal("9999999999999.99")


def validate_money_amount(value: object) -> float:
    if value is None:
        raise ValueError("مبلغ الزامی است")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("مبلغ نامعتبر است") from exc

    if not amount.is_finite():
        raise ValueError("مبلغ نامعتبر است")

    if amount <= 0:
        raise ValueError("مبلغ باید بزرگ‌تر از صفر باشد")

    if amount > MAX_MONEY_AMOUNT:
        raise ValueError(
            "مبلغ از حد مجاز سیستم بیشتر است "
            "(حداکثر ۹٬۹۹۹٬۹۹۹٬۹۹۹٬۹۹۹٫۹۹ ریال)"
        )

    return float(amount)


MoneyAmount = Annotated[
    float,
    PlainValidator(validate_money_amount),
    Field(gt=0, le=float(MAX_MONEY_AMOUNT)),
]

OptionalMoneyAmount = Annotated[
    float | None,
    PlainValidator(lambda v: None if v is None else validate_money_amount(v)),
]
