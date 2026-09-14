"""Read-only orphan-report coverage audit; never emits message contents."""
import argparse
import asyncio
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import sys

ENTITY_ID = "70eec83d-a767-4c99-8f28-0a068bfcc8a8"
REPORT_KIND = "brand_association_circle"
SECTION_IDS = frozenset({"core_verdict", "ai_archive", "value_pillars", "living_young_autonomy"})
SECTION_TITLES = frozenset({
    "四个价值支柱，在 AI 叙事里是什么状态", "活得年轻：掌控生活的自主",
})
TARGET_HEADING = re.compile(
    r"^ {0,3}#{2,3}[ \t]+(?:" + "|".join(re.escape(title) for title in SECTION_TITLES) + r")[ \t]*#*[ \t]*\r?$",
    re.MULTILINE,
)


def load_runner():
    path = Path(__file__).resolve().with_name("repair-amway-report-outline.py")
    spec = importlib.util.spec_from_file_location("outline_coverage_runner", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def legacy_report_structure(payload):
    for key in ("report_narrative_sections", "narrative_sections", "report_sections", "sections"):
        sections = payload.get(key)
        if not isinstance(sections, list):
            continue
        for section in sections:
            if not isinstance(section, dict):
                continue
            if (isinstance(section.get("section_id"), str) and section["section_id"] in SECTION_IDS
                    or isinstance(section.get("title"), str) and section["title"] in SECTION_TITLES):
                return True
            if section.get("section_name") == "narrative":
                if isinstance(section.get("markdown"), str) and TARGET_HEADING.search(section["markdown"]):
                    return True
                data = section.get("data")
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    if legacy_report_structure({"report_narrative_sections": data["items"]}):
                        return True
    return any(isinstance(payload.get(key), str) and TARGET_HEADING.search(payload[key])
               for key in ("report_markdown", "full_markdown", "markdown_body"))


def classify_payload(value, session_entity_id, output_type="report"):
    """Return target/other/ambiguous without guessing from a brand-name string."""
    try:
        payload = json.loads(value or "null")
    except (ValueError, TypeError):
        if output_type and output_type != "report":
            return "other", "non_report_output", None
        reason = "invalid_target_payload" if session_entity_id == ENTITY_ID else "invalid_unowned_payload"
        return ("ambiguous", reason, None) if session_entity_id in (None, ENTITY_ID) else ("other", "foreign_session", None)
    if not isinstance(payload, dict):
        if output_type and output_type != "report":
            return "other", "non_report_output", None
        return ("ambiguous", "non_object_report_payload", None) if session_entity_id in (None, ENTITY_ID) else ("other", "foreign_session", None)
    containers = [payload]
    if isinstance(payload.get("report_data"), dict):
        containers.append(payload["report_data"])
    identities = {str(item["entity_id"]) for item in containers if item.get("entity_id")}
    kinds = {str(item[key]) for item in containers for key in ("report_kind", "artifact_kind", "kind") if item.get(key)}
    structure = any(legacy_report_structure(item) for item in containers)
    structure = structure or any(
        isinstance(item.get("dashboard_projection"), dict)
        and isinstance(item["dashboard_projection"].get("association_circle_projection"), dict)
        for item in containers
    )
    if REPORT_KIND not in kinds and not structure:
        if not kinds and output_type == "report" and (session_entity_id == ENTITY_ID or ENTITY_ID in identities):
            return "ambiguous", "unclassified_target_report_payload", payload
        return "other", "other_report_kind", payload
    if ENTITY_ID in identities:
        if identities != {ENTITY_ID} or session_entity_id not in (None, ENTITY_ID):
            return "ambiguous", "conflicting_entity_identity", payload
        return "target", "payload_entity", payload
    if session_entity_id == ENTITY_ID:
        if identities:
            return "ambiguous", "conflicting_entity_identity", payload
        return "target", "session_entity", payload
    if not identities and session_entity_id is None:
        return "ambiguous", "association_report_without_entity_binding", payload
    return "other", "foreign_entity", payload


async def inspect_messages(db, service):
    from sqlalchemy import or_, select
    from uuid import UUID
    from app.models.brand_intelligence import BrandReportVersion
    from app.models.message import Message, MessageType
    from app.models.session import Session

    bound_ids = {str(value) for value in (await db.scalars(select(BrandReportVersion.message_id).where(
        BrandReportVersion.entity_id == UUID(ENTITY_ID), BrandReportVersion.message_id.is_not(None),
    ))).all()}
    query = select(
        Message.id, Message.output_data, Message.session_id, Message.output_type,
        Session.entity_id.label("session_entity_id"),
    ).outerjoin(Session, Session.id == Message.session_id).where(or_(
        Message.type == MessageType.OUTPUT, Message.output_type == "report",
    )).order_by(Message.id).execution_options(yield_per=1)
    counts, reasons, seen_bound = Counter(), Counter(), set()
    orphans, ambiguous = [], []
    stream = await db.stream(query)
    try:
        async for row in stream.mappings():
            counts["scanned_output_or_report_messages"] += 1
            row_id = str(row["id"])
            if row_id in bound_ids:
                seen_bound.add(row_id)
            session_entity = str(row["session_entity_id"]) if row["session_entity_id"] else None
            classification, reason, payload = classify_payload(row["output_data"], session_entity, row["output_type"])
            counts[classification] += 1
            if classification == "other":
                continue
            reasons[reason] += 1
            _, locations = service.trim_report(payload, "messages.output_data") if payload is not None else (None, [])
            summary = {"id": row_id, "session_id": str(row["session_id"]),
                       "bound_to_version": row_id in bound_ids, "reason": reason,
                       "affected_locations": locations}
            if classification == "ambiguous":
                ambiguous.append(summary)
            elif row_id not in bound_ids:
                orphans.append(summary)
            else:
                counts["target_bound_messages"] += 1
            del payload
    finally:
        await stream.close()
    return {"mode": "message-inventory", "entity_id": ENTITY_ID,
            "counts": dict(counts), "identity_reasons": dict(reasons),
            "version_bound_message_count": len(bound_ids),
            "bound_messages_not_in_output_scan": sorted(bound_ids - seen_bound),
            "orphan_count": len(orphans), "orphan_messages": orphans,
            "ambiguous_count": len(ambiguous), "ambiguous_messages": ambiguous,
            "provider_calls": False, "database_committed": False}


async def run(args, runner):
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal, engine

    service = runner.service_module()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            await db.execute(text("SET LOCAL statement_timeout = '90s'"))
            result = await inspect_messages(db, service)
            await db.rollback()
            runner.check_release(args.expected_release)
            return result | {"release_sha": args.expected_release}
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("message-inventory",), required=True)
    parser.add_argument("--expected-release", required=True)
    parser.add_argument("--repair-id", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--expected-manifest-hash")
    args = parser.parse_args()
    try:
        runner = load_runner()
        runner.configure(args)

        async def bounded():
            return await asyncio.wait_for(run(args, runner), timeout=780)

        print(json.dumps(asyncio.run(bounded()), ensure_ascii=True), flush=True)
    except Exception as exc:
        detail = str(exc) if type(exc) is ValueError else ""
        code = detail if re.fullmatch(r"[a-z0-9_:.-]{1,180}", detail) else None
        print(json.dumps({"failed": True, "failure_type": type(exc).__name__, "failure_code": code}), flush=True)
        raise SystemExit(1)
