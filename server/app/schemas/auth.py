from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3,
                                         max_length=255, pattern=r"^[^@\s]+@[^@\s]+$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class AdminLoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=1024)


class SessionUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    role: Literal["assistive_user", "admin"]


class AssistiveTileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    last_calibrated_at: datetime | None
    accuracy_score: Decimal | None
    continue_profile_id: str | None
    continue_unavailable_reason: str | None


class AssistiveSelectRequest(BaseModel):
    user_id: int = Field(gt=0)


class AssistiveCreateRequest(BaseModel):
    full_name: Name
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    barangay: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    email: str | None
    role: Literal["assistive_user", "admin"]
    status: Literal["active", "inactive"]
    address: str | None
    barangay: str | None
    created_at: datetime
