"""Authentication request bodies."""

from pydantic import BaseModel, Field, SecretStr

from app.core.security import PASSWORD_MAX_LENGTH

LOGIN_NAME_MAX_LENGTH = 320


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=LOGIN_NAME_MAX_LENGTH)
    # An empty password is accepted here and answered with 401 without contacting the directory.
    password: SecretStr = Field(max_length=PASSWORD_MAX_LENGTH)
