from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.dependencies.pagination import ListQueryParams, get_list_params
from app.schemas.permission import (
    PermissionCreate,
    PermissionListResponse,
    PermissionOut,
    PermissionUpdate,
)
from app.services import rbac

router = APIRouter(prefix="/permissions", tags=["Permissions"])


@router.post("/", response_model=PermissionOut, status_code=status.HTTP_201_CREATED)
def create_permission(
    payload: PermissionCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        return rbac.create_permission(db, payload.code, payload.name)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/", response_model=PermissionListResponse)
def list_permissions(
    params: ListQueryParams = Depends(get_list_params),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    items = rbac.get_permissions(
        db,
        offset=params.offset,
        limit=params.page_size,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
        filter_by=params.filter_by,
        filter_value=params.filter_value,
        search=params.search,
    )
    total = rbac.count_permissions(
        db,
        filter_by=params.filter_by,
        filter_value=params.filter_value,
        search=params.search,
    )
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "pageSize": params.page_size,
    }


@router.get("/{permission_id}", response_model=PermissionOut)
def get_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    perm = rbac.get_permission(db, permission_id)
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="permission not found")
    return perm


@router.put("/{permission_id}", response_model=PermissionOut)
def update_permission(
    permission_id: int,
    payload: PermissionUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        return rbac.update_permission(
            db, permission_id, code=payload.code, name=payload.name
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission(
    permission_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        rbac.delete_permission(db, permission_id)
    except ValueError as err:
        raise_from_value_error(err)


@router.patch("/{permission_id}", response_model=PermissionOut)
def patch_permission(
    permission_id: int,
    payload: PermissionUpdate,
    db: Session = Depends(get_db),
):
    return update_permission(permission_id, payload, db)
