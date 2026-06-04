from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import WAREHOUSE_FORMS
from app.dependencies.auth import require_any_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.forms import WarehouseFormCreate, WarehouseFormUpdate
from app.services.warehouse_form import (
    count_warehouse_forms,
    create_warehouse_form,
    delete_warehouse_form,
    get_warehouse_form,
    list_warehouse_forms,
    update_warehouse_form,
)

router = APIRouter(prefix="/warehouse-forms", tags=["Warehouse Forms"])


@router.post("/")
def create_warehouse_form_api(
    payload: WarehouseFormCreate,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WAREHOUSE_FORMS)),
):
    return create_warehouse_form(
        db=db,
        requester_id=user.id,
        form_type=payload.form_type,
        source=payload.source,
        destination=payload.destination,
        receiver_name=payload.receiver_name,
        effective_date=payload.effective_date,
        description=payload.description,
        assignees_by_order=payload.assignees_by_order,
    )


@router.get("/")
def list_warehouse_forms_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("desc", alias="sortOrder"),
    filter_by: str | None = Query(None, alias="filterBy"),
    filter_value: str | None = Query(None, alias="filterValue"),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WAREHOUSE_FORMS)),
):
    offset = (page - 1) * page_size
    items = list_warehouse_forms(
        db,
        requester_id=user.id,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    total = count_warehouse_forms(
        db,
        requester_id=user.id,
        filter_by=filter_by,
        filter_value=filter_value,
        search=search,
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/{form_id}")
def get_warehouse_form_api(
    form_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WAREHOUSE_FORMS)),
):
    form = get_warehouse_form(db, form_id)
    if not form:
        raise HTTPException(status_code=404, detail="warehouse form not found")
    return form


@router.put("/{form_id}")
@router.patch("/{form_id}")
def update_warehouse_form_api(
    form_id: int,
    payload: WarehouseFormUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WAREHOUSE_FORMS)),
):
    try:
        return update_warehouse_form(db, form_id, payload, requester_id=user.id)
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_warehouse_form_api(
    form_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*WAREHOUSE_FORMS)),
):
    try:
        delete_warehouse_form(db, form_id, requester_id=user.id)
    except ValueError as err:
        raise_from_value_error(err)
