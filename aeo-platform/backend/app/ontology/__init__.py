"""Specta Ontology foundation.

This package contains the first lightweight registry for the AI brand
intelligence model. It is intentionally read-only for now: workflow nodes can
adopt it incrementally without changing persistence or runtime behavior.
"""

from app.ontology.registry import (
    DEFAULT_ONTOLOGY_PATH,
    OntologyRegistry,
    OntologyRegistryError,
    load_default_ontology,
)
from app.ontology.amway_entity_registry import (
    DEFAULT_AMWAY_ENTITY_ONTOLOGY_PATH,
    AmwayEntityOntologyRegistry,
    load_default_amway_entity_ontology,
)
from app.ontology.amway_entity_schemas import (
    AmwayCenterBrandPolicy,
    AmwayEntityDefinition,
    AmwayEntityOntologyDefinition,
    AmwayEntityTypeDefinition,
    AmwayExtractionContract,
    AmwayGraphPolicy,
    AmwayRelationTypeDefinition,
    AmwayReviewActionDefinition,
    AmwayReviewIssue,
    AmwaySourcePolicy,
    AmwayValidationRule,
)
from app.ontology.schemas import (
    ActionTypeDefinition,
    FunctionDefinition,
    LinkTypeDefinition,
    ObjectTypeDefinition,
    ObjectViewDefinition,
    OntologyDefinition,
    PropertyDefinition,
)

__all__ = [
    "ActionTypeDefinition",
    "AmwayCenterBrandPolicy",
    "AmwayEntityDefinition",
    "AmwayEntityOntologyDefinition",
    "AmwayEntityOntologyRegistry",
    "AmwayEntityTypeDefinition",
    "AmwayExtractionContract",
    "AmwayGraphPolicy",
    "AmwayRelationTypeDefinition",
    "AmwayReviewActionDefinition",
    "AmwayReviewIssue",
    "AmwaySourcePolicy",
    "AmwayValidationRule",
    "DEFAULT_AMWAY_ENTITY_ONTOLOGY_PATH",
    "DEFAULT_ONTOLOGY_PATH",
    "FunctionDefinition",
    "LinkTypeDefinition",
    "ObjectTypeDefinition",
    "ObjectViewDefinition",
    "OntologyDefinition",
    "OntologyRegistry",
    "OntologyRegistryError",
    "PropertyDefinition",
    "load_default_amway_entity_ontology",
    "load_default_ontology",
]
