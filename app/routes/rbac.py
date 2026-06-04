from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.dependencies.pagination import ListQueryParams, get_list_params, paginated_response
from app.schemas.permission import PermissionCreate, PermissionOut, PermissionUpdate
from app.schemas.role import (
    RoleCreate,
    RoleOut,
    RolePermissionsReplace,
    RolePermissionsResponse,
    RoleUpdate,
)
from app.services import rbac

router = APIRouter(prefix="/rbac", tags=["RBAC"])


def _as_http_400(err: ValueError):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(err),
    )


# ======================
# ROLE
# ======================
@router.post("/roles", response_model=RoleOut)
def create_role(payload: RoleCreate, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    return rbac.create_role(db, payload.name)


@router.get("/roles/{role_id}", response_model=RoleOut)
def get_role(role_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    role = rbac.get_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role not found")
    return role


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: int, payload: RoleUpdate, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    try:
        return rbac.update_role(db, role_id, payload.name)
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    try:
        rbac.delete_role(db, role_id)
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/roles")
def list_roles_rbac(
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
    return paginated_response(items, total, params)


# ======================
# PERMISSION
# ======================
@router.post("/permissions", response_model=PermissionOut)
def create_permission(payload: PermissionCreate, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    try:
        return rbac.create_permission(db, payload.code, payload.name)
    except ValueError as err:
        _as_http_400(err)


@router.get("/permissions")
def list_permissions_rbac(
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
    return paginated_response(items, total, params)


@router.get("/permissions/{permission_id}", response_model=PermissionOut)
def get_permission(permission_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    perm = rbac.get_permission(db, permission_id)
    if not perm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="permission not found"
        )
    return perm


@router.put("/permissions/{permission_id}", response_model=PermissionOut)
def update_permission(
    permission_id: int, payload: PermissionUpdate, db: Session = Depends(get_db)
):
    try:
        return rbac.update_permission(
            db, permission_id, code=payload.code, name=payload.name
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission(permission_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    try:
        rbac.delete_permission(db, permission_id)
    except ValueError as err:
        raise_from_value_error(err)


# ======================
# ASSIGN PERMISSION → ROLE
# ======================
@router.get("/roles/{role_id}/permissions", response_model=RolePermissionsResponse)
def get_role_permissions_rbac(role_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    try:
        permissions = rbac.get_role_permissions(db, role_id)
    except ValueError as err:
        raise_from_value_error(err)
    return {"role_id": role_id, "permissions": permissions}


@router.put("/roles/{role_id}/permissions", response_model=RolePermissionsResponse)
@router.post("/roles/{role_id}/permissions/replace", response_model=RolePermissionsResponse)
def replace_role_permissions_rbac(
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


@router.post("/roles/{role_id}/permissions/{permission_id}")
def assign_permission(role_id: int, permission_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    try:
        return rbac.assign_permission_to_role(db, role_id, permission_id)
    except ValueError as err:
        _as_http_400(err)


@router.delete(
    "/roles/{role_id}/permissions/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unassign_permission(role_id: int, permission_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    try:
        rbac.unassign_permission_from_role(db, role_id, permission_id)
    except ValueError as err:
        raise_from_value_error(err)


# ======================
# ASSIGN ROLE → USER
# ======================
@router.post("/users/{user_id}/roles/{role_id}")
def assign_role(user_id: int, role_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    try:
        return rbac.assign_role_to_user(db, user_id, role_id)
    except ValueError as err:
        _as_http_400(err)


@router.post("/user-roles/{user_role_id}/revoke")
def revoke_role(user_role_id: int, db: Session = Depends(get_db), _user=Depends(require_permission("admin.manage"))):
    try:
        return rbac.revoke_role(db, user_role_id)
    except ValueError as err:
        _as_http_400(err)
