"""روش پرداخت برای دستور پرداخت."""

PAYMENT_METHOD_CHECK = "check"
PAYMENT_METHOD_TRANSFER = "transfer"

PAYMENT_METHOD_LABELS: dict[str, str] = {
    PAYMENT_METHOD_CHECK: "چک",
    PAYMENT_METHOD_TRANSFER: "حواله",
}

ALLOWED_PAYMENT_METHODS = frozenset({PAYMENT_METHOD_CHECK, PAYMENT_METHOD_TRANSFER})


def normalize_payment_method(value: str | None) -> str | None:
    if value is None:
        return None
    key = str(value).strip().lower()
    if not key:
        return None
    if key in ALLOWED_PAYMENT_METHODS:
        return key
    aliases = {
        "cheque": PAYMENT_METHOD_CHECK,
        "check": PAYMENT_METHOD_CHECK,
        "چک": PAYMENT_METHOD_CHECK,
        "hawala": PAYMENT_METHOD_TRANSFER,
        "havale": PAYMENT_METHOD_TRANSFER,
        "havaleh": PAYMENT_METHOD_TRANSFER,
        "transfer": PAYMENT_METHOD_TRANSFER,
        "wire": PAYMENT_METHOD_TRANSFER,
        "حواله": PAYMENT_METHOD_TRANSFER,
    }
    return aliases.get(key)


def payment_method_label(value: str | None) -> str | None:
    norm = normalize_payment_method(value)
    if not norm:
        return None
    return PAYMENT_METHOD_LABELS.get(norm, norm)
