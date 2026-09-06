"""Tenant-scoped, compare-and-swap application of reviewed lexicon repairs."""
from typing import Any
import hashlib
import json

from sqlalchemy import select

from app.models.entity import Entity
from app.ontology import AmwayEntityDefinition, AmwayEntityOntologyRegistry
from app.ontology.amway_entity_schemas import AmwaySemanticSource
from app.services.amway_entity_lexicon_service import (
    AmwayEntityLexiconService, _row_from_base_entity,
)


async def export_repair_state(service: AmwayEntityLexiconService, entity_id) -> dict:
    await service._lock_entity(entity_id)
    rows = await service._overrides_for_entity(entity_id)
    return {
        "entity_id": str(entity_id),
        "payload": await service.payload_for_entity(entity_id),
        "override_before_images": [
            {column.name: _json_value(getattr(row, column.name))
             for column in row.__table__.columns}
            for row in rows
        ],
    }


def _json_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is not None and not isinstance(value, (str, int, float, bool, dict, list)):
        return str(value)
    return value


def prepare_repair(registry: AmwayEntityOntologyRegistry, package: dict) -> tuple:
    records = package.get("records")
    if not package.get("repair_id") or not isinstance(records, list) or not records:
        raise ValueError("repair_id and nonempty records are required")
    current = {entry.entity_id: entry for entry in registry.entities}
    preserved = set(package.get("preserve_entity_ids") or [])
    if len(preserved) != 128 or not preserved.issubset(current):
        raise ValueError("preserved IDs must exist in the current lexicon")
    desired = dict(current)
    seen = set()
    for record in records:
        entity_id = record.get("entity_id")
        if not entity_id or entity_id in seen:
            raise ValueError("records require unique stable entity_id values")
        seen.add(entity_id)
        base = current.get(entity_id)
        payload = base.model_dump() if base else {}
        payload.update(record)
        if isinstance(payload.get("semantic_definition"), dict):
            payload["semantic_definition"] = {
                **payload["semantic_definition"], "repair_id": package["repair_id"],
                "source_manifest_hash": package.get("source_manifest_hash"),
            }
        entry = AmwayEntityDefinition.model_validate(payload)
        if entry.semantic_definition is None:
            raise ValueError("reviewed records require semantic_definition")
        desired[entity_id] = entry
    crosswalk = package.get("article_crosswalk") or []
    source_ids = [str(row.get("source_record_id") or "") for row in crosswalk]
    if len(source_ids) != 71 or len(set(source_ids)) != 71 or "" in source_ids:
        raise ValueError("article_crosswalk must contain 71 distinct source records")
    if any(row.get("entity_id") not in desired for row in crosswalk):
        raise ValueError("article_crosswalk references an unknown identity")
    _validate_manifest(package, crosswalk, desired)
    effective = AmwayEntityOntologyRegistry(registry.definition.model_copy(
        update={"entities": tuple(desired.values())}
    ))
    changed = [entry for key, entry in desired.items() if current.get(key) != entry]
    if changed and package.get("expected_effective_hash") != registry.effective_hash:
        raise ValueError("effective lexicon changed; export and review again")
    return effective, changed


def _validate_manifest(package, crosswalk, desired) -> None:
    manifest = package.get("source_manifest")
    if not isinstance(manifest, list) or len(manifest) != 71:
        raise ValueError("source_manifest must contain 71 records")
    digest = hashlib.sha256(json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    if digest != package.get("source_manifest_hash"):
        raise ValueError("source_manifest_hash mismatch")
    by_id = {str(row.get("source_record_id")): row for row in manifest}
    if set(by_id) != {str(row["source_record_id"]) for row in crosswalk}:
        raise ValueError("crosswalk does not match source manifest")
    for row in crosswalk:
        source = by_id[str(row["source_record_id"])]
        if row.get("decision") not in {"reuse", "create", "scoped", "merge"} or not str(row.get("reason") or "").strip():
            raise ValueError("crosswalk requires reviewed decision and reason")
        if not str(source.get("original_name") or "").strip() or not source.get("source_refs"):
            raise ValueError("manifest requires original_name and source_refs")
        semantic = desired[row["entity_id"]].semantic_definition
        if semantic is None:
            raise ValueError("crosswalk identity has no semantic provenance")
        actual = {json.dumps(ref.model_dump(), sort_keys=True, ensure_ascii=False) for ref in semantic.source_refs}
        required = {json.dumps(AmwaySemanticSource.model_validate(ref).model_dump(), sort_keys=True, ensure_ascii=False)
                    for ref in source["source_refs"]}
        if not required.issubset(actual):
            raise ValueError("crosswalk source references are missing from identity provenance")


async def repair_lexicon(service, *, entity, user_id, package, apply=False) -> dict[str, Any]:
    # The same entity lock is used by single-entry writes to serialize reviews.
    await service.db.execute(select(Entity.id).where(Entity.id == entity.id).with_for_update())
    registry = await service.registry_for_entity(entity.id)
    effective, changed = prepare_repair(registry, package)
    result = {
        "repair_id": package["repair_id"], "changed_ids": [row.entity_id for row in changed],
        "before_hash": registry.effective_hash, "effective_hash": effective.effective_hash,
        "status": "unchanged" if not changed else "preview",
        "before_image": await export_repair_state(service, entity.id),
        "entries": [row.model_dump(mode="json") for row in effective.entities],
        "changes": [{"entity_id": row.entity_id,
                     "before": registry.get_entity(row.entity_id).model_dump(mode="json") if registry.get_entity(row.entity_id) else None,
                     "after": row.model_dump(mode="json")} for row in changed],
    }
    if not apply or not changed:
        return result
    for entry in changed:
        row = await service._override_for_entry(entity.id, entry.entity_id)
        if row is None:
            row = _row_from_base_entity(entity=entity, base=entry, current_user_id=user_id)
            service.db.add(row)
        for key, value in entry.model_dump(mode="json").items():
            if key != "entity_id":
                setattr(row, key, value)
        row.is_deleted = False
        row.updated_by_user_id = user_id
    await service.db.commit()
    actual = await service.registry_for_entity(entity.id)
    if actual.effective_hash != effective.effective_hash:
        raise RuntimeError("Committed lexicon readback differs from preview; retain before_image")
    result["status"] = "applied"
    return result
