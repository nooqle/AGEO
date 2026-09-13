"""Read-only seven-day inventory for the authorized Amway report repair."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


async def inventory(helper):
    from sqlalchemy import select, text, func
    from app.core.database import AsyncSessionLocal, engine
    from app.models.amway_circle_tracking import AmwayCircleRun, AmwayCircleReport, AmwayCircleProjection, AmwayCircleExport
    from app.models.brand_intelligence import BrandReportVersion, BrandMetricSnapshot, BrandIntelligenceFinding, BrandMention
    from app.models.message import Message
    from app.models.brand_intelligence_run import BrandIntelligenceRun
    from app.models.snapshot import AnalysisSnapshot
    from app.models.task import AnalysisTask
    from app.services.amway_entity_lexicon_service import AmwayEntityLexiconService
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            await db.execute(text("SET LOCAL statement_timeout = '45s'"))
            if await db.scalar(text("SHOW transaction_read_only")) != "on":
                raise ValueError("not_read_only")
            runs = list((await db.scalars(select(AmwayCircleRun).where(
                AmwayCircleRun.entity_id == helper.ENTITY_ID,
                func.coalesce(AmwayCircleRun.completed_at, AmwayCircleRun.created_at) >= start,
                func.coalesce(AmwayCircleRun.completed_at, AmwayCircleRun.created_at) <= end,
            ).order_by(AmwayCircleRun.created_at))).all())
            reports = list((await db.scalars(select(AmwayCircleReport).where(
                AmwayCircleReport.entity_id == helper.ENTITY_ID,
                AmwayCircleReport.created_at >= start, AmwayCircleReport.created_at <= end,
            ))).all())
            old_run_count = await db.scalar(select(func.count()).select_from(AmwayCircleRun).where(
                AmwayCircleRun.entity_id == helper.ENTITY_ID,
                func.coalesce(AmwayCircleRun.completed_at, AmwayCircleRun.created_at) < start,
            ))
            result = {"entity_id": str(helper.ENTITY_ID), "start_utc": start.isoformat(), "end_utc": end.isoformat(),
                      "runs": [], "reports": [], "old_run_count": old_run_count,
                      "current_lexicon": (await AmwayEntityLexiconService(db).registry_for_entity(helper.ENTITY_ID)).snapshot()}
            for run in runs:
                brand = await db.get(BrandIntelligenceRun, run.brand_intelligence_run_id) if run.brand_intelligence_run_id else None
                task = await db.get(AnalysisTask, run.analysis_task_id) if run.analysis_task_id else None
                snapshot_id = (brand.output_refs or {}).get("snapshot_id") if brand else None
                snapshot_id = snapshot_id or (task.snapshot_id if task else None)
                from uuid import UUID
                snapshot = await db.get(AnalysisSnapshot, UUID(str(snapshot_id))) if snapshot_id else None
                if snapshot and snapshot.entity_id != helper.ENTITY_ID:
                    raise ValueError("snapshot_entity_mismatch")
                raw = (snapshot.raw_data or {}) if snapshot else {}
                answers = raw.get("fetch_results") or []
                projections = list((await db.scalars(select(AmwayCircleProjection).where(AmwayCircleProjection.circle_run_id == run.id))).all())
                row = {"run_id": str(run.id), "brand_run_id": str(run.brand_intelligence_run_id),
                       "task_id": str(run.analysis_task_id), "snapshot_id": str(snapshot_id),
                       "status": run.status, "center_term": run.center_term,
                       "completed_at": str(run.completed_at), "created_at": str(run.created_at),
                       "question_count": run.question_count, "valid_answer_count": run.valid_answer_count,
                       "failed_answer_count": run.failed_answer_count, "include_in_cumulative": run.include_in_cumulative,
                       "lexicon_hash": run.lexicon_hash, "answer_hash": digest(answers),
                       "snapshot_keys": sorted(raw), "report_keys": sorted(raw.get("report_data") or {}),
                       "output_refs": helper.redact_export(brand.output_refs or {}) if brand else {},
                       "snapshot_created_at": str(snapshot.created_at) if snapshot else None,
                       "answers": helper.safe_answers(answers),
                       "projections": [{"id": str(p.id), "scope": p.projection_scope,
                                        "node_count": len((p.association_circle_projection or {}).get("nodes") or [])} for p in projections]}
                result["runs"].append(row)
            for report in reports:
                projection = await db.get(AmwayCircleProjection, report.projection_id)
                item = {key: getattr(report, key) for key in (
                    "id", "projection_id", "circle_run_id", "report_scope", "title", "status", "created_at", "updated_at")}
                item["projection_metadata"] = {key: getattr(projection, key, None) for key in ("sample_scope", "compare_summary", "source_run_ids")} if projection else None
                result["reports"].append(item)
            result["brand_report_versions"] = [{key: getattr(report, key) for key in (
                "id", "session_id", "message_id", "report_id", "version", "report_kind", "artifact_id", "created_at", "updated_at")}
                for report in (await db.scalars(select(BrandReportVersion).where(
                    BrandReportVersion.entity_id == helper.ENTITY_ID, BrandReportVersion.created_at >= start,
                    BrandReportVersion.created_at <= end))).all()]
            result["exports"] = [{key: getattr(export, key) for key in (
                "id", "projection_id", "report_id", "circle_run_id", "export_type", "export_scope", "created_at")}
                for export in (await db.scalars(select(AmwayCircleExport).where(
                    AmwayCircleExport.entity_id == helper.ENTITY_ID, AmwayCircleExport.created_at >= start,
                    AmwayCircleExport.created_at <= end))).all()]
            result["consumer_counts"] = []
            for version in result["brand_report_versions"]:
                row = await db.get(BrandReportVersion, version["id"])
                message = await db.get(Message, row.message_id) if row.message_id else None
                output = json.loads(message.output_data or "{}") if message else {}
                counts = {model.__tablename__: await db.scalar(select(func.count()).select_from(model).where(model.report_version_id == row.id))
                          for model in (BrandMetricSnapshot, BrandIntelligenceFinding, BrandMention)}
                result["consumer_counts"].append({"version_id": str(row.id), "counts": counts,
                    "payload_keys": sorted(row.payload or {}), "output_keys": sorted(output),
                    "payload_report_id": (row.payload or {}).get("report_id"), "output_report_id": output.get("report_id")})
            await db.rollback()
            return helper.redact_export(result)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-release", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("replay_helper", Path(__file__).with_name("replay-topic-nodes.py"))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    try:
        output = helper.configure(args.expected_release, args.output_dir)
        async def bounded():
            return await asyncio.wait_for(inventory(helper), timeout=180)
        result = asyncio.run(bounded())
        result["release_sha"] = args.expected_release
        if Path("/srv/ageo-deploy/current/.release-sha").read_text().strip() != args.expected_release:
            raise ValueError("release_changed")
        destination = output / "inventory.json"
        with os.fdopen(os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, default=str)
        owner = output.stat()
        os.chown(destination, owner.st_uid, owner.st_gid)
        print(json.dumps({"run_count": len(result["runs"]), "report_count": len(result["reports"]),
                          "start_utc": result["start_utc"], "end_utc": result["end_utc"],
                          "old_run_count": result["old_run_count"], "database_writes": False}))
    except Exception as exc:
        print(json.dumps({"failed": True, "failure_type": type(exc).__name__}))
        raise SystemExit(1)
