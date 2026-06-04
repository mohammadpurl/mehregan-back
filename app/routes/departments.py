from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.auth import require_permission
from app.dependencies.crud_http import raise_from_value_error
from app.schemas.department import (
    DepartmentCreate,
    DepartmentListResponse,
    DepartmentOut,
    DepartmentTreeNode,
    DepartmentUpdate,
)
from app.services import department as department_service

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.post("/", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department_api(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        return department_service.create_department(
            db,
            payload.name,
            parent_id=payload.parent_id,
            head_user_id=payload.head_user_id,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.get("/", response_model=DepartmentListResponse)
def list_departments_api(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200, alias="pageSize"),
    sort_by: str = Query("id", alias="sortBy"),
    sort_order: str = Query("asc", alias="sortOrder"),
    search: str | None = Query(None),
    parent_id: int | None = Query(None, alias="parentId"),
    roots_only: bool = Query(False, alias="rootsOnly"),
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    offset = (page - 1) * page_size
    items = department_service.list_departments(
        db,
        offset=offset,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        search=search,
        parent_id=parent_id,
        roots_only=roots_only,
    )
    total = department_service.count_departments(
        db, search=search, parent_id=parent_id, roots_only=roots_only
    )
    return {"items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/tree", response_model=list[DepartmentTreeNode])
def department_tree_api(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    return department_service.build_department_tree(db)


@router.get("/{department_id}", response_model=DepartmentOut)
def get_department_api(
    department_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    item = department_service.get_department(db, department_id)
    if not item:
        raise HTTPException(status_code=404, detail="واحد سازمانی یافت نشد")
    return item


@router.put("/{department_id}", response_model=DepartmentOut)
@router.patch("/{department_id}", response_model=DepartmentOut)
def update_department_api(
    department_id: int,
    payload: DepartmentUpdate,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        data = payload.model_dump(exclude_unset=True)
        return department_service.update_department(
            db,
            department_id,
            name=data.get("name"),
            parent_id=data.get("parent_id"),
            head_user_id=data.get("head_user_id"),
            unset_head="head_user_id" in data and data["head_user_id"] is None,
        )
    except ValueError as err:
        raise_from_value_error(err)


@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department_api(
    department_id: int,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("admin.manage")),
):
    try:
        department_service.delete_department(db, department_id)
    except ValueError as err:
        raise_from_value_error(err)
