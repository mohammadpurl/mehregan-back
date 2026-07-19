from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.attachment import AttachmentOut


class PurchaseLineInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    item_id: int | None = Field(None, gt=0, validation_alias="itemId")
    item_name: str = Field(..., min_length=1, max_length=300, validation_alias="itemName")
    quantity: int = Field(..., gt=0)
    description: str | None = Field(None, max_length=2000)
    unit: str | None = Field(None, max_length=50)
    supply_source: str | None = Field(
        None, max_length=200, validation_alias="supplySource"
    )
    warehouse_stock: float | None = Field(
        None, validation_alias="warehouseStock", ge=0
    )


class CreatePurchaseRequestInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = Field(None, max_length=255)
    reason: str | None = Field(None, max_length=2000)
    warehouse_id: int = Field(..., gt=0, validation_alias="warehouseId")
    lines: list[PurchaseLineInput] = Field(min_length=1)
    assignees_by_order: dict[str, int] | None = Field(
        None, validation_alias="assigneesByOrder"
    )


class UpdatePurchaseRequestInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reason: str | None = Field(None, max_length=2000)
    lines: list[PurchaseLineInput] = Field(min_length=1)


class UpdatePurchaseStockInput(BaseModel):
    """سرپرست مالی: به‌روزرسانی موجودی انبار اقلام."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[dict] = Field(
        ...,
        description="[{id, warehouseStock}]",
    )


class PurchaseLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    item_name: str | None = Field(None, serialization_alias="itemName")
    quantity: int
    description: str | None = None
    item_id: int | None = Field(None, serialization_alias="itemId")
    unit: str | None = None
    supply_source: str | None = Field(None, serialization_alias="supplySource")
    warehouse_stock: float | None = Field(None, serialization_alias="warehouseStock")


class WorkflowProgressStepOut(BaseModel):
    order: int
    label: str
    status: str
    role: str | None = None


class WorkflowProgressPhaseOut(BaseModel):
    phase: str
    instance_id: int = Field(serialization_alias="instanceId")
    instance_status: str = Field(serialization_alias="instanceStatus")
    steps: list[WorkflowProgressStepOut] = Field(default_factory=list)


class PurchaseOrderSummaryOut(BaseModel):
    id: int
    order_no: str | None = Field(None, serialization_alias="orderNo")
    status: str | None = None


class ProcurementPaymentSummaryOut(BaseModel):
    id: int
    amount: float
    status: str
    payment_type: str | None = Field(None, serialization_alias="paymentType")
    workflow_instance_id: int | None = Field(None, serialization_alias="workflowInstanceId")


class CreateProcurementPaymentInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    counterparty_id: int | None = Field(None, serialization_alias="counterpartyId")
    counterparty_bank_account_id: int | None = Field(
        None, serialization_alias="counterpartyBankAccountId"
    )
    payer_company_account_id: int | None = Field(
        None, serialization_alias="payerCompanyAccountId"
    )
    payment_method: str | None = Field(None, serialization_alias="paymentMethod")
    payment_date: date | None = Field(None, serialization_alias="paymentDate")
    notes: str | None = None
    assignees_by_order: dict[str, int] | None = Field(
        None, serialization_alias="assigneesByOrder"
    )


class PurchaseRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    type: str
    status: str
    title: str | None = None
    requester_id: int = Field(serialization_alias="requesterId")
    requester_name: str | None = Field(None, serialization_alias="requesterName")
    reason: str | None = None
    warehouse_id: int | None = Field(None, serialization_alias="warehouseId")
    warehouse_name: str | None = Field(None, serialization_alias="warehouseName")
    items: list[PurchaseLineOut] = Field(default_factory=list)
    can_edit_items: bool = Field(False, serialization_alias="canEditItems")
    can_edit_stock: bool = Field(False, serialization_alias="canEditStock")
    current_step_action: str | None = Field(None, serialization_alias="currentStepAction")
    workflow_instance_id: int | None = Field(None, serialization_alias="workflowInstanceId")
    workflow_progress: list[WorkflowProgressPhaseOut] | None = Field(
        None, serialization_alias="workflowProgress"
    )
    payment_request_id: int | None = Field(None, serialization_alias="paymentRequestId")
    purchase_order_id: int | None = Field(None, serialization_alias="purchaseOrderId")
    payment: ProcurementPaymentSummaryOut | None = None
    purchase_order: PurchaseOrderSummaryOut | None = Field(
        None, serialization_alias="purchaseOrder"
    )
    attachments: list[AttachmentOut] = Field(default_factory=list)
    invoices: list[AttachmentOut] = Field(default_factory=list)
    payment_slips: list[AttachmentOut] = Field(
        default_factory=list, serialization_alias="paymentSlips"
    )
    bills_of_lading: list[AttachmentOut] = Field(
        default_factory=list, serialization_alias="billsOfLading"
    )
    approved_payment_method: str | None = Field(
        None, serialization_alias="approvedPaymentMethod"
    )
    approved_payment_comment: str | None = Field(
        None, serialization_alias="approvedPaymentComment"
    )
    payment_location: str | None = Field(None, serialization_alias="paymentLocation")
    check_plan: list | None = Field(None, serialization_alias="checkPlan")
    invoice_paid_at: datetime | None = Field(None, serialization_alias="invoicePaidAt")
    invoice_paid_by: int | None = Field(None, serialization_alias="invoicePaidBy")
    sepidar_registered_at: datetime | None = Field(
        None, serialization_alias="sepidarRegisteredAt"
    )
    sepidar_confirmed_at: datetime | None = Field(
        None, serialization_alias="sepidarConfirmedAt"
    )
    created_at: datetime | None = None


class SupplierCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str | None = Field(None, max_length=50)
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    description: str | None = None
    is_active: bool = True


class SupplierUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    code: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    description: str | None = None
    is_active: bool | None = None


class SupplierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    description: str | None = None
    is_active: bool = True


class PurchaseOrderCreate(BaseModel):
    request_id: str | None = None
    supplier_name: str = Field(..., min_length=1, max_length=200)
    item_name: str | None = Field(None, max_length=300)
    quantity: int | None = Field(None, gt=0)
    unit_price: float | None = Field(None, ge=0)
    expected_date: date | str | None = None
    status: str = "draft"
    description: str | None = Field(None, max_length=2000)


class PurchaseOrderUpdate(BaseModel):
    request_id: str | None = None
    supplier_name: str | None = Field(None, min_length=1, max_length=200)
    item_name: str | None = Field(None, max_length=300)
    quantity: int | None = Field(None, gt=0)
    unit_price: float | None = Field(None, ge=0)
    expected_date: date | str | None = None
    status: str | None = None
    description: str | None = Field(None, max_length=2000)


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_no: str | None = Field(None, serialization_alias="orderNo")
    request_id: str | None = Field(None, serialization_alias="requestId")
    supplier_name: str = Field(serialization_alias="supplierName")
    item_name: str | None = Field(None, serialization_alias="itemName")
    quantity: int | None = None
    unit_price: float | None = Field(None, serialization_alias="unitPrice")
    expected_date: str | None = Field(None, serialization_alias="expectedDate")
    status: str
    description: str | None = None
    created_at: datetime | None = Field(None, serialization_alias="createdAt")


class ProformaCreate(BaseModel):
    supplier_id: int = Field(..., gt=0)
    amount: float = Field(..., gt=0)
    notes: str | None = Field(None, max_length=2000)


class GoodsReceiptLineInput(BaseModel):
    request_item_id: int | None = None
    item_id: int | None = None
    item_name: str | None = Field(None, max_length=300)
    quantity_received: int = Field(..., gt=0)
    unit_price: float | None = Field(None, ge=0)


class CreateGoodsReceiptInput(BaseModel):
    request_id: int = Field(..., gt=0)
    warehouse_id: int = Field(..., gt=0)
    supplier_id: int | None = Field(None, gt=0)
    receipt_date: date | None = None
    invoice_notes: str | None = Field(None, max_length=2000)
    lines: list[GoodsReceiptLineInput] | None = None


class UpdateGoodsReceiptInput(BaseModel):
    warehouse_id: int | None = Field(None, gt=0)
    receipt_date: date | None = None
    invoice_notes: str | None = Field(None, max_length=2000)
    lines: list[GoodsReceiptLineInput] | None = None


class GoodsReceiptLineOut(BaseModel):
    id: int
    request_item_id: int | None = Field(None, serialization_alias="requestItemId")
    item_id: int = Field(serialization_alias="itemId")
    item_name: str | None = Field(None, serialization_alias="itemName")
    quantity_received: int = Field(serialization_alias="quantityReceived")
    unit_price: float | None = Field(None, serialization_alias="unitPrice")


class GoodsReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    grn_no: str | None = Field(None, serialization_alias="grnNo")
    request_id: int = Field(serialization_alias="requestId")
    supplier_id: int = Field(serialization_alias="supplierId")
    supplier_name: str | None = Field(None, serialization_alias="supplierName")
    warehouse_id: int = Field(serialization_alias="warehouseId")
    warehouse_name: str | None = Field(None, serialization_alias="warehouseName")
    proforma_id: int | None = Field(None, serialization_alias="proformaId")
    status: str
    invoice_notes: str | None = Field(None, serialization_alias="invoiceNotes")
    receipt_date: date | None = Field(None, serialization_alias="receiptDate")
    created_at: datetime | None = Field(None, serialization_alias="createdAt")
    posted_at: datetime | None = Field(None, serialization_alias="postedAt")
    lines: list[GoodsReceiptLineOut] = Field(default_factory=list)
    request_status: str | None = Field(None, serialization_alias="requestStatus")
    file_name: str | None = Field(None, serialization_alias="fileName")
    download_url: str | None = Field(None, serialization_alias="downloadUrl")


class ProformaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int = Field(serialization_alias="requestId")
    supplier_id: int = Field(serialization_alias="supplierId")
    supplier_name: str | None = Field(None, serialization_alias="supplierName")
    amount: float
    notes: str | None = None
    status: str
    uploaded_by: int = Field(serialization_alias="uploadedBy")
    created_at: datetime | None = Field(None, serialization_alias="createdAt")
    file_name: str | None = Field(None, serialization_alias="fileName")
    download_url: str | None = Field(None, serialization_alias="downloadUrl")
