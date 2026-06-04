# ERP Execution Next Steps

This project now includes the 4 primary forms requested in the project brief:

1. `workflow_forms` via `/workflow-forms`
2. `payment_requests` via `/payment-requests`
3. `warehouse_forms` via `/warehouse-forms`
4. `requests` via `/requests` (existing procurement request flow)

## Frontend: What forms you can build now

Below is the current list of forms/screens you can implement in the frontend today based on available backend routes.

### 1) فرم گردش کار عمومی (Workflow Form)

- **Route**: `POST /workflow-forms`
- **List**: `GET /workflow-forms`
- **Fields**:
  - `receiver_id` (int)
  - `title` (string)
  - `description` (string | optional)
- **Workflow**:
  - On create, publishes `workflow.start` with `ref_type=workflow_form`
  - Approval chain: manager / project_manager (alias-aware)

### 2) فرم درخواست پرداخت (Payment Request)

- **Route**: `POST /payment-requests`
- **List**: `GET /payment-requests`
- **Fields**:
  - `payment_type` (string)
  - `amount` (number)
  - `payer_account` (string)
  - `receiver_account` (string)
  - `payment_date` (date | optional, ISO `YYYY-MM-DD`)
  - `reason` (string | optional)
- **Workflow**:
  - On create, publishes `workflow.start` with `ref_type=payment_request`
  - Approval chain: finance_manager/accountant -> ceo (alias-aware)

### 3) فرم انبار (Warehouse Form)

- **Route**: `POST /warehouse-forms`
- **List**: `GET /warehouse-forms`
- **Fields**:
  - `form_type` (string) `IN | OUT | TRANSFER`
  - `source` (string | optional)
  - `destination` (string | optional)
  - `receiver_name` (string | optional)
  - `effective_date` (date | optional, ISO `YYYY-MM-DD`)
  - `description` (string | optional)
- **Workflow**:
  - On create, publishes `workflow.start` with `ref_type=warehouse_form`
  - Approval chain: warehouse_manager/warehouse -> finance_manager/accountant -> ceo (alias-aware)

### 4) فرم درخواست کالا (Procurement Request / Item Request)

- **Route**: `POST /requests`
- **Fields**:
  - `warehouse_id` (int)
  - `items` (array)
    - `item_id` (int)
    - `quantity` (int)
- **Workflow**:
  - On create, publishes `workflow.start` with `ref_type=request`
  - Approval chain: purchase_manager -> finance_manager/accountant -> ceo (alias-aware)

### Inbox / Notifications / Workflow actions (screens)

These are supporting screens that make the forms usable in an ERP-style UX:

- **Inbox (کارتابل)**: `GET /inbox/` (existing)
  - Mark read: `POST /inbox/{inbox_id}/read`
  - Mark done: `POST /inbox/{inbox_id}/done`
- **Notifications**: `GET /notifications` (existing) and grouped/mark-as-read (existing)
- **Workflow approve/reject**:
  - `POST /workflow/{instance_id}/approve`
  - `POST /workflow/{instance_id}/reject`
- **Dashboards**:
  - User dashboard: `GET /dashboard/`
  - Management dashboard (KPIs): `GET /dashboard/management`

## What was implemented

- Added new models:
  - `WorkflowForm`
  - `WarehouseForm`
- Enabled existing model in metadata:
  - `PaymentRequest`
- Added services and routes for all 3 new API areas.
- Connected all new forms to event publishing (`workflow.start`) for workflow engine integration.

## Immediate backlog (next coding steps)

1. Add attachments support for payment and item requests.
2. Add reporting endpoints by role (CEO/Finance/Project manager).
3. Add automated integration tests for each form submission path.
4. Add DB migration tooling (Alembic) and create migration scripts for new/changed columns.
5. Add role-management UI/API to map real organization roles to matrix aliases.
6. Add SLA policy per form type (target hours, escalation target).
## Completed in current phase

- `workflow.start` now creates workflow instances + ordered steps.
- Form APIs now use Pydantic schemas instead of raw `dict`.
- Approval matrix is active and role-alias aware for all 4 forms.
- Management dashboard exposes KPI blocks:
  - forms volume
  - workflow totals/rates/by ref_type
  - operational inbox/SLA indicators

## Current approval matrix behavior

Workflow start now uses role sequences per form with alias matching:

- `workflow_form`: manager / project_manager
- `payment_request`: finance_manager -> ceo
- `warehouse_form`: warehouse_manager -> finance_manager -> ceo
- `request`: purchase_manager -> finance_manager -> ceo

If no matching role exists, workflow falls back to the first available role in the system.

## Suggested API payload examples

### POST `/workflow-forms`
```json
{
  "receiver_id": 1,
  "title": "Project kickoff follow-up",
  "description": "Coordinate action items and due dates."
}
```

### POST `/payment-requests`
```json
{
  "payment_type": "advance",
  "amount": 2500000,
  "payer_account": "Company Account - 001",
  "receiver_account": "Employee Account - 9284",
  "payment_date": "2026-05-01",
  "reason": "Travel advance"
}
```

### POST `/warehouse-forms`
```json
{
  "form_type": "TRANSFER",
  "source": "Main Warehouse",
  "destination": "Project Site A",
  "receiver_name": "Site Supervisor",
  "effective_date": "2026-05-01",
  "description": "Transfer cable and tools"
}
```
