from pydantic import BaseModel, ConfigDict, Field


class SlaPolicyCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ref_type: str = Field(..., min_length=1, max_length=80, validation_alias="refType")
    step_order: int = Field(..., ge=1, validation_alias="stepOrder")
    max_minutes: int = Field(..., ge=1, validation_alias="maxMinutes")
    escalate_to_role_id: int | None = Field(
        None, validation_alias="escalateToRoleId"
    )
    is_active: bool = Field(True, validation_alias="isActive")


class SlaPolicyUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    max_minutes: int | None = Field(None, ge=1, validation_alias="maxMinutes")
    escalate_to_role_id: int | None = Field(
        None, validation_alias="escalateToRoleId"
    )
    is_active: bool | None = Field(None, validation_alias="isActive")


class SlaPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    ref_type: str = Field(serialization_alias="refType")
    step_order: int = Field(serialization_alias="stepOrder")
    max_minutes: int = Field(serialization_alias="maxMinutes")
    escalate_to_role_id: int | None = Field(
        None, serialization_alias="escalateToRoleId"
    )
    is_active: bool = Field(serialization_alias="isActive")
