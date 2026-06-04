from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    parent_id: int | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    parent_id: int | None = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None = None
    parent_name: str | None = None
    children_count: int = 0
    items_count: int = 0


class CategoryListResponse(BaseModel):
    items: list[CategoryOut]
    total: int
    page: int
    pageSize: int


class CategoryTreeNode(BaseModel):
    id: int
    name: str
    parent_id: int | None = None
    children: list["CategoryTreeNode"] = Field(default_factory=list)


CategoryTreeNode.model_rebuild()
