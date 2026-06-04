"""
Lightweight schema adjustments for existing PostgreSQL databases where
Base.metadata.create_all does not ALTER tables.

Safe to run on every startup (idempotent).
"""

import logging

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

# Tables that commonly get out-of-sync SERIAL sequences after manual SQL seeding
_SEQUENCE_TABLES = (
    "users",
    "user_roles",
    "roles",
    "permissions",
    "role_permissions",
    "departments",
    "workflow_instances",
    "workflow_steps",
)


def ensure_postgres_sequences(engine) -> None:
    """Align id sequences with MAX(id) to prevent duplicate PK on INSERT."""
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    existing = set(insp.get_table_names())

    with engine.begin() as conn:
        for table in _SEQUENCE_TABLES:
            if table not in existing:
                continue
            seq = conn.execute(
                text("SELECT pg_get_serial_sequence(:tbl, 'id')"),
                {"tbl": table},
            ).scalar()
            if not seq:
                continue
            conn.execute(
                text(
                    f"SELECT setval(CAST(:seq AS regclass), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
                ),
                {"seq": seq},
            )
        logger.info("Synchronized PostgreSQL id sequences for core tables")


_USER_PROFILE_COLUMNS = (
    ("first_name", "VARCHAR(100)"),
    ("last_name", "VARCHAR(100)"),
    ("national_id", "VARCHAR(10)"),
    ("father_name", "VARCHAR(100)"),
    ("card_number", "VARCHAR(24)"),
    ("sheba_number", "VARCHAR(26)"),
    ("profile_pic", "VARCHAR(500)"),
)


def _add_column_if_missing(
    conn,
    *,
    dialect: str,
    table: str,
    column: str,
    ddl: str,
    existing: set[str],
) -> bool:
    if column in existing:
        return False
    if dialect == "postgresql":
        conn.execute(
            text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
        )
    elif dialect == "sqlite":
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    else:
        logger.warning(
            "Skipping %s.%s: unsupported dialect %s", table, column, dialect
        )
        return False
    existing.add(column)
    logger.info("Added column %s.%s", table, column)
    return True


def ensure_user_profile_schema(engine) -> None:
    """Add profile / banking columns on users when missing (PostgreSQL + SQLite)."""
    dialect = engine.dialect.name
    if dialect not in ("postgresql", "sqlite"):
        logger.warning("ensure_user_profile_schema skipped: dialect=%s", dialect)
        return

    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        logger.warning("ensure_user_profile_schema skipped: users table missing")
        return

    existing = {c["name"] for c in insp.get_columns("users")}
    added: list[str] = []

    with engine.begin() as conn:
        for col, ddl in _USER_PROFILE_COLUMNS:
            if _add_column_if_missing(
                conn,
                dialect=dialect,
                table="users",
                column=col,
                ddl=ddl,
                existing=existing,
            ):
                added.append(col)

    if added:
        logger.info("users table: added columns %s", ", ".join(added))
    else:
        logger.info("users table: profile/banking columns already present")

    for name in ("card_number", "sheba_number"):
        if name not in existing:
            logger.error(
                "DB missing users.%s — run: python scripts/apply_schema_patches.py",
                name,
            )
        else:
            logger.info("DB OK: users.%s", name)


def ensure_department_schema(engine) -> None:
    if engine.dialect.name not in ("postgresql", "sqlite"):
        return

    insp = inspect(engine)
    if "departments" not in insp.get_table_names():
        return

    existing = {c["name"] for c in insp.get_columns("departments")}
    with engine.begin() as conn:
        if "head_user_id" not in existing:
            if engine.dialect.name == "postgresql":
                conn.execute(
                    text(
                        "ALTER TABLE departments "
                        "ADD COLUMN IF NOT EXISTS head_user_id INTEGER "
                        "REFERENCES users(id)"
                    )
                )
            else:
                conn.execute(
                    text("ALTER TABLE departments ADD COLUMN head_user_id INTEGER")
                )
            logger.info("Added departments.head_user_id column")


def ensure_permissions_schema(engine) -> None:
    """Add permissions.code when missing (legacy DBs only had name)."""
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    if "permissions" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("permissions")}
    with engine.begin() as conn:
        if "code" not in cols:
            conn.execute(
                text("ALTER TABLE permissions ADD COLUMN code VARCHAR(100)")
            )
        conn.execute(
            text(
                "UPDATE permissions SET code = name "
                "WHERE code IS NULL AND name IS NOT NULL"
            )
        )
        logger.info("Ensured permissions.code column (backfilled from name)")


def ensure_roles_schema(engine) -> None:
    """Add roles.display_name and backfill Persian labels."""
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    if "roles" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("roles")}
    with engine.begin() as conn:
        if "display_name" not in cols:
            conn.execute(
                text("ALTER TABLE roles ADD COLUMN display_name VARCHAR(100)")
            )
        from app.constants.role_labels import ROLE_DISPLAY_NAMES

        conn.execute(
            text(
                "ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_singleton BOOLEAN "
                "NOT NULL DEFAULT FALSE"
            )
        )
        for slug, label in ROLE_DISPLAY_NAMES.items():
            conn.execute(
                text(
                    "UPDATE roles SET display_name = :label "
                    "WHERE name = :slug AND (display_name IS NULL OR display_name = '')"
                ),
                {"slug": slug, "label": label},
            )
        from app.constants.role_policy import DEFAULT_SINGLETON_ROLE_NAMES

        for slug in DEFAULT_SINGLETON_ROLE_NAMES:
            conn.execute(
                text("UPDATE roles SET is_singleton = TRUE WHERE name = :slug"),
                {"slug": slug},
            )
        logger.info("Ensured roles.display_name and roles.is_singleton columns")


def ensure_workflow_schema(engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    with engine.begin() as conn:
        if "workflow_definitions" in tables:
            conn.execute(
                text(
                    "ALTER TABLE workflow_definitions "
                    "ADD COLUMN IF NOT EXISTS ref_type VARCHAR(80)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE workflow_definitions "
                    "ADD COLUMN IF NOT EXISTS steps_config JSONB"
                )
            )
            conn.execute(
                text(
                    "UPDATE workflow_definitions SET ref_type = code "
                    "WHERE ref_type IS NULL AND code IS NOT NULL"
                )
            )
            logger.info("Ensured workflow_definitions.ref_type / steps_config columns")

        if "workflow_steps" in tables:
            conn.execute(
                text(
                    "ALTER TABLE workflow_steps "
                    "ADD COLUMN IF NOT EXISTS assigned_user_id INTEGER"
                )
            )
            logger.info("Ensured workflow_steps.assigned_user_id column")


def ensure_payment_request_schema(engine) -> None:
    """وام/مساعده: ستون‌های شرایط تأییدکننده."""
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    if "payment_requests" not in insp.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE payment_requests "
                "ADD COLUMN IF NOT EXISTS installment_count INTEGER"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE payment_requests "
                "ADD COLUMN IF NOT EXISTS first_installment_date DATE"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE payment_requests "
                "ADD COLUMN IF NOT EXISTS settlement_date DATE"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE payment_requests "
                "ADD COLUMN IF NOT EXISTS counterparty_id INTEGER"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE payment_requests "
                "ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE payment_requests "
                "ADD COLUMN IF NOT EXISTS payment_order_kind VARCHAR(20)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE payment_requests "
                "ADD COLUMN IF NOT EXISTS payment_marked_at TIMESTAMP"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE payment_requests "
                "ADD COLUMN IF NOT EXISTS payment_marked_by INTEGER "
                "REFERENCES users(id)"
            )
        )
        logger.info(
            "Ensured payment_requests loan/advance/counterparty/payment_method columns"
        )


def ensure_financial_schema(engine) -> None:
    """counterparties, sla_policies tables/columns."""
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    with engine.begin() as conn:
        if "counterparties" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS counterparties (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        party_type VARCHAR(20) NOT NULL DEFAULT 'company',
                        company_name VARCHAR(255),
                        account_number VARCHAR(50),
                        sheba_number VARCHAR(26),
                        card_number VARCHAR(24),
                        notes VARCHAR(500),
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
            logger.info("Created counterparties table")

        if "sla_policies" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS sla_policies (
                        id SERIAL PRIMARY KEY,
                        ref_type VARCHAR(80) NOT NULL,
                        step_order INTEGER NOT NULL,
                        max_minutes INTEGER NOT NULL,
                        escalate_to_role_id INTEGER REFERENCES roles(id),
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        CONSTRAINT uq_sla_policy_ref_type_step UNIQUE (ref_type, step_order)
                    )
                    """
                )
            )
            logger.info("Created sla_policies table")

        if "company_bank_accounts" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS company_bank_accounts (
                        id SERIAL PRIMARY KEY,
                        label VARCHAR(120) NOT NULL,
                        bank_name VARCHAR(120),
                        account_number VARCHAR(50),
                        sheba_number VARCHAR(26),
                        card_number VARCHAR(24),
                        is_default BOOLEAN NOT NULL DEFAULT FALSE,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
            logger.info("Created company_bank_accounts table")

        if "counterparty_bank_accounts" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS counterparty_bank_accounts (
                        id SERIAL PRIMARY KEY,
                        counterparty_id INTEGER NOT NULL
                            REFERENCES counterparties(id) ON DELETE CASCADE,
                        label VARCHAR(120) NOT NULL,
                        bank_name VARCHAR(120),
                        account_number VARCHAR(50),
                        sheba_number VARCHAR(26),
                        card_number VARCHAR(24),
                        is_default BOOLEAN NOT NULL DEFAULT FALSE,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_cp_bank_accounts_counterparty_id "
                    "ON counterparty_bank_accounts (counterparty_id)"
                )
            )
            logger.info("Created counterparty_bank_accounts table")

        if "payment_requests" in tables:
            conn.execute(
                text(
                    "ALTER TABLE payment_requests "
                    "ADD COLUMN IF NOT EXISTS counterparty_id INTEGER "
                    "REFERENCES counterparties(id)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE payment_requests "
                    "ADD COLUMN IF NOT EXISTS payer_company_account_id INTEGER "
                    "REFERENCES company_bank_accounts(id)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE payment_requests "
                    "ADD COLUMN IF NOT EXISTS receiver_counterparty_account_id INTEGER "
                    "REFERENCES counterparty_bank_accounts(id)"
                )
            )

        # مهاجرت فیلدهای تک‌حساب قدیمی طرف‌حساب به جدول چندحسابه
        if "counterparties" in tables:
            conn.execute(
                text(
                    """
                    INSERT INTO counterparty_bank_accounts (
                        counterparty_id, label, bank_name,
                        account_number, sheba_number, card_number,
                        is_default, is_active, created_at, updated_at
                    )
                    SELECT c.id,
                           COALESCE(NULLIF(TRIM(c.name), ''), 'حساب اصلی'),
                           NULL,
                           NULLIF(TRIM(c.account_number), ''),
                           NULLIF(TRIM(c.sheba_number), ''),
                           NULLIF(TRIM(c.card_number), ''),
                           TRUE,
                           c.is_active,
                           NOW(),
                           NOW()
                    FROM counterparties c
                    WHERE (
                        NULLIF(TRIM(COALESCE(c.account_number, '')), '') IS NOT NULL
                        OR NULLIF(TRIM(COALESCE(c.sheba_number, '')), '') IS NOT NULL
                        OR NULLIF(TRIM(COALESCE(c.card_number, '')), '') IS NOT NULL
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM counterparty_bank_accounts ba
                        WHERE ba.counterparty_id = c.id
                    )
                    """
                )
            )
            logger.info("Migrated legacy counterparty bank fields to counterparty_bank_accounts")


def ensure_petty_cash_schema(engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    with engine.begin() as conn:
        if "petty_cash_requests" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS petty_cash_requests (
                        id SERIAL PRIMARY KEY,
                        requester_id INTEGER NOT NULL REFERENCES users(id),
                        amount NUMERIC(15, 2) NOT NULL,
                        reason TEXT,
                        requested_date DATE,
                        status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                        settlement_status VARCHAR(50) NOT NULL DEFAULT 'NONE',
                        payer_company_account_id INTEGER
                            REFERENCES company_bank_accounts(id),
                        total_expenses NUMERIC(15, 2),
                        settled_at TIMESTAMP WITHOUT TIME ZONE,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_petty_cash_requests_requester "
                    "ON petty_cash_requests (requester_id)"
                )
            )
            logger.info("Created petty_cash_requests table")

        if "petty_cash_expense_lines" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS petty_cash_expense_lines (
                        id SERIAL PRIMARY KEY,
                        petty_cash_request_id INTEGER NOT NULL
                            REFERENCES petty_cash_requests(id) ON DELETE CASCADE,
                        description VARCHAR(500) NOT NULL,
                        amount NUMERIC(15, 2) NOT NULL,
                        expense_date DATE,
                        source VARCHAR(20) NOT NULL DEFAULT 'manual',
                        row_order INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_petty_cash_expense_request "
                    "ON petty_cash_expense_lines (petty_cash_request_id)"
                )
            )
            logger.info("Created petty_cash_expense_lines table")


def ensure_financial_document_schema(engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    with engine.begin() as conn:
        if "financial_documents" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS financial_documents (
                        id SERIAL PRIMARY KEY,
                        requester_id INTEGER NOT NULL REFERENCES users(id),
                        document_type VARCHAR(30) NOT NULL DEFAULT 'check',
                        title VARCHAR(255),
                        description TEXT,
                        amount NUMERIC(15, 2),
                        document_date DATE,
                        check_number VARCHAR(100),
                        party_name VARCHAR(255),
                        status VARCHAR(50) NOT NULL DEFAULT 'pending',
                        finance_confirmed_at TIMESTAMP WITHOUT TIME ZONE,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_financial_documents_requester "
                    "ON financial_documents (requester_id)"
                )
            )
            logger.info("Created financial_documents table")


def ensure_procurement_schema(engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    with engine.begin() as conn:
        if "requests" in tables:
            conn.execute(
                text("ALTER TABLE requests ALTER COLUMN warehouse_id DROP NOT NULL")
            )
            conn.execute(
                text("ALTER TABLE requests ADD COLUMN IF NOT EXISTS reason TEXT")
            )
            conn.execute(
                text(
                    "ALTER TABLE requests "
                    "ADD COLUMN IF NOT EXISTS payment_request_id INTEGER "
                    "REFERENCES payment_requests(id)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE requests "
                    "ADD COLUMN IF NOT EXISTS purchase_order_id INTEGER "
                    "REFERENCES purchase_orders(id)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE requests "
                    "ADD COLUMN IF NOT EXISTS approved_payment_method VARCHAR(80)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE requests "
                    "ADD COLUMN IF NOT EXISTS approved_payment_comment TEXT"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE requests "
                    "ADD COLUMN IF NOT EXISTS invoice_paid_at TIMESTAMP"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE requests "
                    "ADD COLUMN IF NOT EXISTS invoice_paid_by INTEGER "
                    "REFERENCES users(id)"
                )
            )

        if "request_items" in tables:
            conn.execute(
                text(
                    "ALTER TABLE request_items "
                    "ALTER COLUMN item_id DROP NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE request_items "
                    "ADD COLUMN IF NOT EXISTS item_name VARCHAR(300)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE request_items "
                    "ADD COLUMN IF NOT EXISTS description TEXT"
                )
            )

        if "suppliers" in tables:
            conn.execute(
                text("ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS code VARCHAR(50)")
            )
            conn.execute(
                text("ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS email VARCHAR(255)")
            )
            conn.execute(
                text("ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS address TEXT")
            )
            conn.execute(
                text("ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS description TEXT")
            )
            conn.execute(
                text(
                    "ALTER TABLE suppliers "
                    "ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"
                )
            )

        if "procurement_proformas" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE procurement_proformas (
                        id SERIAL PRIMARY KEY,
                        request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
                        supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
                        amount NUMERIC(18, 2) NOT NULL,
                        currency VARCHAR(10) NOT NULL DEFAULT 'IRR',
                        notes TEXT,
                        status VARCHAR(30) NOT NULL DEFAULT 'draft',
                        uploaded_by INTEGER NOT NULL REFERENCES users(id),
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                        submitted_at TIMESTAMP WITHOUT TIME ZONE,
                        archived_at TIMESTAMP WITHOUT TIME ZONE
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_procurement_proformas_request "
                    "ON procurement_proformas (request_id)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_procurement_proformas_supplier "
                    "ON procurement_proformas (supplier_id)"
                )
            )
        if "goods_receipts" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE goods_receipts (
                        id SERIAL PRIMARY KEY,
                        grn_no VARCHAR(50) UNIQUE,
                        request_id INTEGER NOT NULL REFERENCES requests(id),
                        supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
                        warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                        proforma_id INTEGER REFERENCES procurement_proformas(id),
                        status VARCHAR(30) NOT NULL DEFAULT 'draft',
                        invoice_notes TEXT,
                        receipt_date DATE,
                        created_by INTEGER NOT NULL REFERENCES users(id),
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                        posted_at TIMESTAMP WITHOUT TIME ZONE,
                        posted_by INTEGER REFERENCES users(id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_goods_receipts_request "
                    "ON goods_receipts (request_id)"
                )
            )

        if "goods_receipt_lines" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE goods_receipt_lines (
                        id SERIAL PRIMARY KEY,
                        grn_id INTEGER NOT NULL REFERENCES goods_receipts(id) ON DELETE CASCADE,
                        request_item_id INTEGER REFERENCES request_items(id),
                        item_id INTEGER NOT NULL REFERENCES items(id),
                        quantity_received INTEGER NOT NULL,
                        unit_price NUMERIC(18, 2)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_goods_receipt_lines_grn "
                    "ON goods_receipt_lines (grn_id)"
                )
            )

        if "purchase_orders" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE purchase_orders (
                        id SERIAL PRIMARY KEY,
                        order_no VARCHAR(50) UNIQUE,
                        supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
                        request_id INTEGER REFERENCES requests(id),
                        item_name VARCHAR(300),
                        quantity INTEGER,
                        unit_price NUMERIC(18, 2),
                        expected_date DATE,
                        description TEXT,
                        status VARCHAR(30) NOT NULL DEFAULT 'draft',
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                    )
                    """
                )
            )
        else:
            conn.execute(
                text(
                    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS order_no VARCHAR(50)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS item_name VARCHAR(300)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS quantity INTEGER"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS unit_price NUMERIC(18, 2)"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS expected_date DATE"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS description TEXT"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE purchase_orders ALTER COLUMN request_id DROP NOT NULL"
                )
            )

        if "purchase_order_items" not in tables:
            conn.execute(
                text(
                    """
                    CREATE TABLE purchase_order_items (
                        id SERIAL PRIMARY KEY,
                        po_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
                        item_id INTEGER REFERENCES items(id),
                        quantity INTEGER NOT NULL
                    )
                    """
                )
            )
        else:
            conn.execute(
                text(
                    "ALTER TABLE purchase_order_items "
                    "ALTER COLUMN item_id DROP NOT NULL"
                )
            )

        logger.info(
            "Ensured procurement schema (requests, suppliers, proformas, goods_receipts, purchase_orders)"
        )


def ensure_ad_hoc_task_schema(engine) -> None:
    """Add SLA/deadline columns to ad_hoc_tasks if missing."""
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    if "ad_hoc_tasks" not in insp.get_table_names():
        return

    existing = {c["name"] for c in insp.get_columns("ad_hoc_tasks")}
    with engine.begin() as conn:
        if "due_at" not in existing:
            conn.execute(
                text(
                    "ALTER TABLE ad_hoc_tasks "
                    "ADD COLUMN IF NOT EXISTS due_at TIMESTAMP WITHOUT TIME ZONE"
                )
            )
            logger.info("Added ad_hoc_tasks.due_at column")
        if "sla_notified" not in existing:
            conn.execute(
                text(
                    "ALTER TABLE ad_hoc_tasks "
                    "ADD COLUMN IF NOT EXISTS sla_notified BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            logger.info("Added ad_hoc_tasks.sla_notified column")


def ensure_mission_request_schema(engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    insp = inspect(engine)
    if "mission_requests" in insp.get_table_names():
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mission_requests (
                    id SERIAL PRIMARY KEY,
                    requester_id INTEGER NOT NULL REFERENCES users(id),
                    destination VARCHAR(500) NOT NULL,
                    reason TEXT NOT NULL,
                    vehicle VARCHAR(255) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                    report_text TEXT,
                    reported_at TIMESTAMP WITHOUT TIME ZONE,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mission_requests_requester "
                "ON mission_requests (requester_id)"
            )
        )
        logger.info("Created mission_requests table")
