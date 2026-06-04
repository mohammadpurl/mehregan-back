from pydantic import BaseModel, ConfigDict, Field


class NavMenuItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    href: str | None = None
    label: str
    required_permissions: list[str] = Field(
        default_factory=list, serialization_alias="requiredPermissions"
    )
    children: list["NavMenuItemOut"] = Field(default_factory=list)


NavMenuItemOut.model_rebuild()
