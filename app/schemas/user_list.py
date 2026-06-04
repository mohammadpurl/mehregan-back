from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user_banking import UserBankingFieldsMixin


class UserUpdate(UserBankingFieldsMixin, BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    password: str | None = Field(None, min_length=6)
    is_active: bool | None = None
    role_id: int | None = None
    manager_id: int | None = None
    department_id: int | None = None


class UserCreate(UserBankingFieldsMixin, BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    is_active: bool = True
    role_id: int | None = None
    manager_id: int | None = None
    department_id: int | None = None


class UserListItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    username: str
    email: str | None = None
    full_name: str | None = None
    phone: str | None = None
    is_active: bool = True
    role_id: int | None = None
    role_name: str | None = None
    manager_id: int | None = None
    manager_name: str | None = None
    department_id: int | None = None
    department_name: str | None = None
    card_number: str | None = None
    cardNumber: str | None = None
    sheba_number: str | None = None
    shebaNumber: str | None = None


class UserListResponse(BaseModel):
    items: list[UserListItem]
    total: int
    page: int
    pageSize: int
