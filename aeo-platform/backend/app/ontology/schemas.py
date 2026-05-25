"""Schema definitions for Specta's lightweight ontology registry."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ValueType = Literal[
    "string",
    "text",
    "integer",
    "float",
    "boolean",
    "datetime",
    "enum",
    "json",
    "url",
    "uuid",
    "list",
]

Cardinality = Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many"]


class PropertyDefinition(BaseModel):
    """A business property on an object type."""

    model_config = ConfigDict(extra="forbid")

    key: str
    display_name: str
    value_type: ValueType
    description: str
    required: bool = False
    repeated: bool = False


class ObjectTypeDefinition(BaseModel):
    """A durable business object in the AI brand intelligence world."""

    model_config = ConfigDict(extra="forbid")

    key: str
    display_name: str
    description: str
    identity_fields: tuple[str, ...] = Field(default_factory=tuple)
    lifecycle: tuple[str, ...] = Field(default_factory=tuple)
    source_systems: tuple[str, ...] = Field(default_factory=tuple)
    properties: tuple[PropertyDefinition, ...] = Field(default_factory=tuple)


class LinkTypeDefinition(BaseModel):
    """A stable business relationship between two object types."""

    model_config = ConfigDict(extra="forbid")

    key: str
    display_name: str
    description: str
    from_object: str
    to_object: str
    cardinality: Cardinality


class ActionTypeDefinition(BaseModel):
    """A controlled business operation that can change objects or links."""

    model_config = ConfigDict(extra="forbid")

    key: str
    display_name: str
    description: str
    target_objects: tuple[str, ...] = Field(default_factory=tuple)
    required_inputs: tuple[str, ...] = Field(default_factory=tuple)
    writes: tuple[str, ...] = Field(default_factory=tuple)
    creates_links: tuple[str, ...] = Field(default_factory=tuple)
    requires_confirmation: bool = False
    permission_scope: str
    audit_event: str
    side_effects: tuple[str, ...] = Field(default_factory=tuple)


class FunctionDefinition(BaseModel):
    """Reusable deterministic logic over ontology objects."""

    model_config = ConfigDict(extra="forbid")

    key: str
    display_name: str
    description: str
    reads: tuple[str, ...] = Field(default_factory=tuple)
    inputs: tuple[str, ...] = Field(default_factory=tuple)
    outputs: tuple[str, ...] = Field(default_factory=tuple)
    used_by_actions: tuple[str, ...] = Field(default_factory=tuple)


class ObjectViewDefinition(BaseModel):
    """A user-facing hub centered on one object type."""

    model_config = ConfigDict(extra="forbid")

    key: str
    display_name: str
    description: str
    object_type: str
    sections: tuple[str, ...] = Field(default_factory=tuple)
    actions: tuple[str, ...] = Field(default_factory=tuple)


class OntologyDefinition(BaseModel):
    """Machine-readable definition of Specta's first ontology layer."""

    model_config = ConfigDict(extra="forbid")

    version: str
    domain: str
    purpose: str
    principles: tuple[str, ...] = Field(default_factory=tuple)
    object_types: tuple[ObjectTypeDefinition, ...] = Field(default_factory=tuple)
    link_types: tuple[LinkTypeDefinition, ...] = Field(default_factory=tuple)
    action_types: tuple[ActionTypeDefinition, ...] = Field(default_factory=tuple)
    functions: tuple[FunctionDefinition, ...] = Field(default_factory=tuple)
    object_views: tuple[ObjectViewDefinition, ...] = Field(default_factory=tuple)
