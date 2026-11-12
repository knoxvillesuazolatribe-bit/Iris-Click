"""Request and response shapes for /api/accounts (accounts on this computer).

Lengths are capped here only to keep junk out; the real rules (and the messages
people see) are in usernames.py, pins.py and mobiles.py. No response ever carries
a PIN, a hash or a full mobile number.
"""

from typing import Literal

from pydantic import BaseModel, Field


class SigninModeRead(BaseModel):
    mode: Literal["legacy", "device_accounts"]
    sms_enabled: bool = False


class MobileRequest(BaseModel):
    mobile_number: str = Field(max_length=32)


class MobileCodeRequest(MobileRequest):
    code: str = Field(max_length=12)


class MobileTicketRequest(BaseModel):
    mobile_ticket: str = Field(max_length=600)


class CodeSentRead(BaseModel):
    to: str               # masked: 09** *** 2488
    resend_after: int     # seconds


class TicketRead(BaseModel):
    ticket: str


class ForgotSendRequest(BaseModel):
    user_id: int


class ForgotVerifyRequest(ForgotSendRequest):
    code: str = Field(max_length=12)


class ForgotCompleteRequest(BaseModel):
    ticket: str = Field(max_length=600)
    pin: str = Field(max_length=12)
    pin_confirm: str = Field(max_length=12)
    remember: bool = False


class TileRead(BaseModel):
    user_id: int
    username: str
    needs_pin: bool
    accuracy: float | None = None


class TilesRead(BaseModel):
    is_shared: bool
    accounts: list[TileRead]


class ThisComputerRead(BaseModel):
    """Shared computers never remember an account and sign the person out after ``idle_minutes``."""
    is_shared: bool
    idle_minutes: int


class UsernameCheckRequest(BaseModel):
    username: str = Field(max_length=64)


class UsernameCheckRead(BaseModel):
    available: bool
    problem: str | None = None
    message: str | None = None
    suggestions: list[str] = []


class SignupRequest(BaseModel):
    consent: bool
    username: str = Field(max_length=64)
    mobile_number: str = Field(max_length=32)
    pin: str = Field(max_length=16)
    pin_confirm: str = Field(max_length=16)
    remember: bool = False


class SigninRequest(BaseModel):
    """A tile (``user_id``) or "I already have an account" (``username``); the PIN when one is needed."""
    user_id: int | None = Field(default=None, gt=0)
    username: str | None = Field(default=None, max_length=64)
    pin: str | None = Field(default=None, max_length=16)
    remember: bool = False


class RemoveRequest(BaseModel):
    user_id: int = Field(gt=0)
    pin: str | None = Field(default=None, max_length=16)


class AccountSessionRead(BaseModel):
    user_id: int
    full_name: str
    username: str
    role: Literal["assistive_user"] = "assistive_user"


class SetupCodeRequest(BaseModel):
    code: str = Field(max_length=32)


class SetupCodeRead(BaseModel):
    ticket: str
    full_name: str
    username: str | None  # None: no account yet; choose a username and mobile number too


class SetupCompleteRequest(BaseModel):
    ticket: str = Field(max_length=512)
    pin: str = Field(max_length=16)
    pin_confirm: str = Field(max_length=16)
    consent: bool = False
    username: str | None = Field(default=None, max_length=64)
    mobile_number: str | None = Field(default=None, max_length=32)


class AddressRequest(BaseModel):
    """The person's own address for Emergency SOS (step 12). Blank barangay is allowed."""
    address: str = Field(min_length=1, max_length=255)
    barangay: str = Field(default="", max_length=100)


class AddressRead(BaseModel):
    location_text: str | None

