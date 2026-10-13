from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    model_validator,
)

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
    artifact_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None


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


class CaseScoreView(Contract):
    id: UUID
    case_id: UUID
    domain: Domain
    model_version: str
    input_schema_version: str
    positive_class: str
    probability: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    backend: str | None
    artifact_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    created_at: datetime


class EvidenceCreate(Contract):
    # Opaque identifiers only: these fields are never fetched as URLs or file paths.
    source_id: Annotated[str, Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")]
    source_version: Annotated[
        str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    ]
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class EvidenceView(EvidenceCreate):
    id: UUID
    case_id: UUID
    actor_id: str
    created_at: datetime


Disposition = Literal["escalate", "no_further_action", "insufficient_evidence"]


class InvestigationCreate(Contract):
    disposition: Disposition
    summary: Annotated[str, Field(min_length=1, max_length=4000, pattern=r"\S")]
    evidence_ids: Annotated[list[UUID], Field(max_length=20)]

    @model_validator(mode="after")
    def validate_citations(self) -> Self:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Duplicate evidence references")
        if not self.evidence_ids and self.disposition != "insufficient_evidence":
            raise ValueError("Evidence is required for this disposition")
        return self


class InvestigationView(Contract):
    id: UUID
    case_id: UUID
    actor_id: str
    disposition: Disposition
    summary: str
    evidence: Annotated[list[EvidenceView], Field(max_length=20)]
    status: Literal["awaiting_review"]
    requires_human_review: Literal[True] = True
    created_at: datetime
