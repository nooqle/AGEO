"""Schemas for the Amway-specific entity extraction ontology."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


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


class AmwaySemanticSource(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class AmwayTopicMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_entity_id: str = Field(min_length=1)
    review_status: ReviewStatus = "pending_review"
    source_refs: tuple[AmwaySemanticSource, ...] = Field(min_length=1)


class AmwayObjectRelation(AmwayTopicMapping):
    relation_type: Literal[
        "contains", "produced_by", "authored_by", "supports", "used_by",
        "associated_with", "part_of", "uses_technology", "hosted_by",
    ]


class AmwaySemanticDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    semantic_type: Literal[
        "brand", "organization", "product", "material", "tool", "person",
        "concept", "topic", "unresolved", "document", "event", "place", "program",
    ]
    identity_scope: str = Field(min_length=1)
    match_policy: Literal["exact", "contextual", "disabled"] = "disabled"
    context_terms: tuple[str, ...] = ()
    match_exclusions: tuple[str, ...] = ()
    graph_role: Literal["topic", "object", "context", "anchor"]
    merged_into: str | None = None
    repair_id: str | None = None
    source_manifest_hash: str | None = None
    source_refs: tuple[AmwaySemanticSource, ...] = Field(min_length=1)
    topic_mappings: tuple[AmwayTopicMapping, ...] = ()
    relations: tuple[AmwayObjectRelation, ...] = ()

    @model_validator(mode="after")
    def validate_matching(self):
        if self.match_policy == "contextual" and not any(self.context_terms):
            raise ValueError("contextual matching requires context_terms")
        if self.semantic_type == "unresolved" and self.match_policy != "disabled":
            raise ValueError("unresolved identities cannot match automatically")
        if any(len("".join(term.split())) < 2 for term in self.match_exclusions):
            raise ValueError("match exclusions require nonempty containing phrases")
        return self

    @model_serializer(mode="wrap")
    def serialize_matching(self, handler):
        payload = handler(self)
        # Adding an optional matching rule must not invalidate historical hashes.
        if not self.match_exclusions:
            payload.pop("match_exclusions", None)
        return payload


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
    semantic_definition: AmwaySemanticDefinition | None = None


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
