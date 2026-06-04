from fastapi import HTTPException, status

from app.core.api_error import api_error_detail


class EntityInUseError(ValueError):
    """Raised when delete is blocked because the row is referenced elsewhere."""

    def __init__(self, message: str, *, code: str, **extra):
        super().__init__(message)
        self.code = code
        self.extra = extra


def raise_from_value_error(err: ValueError) -> None:
    if isinstance(err, EntityInUseError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error_detail(err.code, str(err), **err.extra),
        )

    msg = str(err)
    lowered = msg.lower()
    if "not found" in lowered:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error_detail("NOT_FOUND", msg),
        )
    if "access denied" in lowered or "permission denied" in lowered:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=api_error_detail("FORBIDDEN", msg),
        )
    if "no pending step" in lowered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error_detail("NO_PENDING_STEP", msg),
        )
    if "قابل حذف نیست" in msg or "already exists" in lowered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error_detail("CONFLICT", msg),
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_error_detail("BAD_REQUEST", msg),
    )
