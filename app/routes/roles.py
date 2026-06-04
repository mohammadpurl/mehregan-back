from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.dependencies.pagination import ListQueryParams, get_list_params, paginated_response
from app.schemas.role import (
    RoleCreate,
    RoleOut,
    RolePermissionsReplace,
    RolePermissionsResponse,
    RoleUpdate,
)
from app.services import rbac

router = APIRouter(prefix="/roles", tags=["Roles"])


def _serialize_role(role) -> dict:
    return RoleOut.model_validate(role).model_dump(by_alias=True)


def _serialize_roles(items) -> list[dict]:
    return [_serialize_role(r) for r in items]


@router.post("/", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    return rbac.create_role(
        db,
        payload.name,
        display_name=payload.display_name,
        is_singleton=payload.is_singleton,
    )


@router.get("/")
def list_roles(
    params: ListQueryParams = Depends(get_list_params),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    items = rbac.get_roles(
        db,
        offset=params.offset,
        limit=params.page_size,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
        filter_by=params.filter_by,
        filter_value=params.filter_value,
        search=params.search,
    )
    total = rbac.count_roles(
        db,
        filter_by=params.filter_by,
        filter_value=params.filter_value,
        search=params.search,
    )
    return paginated_response(_serialize_roles(items), total, params)


@router.get("/{role_id}/permissions", response_model=RolePermissionsResponse)
def get_role_permissions(
    role_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        permissions = rbac.get_role_permissions(db, role_id)
    except ValueError as err:
        raise_from_value_error(err)
    return {"role_id": role_id, "permissions": permissions}


@router.put("/{role_id}/permissions", response_model=RolePermissionsResponse)
@router.post("/{role_id}/permissions/replace", response_model=RolePermissionsResponse)
def replace_role_permissions(
    role_id: int,
    payload: RolePermissionsReplace,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        permissions = rbac.replace_role_permissions(
            db, role_id, payload.permission_ids
        )
    except ValueError as err:
        raise_from_value_error(err)
    return {"role_id": role_id, "permissions": permissions}


@router.get("/{role_id}", response_model=RoleOut)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    role = rbac.get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role not found")
    return role


@router.put("/{role_id}", response_model=RoleOut)
def update_role(
    role_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        return rbac.update_role(
            db,
            role_id,
            name=payload.name,
            display_name=payload.display_name,
            is_singleton=payload.is_singleton,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        rbac.delete_role(db, role_id)
    except ValueError as err:
        raise_from_value_error(err)


@router.patch("/{role_id}", response_model=RoleOut)
def patch_role(
    role_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    return update_role(role_id, payload, db)
