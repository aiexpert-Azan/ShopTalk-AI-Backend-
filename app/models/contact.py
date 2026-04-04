from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ContactSubmission(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    message: str = Field(..., min_length=1, max_length=4000)

    model_config = ConfigDict(extra="ignore")

    @field_validator("name", "message", mode="before")
    @classmethod
    def strip_string_values(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if any(char in value for char in ("\r", "\n")):
            raise ValueError("Name contains invalid characters")
        return value

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            raise ValueError("Message cannot be empty")
        return normalized.strip()
