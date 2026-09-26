from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt

FeatureName = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")]
FeatureValue = (
    Annotated[StrictFloat, Field(allow_inf_nan=False)]
    | StrictInt
    | StrictBool
    | Annotated[str, Field(max_length=1024)]
    | None
)

NonEmpty = Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]


class Domain(StrEnum):
    TRANSACTION = "ieee_cis"
    CREDIT = "home_credit"
    GRAPH = "elliptic"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CaseCreate(Contract):
    domain: Domain
    source_record_id: NonEmpty
    title: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]


class CaseView(Contract):
    id: UUID
    domain: Domain
    source_record_id: str
    title: str
    status: str
    version: int
    created_at: datetime


class AuditView(Contract):
    id: UUID
    case_id: UUID
    actor_id: str
    event: str
    created_at: datetime


class ModelAvailability(Contract):
    domain: Domain
    available: bool
    reason: str
    backend: str | None = None
    model_version: str | None = None


class ScoreRequest(Contract):
    input_schema_version: NonEmpty
    # The adapter must validate domain-specific features once their contract is recovered.
    # This layer deliberately does not guess training-time features or preprocessing.
    features: Annotated[dict[FeatureName, FeatureValue], Field(max_length=512)]


class ScoreResult(Contract):
    domain: Domain
    model_version: NonEmpty
    input_schema_version: NonEmpty
    positive_class: NonEmpty
    probability: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
