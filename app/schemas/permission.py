from pydantic import BaseModel, ConfigDict, Field


class PermissionCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)


class PermissionUpdate(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=100)
    name: str | None = Field(None, min_length=1, max_length=100)


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str | None = None
    name: str


class PermissionListResponse(BaseModel):
    items: list[PermissionOut]
    total: int
    page: int
    pageSize: int
