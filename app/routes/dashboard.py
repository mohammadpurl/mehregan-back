from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.constants.api_permissions import DASHBOARD_READ, WORKFLOW_ALL, ADMIN_MANAGE
from app.dependencies.auth import require_any_permission
from app.services.dashboard import get_user_dashboard, get_management_dashboard

router = APIRouter(prefix="/dashboard")


@router.get("/")
def dashboard(
    db: Session = Depends(get_db),
    user=Depends(require_any_permission(*DASHBOARD_READ)),
):
    return get_user_dashboard(db, user.id)


@router.get("/management")
def management_dashboard(
    db: Session = Depends(get_db),
    _user=Depends(require_any_permission(*WORKFLOW_ALL, *ADMIN_MANAGE)),
):
    return get_management_dashboard(db)
