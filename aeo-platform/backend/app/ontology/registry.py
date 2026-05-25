"""Read-only registry for Specta's AI brand intelligence ontology."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import ValidationError

from app.ontology.schemas import (
    ActionTypeDefinition,
    FunctionDefinition,
    LinkTypeDefinition,
    ObjectTypeDefinition,
    ObjectViewDefinition,
    OntologyDefinition,
)


DEFAULT_ONTOLOGY_PATH = Path(__file__).with_name("specta_ontology.json")

T = TypeVar("T")


class OntologyRegistryError(ValueError):
    """Raised when the ontology definition is structurally invalid."""


class OntologyRegistry:
    """Validated, read-only lookup surface for ontology definitions."""

    def __init__(self, definition: OntologyDefinition) -> None:
        self.definition = definition
        self._object_types = _index_by_key(definition.object_types, "object_types")
        self._link_types = _index_by_key(definition.link_types, "link_types")
        self._action_types = _index_by_key(definition.action_types, "action_types")
        self._functions = _index_by_key(definition.functions, "functions")
        self._object_views = _index_by_key(definition.object_views, "object_views")
        self._validate_references()

    @classmethod
    def from_path(cls, path: str | Path = DEFAULT_ONTOLOGY_PATH) -> "OntologyRegistry":
        source_path = Path(path)
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            definition = OntologyDefinition.model_validate(payload)
        except OSError as exc:
            raise OntologyRegistryError(
                f"Unable to read ontology definition: {source_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise OntologyRegistryError(
                f"Ontology definition is not valid JSON: {source_path}"
            ) from exc
        except ValidationError as exc:
            raise OntologyRegistryError(
                f"Ontology definition failed schema validation: {source_path}"
            ) from exc
        return cls(definition)

    @property
    def object_types(self) -> tuple[ObjectTypeDefinition, ...]:
        return self.definition.object_types

    @property
    def link_types(self) -> tuple[LinkTypeDefinition, ...]:
        return self.definition.link_types

    @property
    def action_types(self) -> tuple[ActionTypeDefinition, ...]:
        return self.definition.action_types

    @property
    def functions(self) -> tuple[FunctionDefinition, ...]:
        return self.definition.functions

    @property
    def object_views(self) -> tuple[ObjectViewDefinition, ...]:
        return self.definition.object_views

    def get_object_type(self, key: str) -> ObjectTypeDefinition | None:
        return self._object_types.get(key)

    def require_object_type(self, key: str) -> ObjectTypeDefinition:
        return _require(self._object_types, key, "object type")

    def require_lifecycle_status(self, object_type: str, status: str) -> str:
        definition = self.require_object_type(object_type)
        normalized = str(status or "").strip().lower()
        if not normalized:
            raise OntologyRegistryError(
                f"Object type {object_type} requires a lifecycle status"
            )
        if normalized not in definition.lifecycle:
            raise OntologyRegistryError(
                f"Object type {object_type} does not allow lifecycle status: "
                f"{normalized}"
            )
        return normalized

    def get_link_type(self, key: str) -> LinkTypeDefinition | None:
        return self._link_types.get(key)

    def require_link_type(self, key: str) -> LinkTypeDefinition:
        return _require(self._link_types, key, "link type")

    def get_action_type(self, key: str) -> ActionTypeDefinition | None:
        return self._action_types.get(key)

    def require_action_type(self, key: str) -> ActionTypeDefinition:
        return _require(self._action_types, key, "action type")

    def get_function(self, key: str) -> FunctionDefinition | None:
        return self._functions.get(key)

    def require_function(self, key: str) -> FunctionDefinition:
        return _require(self._functions, key, "function")

    def get_object_view(self, key: str) -> ObjectViewDefinition | None:
        return self._object_views.get(key)

    def require_object_view(self, key: str) -> ObjectViewDefinition:
        return _require(self._object_views, key, "object view")

    def _validate_references(self) -> None:
        object_keys = set(self._object_types)
        link_keys = set(self._link_types)
        action_keys = set(self._action_types)

        for link in self.definition.link_types:
            _require_key(object_keys, link.from_object, f"{link.key}.from_object")
            _require_key(object_keys, link.to_object, f"{link.key}.to_object")

        for action in self.definition.action_types:
            if not action.target_objects:
                raise OntologyRegistryError(
                    f"Action type {action.key} must target at least one object type"
                )
            for object_key in action.target_objects:
                _require_key(object_keys, object_key, f"{action.key}.target_objects")
            for link_key in action.creates_links:
                _require_key(link_keys, link_key, f"{action.key}.creates_links")

        for function in self.definition.functions:
            for action_key in function.used_by_actions:
                _require_key(action_keys, action_key, f"{function.key}.used_by_actions")

        for view in self.definition.object_views:
            _require_key(object_keys, view.object_type, f"{view.key}.object_type")
            for action_key in view.actions:
                _require_key(action_keys, action_key, f"{view.key}.actions")


def load_default_ontology() -> OntologyRegistry:
    """Load the bundled Specta ontology definition."""

    return OntologyRegistry.from_path(DEFAULT_ONTOLOGY_PATH)


def _index_by_key(items: Iterable[T], collection_name: str) -> dict[str, T]:
    indexed: dict[str, T] = {}
    for item in items:
        key = getattr(item, "key")
        if key in indexed:
            raise OntologyRegistryError(
                f"Duplicate key {key!r} in ontology {collection_name}"
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
            f"Ontology reference {field_name} points to unknown key: {key}"
        )
