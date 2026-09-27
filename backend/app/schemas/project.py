import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.validation import NonBlankName, reject_explicit_nulls


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonBlankName = Field(max_length=200)
    description: str | None = Field(default=None, max_length=5_000)


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonBlankName | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5_000)

    @model_validator(mode="after")
    def _no_null_name(self) -> "ProjectUpdate":
        reject_explicit_nulls(self, "name")
        return self


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
