"""Pydantic schemas for the authentication module."""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Payload for the login endpoint.

    Attributes:
        identifier: Employee id or work email.
        password: Plaintext password.
        remember: Whether the refresh token should outlive the browser session.
    """

    identifier: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)
    remember: bool = False


class UserRead(BaseModel):
    """Serialized user returned to the authenticated frontend.

    Deliberately excludes the password hash and internal identifiers beyond the
    user id.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: str
    email: str
    name: str
    role: str


class AuthResponse(BaseModel):
    """Payload returned by login, refresh and session endpoints.

    The ``user`` field mirrors the shape the frontend auth provider expects.
    """

    user: UserRead
