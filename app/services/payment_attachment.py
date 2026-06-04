"""سازگاری با importهای قدیمی — منطق در attachment_service است."""

from app.services.attachment_service import (  # noqa: F401
    ENTITY_PAYMENT_REQUEST,
    MAX_ATTACHMENT_BYTES,
    ALLOWED_EXTENSIONS,
    count_attachments_batch,
    delete_all_for_entity as delete_all_for_payment,
    delete_entity_attachment as delete_attachment,
    list_attachments as list_attachments_for_payment,
    save_entity_attachment,
    serialize_attachment,
)


async def save_payment_attachment(
    db,
    *,
    payment_request_id: int,
    uploaded_by_id: int,
    file,
):
    return await save_entity_attachment(
        db,
        entity_type=ENTITY_PAYMENT_REQUEST,
        entity_id=payment_request_id,
        uploaded_by_id=uploaded_by_id,
        file=file,
    )
