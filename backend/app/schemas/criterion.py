import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.validation import NonBlankName, Weight, reject_explicit_nulls


class CriterionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonBlankName = Field(max_length=200)
    description: str = Field(default="", max_length=5_000)
    weight: Weight = 1.0
    scale_min: int = Field(default=1, ge=0, le=100)
    scale_max: int = Field(default=5, ge=0, le=100)
    enabled: bool = True

    @model_validator(mode="after")
    def _scale_range(self) -> "CriterionCreate":
        if self.scale_min >= self.scale_max:
            raise ValueError("scale_min must be less than scale_max")
        return self


class CriterionUpdate(BaseModel):
    """Partial update. The merged scale range is re-validated in the service."""

    model_config = ConfigDict(extra="forbid")

    name: NonBlankName | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=5_000)
    weight: Weight | None = None
    scale_min: int | None = Field(default=None, ge=0, le=100)
    scale_max: int | None = Field(default=None, ge=0, le=100)
    enabled: bool | None = None

    @model_validator(mode="after")
    def _no_nulls(self) -> "CriterionUpdate":
        reject_explicit_nulls(
            self, "name", "description", "weight", "scale_min", "scale_max", "enabled"
        )
        return self


class CriterionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    weight: float
    scale_min: int
    scale_max: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
