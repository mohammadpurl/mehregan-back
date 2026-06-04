from pydantic import BaseModel, Field


class RequestItemInput(BaseModel):
    item_id: int
    quantity: int = Field(gt=0)


class UpdateRequestInput(BaseModel):
    warehouse_id: int | None = None
    items: list[RequestItemInput] | None = Field(default=None, min_length=1)


class CreateRequestInput(BaseModel):
    warehouse_id: int
    items: list[RequestItemInput] = Field(min_length=1)
    assignees_by_order: dict[str, int] | None = Field(
        default=None,
        description="Optional 1-based step index -> user id for explicit assignees",
    )
