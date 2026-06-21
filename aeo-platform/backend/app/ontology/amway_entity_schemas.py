"""Schemas for the Amway-specific entity extraction ontology."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MainOrbitPolicy = Literal[
    "always_center",
    "allowed_with_answer_evidence",
    "evidence_only",
    "not_allowed",
]
RiskViewPolicy = Literal["allowed", "aggregate_only", "not_allowed"]
TargetGapViewPolicy = Literal["allowed", "not_allowed"]
ReviewStatus = Literal["approved", "pending_review", "rejected", "merged"]
SourceSide = Literal["question", "answer"]


class AmwayCenterBrandPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_center_brand: str
    allowed_center_brands: tuple[str, ...] = Field(default_factory=tuple)
    market_context_terms: tuple[str, ...] = Field(default_factory=tuple)
    core_asset_terms: tuple[str, ...] = Field(default_factory=tuple)
    rules: tuple[str, ...] = Field(default_factory=tuple)


class AmwayEntityTypeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_id: str
    label: str
    definition: str
    default_graph_role: str
    extractable_from: tuple[SourceSide, ...] = Field(default_factory=tuple)
    allowed_relation_types: tuple[str, ...] = Field(default_factory=tuple)
    review_required: bool = False


class AmwayGraphPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_orbit: MainOrbitPolicy
    risk_view: RiskViewPolicy
    target_gap_view: TargetGapViewPolicy


class AmwaySourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: str
    source_document_section: str
    user_confirmed: bool = False


class AmwayEntityDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    canonical_name: str
    entity_type: str
    aliases: tuple[str, ...] = Field(default_factory=tuple)
    description: str = ""
    related_terms: tuple[str, ...] = Field(default_factory=tuple)
    graph_policy: AmwayGraphPolicy
    source_policy: AmwaySourcePolicy
    review_status: ReviewStatus = "approved"


class AmwayRelationTypeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_type: str
    label: str
    description: str
    source_entity_types: tuple[str, ...] = Field(default_factory=tuple)
    target_entity_types: tuple[str, ...] = Field(default_factory=tuple)
    evidence_required: bool = True
    graph_effect: str


class AmwayExtractionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_fields: tuple[str, ...] = Field(default_factory=tuple)
    source_sides: tuple[SourceSide, ...] = Field(default_factory=tuple)
    review_statuses: tuple[ReviewStatus, ...] = Field(default_factory=tuple)


class AmwayReviewActionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    description: str


class AmwayReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    description: str
    recommended_resolution: str


class AmwayValidationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    description: str
    failure_handling: str


class AmwayEntityOntologyDefinition(BaseModel):
    """Machine-readable Amway entity ontology for extraction and review."""

    model_config = ConfigDict(extra="forbid")

    ontology_id: str
    version: str
    source_document: str
    center_brand_policy: AmwayCenterBrandPolicy
    entity_types: tuple[AmwayEntityTypeDefinition, ...] = Field(default_factory=tuple)
    relation_types: tuple[AmwayRelationTypeDefinition, ...] = Field(
        default_factory=tuple
    )
    entities: tuple[AmwayEntityDefinition, ...] = Field(default_factory=tuple)
    extraction_contract: AmwayExtractionContract
    review_actions: tuple[AmwayReviewActionDefinition, ...] = Field(
        default_factory=tuple
    )
    review_issues: tuple[AmwayReviewIssue, ...] = Field(default_factory=tuple)
    validation_rules: tuple[AmwayValidationRule, ...] = Field(default_factory=tuple)
