import logging
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.api_error import build_error_response
from app.dependencies.crud_http import raise_from_value_error
from fastapi.staticfiles import StaticFiles

from app.routes.auth import router as auth_router
from app.routes.ws import router as ws_router
from app.routes.notification import router as notification_router
from app.routes.workflow import router as workflow_router
from app.routes.inbox import router as inbox_router
from app.routes.notification_center import router as notification_center_router
from app.routes.master_data.item import router as item_router
from app.routes.master_data.category import router as category_router
from app.routes.master_data.warehouse import router as warehouse_router
from app.routes.master_data.stock import router as stock_router
from app.routes.inventory.transactions import router as inventory_router
from app.routes.procurement.request import router as request_router
from app.routes.procurement.suppliers import router as suppliers_router
from app.routes.procurement.grn import router as grn_router
from app.routes.procurement.purchase_orders import router as purchase_orders_router
from app.routes.rbac import router as rbac_router
from app.routes.permissions import router as permissions_router
from app.routes.roles import router as roles_router
from app.routes.dashboard import router as dashboard_router
from app.routes.reports import router as reports_router
from app.routes.workflow_form import router as workflow_form_router
from app.routes.payment_request import router as payment_request_router
from app.routes.warehouse_form import router as warehouse_form_router
from app.routes.workflow_definitions import router as workflow_definitions_router
from app.routes.users import router as users_router
from app.routes.departments import router as departments_router
from app.routes.org import router as org_router
from app.routes.counterparties import router as counterparties_router
from app.routes.company_bank_accounts import router as company_bank_accounts_router
from app.routes.petty_cash import router as petty_cash_router
from app.routes.attachments import router as attachments_router
from app.routes.sla_policies import router as sla_policies_router
from app.routes.assignment_rules import router as assignment_rules_router
from app.routes.ad_hoc_task import router as ad_hoc_task_router
from app.routes.financial_document import router as financial_document_router
from app.routes.mission_request import router as mission_request_router
from app.routes.audit import router as audit_router

from app.core.database import Base, engine
from app.core.logging import configure_logging
from app.core.monitoring import init_sentry
from app.core.config import (
    ALLOWED_ORIGINS,
    ENABLE_API_DOCS,
    ENVIRONMENT,
    IP_WHITELIST_ENABLED,
    ALLOWED_IPS,
    IP_WHITELIST_EXEMPT_PATHS,
)
from app.core.rate_limit import setup_rate_limiting
from app.core.config import ROOT_PATH, TRUST_PROXY_HEADERS, UPLOAD_DIRECTORY
from app.core.schema_patch import (
    ensure_payment_request_schema,
    ensure_permissions_schema,
    ensure_roles_schema,
    ensure_postgres_sequences,
    ensure_user_profile_schema,
    ensure_workflow_schema,
    ensure_department_schema,
    ensure_financial_schema,
    ensure_petty_cash_schema,
    ensure_financial_document_schema,
    ensure_procurement_schema,
    ensure_ad_hoc_task_schema,
    ensure_mission_request_schema,
)


# Import models to ensure they are registered in metadata
import app.models


configure_logging()
init_sentry()

logger = logging.getLogger("app.main")

# root_path for OpenAPI / reverse proxy (see app.core.config.ROOT_PATH)
root_path_value = ROOT_PATH if ROOT_PATH else None

_docs_kwargs: dict = {}
if not ENABLE_API_DOCS:
    _docs_kwargs = {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }

app = FastAPI(
    title="ERP System",
    description="",
    version="1.0.0",
    root_path=root_path_value,
    root_path_in_servers=True,  # اضافه کردن root_path به servers در OpenAPI schema
    default_response_class=JSONResponse,  # مهم
    **_docs_kwargs,
)

if not ENABLE_API_DOCS:
    logger.info(
        "API docs disabled (ENVIRONMENT=%s, ENABLE_API_DOCS=%s)",
        ENVIRONMENT,
        ENABLE_API_DOCS,
    )

UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
# فقط آواتارها به‌صورت عمومی؛ پیوست‌های کسب‌وکار فقط از /attachments/{id}/download
_avatars_dir = UPLOAD_DIRECTORY / "avatars"
_avatars_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/uploads/avatars",
    StaticFiles(directory=str(_avatars_dir)),
    name="uploads_avatars",
)


def get_client_ip(request: Request) -> str:
    """
    IP کلاینت. هدرهای X-Forwarded-For / X-Real-IP فقط وقتی
    TRUST_PROXY_HEADERS=true باشد معتبرند (پشت proxy قابل اعتماد).
    """
    if TRUST_PROXY_HEADERS:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
            if client_ip:
                return client_ip
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

    if request.client:
        return request.client.host

    return "unknown"


def ip_in_subnet(ip: str, subnet: str) -> bool:
    """
    بررسی اینکه آیا IP در subnet قرار دارد یا نه.

    Args:
        ip: IP آدرس (مثلاً "172.18.0.1")
        subnet: subnet با CIDR notation (مثلاً "172.18.0.0/16")

    Returns:
        True اگر IP در subnet باشد
    """
    try:
        import ipaddress

        # اگر subnet نیست (فقط IP است)، مقایسه مستقیم
        if "/" not in subnet:
            return ip == subnet

        # بررسی subnet
        network = ipaddress.ip_network(subnet, strict=False)
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj in network
    except (ValueError, AttributeError):
        # در صورت خطا، مقایسه مستقیم
        return ip == subnet


def is_ip_allowed(client_ip: str, allowed_ips: list) -> bool:
    """
    بررسی اینکه آیا IP کلاینت در لیست مجاز است یا نه.
    این تابع هم IP های دقیق و هم subnet ها را پشتیبانی می‌کند.

    Args:
        client_ip: IP کلاینت
        allowed_ips: لیست IP ها و subnet های مجاز

    Returns:
        True اگر IP مجاز باشد
    """
    # بررسی IP های دقیق و subnet ها
    for allowed_ip in allowed_ips:
        if ip_in_subnet(client_ip, allowed_ip):
            return True

    # بررسی localhost و 127.x.x.x
    if (
        client_ip == "127.0.0.1"
        or client_ip.startswith("127.")
        or client_ip == "localhost"
        or client_ip == "::1"  # IPv6 localhost
    ):
        return True

    return False


@app.middleware("http")
async def ip_whitelist_middleware(request: Request, call_next):
    """
    Middleware برای محدود کردن دسترسی به IP های مجاز.
    این middleware درخواست‌ها را بررسی می‌کند و فقط از IP های مجاز اجازه دسترسی می‌دهد.
    """
    # اگر IP whitelist غیرفعال باشد، همه درخواست‌ها را اجازه می‌دهیم
    if not IP_WHITELIST_ENABLED:
        response = await call_next(request)
        return response

    # بررسی مسیرهای مستثنی
    path = request.url.path
    # حذف root_path از مسیر برای بررسی
    if root_path_value and path.startswith(root_path_value):
        path = path[len(root_path_value) :] or "/"

    # بررسی اینکه آیا مسیر در لیست مستثنی‌ها است
    is_exempt = any(
        path == exempt_path or path.startswith(exempt_path + "/")
        for exempt_path in IP_WHITELIST_EXEMPT_PATHS
    )

    if is_exempt:
        # مسیرهای مستثنی (مثل /health) را بدون بررسی IP اجازه می‌دهیم
        response = await call_next(request)
        return response

    # استخراج IP کلاینت
    client_ip = get_client_ip(request)

    # بررسی اینکه IP در لیست مجاز است یا نه (با پشتیبانی از subnet)
    allowed = is_ip_allowed(client_ip, ALLOWED_IPS)

    if not allowed:
        security_logger = logging.getLogger("app.security")
        security_logger.warning(
            f"IP whitelist violation | IP={client_ip} | Path={request.url.path} | Method={request.method}",
            extra={
                "client_ip": client_ip,
                "path": request.url.path,
                "method": request.method,
                "headers": dict(request.headers),
            },
        )
        return JSONResponse(
            status_code=403,
            content={
                "detail": "دسترسی غیرمجاز: IP شما در لیست مجاز نیست",
                "error_code": "IP_NOT_ALLOWED",
            },
        )

    response = await call_next(request)
    return response


@app.middleware("http")
async def detect_root_path(request: Request, call_next):
    """
    Middleware برای تشخیص خودکار root_path از URL درخواست.
    این برای زمانی است که ROOT_PATH در environment variable تنظیم نشده باشد.
    """
    # اگر root_path_value تنظیم نشده باشد، سعی می‌کنیم از URL تشخیص دهیم
    if not root_path_value and request.url.path.startswith("/backend"):
        # تشخیص root_path از URL
        detected_root = "/backend"
        # ذخیره در app state برای استفاده در custom_openapi
        if not hasattr(app.state, "detected_root_path"):
            app.state.detected_root_path = detected_root
            # به‌روزرسانی openapi_schema اگر قبلاً ساخته شده باشد
            if hasattr(app, "openapi_schema") and app.openapi_schema:
                app.openapi_schema = None  # Force regeneration

    response = await call_next(request)
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware برای لاگ‌کردن همه درخواست‌ها و پاسخ‌ها.
    """
    request_logger = logging.getLogger("app.request")
    # استخراج IP کلاینت برای لاگ
    client_ip = get_client_ip(request)
    # هدر Authorization را برای دیباگ ثبت می‌کنیم (توکن را ماسک می‌کنیم)
    auth_header = request.headers.get("authorization")
    masked_auth = None
    if auth_header:
        # فقط چند کاراکتر اول و آخر را نشان می‌دهیم
        masked_auth = (
            f"{auth_header[:15]}...{auth_header[-5:]}"
            if len(auth_header) > 25
            else auth_header
        )

    request_logger.info(
        f"REQUEST {request.method} {request.url.path} | IP={client_ip}",
        extra={
            "authorization_present": bool(auth_header),
            "authorization": masked_auth,
            "client_ip": client_ip,
        },
    )
    try:
        response = await call_next(request)
        request_logger.info(
            f"RESPONSE {request.method} {request.url.path} -> {response.status_code} | IP={client_ip}",
            extra={
                "client_ip": client_ip,
            },
        )
        return response
    except Exception:
        # هر خطای کنترل‌نشده را لاگ می‌کنیم و دوباره raise می‌کنیم
        request_logger.exception(
            f"UNHANDLED ERROR for {request.method} {request.url.path}"
        )
        raise


# Setup rate limiting
app = setup_rate_limiting(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """Health check endpoint for monitoring and load balancers."""
    return {"status": "ok", "service": "mehreagan-erp-api"}


if ENABLE_API_DOCS:

    @app.get("/openapi.json", include_in_schema=False)
    async def get_openapi_json():
        """Endpoint برای بازگرداندن OpenAPI schema با در نظر گیری root_path."""
        return app.openapi()

    @app.get("/backend/openapi.json", include_in_schema=False)
    async def get_openapi_json_backend():
        """Endpoint برای بازگرداندن OpenAPI schema از مسیر /backend/openapi.json."""
        return app.openapi()


app.include_router(auth_router)
app.include_router(workflow_router)
app.include_router(ws_router)
app.include_router(notification_router)
app.include_router(inbox_router)
app.include_router(notification_center_router)
app.include_router(item_router)
app.include_router(category_router)
app.include_router(warehouse_router)
app.include_router(stock_router)
app.include_router(inventory_router)
app.include_router(request_router)
app.include_router(suppliers_router)
app.include_router(grn_router)
app.include_router(purchase_orders_router)
app.include_router(permissions_router)
app.include_router(roles_router)
app.include_router(rbac_router)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(workflow_form_router)
app.include_router(payment_request_router)
app.include_router(warehouse_form_router)
app.include_router(workflow_definitions_router)
app.include_router(users_router)
app.include_router(departments_router)
app.include_router(org_router)
app.include_router(counterparties_router)
app.include_router(company_bank_accounts_router)
app.include_router(petty_cash_router)
app.include_router(attachments_router)
app.include_router(sla_policies_router)
app.include_router(assignment_rules_router)
app.include_router(ad_hoc_task_router)
app.include_router(financial_document_router)
app.include_router(mission_request_router)
app.include_router(audit_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_logger = logging.getLogger("app.errors")
    error_logger.warning(
        "Validation error | path=%s | errors=%s",
        request.url.path,
        exc.errors(),
    )
    content = build_error_response(422, exc.errors())
    return JSONResponse(status_code=422, content=content)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """همه ValueErrorهای بدون catch در route → پاسخ استاندارد JSON."""
    error_logger = logging.getLogger("app.errors")
    try:
        raise_from_value_error(exc)
    except HTTPException as http_exc:
        error_logger.warning(
            "ValueError | status=%s | path=%s | detail=%s",
            http_exc.status_code,
            request.url.path,
            http_exc.detail,
        )
        content = build_error_response(http_exc.status_code, http_exc.detail)
        return JSONResponse(status_code=http_exc.status_code, content=content)
    raise exc


@app.exception_handler(HTTPException)
async def http_exception_logger(request: Request, exc: HTTPException):
    """
    لاگر مرکزی برای همه HTTPException ها.
    """
    error_logger = logging.getLogger("app.errors")
    log_fn = error_logger.warning if exc.status_code < 500 else error_logger.error
    log_fn(
        "HTTPException | status=%s | path=%s | detail=%s",
        exc.status_code,
        request.url.path,
        exc.detail,
    )
    content = build_error_response(exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def unhandled_exception_logger(request: Request, exc: Exception):
    """
    لاگر مرکزی برای همه خطاهای غیرمنتظره (500).
    """
    error_logger = logging.getLogger("app.errors")
    error_logger.error(
        "Unhandled exception | path=%s | error=%s",
        request.url.path,
        exc,
        exc_info=True,
    )
    content = build_error_response(
        500,
        "خطای داخلی سرور رخ داد. لطفاً بعداً دوباره تلاش کنید.",
    )
    return JSONResponse(status_code=500, content=content)


@app.on_event("startup")
def on_startup():
    import threading

    print(Base.metadata.tables.keys())
    Base.metadata.create_all(bind=engine)
    ensure_user_profile_schema(engine)
    ensure_department_schema(engine)
    ensure_permissions_schema(engine)
    ensure_roles_schema(engine)
    ensure_workflow_schema(engine)
    ensure_payment_request_schema(engine)
    ensure_financial_schema(engine)
    ensure_petty_cash_schema(engine)
    ensure_financial_document_schema(engine)
    ensure_procurement_schema(engine)
    ensure_ad_hoc_task_schema(engine)
    ensure_mission_request_schema(engine)
    ensure_postgres_sequences(engine)

    try:
        from app.core.database import SessionLocal
        from app.services.sla_policy_service import sync_sla_policies_from_definitions

        _sla_db = SessionLocal()
        try:
            n = sync_sla_policies_from_definitions(_sla_db)
            logger.info("SLA policies synced on startup: %s new", n)
        finally:
            _sla_db.close()
    except Exception:
        logger.exception("SLA policy sync on startup failed")

    logger.info("Startup completed: database tables ensured")

    from app.workers.sla_worker import start_worker

    sla_thread = threading.Thread(target=start_worker, daemon=True, name="sla-worker")
    sla_thread.start()
    logger.info("SLA background worker thread started")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
