"""Bounded, reversible report-only repair. Never generates analysis or answers."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import Enum
import json
import re
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amway_circle_tracking import (
    AmwayCircleEvidence, AmwayCircleEdgeSnapshot, AmwayCircleExport,
    AmwayCircleProjection, AmwayCircleReport, AmwayCircleRun,
)
from app.models.entity import Entity
from app.models.brand_intelligence import BrandIntelligenceFinding, BrandReportVersion
from app.models.message import Message
from app.models.snapshot import AnalysisSnapshot
from app.services.amway_topic_repair_service import (
    MODELS, RepairRowStore, digest, json_value, repair_stage,
)
from app.services.amway_circle_tracking_service import AmwayCircleTrackingService

ENTITY_ID = UUID("70eec83d-a767-4c99-8f28-0a068bfcc8a8")
REPAIR_ID = "amway-report-outline-20260914-v1"
SCHEMA_VERSION = "2026-09-14-report-outline-v1"
OMITTED_IDS = frozenset({"value_pillars", "living_young_autonomy"})
OMITTED_TITLES = frozenset({
    "四个价值支柱，在 AI 叙事里是什么状态", "活得年轻：掌控生活的自主",
})
REPORT_KIND = "brand_association_circle"
REPORT_MODELS = (
    AmwayCircleReport, AmwayCircleProjection, AnalysisSnapshot,
    BrandReportVersion, Message, BrandIntelligenceFinding,
)
MODELS_BY_TABLE = {model.__tablename__: model for model in REPORT_MODELS}
ALLOWED_COLUMNS = {
    AmwayCircleReport.__tablename__: {"structured_body", "markdown_body"},
    AmwayCircleProjection.__tablename__: {"association_circle_projection"},
    AnalysisSnapshot.__tablename__: {"raw_data"},
    BrandReportVersion.__tablename__: {"payload"},
    Message.__tablename__: {"output_data"},
    BrandIntelligenceFinding.__tablename__: {"source_payload"},
}
REPORT_WRAPPERS = frozenset({
    "report_data", "report", "report_payload", "report_artifact",
    "dashboard_projection", "association_circle_projection", "entity_calibration_result",
})
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*(?:\r?\n)?$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def omitted_section(section) -> bool:
    return isinstance(section, dict) and (
        section.get("section_id") in OMITTED_IDS
        or section.get("chapter_id") in OMITTED_IDS
        or section.get("title") in OMITTED_TITLES
    )


def trim_markdown(value: str, path: str) -> tuple[str, list[str]]:
    """Remove exact chapter headings through their boundary; preserve other bytes."""
    lines, result, locations = value.splitlines(keepends=True), [], []
    skipped_level = None
    fence = None
    for index, line in enumerate(lines):
        marker = FENCE.match(line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[marker.end():].strip():
                fence = None
            if skipped_level is None:
                result.append(line)
            continue
        heading = HEADING.match(line) if fence is None else None
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip()
            if skipped_level is not None and level <= skipped_level:
                skipped_level = None
            if skipped_level is None and title in OMITTED_TITLES and level in (2, 3):
                skipped_level = level
                locations.append(f"{path}:heading:{index + 1}")
        if skipped_level is None:
            result.append(line)
    return "".join(result), locations


def _sections(value: list, path: str) -> tuple[list, list[str]]:
    result, locations = [], []
    for index, section in enumerate(value):
        item_path = f"{path}[{index}]"
        if omitted_section(section):
            locations.append(item_path)
            continue
        if isinstance(section, dict) and section.get("section_name") == "narrative":
            section = dict(section)
            if isinstance(section.get("markdown"), str):
                section["markdown"], found = trim_markdown(section["markdown"], item_path + ".markdown")
                locations.extend(found)
            data = section.get("data")
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                items, found = _sections(data["items"], item_path + ".data.items")
                section["data"] = {**data, "items": items}
                locations.extend(found)
        result.append(section)
    return result, locations


def trim_report(value, path: str = "report") -> tuple[object, list[str]]:
    """Visit only report structure slots; never traverse source answers or analysis."""
    if not isinstance(value, dict):
        return value, []
    result, locations = dict(value), []
    for key, item in value.items():
        item_path = f"{path}.{key}"
        if key in {"report_narrative_sections", "narrative_sections", "report_sections", "sections", "report_outline"} and isinstance(item, list):
            result[key], found = _sections(item, item_path)
        elif key in {"full_markdown", "report_markdown", "markdown_body"} and isinstance(item, str):
            result[key], found = trim_markdown(item, item_path)
        elif key in REPORT_WRAPPERS and isinstance(item, dict):
            result[key], found = trim_report(item, item_path)
        else:
            continue
        locations.extend(found)
    return (result if locations else value), locations


def transform_row(table: str, row: dict) -> tuple[dict, list[str]]:
    result, locations = dict(row), []
    for column in ALLOWED_COLUMNS[table]:
        value = row.get(column)
        path = f"{table}.{column}"
        if table == Message.__tablename__:
            if not value:
                continue
            try:
                decoded = json.loads(value)
            except (ValueError, TypeError):
                raise ValueError("invalid_report_message_json") from None
            if not isinstance(decoded, dict):
                continue
            replacement, found = trim_report(decoded, path)
            if found:
                result[column] = json.dumps(replacement, ensure_ascii=False)
        elif column == "markdown_body":
            replacement, found = trim_markdown(value or "", path)
            if found:
                result[column] = replacement
        else:
            replacement, found = trim_report(value, path)
            if found:
                result[column] = replacement
        locations.extend(found)
    return (result if locations else row), locations


class AmwayReportOutlineRepairService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def bindings(self) -> dict:
        versions = (await self.db.execute(select(
            BrandReportVersion.id, BrandReportVersion.report_id, BrandReportVersion.version,
            BrandReportVersion.report_kind, BrandReportVersion.session_id, BrandReportVersion.message_id,
        ).where(BrandReportVersion.entity_id == ENTITY_ID).order_by(BrandReportVersion.id))).mappings().all()
        message_ids = {row["message_id"] for row in versions if row["message_id"]}
        foreign = list((await self.db.scalars(select(BrandReportVersion.id).where(
            BrandReportVersion.message_id.in_(message_ids), BrandReportVersion.entity_id != ENTITY_ID,
        ))).all()) if message_ids else []
        messages = (await self.db.execute(select(Message.id, Message.session_id).where(
            Message.id.in_(message_ids)
        ))).mappings().all()
        message_sessions = {row["id"]: row["session_id"] for row in messages}
        errors = [str(row["id"]) for row in versions if row["message_id"] and (
            row["message_id"] not in message_sessions
            or message_sessions[row["message_id"]] != row["session_id"]
        )]
        exports = (await self.db.execute(select(
            AmwayCircleExport.id, AmwayCircleExport.report_id, AmwayCircleExport.projection_id,
            AmwayCircleExport.export_type, AmwayCircleExport.created_at,
        ).where(or_(
            AmwayCircleExport.entity_id == ENTITY_ID,
            AmwayCircleExport.report_id.in_(select(AmwayCircleReport.id).where(AmwayCircleReport.entity_id == ENTITY_ID)),
            AmwayCircleExport.projection_id.in_(select(AmwayCircleProjection.id).where(AmwayCircleProjection.entity_id == ENTITY_ID)),
        )).order_by(AmwayCircleExport.id))).mappings().all()
        return {"versions": [json_value(dict(row)) for row in versions],
                "message_ids": sorted(str(value) for value in message_ids),
                "binding_errors": errors, "foreign_message_bindings": len(foreign),
                "exports": [json_value(dict(row)) for row in exports]}

    async def rows(self, model, bindings: dict, *, lock=False):
        if model is Message:
            condition = model.id.in_([UUID(value) for value in bindings["message_ids"]])
        elif model in (AmwayCircleEvidence, AmwayCircleEdgeSnapshot):
            condition = model.circle_run_id.in_(select(AmwayCircleRun.id).where(AmwayCircleRun.entity_id == ENTITY_ID))
        else:
            condition = model.entity_id == ENTITY_ID
        query = select(*model.__table__.columns).where(condition).order_by(model.id).execution_options(yield_per=1)
        if lock:
            query = query.with_for_update()
        stream = await self.db.stream(query)
        try:
            async for row in stream.mappings():
                yield {key: json_value(value) if isinstance(value, (UUID, datetime, Enum)) else value for key, value in row.items()}
        finally:
            await stream.close()

    async def inventory(self) -> dict:
        bindings = await self.bindings()
        tables, affected, copy_versions = {}, [], Counter()
        for model in REPORT_MODELS:
            table, total, changed = model.__tablename__, 0, 0
            async for row in self.rows(model, bindings):
                total += 1
                _, locations = transform_row(table, row)
                copy_versions.update(report_copy_versions(row))
                if locations:
                    changed += 1
                    affected.append({"table": table, "id": row["id"], "locations": locations})
            tables[table] = {"total": total, "affected": changed}
        return {"mode": "inventory", "entity_id": str(ENTITY_ID), "repair_id": REPAIR_ID,
                "tables": tables, "bindings": bindings, "affected": affected,
                "copy_constraint_versions": dict(copy_versions),
                "provider_calls": False, "database_committed": False}

    async def capture_index(self, bindings: dict, *, lock=False) -> dict:
        result = {}
        for model in MODELS:
            values = {}
            async for row in self.rows(model, bindings, lock=lock and model in REPORT_MODELS):
                values[row["id"]] = digest(row)
            result[model.__tablename__] = values
            repair_stage("outline_index_table", table=model.__tablename__, rows=len(values))
        return result

    async def stage(self, store: RepairRowStore, release_sha: str) -> dict:
        """Read-only plan generation; caller publishes verified disk images atomically."""
        bindings = await self.bindings()
        validate_bindings(bindings)
        if bindings["exports"]:
            raise ValueError("existing_exports_require_explicit_file_repair")
        before_index, after_index, changes = {}, {}, []
        for model in MODELS:
            table, before_table, after_table = model.__tablename__, {}, {}
            async for before in self.rows(model, bindings):
                row_id = before["id"]
                before_table[row_id] = digest(before)
                if model in REPORT_MODELS:
                    after, locations = transform_row(table, before)
                else:
                    after, locations = before, []
                after_table[row_id] = digest(after) if locations else before_table[row_id]
                if locations:
                    changes.append({"table": table, "id": row_id,
                                    "before": store.write("before", table, row_id, before),
                                    "after": store.write("after", table, row_id, after),
                                    "locations": locations})
                del before, after
            before_index[table], after_index[table] = before_table, after_table
            repair_stage("outline_staged_table", table=table, rows=len(before_table), changes=len(changes))
        plan = {"schema_version": SCHEMA_VERSION, "repair_id": REPAIR_ID,
                "entity_id": str(ENTITY_ID), "release_sha": release_sha,
                "bindings": bindings, "before_index": before_index, "after_index": after_index,
                "before_hash": digest(before_index), "after_hash": digest(after_index),
                "changes": changes, "row_storage": {"version": 1, "namespace": store.namespace}}
        plan["manifest_hash"] = digest(plan)
        validate_plan(plan, store, expected_hash=plan["manifest_hash"])
        return plan

    async def apply(self, plan: dict, store: RepairRowStore, *, expected_hash: str, reverse=False) -> dict:
        """Single caller-owned transaction; complete scope drift check before writes."""
        validate_plan(plan, store, expected_hash=expected_hash)
        await AmwayCircleTrackingService(self.db)._lock_entity(ENTITY_ID)
        await self.db.execute(select(Entity.id).where(Entity.id == ENTITY_ID).with_for_update())
        bindings = await self.bindings()
        validate_bindings(bindings)
        if digest(bindings) != digest(plan["bindings"]):
            raise ValueError("report_bindings_drifted")
        current = await self.capture_index(bindings, lock=True)
        source, target = ("after", "before") if reverse else ("before", "after")
        if digest(current) == plan[target + "_hash"]:
            return {"status": "already_restored" if reverse else "already_applied",
                    "changed_rows": len(plan["changes"])}
        if digest(current) != plan[source + "_hash"]:
            raise ValueError("source_rows_drifted")
        for change in plan["changes"]:
            model = MODELS_BY_TABLE[change["table"]]
            after = store.read(change[target])
            # Explicit timestamp values suppress SQLAlchemy's onupdate defaults.
            values = {column: after[column] for column in ALLOWED_COLUMNS[change["table"]]}
            if "updated_at" in model.__table__.columns:
                values["updated_at"] = datetime.fromisoformat(after["updated_at"])
            result = await self.db.execute(update(model.__table__).where(
                model.id == UUID(change["id"])
            ).values(**values))
            if result.rowcount != 1:
                raise ValueError("target_row_missing")
            del after, values
        await self.db.flush()
        result_index = await self.capture_index(bindings)
        if digest(result_index) != plan[target + "_hash"]:
            raise ValueError("post_write_row_hash_mismatch")
        return {"status": "restored" if reverse else "applied", "changed_rows": len(plan["changes"])}

    async def verify(self, plan: dict, store: RepairRowStore, *, expected_hash: str) -> dict:
        validate_plan(plan, store, expected_hash=expected_hash)
        bindings = await self.bindings()
        validate_bindings(bindings)
        if digest(bindings) != digest(plan["bindings"]):
            raise ValueError("report_bindings_drifted")
        if digest(await self.capture_index(bindings)) != plan["after_hash"]:
            raise ValueError("verification_rows_drifted")
        inventory = await self.inventory()
        if inventory["affected"]:
            raise ValueError("target_chapters_still_present")
        return {"status": "verified", "all_persisted_rows_match_plan": True,
                "remaining_target_chapters": 0, "tables": inventory["tables"],
                "copy_constraint_versions": inventory["copy_constraint_versions"]}


def report_copy_versions(row: dict) -> Counter:
    """Only known report slots; skip original answer/strategy content."""
    found = Counter()
    for key, value in row.items():
        if key == "output_data" and isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if key in {"copy_constraints", "report_copy_constraints"} and isinstance(value, dict):
            found[str(value.get("version") or "unrecorded")] += 1
        elif key in REPORT_WRAPPERS | {"structured_body", "raw_data", "payload", "output_data", "source_payload"} and isinstance(value, dict):
            found.update(report_copy_versions(value))
    return found


def validate_bindings(bindings: dict) -> None:
    if bindings["binding_errors"] or bindings["foreign_message_bindings"]:
        raise ValueError("unsafe_report_message_bindings")


def validate_plan(plan: dict, store: RepairRowStore, *, expected_hash: str) -> None:
    if (plan.get("manifest_hash") != expected_hash
            or digest({key: value for key, value in plan.items() if key != "manifest_hash"}) != expected_hash):
        raise ValueError("manifest_hash_mismatch")
    if plan.get("schema_version") != SCHEMA_VERSION or plan.get("repair_id") != REPAIR_ID or plan.get("entity_id") != str(ENTITY_ID):
        raise ValueError("invalid_manifest_scope")
    if plan["row_storage"] != {"version": 1, "namespace": store.namespace}:
        raise ValueError("row_storage_mismatch")
    validate_bindings(plan["bindings"])
    if plan["bindings"]["exports"]:
        raise ValueError("existing_exports_require_explicit_file_repair")
    required_tables = {model.__tablename__ for model in MODELS}
    if set(plan["before_index"]) != required_tables or set(plan["after_index"]) != required_tables:
        raise ValueError("incomplete_scope_index")
    expected_index = {table: dict(rows) for table, rows in plan["before_index"].items()}
    seen = set()
    for change in plan["changes"]:
        key = (change["table"], change["id"])
        if key in seen or key[0] not in MODELS_BY_TABLE:
            raise ValueError("invalid_or_duplicate_manifest_row")
        seen.add(key)
        before, after = store.read(change["before"]), store.read(change["after"])
        model = MODELS_BY_TABLE[key[0]]
        if set(before) != set(model.__table__.columns.keys()) or set(after) != set(before):
            raise ValueError("incomplete_row_image")
        if before["id"] != key[1] or after["id"] != key[1]:
            raise ValueError("row_identity_mismatch")
        if model is Message:
            if key[1] not in plan["bindings"]["message_ids"]:
                raise ValueError("unbound_message_row")
        elif before["entity_id"] != str(ENTITY_ID):
            raise ValueError("foreign_entity_row")
        generated, locations = transform_row(key[0], before)
        if not locations or locations != change["locations"] or digest(generated) != digest(after):
            raise ValueError("after_image_outside_report_outline_scope")
        if transform_row(key[0], after)[1]:
            raise ValueError("non_idempotent_report_transform")
        if expected_index[key[0]].get(key[1]) != digest(before):
            raise ValueError("before_image_not_in_scope_index")
        expected_index[key[0]][key[1]] = digest(after)
        del before, after, generated
    if expected_index != plan["after_index"]:
        raise ValueError("unexpected_changed_or_protected_rows")
    if digest(plan["before_index"]) != plan["before_hash"] or digest(expected_index) != plan["after_hash"]:
        raise ValueError("scope_index_hash_mismatch")


def plan_summary(plan: dict) -> dict:
    return {"repair_id": REPAIR_ID, "entity_id": str(ENTITY_ID),
            "manifest_hash": plan["manifest_hash"], "release_sha": plan["release_sha"],
            "changed_rows": len(plan["changes"]),
            "changed_rows_by_table": dict(Counter(item["table"] for item in plan["changes"])),
            "before_hash": plan["before_hash"], "after_hash": plan["after_hash"],
            "provider_calls": False, "raw_answers_changed": False,
            "analysis_nodes_changed": False, "timestamps_changed": False,
            "scope": "all_entity_report_history_no_date_limit"}
