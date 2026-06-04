from pydantic import BaseModel, ConfigDict, Field

from app.schemas.permission import PermissionOut


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="شناسه فنی انگلیسی")
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        validation_alias="displayName",
        description="نام نمایشی فارسی",
    )
    is_singleton: bool = Field(False, validation_alias="isSingleton")


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    display_name: str | None = Field(None, max_length=100, validation_alias="displayName")
    is_singleton: bool | None = Field(None, validation_alias="isSingleton")


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    display_name: str | None = Field(None, serialization_alias="displayName")
    is_singleton: bool = Field(False, serialization_alias="isSingleton")


class RolePermissionsReplace(BaseModel):
    permission_ids: list[int] = Field(
        default_factory=list,
        description="Full permission list for the role; replaces all existing links",
    )


class RolePermissionsResponse(BaseModel):
    role_id: int
    permissions: list[PermissionOut]
