from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    parent_id: int | None = Field(None, alias="parentId")
    head_user_id: int | None = Field(None, alias="headUserId")

    model_config = ConfigDict(populate_by_name=True)


class DepartmentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    parent_id: int | None = Field(None, alias="parentId")
    head_user_id: int | None = Field(None, alias="headUserId")

    model_config = ConfigDict(populate_by_name=True)


class DepartmentOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    parent_id: int | None = Field(None, serialization_alias="parentId")
    parent_name: str | None = Field(None, serialization_alias="parentName")
    head_user_id: int | None = Field(None, serialization_alias="headUserId")
    head_user_name: str | None = Field(None, serialization_alias="headUserName")
    children_count: int = Field(0, serialization_alias="childrenCount")
    users_count: int = Field(0, serialization_alias="usersCount")


class DepartmentTreeNode(DepartmentOut):
    children: list["DepartmentTreeNode"] = Field(default_factory=list)


class DepartmentListResponse(BaseModel):
    items: list[DepartmentOut]
    total: int
    page: int
    pageSize: int
