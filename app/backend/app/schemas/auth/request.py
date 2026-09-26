"""Authentication request bodies."""

from pydantic import BaseModel, Field, SecretStr

from app.core.security import PASSWORD_MAX_LENGTH


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(max_length=PASSWORD_MAX_LENGTH)
