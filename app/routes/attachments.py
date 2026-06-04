import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.constants.api_permissions import ATTACHMENT_DOWNLOAD
from app.core.database import get_db
from app.dependencies.auth import require_any_permission
from app.dependencies.crud_http import raise_from_value_error
from app.services.attachment_service import (
    assert_user_can_access_attachment,
    get_attachment,
    resolve_attachment_file_path,
)

router = APIRouter(prefix="/attachments", tags=["Attachments"])


@router.get("/{attachment_id}/download")
def download_attachment_api(
    attachment_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*ATTACHMENT_DOWNLOAD)),
):
    att = get_attachment(db, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="پیوست یافت نشد")
    try:
        assert_user_can_access_attachment(db, user, att)
        file_path = resolve_attachment_file_path(att)
    except ValueError as err:
        raise_from_value_error(err)

    media_type, _ = mimetypes.guess_type(att.file_name)
    return FileResponse(
        path=file_path,
        media_type=media_type or "application/octet-stream",
        filename=att.file_name,
    )
