import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.user_banking import UserBankingFieldsMixin

_NATIONAL_ID_RE = re.compile(r"^\d{10}$")


class UserAuthContext(BaseModel):
    """نقش‌ها و مجوزهای فعال کاربر (برای منو و UI)."""

    model_config = ConfigDict(populate_by_name=True)

    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class UserProfileResponse(BaseModel):
    """profileVersion=2 یعنی فیلدهای card/sheba فعال است (برای تشخیص deploy جدید)."""

    profile_version: int = Field(2, serialization_alias="profileVersion")

    id: int
    username: str
    email: str | None = None
    mobile: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    national_id: str | None = None
    father_name: str | None = None
    account_number: str | None = None
    accountNumber: str | None = None
    card_number: str | None = None
    cardNumber: str | None = None
    sheba_number: str | None = None
    shebaNumber: str | None = None
    pic: str = ""
    picUrl: str = ""
    full_name: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AuthMeResponse(UserProfileResponse):
    """GET /auth/me — پروفایل + نقش و مجوز (برای به‌روزرسانی منو بدون لاگین مجدد)."""

    pass


class UserProfileUpdate(UserBankingFieldsMixin, BaseModel):
    """PATCH /auth/profile — شامل card_number / sheba_number (یا cardNumber / shebaNumber)."""

    model_config = ConfigDict(populate_by_name=True)

    email: EmailStr | None = None
    mobile: str | None = Field(None, max_length=20)
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    national_id: str | None = Field(None, min_length=10, max_length=10)
    father_name: str | None = Field(None, min_length=1, max_length=100)

    @model_validator(mode="before")
    @classmethod
    def empty_optional_strings_to_none(cls, data):
        """رشته خالی از فرانت (= پاک کردن فیلد اختیاری) نباید 422 بدهد."""
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for key, value in list(out.items()):
            if isinstance(value, str) and not value.strip():
                out[key] = None
        return out

    @field_validator("national_id")
    @classmethod
    def validate_national_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not _NATIONAL_ID_RE.match(value):
            raise ValueError("کد ملی باید ۱۰ رقم باشد")
        return value
