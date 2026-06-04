from pydantic import BaseModel, ConfigDict, Field


class ItemCreate(BaseModel):
    name: str
    code: str
    category_id: int | None = None
    unit: str | None = None


class ItemUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    unit: str | None = None
    is_active: bool | None = None


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    code: str
    category_id: int | None = Field(None, serialization_alias="categoryId")
    category_name: str | None = Field(None, serialization_alias="categoryName")
    unit: str | None = None


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int
    page: int
    pageSize: int
