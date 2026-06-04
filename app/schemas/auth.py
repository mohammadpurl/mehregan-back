from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr | None = None
    password: str = Field(..., min_length=6)
    mobile: str | None = None


class TokenResponse(BaseModel):
    """Frontend uses camelCase; Swagger OAuth2 expects access_token / token_type."""

    model_config = ConfigDict(populate_by_name=True)

    accessToken: str
    access_token: str
    tokenType: str = "bearer"
    token_type: str = "bearer"
    sessionId: Optional[str] = None
    sessionExpiry: Optional[int] = None  # unix timestamp
    userId: Optional[int] = Field(None, serialization_alias="userId")
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
