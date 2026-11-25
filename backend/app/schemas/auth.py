import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not _EMAIL.match(value):
        raise ValueError("Enter a valid email address.")
    return value


def _password(value: str) -> str:
    if len(value) < 10:
        raise ValueError("Use at least 10 characters.")
    if len(value) > 128:
        raise ValueError("Use at most 128 characters.")
    if value.isalpha() or value.isdigit():
        raise ValueError("Mix letters with numbers or symbols.")
    return value


def _name(value: str) -> str:
    value = " ".join(value.split())
    if not 2 <= len(value) <= 120:
        raise ValueError("Enter your name (2 to 120 characters).")
    return value


Email = Annotated[str, AfterValidator(_email)]
Password = Annotated[str, AfterValidator(_password)]
FullName = Annotated[str, AfterValidator(_name)]


class LoginIn(BaseModel):
    email: Email
    password: str = Field(max_length=200)


class RegisterIn(BaseModel):
    email: Email
    password: Password
    full_name: FullName


class AcceptInviteIn(BaseModel):
    token: str = Field(max_length=200)
    password: Password
    full_name: FullName


class InviteIn(BaseModel):
    email: Email


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: Literal["student", "coordinator"]
    consent_at: datetime | None
    onboarded_at: datetime | None


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class InviteCreated(InviteOut):
    link: str
