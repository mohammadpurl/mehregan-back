from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import get_current_active_user
from app.dependencies.crud_http import raise_from_value_error
from app.dependencies.pagination import MAX_PAGE_SIZE
from app.schemas.ad_hoc_task import (
    AdHocTaskCreate,
    AdHocTaskListResponse,
    AdHocTaskOut,
    AdHocTaskStepCreate,
    UserLookupItem,
)
from app.schemas.attachment import AttachmentOut
from app.services.ad_hoc_task_service import (
    add_ad_hoc_task_step,
    count_ad_hoc_tasks,
    create_ad_hoc_task,
    get_ad_hoc_task_detail,
    list_ad_hoc_tasks,
    search_users_for_assign,
    user_can_access_task,
    user_can_view_all_ad_hoc_tasks,
)
from app.services.attachment_service import (
    ENTITY_AD_HOC_TASK,
    ENTITY_AD_HOC_TASK_STEP,
    delete_entity_attachment,
    list_attachments_serialized,
    save_entity_attachment,
)
from app.models.ad_hoc_task import AdHocTask

router = APIRouter(prefix="/ad-hoc-tasks", tags=["Ad hoc tasks"])


@router.get("/users/lookup", response_model=list[UserLookupItem])
def users_lookup_api(
    search: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    _user=Depends(get_current_active_user),
):
    """همه کاربران واردشده می‌توانند گیرنده انتخاب کنند."""
    return search_users_for_assign(db, search=search, limit=limit)


@router.get("/capabilities")
def ad_hoc_capabilities_api(
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    return {
        "can_create": True,
        "can_view_all": user_can_view_all_ad_hoc_tasks(db, user),
    }


@router.post("/", response_model=AdHocTaskOut, status_code=status.HTTP_201_CREATED)
def create_ad_hoc_task_api(
    payload: AdHocTaskCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """همه کاربران واردشده می‌توانند کار پیش‌بینی‌نشده تعریف کنند."""
    try:
        return create_ad_hoc_task(db, user_id=user.id, payload=payload)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/", response_model=AdHocTaskListResponse)
def list_ad_hoc_tasks_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE, alias="pageSize"),
    sort_by: str = Query("updated_at", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    search: str | None = Query(None),
    scope: str | None = Query("all", description="all | mine | assigned"),
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    offset = (page - 1) * page_size
    items = list_ad_hoc_tasks(
        db,
        user=user,
        scope=scope,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
    )
    total = count_ad_hoc_tasks(db, user=user, scope=scope, search=search)
    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "can_view_all": user_can_view_all_ad_hoc_tasks(db, user),
    }


@router.get("/{task_id}", response_model=AdHocTaskOut)
def get_ad_hoc_task_api(
    task_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    try:
        return get_ad_hoc_task_detail(db, task_id, user)
    except ValueError as err:
        raise_from_value_error(err)


@router.post("/{task_id}/steps", response_model=AdHocTaskOut)
def add_ad_hoc_task_step_api(
    task_id: int,
    payload: AdHocTaskStepCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    try:
        return add_ad_hoc_task_step(db, task_id=task_id, user_id=user.id, payload=payload)
    except ValueError as err:
        raise_from_value_error(err)


@router.post(
    "/{task_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_task_attachment_api(
    task_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    task = db.get(AdHocTask, task_id)
    if not task:
        raise_from_value_error(ValueError("کار یافت نشد"))
    if not user_can_access_task(db, task, user):
        raise_from_value_error(ValueError("دسترسی مجاز نیست"))
    row = await save_entity_attachment(
        db,
        entity_type=ENTITY_AD_HOC_TASK,
        entity_id=task_id,
        uploaded_by_id=user.id,
        file=file,
    )
    db.commit()
    from app.services.attachment_service import serialize_attachment

    return serialize_attachment(row)


@router.post(
    "/{task_id}/steps/{step_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_step_attachment_api(
    task_id: int,
    step_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    from app.models.ad_hoc_task import AdHocTaskStep

    task = db.get(AdHocTask, task_id)
    if not task:
        raise_from_value_error(ValueError("کار یافت نشد"))
    if not user_can_access_task(db, task, user):
        raise_from_value_error(ValueError("دسترسی مجاز نیست"))
    step = db.get(AdHocTaskStep, step_id)
    if not step or step.task_id != task_id:
        raise_from_value_error(ValueError("مرحله یافت نشد"))
    row = await save_entity_attachment(
        db,
        entity_type=ENTITY_AD_HOC_TASK_STEP,
        entity_id=step_id,
        uploaded_by_id=user.id,
        file=file,
    )
    db.commit()
    from app.services.attachment_service import serialize_attachment

    return serialize_attachment(row)


@router.get("/{task_id}/attachments", response_model=list[AttachmentOut])
def list_task_attachments_api(
    task_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    task = db.get(AdHocTask, task_id)
    if not task:
        raise_from_value_error(ValueError("کار یافت نشد"))
    if not user_can_access_task(db, task, user):
        raise_from_value_error(ValueError("دسترسی مجاز نیست"))
    return list_attachments_serialized(db, ENTITY_AD_HOC_TASK, task_id)


@router.delete("/{task_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task_attachment_api(
    task_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    task = db.get(AdHocTask, task_id)
    if not task:
        raise_from_value_error(ValueError("کار یافت نشد"))
    if not user_can_access_task(db, task, user):
        raise_from_value_error(ValueError("دسترسی مجاز نیست"))
    if not delete_entity_attachment(
        db, entity_type=ENTITY_AD_HOC_TASK, entity_id=task_id, attachment_id=attachment_id
    ):
        raise_from_value_error(ValueError("پیوست یافت نشد"))
