from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.constants.api_permissions import (
    ADMIN_MANAGE,
    INVENTORY_READ,
    PAYMENT_APPROVE,
    PAYMENT_WRITE,
    PROCUREMENT_READ,
    PROCUREMENT_WRITE,
    WAREHOUSE_FORMS,
    WORKFLOW_ALL,
    WORKFLOW_TRACKING,
)
from app.core.database import get_db
from app.dependencies.auth import require_any_permission
from app.services.reports_executive import get_executive_financial_report
from app.services.reports_requests import (
    export_requests_report_excel,
    get_requests_report,
    list_request_report_types,
)
from app.services.reports_sla import get_sla_report
from app.services.reports_warehouse import get_warehouse_daily_report
from app.services.request_title import suggest_title_for_ref_type

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/executive/financial")
def executive_financial_report_api(
    date_from: date | None = Query(None, alias="dateFrom"),
    date_to: date | None = Query(None, alias="dateTo"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*PAYMENT_APPROVE, *WORKFLOW_ALL, *ADMIN_MANAGE)),
):
    return get_executive_financial_report(db, date_from=date_from, date_to=date_to)


@router.get("/executive/sla")
def executive_sla_report_api(
    date_from: date | None = Query(None, alias="dateFrom"),
    date_to: date | None = Query(None, alias="dateTo"),
    ref_type: str | None = Query(None, alias="refType"),
    assignee_id: int | None = Query(None, alias="assigneeId", gt=0),
    kind: str | None = Query(
        "all",
        description="all | workflow | ad_hoc",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200, alias="pageSize"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_TRACKING)),
):
    offset = (page - 1) * page_size
    return get_sla_report(
        db,
        date_from=date_from,
        date_to=date_to,
        ref_type=ref_type,
        assignee_id=assignee_id,
        kind=kind,
        offset=offset,
        limit=page_size,
    )


@router.get("/warehouse/daily")
def warehouse_daily_report_api(
    report_date: date | None = Query(None, alias="date"),
    warehouse_id: int | None = Query(None, alias="warehouseId"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*INVENTORY_READ, *PROCUREMENT_READ)),
):
    return get_warehouse_daily_report(
        db, report_date=report_date, warehouse_id=warehouse_id
    )


@router.get("/request-types")
def request_report_types_api(
    _user=Depends(require_any_permission(*WORKFLOW_TRACKING, *ADMIN_MANAGE, *WORKFLOW_ALL)),
):
    return {"items": list_request_report_types()}


@router.get("/request-title-suggestion")
def request_title_suggestion_api(
    ref_type: str = Query(..., alias="refType"),
    db: Session = Depends(get_db),
    user=Depends(
        require_any_permission(
            *PAYMENT_WRITE,
            *PROCUREMENT_WRITE,
            *WAREHOUSE_FORMS,
            *WORKFLOW_TRACKING,
            *ADMIN_MANAGE,
        )
    ),
):
    return {
        "suggestedTitle": suggest_title_for_ref_type(db, ref_type=ref_type, user=user),
    }


@router.get("/requests")
def requests_report_api(
    ref_type: str | None = Query(None, alias="refType"),
    requester_id: int | None = Query(None, alias="requesterId", gt=0),
    date_from: date | None = Query(None, alias="dateFrom"),
    date_to: date | None = Query(None, alias="dateTo"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200, alias="pageSize"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_TRACKING, *ADMIN_MANAGE, *WORKFLOW_ALL)),
):
    offset = (page - 1) * page_size
    return get_requests_report(
        db,
        ref_type=ref_type,
        requester_id=requester_id,
        date_from=date_from,
        date_to=date_to,
        offset=offset,
        limit=page_size,
    )


@router.get("/requests/export.xlsx")
def requests_report_export_api(
    ref_type: str | None = Query(None, alias="refType"),
    requester_id: int | None = Query(None, alias="requesterId", gt=0),
    date_from: date | None = Query(None, alias="dateFrom"),
    date_to: date | None = Query(None, alias="dateTo"),
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_TRACKING, *ADMIN_MANAGE, *WORKFLOW_ALL)),
):
    content = export_requests_report_excel(
        db,
        ref_type=ref_type,
        requester_id=requester_id,
        date_from=date_from,
        date_to=date_to,
    )
    filename = "requests-report.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
