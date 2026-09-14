"""Bounded, reversible report-only repair. Never generates analysis or answers."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import Enum
import json
import re
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amway_circle_tracking import (
    AmwayCircleExport, AmwayCircleProjection, AmwayCircleReport,
)
from app.models.brand_intelligence import BrandIntelligenceFinding, BrandReportVersion
from app.models.message import Message
from app.models.snapshot import AnalysisSnapshot
from app.services.amway_topic_repair_service import RepairRowStore, digest, json_value

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
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            if skipped_level is None:
                result.append(line)
            continue
        heading = HEADING.match(line) if fence is None else None
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip()
            if skipped_level is not None and level <= skipped_level:
                skipped_level = None
            if title in OMITTED_TITLES and level in (2, 3):
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
    if table == BrandReportVersion.__tablename__ and row.get("report_kind") != REPORT_KIND:
        return row, []
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
            if not isinstance(decoded, dict) or decoded.get("report_kind") != REPORT_KIND:
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
        ).where(BrandReportVersion.entity_id == ENTITY_ID))).mappings().all()
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
        ).where(AmwayCircleExport.entity_id == ENTITY_ID))).mappings().all()
        return {"versions": [json_value(dict(row)) for row in versions],
                "message_ids": sorted(str(value) for value in message_ids),
                "binding_errors": errors, "foreign_message_bindings": len(foreign),
                "exports": [json_value(dict(row)) for row in exports]}

    async def rows(self, model, bindings: dict, *, lock=False):
        condition = model.id.in_([UUID(value) for value in bindings["message_ids"]]) if model is Message else model.entity_id == ENTITY_ID
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
        tables, affected = {}, []
        for model in REPORT_MODELS:
            table, total, changed = model.__tablename__, 0, 0
            async for row in self.rows(model, bindings):
                total += 1
                _, locations = transform_row(table, row)
                if locations:
                    changed += 1
                    affected.append({"table": table, "id": row["id"], "locations": locations})
            tables[table] = {"total": total, "affected": changed}
        return {"mode": "inventory", "entity_id": str(ENTITY_ID), "repair_id": REPAIR_ID,
                "tables": tables, "bindings": bindings, "affected": affected,
                "provider_calls": False, "database_committed": False}
