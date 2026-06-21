"""Read-only registry for the Amway entity extraction ontology."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import ValidationError

from app.ontology.amway_entity_schemas import (
    AmwayEntityDefinition,
    AmwayEntityOntologyDefinition,
    AmwayEntityTypeDefinition,
    AmwayRelationTypeDefinition,
)
from app.ontology.registry import OntologyRegistryError


DEFAULT_AMWAY_ENTITY_ONTOLOGY_PATH = Path(__file__).with_name(
    "amway_entity_ontology.json"
)

T = TypeVar("T")


class AmwayEntityOntologyRegistry:
    """Validated lookup surface for Amway entity definitions."""

    def __init__(self, definition: AmwayEntityOntologyDefinition) -> None:
        self.definition = definition
        self._entity_types = _index_by(
            definition.entity_types, "type_id", "entity_types"
        )
        self._relation_types = _index_by(
            definition.relation_types, "relation_type", "relation_types"
        )
        self._entities = _index_by(definition.entities, "entity_id", "entities")
        self._entities_by_name = _index_by(
            definition.entities, "canonical_name", "entities.canonical_name"
        )
        self._ambiguous_aliases: set[str] = set()
        self._alias_index = self._build_alias_index(definition.entities)
        self._validate_references()

    @classmethod
    def from_path(
        cls, path: str | Path = DEFAULT_AMWAY_ENTITY_ONTOLOGY_PATH
    ) -> "AmwayEntityOntologyRegistry":
        source_path = Path(path)
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            definition = AmwayEntityOntologyDefinition.model_validate(payload)
        except OSError as exc:
            raise OntologyRegistryError(
                f"Unable to read Amway entity ontology: {source_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise OntologyRegistryError(
                f"Amway entity ontology is not valid JSON: {source_path}"
            ) from exc
        except ValidationError as exc:
            raise OntologyRegistryError(
                f"Amway entity ontology failed schema validation: {source_path}"
            ) from exc
        return cls(definition)

    @property
    def entity_types(self) -> tuple[AmwayEntityTypeDefinition, ...]:
        return self.definition.entity_types

    @property
    def relation_types(self) -> tuple[AmwayRelationTypeDefinition, ...]:
        return self.definition.relation_types

    @property
    def entities(self) -> tuple[AmwayEntityDefinition, ...]:
        return self.definition.entities

    def get_entity(self, entity_id: str) -> AmwayEntityDefinition | None:
        return self._entities.get(entity_id)

    def require_entity(self, entity_id: str) -> AmwayEntityDefinition:
        return _require(self._entities, entity_id, "Amway entity")

    def get_entity_type(self, type_id: str) -> AmwayEntityTypeDefinition | None:
        return self._entity_types.get(type_id)

    def require_entity_type(self, type_id: str) -> AmwayEntityTypeDefinition:
        return _require(self._entity_types, type_id, "Amway entity type")

    def get_relation_type(
        self, relation_type: str
    ) -> AmwayRelationTypeDefinition | None:
        return self._relation_types.get(relation_type)

    def require_relation_type(
        self, relation_type: str
    ) -> AmwayRelationTypeDefinition:
        return _require(self._relation_types, relation_type, "Amway relation type")

    def find_entity_by_name_or_alias(self, text: str) -> AmwayEntityDefinition | None:
        normalized = _normalize_term(text)
        if not normalized:
            return None
        entity = self._entities_by_name.get(text)
        if entity is not None:
            return entity
        if normalized in self._ambiguous_aliases:
            return None
        entity_id = self._alias_index.get(normalized)
        if entity_id is None:
            return None
        return self._entities.get(entity_id)

    def entities_by_type(self, type_id: str) -> tuple[AmwayEntityDefinition, ...]:
        self.require_entity_type(type_id)
        return tuple(entity for entity in self.entities if entity.entity_type == type_id)

    def _validate_references(self) -> None:
        entity_type_keys = set(self._entity_types)
        relation_type_keys = set(self._relation_types)

        for entity_type in self.entity_types:
            for relation_type in entity_type.allowed_relation_types:
                _require_key(
                    relation_type_keys,
                    relation_type,
                    f"{entity_type.type_id}.allowed_relation_types",
                )

        for relation_type in self.relation_types:
            for source_type in relation_type.source_entity_types:
                _require_key(
                    entity_type_keys,
                    source_type,
                    f"{relation_type.relation_type}.source_entity_types",
                )
            for target_type in relation_type.target_entity_types:
                _require_key(
                    entity_type_keys,
                    target_type,
                    f"{relation_type.relation_type}.target_entity_types",
                )

        for entity in self.entities:
            _require_key(entity_type_keys, entity.entity_type, f"{entity.entity_id}.type")

        default_center = self.definition.center_brand_policy.default_center_brand
        allowed_centers = set(self.definition.center_brand_policy.allowed_center_brands)
        if default_center not in allowed_centers:
            raise OntologyRegistryError(
                "Amway default center brand must be present in allowed center brands"
            )

    def _build_alias_index(
        self,
        entities: Iterable[AmwayEntityDefinition],
    ) -> dict[str, str]:
        alias_index: dict[str, str] = {}
        for entity in entities:
            terms = (entity.canonical_name, *entity.aliases)
            for term in terms:
                normalized = _normalize_term(term)
                if not normalized:
                    continue
                existing = alias_index.get(normalized)
                if existing is not None and existing != entity.entity_id:
                    alias_index.pop(normalized, None)
                    self._ambiguous_aliases.add(normalized)
                    continue
                if normalized in self._ambiguous_aliases:
                    continue
                alias_index[normalized] = entity.entity_id
        return alias_index


def load_default_amway_entity_ontology() -> AmwayEntityOntologyRegistry:
    """Load the bundled Amway entity ontology definition."""

    return AmwayEntityOntologyRegistry.from_path(DEFAULT_AMWAY_ENTITY_ONTOLOGY_PATH)


def _normalize_term(term: str) -> str:
    return "".join(str(term or "").strip().lower().split())


def _index_by(items: Iterable[T], attr_name: str, collection_name: str) -> dict[str, T]:
    indexed: dict[str, T] = {}
    for item in items:
        key = getattr(item, attr_name)
        if key in indexed:
            raise OntologyRegistryError(
                f"Duplicate key {key!r} in Amway ontology {collection_name}"
            )
        indexed[key] = item
    return indexed


def _require(mapping: dict[str, T], key: str, label: str) -> T:
    value = mapping.get(key)
    if value is None:
        raise OntologyRegistryError(f"Unknown {label}: {key}")
    return value


def _require_key(keys: set[str], key: str, field_name: str) -> None:
    if key not in keys:
        raise OntologyRegistryError(
            f"Amway ontology reference {field_name} points to unknown key: {key}"
        )
