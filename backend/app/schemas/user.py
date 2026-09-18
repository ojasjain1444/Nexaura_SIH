from pydantic import BaseModel, field_validator

PIN_LENGTH = 2


class RegisterRequest(BaseModel):
    username: str
    pin: str

    @field_validator("username")
    @classmethod
    def username_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("username must not be blank")
        return value.strip()

    @field_validator("pin")
    @classmethod
    def pin_is_two_digits(cls, value: str) -> str:
        if not (len(value) == PIN_LENGTH and value.isdigit()):
            raise ValueError(f"pin must be exactly {PIN_LENGTH} digits")
        return value


class LoginRequest(BaseModel):
    username: str
    pin: str


class UserResponse(BaseModel):
    id: str
    username: str


class LoginResponse(BaseModel):
    token: str
    user: UserResponse
