from pydantic import BaseModel, ConfigDict, Field


class AssignmentRuleCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role_id: int = Field(..., validation_alias="roleId")
    strategy: str = Field("random", description="random | least_loaded | round_robin")
    is_active: bool = Field(True, validation_alias="isActive")


class AssignmentRuleUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    strategy: str | None = None
    is_active: bool | None = Field(None, validation_alias="isActive")


class AssignmentRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    role_id: int = Field(serialization_alias="roleId")
    strategy: str
    is_active: bool = Field(serialization_alias="isActive")
