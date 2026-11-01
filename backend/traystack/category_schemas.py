from pydantic import BaseModel, ConfigDict, Field, field_validator


class CategoryWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str | None = Field(default=None, max_length=100)

    @field_validator("category")
    @classmethod
    def clean(cls, value):
        if value is None:
            return None
        value = value.strip()
        if "\x00" in value:
            raise ValueError("Category cannot contain null characters")
        value.encode("utf-8")
        return value or None
