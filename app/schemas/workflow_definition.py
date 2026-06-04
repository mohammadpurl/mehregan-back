from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.workflow_step_config import ASSIGNEE_STRATEGIES, normalize_steps_config


class WorkflowStepConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role_aliases: list[str] = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("roleAliases", "role_aliases"),
        description="نام‌های نقش (اولین تطابق در سیستم)",
    )
    assignee_strategy: str = Field(
        "role_pool",
        validation_alias=AliasChoices("assigneeStrategy", "assignee_strategy"),
        description="role_pool | fixed_user | submitter_manager | department_head",
    )
    assignee_user_id: int | None = Field(
        None,
        validation_alias=AliasChoices("assigneeUserId", "assignee_user_id"),
        description="برای fixed_user — شناسه تأییدکننده ثابت",
    )
    label: str | None = Field(None, max_length=255)
    order: int | None = None

    @field_validator("assignee_strategy")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        v = (value or "role_pool").strip().lower()
        if v not in ASSIGNEE_STRATEGIES:
            raise ValueError(
                f"assignee_strategy باید یکی از {sorted(ASSIGNEE_STRATEGIES)} باشد"
            )
        return v

    @field_validator("assignee_user_id", mode="before")
    @classmethod
    def empty_assignee_as_none(cls, value: Any) -> Any:
        if value in ("", None, "undefined"):
            return None
        return value


class WorkflowDefinitionUpsert(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ref_type: str = Field(
        ...,
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices("refType", "ref_type"),
    )
    name: str = Field(..., min_length=1, max_length=255)
    steps: list[Any] = Field(
        ...,
        description="لیست مراحل (dict با roleAliases یا role_aliases)",
    )
    code: str | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def normalize_steps(self) -> "WorkflowDefinitionUpsert":
        try:
            normalized = normalize_steps_config(self.steps)
            self.steps = [WorkflowStepConfig(**s) for s in normalized]
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self


class WorkflowDefinitionOut(BaseModel):
    id: int
    ref_type: str | None
    code: str
    name: str
    steps_config: list[dict]

    model_config = {"from_attributes": True}


class WorkflowAssigneePreview(BaseModel):
    order: int
    role_aliases: list[str] = Field(
        serialization_alias="roleAliases",
        validation_alias=AliasChoices("roleAliases", "role_aliases"),
    )
    role_id: int | None = Field(
        None,
        serialization_alias="roleId",
        validation_alias=AliasChoices("roleId", "role_id"),
    )
    assignee_strategy: str = Field(
        serialization_alias="assigneeStrategy",
        validation_alias=AliasChoices("assigneeStrategy", "assignee_strategy"),
    )
    assignee_user_id: int | None = Field(
        None,
        serialization_alias="assigneeUserId",
        validation_alias=AliasChoices("assigneeUserId", "assignee_user_id"),
    )
    resolved_user_id: int | None = Field(
        None,
        serialization_alias="resolvedUserId",
        validation_alias=AliasChoices("resolvedUserId", "resolved_user_id"),
    )
    resolved_user_name: str | None = Field(
        None,
        serialization_alias="resolvedUserName",
        validation_alias=AliasChoices("resolvedUserName", "resolved_user_name"),
    )
    label: str | None = None

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
