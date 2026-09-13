"""Explicit, reversible historical repair; never called by normal report writes.

Dry-run executes the complete write path inside a transaction which the caller
must roll back. Its exact row images form the reviewed plan. Apply replays those
images, checks source drift and never invokes collection or an LLM.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import gc
from typing import Any
from uuid import UUID

from sqlalchemy import delete, inspect, or_, select, update
from types import SimpleNamespace
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.amway_circle_tracking import (
    AmwayCircleAnswer, AmwayCircleEdgeSnapshot, AmwayCircleEntityMention,
    AmwayCircleEvidence, AmwayCircleExport, AmwayCircleNodeSnapshot,
    AmwayCircleProjection, AmwayCircleReport, AmwayCircleRun,
)
from app.models.brand_intelligence import (
    BrandIntelligenceFinding, BrandMention, BrandMetricSnapshot, BrandReportVersion,
)
from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.message import Message
from app.models.snapshot import AnalysisSnapshot
from app.models.task import AnalysisTask
from app.models.entity import Entity
from app.models.amway_entity_lexicon import AmwayEntityLexiconOverride
from app.services import amway_circle_tracking_service as tracking
from app.services.amway_entity_calibration_service import AmwayEntityCalibrationService
from app.services.amway_entity_extraction_service import AmwayEntityExtractionService
from app.services.amway_entity_lexicon_service import AmwayEntityLexiconService, _row_from_base_entity
from app.services.brand_intelligence_projection_service import BrandIntelligenceProjectionService
from app.workflow.a5.association_circle import build_brand_association_circle_report_artifact

ENTITY_ID = UUID("70eec83d-a767-4c99-8f28-0a068bfcc8a8")
SCHEMA_VERSION = "2026-09-13-topic-repair-v1"
CHILD_MODELS = (
    AmwayCircleEvidence, AmwayCircleEntityMention,
    AmwayCircleEdgeSnapshot, AmwayCircleNodeSnapshot,
)
MODELS = (
    AmwayCircleRun, AmwayCircleAnswer, *CHILD_MODELS,
    AmwayCircleProjection, AmwayCircleReport, AnalysisSnapshot,
    BrandReportVersion, Message, BrandMetricSnapshot,
    BrandIntelligenceFinding, BrandMention, AmwayEntityLexiconOverride, AmwayCircleExport,
)
MODEL_BY_TABLE = {model.__tablename__: model for model in MODELS}


def json_value(value: Any) -> Any:
    if isinstance(value, (UUID, datetime)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    return value


def digest(value: Any) -> str:
    checksum = hashlib.sha256()
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=json_value)
    for chunk in encoder.iterencode(value):
        checksum.update(chunk.encode())
    return checksum.hexdigest()


def row_image(row: Any) -> dict[str, Any]:
    # JSONText columns are already JSON primitives. Keep immutable references to
    # their old values; all writes below replace whole values, never mutate them.
    result = {}
    for column in inspect(type(row)).columns:
        value = getattr(row, column.key)
        result[column.key] = json_value(value) if isinstance(value, (UUID, datetime, Enum)) else value
    return result


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _set(row: Any, values: dict[str, Any]) -> None:
    # Historical sorting is based on these dates; a repair is not a new report.
    updated_at = getattr(row, "updated_at", None)
    for key, value in values.items():
        setattr(row, key, deepcopy(value))
    if updated_at is not None:
        row.updated_at = updated_at
        flag_modified(row, "updated_at")


def _preserve_identity(artifact: dict, old: dict, repair: dict) -> dict:
    result = deepcopy(artifact)
    for key in ("id", "report_id", "artifact_id", "artifact_key", "session_id",
                "entity_id", "created_at", "updated_at"):
        if key in old:
            result[key] = deepcopy(old[key])
    result["topic_repair"] = deepcopy(repair)
    return result


def _projection(artifact: dict) -> dict:
    return deepcopy(artifact["dashboard_projection"]["association_circle_projection"])


class AmwayTopicRepairService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.tracking = tracking.AmwayCircleTrackingService(db)

    async def _rows(self, model, *conditions, lock=False):
        query = select(model).where(*conditions)
        if lock:
            query = query.with_for_update()
        return list((await self.db.scalars(query)).all())

    async def capture(self, *, lock=False) -> dict[str, dict[str, dict]]:
        """Capture all entity-owned report surfaces, including protected old rows."""
        runs = await self._rows(AmwayCircleRun, AmwayCircleRun.entity_id == ENTITY_ID)
        run_ids = [row.id for row in runs]
        versions = await self._rows(BrandReportVersion, BrandReportVersion.entity_id == ENTITY_ID)
        result = {}
        for model in MODELS:
            if model is Message:
                condition = Message.id.in_([row.message_id for row in versions if row.message_id])
            elif model in (AmwayCircleEvidence, AmwayCircleEdgeSnapshot):
                condition = model.circle_run_id.in_(run_ids)
            else:
                condition = model.entity_id == ENTITY_ID
            rows = await self._rows(model, condition, lock=lock)
            result[model.__tablename__] = {str(row.id): row_image(row) for row in rows}
        return result

    async def _source(self, run: AmwayCircleRun) -> tuple[Any, Any, dict]:
        brand = await self.db.get(BrandIntelligenceRun, run.brand_intelligence_run_id)
        task = await self.db.get(AnalysisTask, run.analysis_task_id) if run.analysis_task_id else None
        snapshot_id = (brand.output_refs or {}).get("snapshot_id") if brand else None
        snapshot_id = snapshot_id or (task.snapshot_id if task else None)
        snapshot = await self.db.get(AnalysisSnapshot, UUID(str(snapshot_id))) if snapshot_id else None
        if not snapshot or snapshot.entity_id != ENTITY_ID:
            raise ValueError(f"missing_scoped_snapshot:{run.id}")
        raw = deepcopy(snapshot.raw_data or {})
        if not isinstance(raw.get("fetch_results"), list) or not raw["fetch_results"]:
            raise ValueError(f"missing_original_answers:{run.id}")
        stored = await self._rows(AmwayCircleAnswer, AmwayCircleAnswer.circle_run_id == run.id)
        stored_hashes = {(row.question_id, row.platform): row.answer_hash for row in stored}
        expected = tracking._answer_records(fetch_results=raw["fetch_results"], source_appendix=[], center_terms=run.center_terms)
        for answer in expected:
            key = (answer["question_id"], answer["platform"])
            if key not in stored_hashes or stored_hashes[key] != answer["answer_hash"]:
                raise ValueError(f"snapshot_answer_binding_mismatch:{run.id}")
        return brand, snapshot, raw

    async def _stage_lexicon(self, package):
        service = AmwayEntityLexiconService(self.db)
        current = await service.registry_for_entity(ENTITY_ID)
        if current.effective_hash != package["expected_lexicon_hash"]:
            raise ValueError("source_lexicon_drifted")
        entity = await self.db.get(Entity, ENTITY_ID)
        entries = {entry.entity_id: entry for entry in current.entities}
        for patch in package["updates"]:
            entry_id = patch["entity_id"]
            if entry_id not in {"strategy_active_health", "touchpoint_sports_area", "touchpoint_national_experience_centers"}:
                raise ValueError("unapproved_lexicon_patch")
            row = await service._override_for_entry(ENTITY_ID, entry_id)
            if row is None:
                row = _row_from_base_entity(entity=entity, base=entries[entry_id], current_user_id=None)
                self.db.add(row)
            if "review_status" in patch:
                row.review_status = patch["review_status"]
            if "aliases" in patch:
                row.aliases = patch["aliases"]
            if "match_exclusions" in patch:
                semantic = deepcopy(row.semantic_definition or {})
                semantic["match_exclusions"] = patch["match_exclusions"]
                row.semantic_definition = semantic
        await self.db.flush()
        target = await service.registry_for_entity(ENTITY_ID)
        if target.effective_hash != package["expected_target_lexicon_hash"]:
            raise ValueError("target_lexicon_hash_mismatch")
        return target

    async def _compute(self, run, registry, repair):
        brand, snapshot, raw = await self._source(run)
        fetch = raw["fetch_results"]
        extraction = AmwayEntityExtractionService(registry).extract_from_fetch_results(fetch)
        calibration = AmwayEntityCalibrationService(registry).calibrate(
            fetch_results=fetch, extraction_result=extraction, center_terms=run.center_terms)
        old = raw.get("report_data") or {}
        artifact = build_brand_association_circle_report_artifact(
            session_id=str(snapshot.session_id), entity_id=str(ENTITY_ID),
            brand_profile=raw.get("brand_profile") or {"brand_name": run.center_term},
            fetch_results=fetch, simulated_questions=old.get("question_bank"),
            center_terms=run.center_terms, entity_calibration_result=calibration)
        artifact = _preserve_identity(artifact, old, repair)
        body = _projection(artifact)
        body.update(effective_lexicon_hash=registry.effective_hash,
                    extraction_version=extraction["schema_version"], topic_repair=repair)
        artifact["dashboard_projection"]["association_circle_projection"] = body
        # Use one calibrated coverage payload on every run consumer surface.
        if calibration.get("topic_coverage"):
            body["topic_coverage"] = calibration["topic_coverage"]
            artifact.setdefault("report_input", {})["topic_coverage"] = calibration["topic_coverage"]
        if int(calibration["sample_scope"]["valid_answer_count"]) != run.valid_answer_count:
            raise ValueError(f"answer_count_changed:{run.id}")
        return {"run": run, "brand": brand, "snapshot": snapshot, "raw": raw,
                "extraction": extraction, "calibration": calibration,
                "artifact": artifact, "body": body,
                "original_node_hash": digest(_projection(old).get("nodes") or [])}

    def _replace_projection(self, row, artifact, body, sample_scope=None):
        old_report_id = (row.association_circle_projection or {}).get("report_id")
        if old_report_id:
            body = {**body, "report_id": old_report_id}
        _set(row, {"association_circle_projection": body,
                   "sample_scope": sample_scope or artifact.get("sample_scope") or body.get("sample_scope") or {},
                   "report_input": artifact.get("report_input") or {},
                   "data_quality": artifact.get("report_quality_checks") or {},
                   "projection_version": artifact.get("schema_version") or row.projection_version})

    def _replace_report(self, report, artifact, source_hash):
        artifact = _preserve_identity(artifact, report.structured_body or {}, artifact["topic_repair"])
        quality = artifact.get("report_quality_checks") or {}
        _set(report, {"structured_body": artifact,
                      "markdown_body": artifact.get("report_markdown") or artifact.get("full_markdown") or "",
                      "source_report_input": artifact.get("report_input") or {},
                      "source_projection_hash": source_hash,
                      "status": "ready" if quality.get("passed") is True else "quality_failed"})

    async def _stage_run(self, computed, versions, repair):
        run, snapshot = computed["run"], computed["snapshot"]
        artifact, body = computed["artifact"], computed["body"]
        extraction, calibration = computed["extraction"], computed["calibration"]
        answers = await self._rows(AmwayCircleAnswer, AmwayCircleAnswer.circle_run_id == run.id)
        answer_rows = {(row.question_id, row.platform): row for row in answers}
        evidence = tracking._evidence_records(artifact, body)
        if any((item["question_id"], item["platform"]) not in answer_rows for item in evidence):
            raise ValueError(f"evidence_would_create_answer:{run.id}")
        for model in CHILD_MODELS:
            await self.db.execute(delete(model).where(model.circle_run_id == run.id))
        mentions = await self.tracking._persist_mentions(run, answer_rows, extraction)
        await self.tracking._persist_evidence(run, answer_rows, mentions, evidence)
        await self.tracking._persist_node_edge_snapshots(run, body)
        _set(run, {"lexicon_hash": extraction["effective_lexicon_hash"],
                   "lexicon_version": extraction.get("ontology_version") or run.lexicon_version,
                   "extraction_version": extraction["schema_version"],
                   "calibration_version": calibration["schema_version"]})
        raw = computed["raw"]
        raw.update(entity_extraction_result=extraction, entity_calibration_result=calibration,
                   report_data=artifact, topic_repair=repair)
        for key in ("dashboard_projection", "metric_bundle", "comparison_bundle", "sections"):
            raw[key] = deepcopy(artifact.get(key, {} if key != "sections" else []))
        _set(snapshot, {"raw_data": raw})
        projections = await self._rows(AmwayCircleProjection,
                                      AmwayCircleProjection.circle_run_id == run.id,
                                      AmwayCircleProjection.projection_scope == "run")
        if not projections:
            raise ValueError(f"missing_run_projection:{run.id}")
        for projection in projections:
            self._replace_projection(projection, artifact, body)
            reports = await self._rows(AmwayCircleReport, AmwayCircleReport.projection_id == projection.id)
            for report in reports:
                self._replace_report(report, artifact, projection.source_run_hash)
        candidates = [v for v in versions if v.session_id == snapshot.session_id
                      and (not artifact.get("report_id") or v.report_id == artifact["report_id"])]
        if len(candidates) != 1:
            raise ValueError(f"ambiguous_brand_report_binding:{run.id}:{len(candidates)}")
        # raw has just been staged; recover the original snapshot artifact from
        # its persisted version for binding by identity and original sample scope.
        version = candidates[0]
        if version.report_id != f"{snapshot.session_id}_report_brand_association_circle" or version.report_kind != "brand_association_circle":
            raise ValueError("brand_report_identity_mismatch")
        if (version.payload or {}).get("session_id") != str(snapshot.session_id):
            raise ValueError("brand_report_session_mismatch")
        if digest(_projection(version.payload or {}).get("nodes") or []) != computed["original_node_hash"]:
            raise ValueError("brand_report_snapshot_nodes_mismatch")
        if int(((version.payload or {}).get("sample_scope") or {}).get("valid_answer_count", -1)) != run.valid_answer_count:
            raise ValueError("brand_report_answer_scope_mismatch")
        await self._stage_brand_report(candidates[0], artifact, repair)

    async def _stage_brand_report(self, version, artifact, repair):
        message = await self.db.get(Message, version.message_id)
        if message is None or message.session_id != version.session_id:
            raise ValueError("missing_exact_report_message")
        output = json.loads(message.output_data or "{}")
        if output.get("report_id") and output["report_id"] != version.report_id:
            raise ValueError("message_report_identity_mismatch")
        if output.get("session_id") != str(version.session_id):
            raise ValueError("message_session_identity_mismatch")
        if output.get("entity_id") != str(ENTITY_ID) or output.get("report_kind") != "brand_association_circle":
            raise ValueError("message_entity_kind_mismatch")
        if digest(_projection(output)) != digest(_projection(version.payload or {})):
            raise ValueError("message_projection_binding_mismatch")
        artifact = _preserve_identity(artifact, version.payload or {}, repair)
        _set(version, {"payload": artifact,
                       "summary": BrandIntelligenceProjectionService._report_summary(artifact)})
        _set(message, {"output_data": json.dumps(_preserve_identity(artifact, output, repair), ensure_ascii=False)})
        metrics = BrandIntelligenceProjectionService._extract_metric_payload(artifact)
        for metric in await self._rows(BrandMetricSnapshot, BrandMetricSnapshot.report_version_id == version.id):
            number = BrandIntelligenceProjectionService._number_or_none
            total = number(metrics.get("total_questions"))
            _set(metric, {"metric_payload": metrics, "bwvs_index": number(metrics.get("bwvs_index")),
                          "mention_rate": number(metrics.get("mention_rate")),
                          "total_questions": int(total) if total is not None else None})
        findings = await self._rows(BrandIntelligenceFinding, BrandIntelligenceFinding.report_version_id == version.id)
        projections = BrandIntelligenceProjectionService.normalize_report_findings(
            payload=artifact, report_id=version.report_id, report_version=version.version)
        if findings:
            if len(findings) != 1 or len(projections) != 1 or findings[0].finding_type != "summary" or projections[0].finding_type != "summary":
                raise ValueError(f"ambiguous_report_finding_binding:{version.id}")
            finding, normalized = findings[0], projections[0]
            # The finding key and its graph links are persistent identities.
            # Preserve them while replacing the derived judgment and evidence.
            _set(finding, {key: getattr(normalized, key) for key in (
                "title", "summary", "finding_type", "severity", "confidence", "evidence_summary",
                "suggested_action_type", "suggested_action_payload", "source_payload")})
        if await self._rows(BrandMention, BrandMention.report_version_id == version.id):
            raise ValueError(f"unhandled_report_mentions:{version.id}")

    async def _stage_period(self, report, computed, repair):
        projection = await self.db.get(AmwayCircleProjection, report.projection_id)
        current = deepcopy(projection.sample_scope or {})
        previous = deepcopy((projection.compare_summary or {}).get("previous_period"))
        current_ids = current.get("run_ids") or []
        previous_ids = (previous or {}).get("run_ids") or []
        if not current_ids:
            raise ValueError("period_missing_fixed_run_ids")
        # Sources outside the repair window are read/recomputed in memory only.
        async def proxies(ids):
            persisted = await self.tracking._run_projections(ENTITY_ID, [UUID(r) for r in ids])
            by_id = {str(row.circle_run_id): row for row in persisted}
            if set(by_id) != set(ids):
                raise ValueError("missing_period_source_projection")
            result = []
            for run_id in ids:
                row = by_id[run_id]
                if (row.association_circle_projection or {}).get("topic_repair", {}).get("repair_id") == repair["repair_id"]:
                    result.append(row)
                else:
                    result.append(AmwayCircleProjection(circle_run_id=UUID(run_id),
                        source_run_hash=row.source_run_hash,
                        projection_version=computed[run_id]["artifact"].get("schema_version") or row.projection_version,
                        association_circle_projection=deepcopy(computed[run_id]["body"])))
            return result
        currents, previouses = await proxies(current_ids), await proxies(previous_ids)
        body = tracking._aggregate_projection(currents, current)
        prior = tracking._aggregate_projection(previouses, previous)
        current = body.get("sample_scope") or current
        if prior:
            previous = prior.get("sample_scope") or previous
        changes = tracking._change_top5(body, prior) if tracking._should_compare_period(currents, prior, body) else []
        current_runs = [computed[r]["run"] for r in current_ids]
        previous_runs = [computed[r]["run"] for r in previous_ids]
        changed = bool(previous_runs) and tracking._question_signatures(current_runs) != tracking._question_signatures(previous_runs)
        def analyzed_versions(ids):
            return [SimpleNamespace(extraction_version=computed[r]["extraction"]["schema_version"],
                                    lexicon_hash=computed[r]["extraction"]["effective_lexicon_hash"]) for r in ids]
        notice = tracking._comparison_notice(analyzed_versions(current_ids), analyzed_versions(previous_ids), changed)
        tracking._attach_period_tracking(body, current, previous, changes, changed, notice)
        artifact = tracking._build_period_report_artifact(tracking._projection_bodies(currents),
                    body, current, body.get("tracking_projection") or {}, entity_id=ENTITY_ID)
        artifact = _preserve_identity(artifact, report.structured_body or {}, repair)
        generated = tracking._period_projection_from_artifact(artifact, body, current,
                                                             body.get("tracking_projection") or {})
        # Reuse the production aggregate coverage contract, never latest-run counts.
        generated["topic_repair"] = repair
        tracking._finalize_period_projection_quality(generated)
        tracking._synchronize_report_artifact(artifact, generated)
        source_hash = tracking._period_view_source_hash(period_type=current["period_type"],
            current_summary=current, previous_summary=previous, current_projections=currents,
            previous_projections=previouses, center_term=computed[current_ids[0]]["run"].center_term)
        self._replace_projection(projection, artifact, generated, current)
        _set(projection, {"source_run_hash": source_hash,
                          "compare_summary": {"previous_period": previous, "change_top5": changes},
                          "report_input": tracking._period_report_input(current, previous, changes, changed, notice, generated)})
        self._replace_report(report, artifact, source_hash)

    async def stage(self, inventory: dict, package: dict) -> dict:
        """Stage the full repair; caller MUST rollback after extracting the plan."""
        if UUID(inventory["entity_id"]) != ENTITY_ID:
            raise ValueError("wrong_entity")
        for key in ("entity_id", "start_utc", "end_utc"):
            if inventory[key] != package[key]:
                raise ValueError(f"package_inventory_mismatch:{key}")
        repair_id = package["repair_id"]
        start, end = (datetime.fromisoformat(inventory[k]) for k in ("start_utc", "end_utc"))
        if end - start != timedelta(days=7):
            raise ValueError("repair_window_must_be_seven_days")
        await self.tracking._lock_entity(ENTITY_ID)
        before = await self.capture(lock=True)
        registry = await self._stage_lexicon(package)
        run_ids = {r["run_id"] for r in inventory["runs"]}
        report_ids = {r["id"] for r in inventory["reports"]}
        version_ids = {r["id"] for r in inventory["brand_report_versions"]}
        actual_runs = {key for key, r in before[AmwayCircleRun.__tablename__].items()
                       if start <= _utc(datetime.fromisoformat(r["completed_at"] or r["created_at"])) <= end}
        actual_reports = {key for key, r in before[AmwayCircleReport.__tablename__].items()
                          if start <= _utc(datetime.fromisoformat(r["created_at"])) <= end}
        if actual_runs != run_ids or actual_reports != report_ids:
            raise ValueError("inventory_target_drift")
        if len(run_ids) != package["expected_run_count"] or len(report_ids) != package["expected_report_count"]:
            raise ValueError("package_count_mismatch")
        target_projection_ids = {row["projection_id"] for row in inventory["reports"]}
        target_projection_ids.update(key for key, value in before[AmwayCircleProjection.__tablename__].items()
                                     if value.get("circle_run_id") in run_ids)
        if await self._rows(AmwayCircleExport, AmwayCircleExport.entity_id == ENTITY_ID,
            or_((AmwayCircleExport.created_at >= start) & (AmwayCircleExport.created_at <= end),
                AmwayCircleExport.circle_run_id.in_([UUID(r) for r in run_ids]),
                AmwayCircleExport.report_id.in_([UUID(r) for r in report_ids]),
                AmwayCircleExport.projection_id.in_([UUID(p) for p in target_projection_ids]))):
            raise ValueError("export_requires_explicit_file_repair")
        reports = await self._rows(AmwayCircleReport, AmwayCircleReport.id.in_([UUID(r) for r in report_ids]))
        versions = await self._rows(BrandReportVersion, BrandReportVersion.id.in_([UUID(v) for v in version_ids]))
        source_ids = set(run_ids)
        for report in reports:
            projection = await self.db.get(AmwayCircleProjection, report.projection_id)
            source_ids.update(projection.source_run_ids or [])
        repair = {"repair_id": repair_id, "schema_version": SCHEMA_VERSION,
                  "start_utc": start.isoformat(), "end_utc": end.isoformat(),
                  "target_lexicon_hash": registry.effective_hash}
        computed = {}
        for run_id in sorted(source_ids):
            run = await self.db.get(AmwayCircleRun, UUID(run_id))
            if not run or run.entity_id != ENTITY_ID or run.status not in ("completed", "partial"):
                raise ValueError(f"invalid_source_run:{run_id}")
            computed[run_id] = await self._compute(run, registry, repair)
        for run_id in sorted(run_ids):
            await self._stage_run(computed[run_id], versions, repair)
        for report in reports:
            if report.report_scope == "period_view":
                await self._stage_period(report, computed, repair)
        source_answer_hashes = {r: digest(computed[r]["raw"]["fetch_results"]) for r in source_ids}
        snapshot_ids = sorted(str(computed[r]["snapshot"].id) for r in run_ids)
        await self.db.flush()
        computed.clear()
        del reports, versions
        self.db.expire_all()
        gc.collect()
        after = await self.capture()
        changes = []
        for table, old_rows in before.items():
            for row_id in sorted(set(old_rows) | set(after[table])):
                old, new = old_rows.get(row_id), after[table].get(row_id)
                if old != new:
                    changes.append({"table": table, "id": row_id, "before": old, "after": new})
        manifest = {**repair, "entity_id": str(ENTITY_ID), "source_lexicon_hash": package["expected_lexicon_hash"],
                    "run_ids": sorted(run_ids), "report_ids": sorted(report_ids),
                    "version_ids": sorted(version_ids), "changes": changes,
                    "before_hash": digest(before), "after_hash": digest(after),
                    "counts": {"runs": len(run_ids), "reports": len(report_ids), "versions": len(version_ids)},
                    "source_answer_hashes": source_answer_hashes}
        manifest["allowed_ids"] = {
            AnalysisSnapshot.__tablename__: snapshot_ids,
            AmwayCircleProjection.__tablename__: sorted(key for key, value in before[AmwayCircleProjection.__tablename__].items()
                if value.get("circle_run_id") in run_ids or any(r["projection_id"] == key for r in inventory["reports"])),
            Message.__tablename__: sorted(v["message_id"] for v in inventory["brand_report_versions"]),
            BrandMetricSnapshot.__tablename__: sorted(key for key, value in before[BrandMetricSnapshot.__tablename__].items()
                if value.get("report_version_id") in version_ids),
            BrandIntelligenceFinding.__tablename__: sorted(key for key, value in before[BrandIntelligenceFinding.__tablename__].items()
                if value.get("report_version_id") in version_ids),
        }
        validate_manifest(manifest)
        changed_keys = {(change["table"], change["id"]) for change in changes}
        protected_before = {table: {row_id: value for row_id, value in rows.items() if (table, row_id) not in changed_keys}
                            for table, rows in before.items()}
        protected_after = {table: {row_id: value for row_id, value in rows.items() if (table, row_id) not in changed_keys}
                           for table, rows in after.items()}
        if digest(protected_before) != digest(protected_after):
            raise ValueError("protected_rows_changed")
        manifest["protected_rows_hash"] = digest(protected_before)
        manifest["manifest_hash"] = digest(manifest)
        return manifest


def validate_manifest(plan: dict) -> None:
    """Every mutation must belong to the exact authorized historical target."""
    run_ids, report_ids, version_ids = map(set, (plan["run_ids"], plan["report_ids"], plan["version_ids"]))
    start, end = (datetime.fromisoformat(plan[k]) for k in ("start_utc", "end_utc"))
    if UUID(plan["entity_id"]) != ENTITY_ID or end - start != timedelta(days=7):
        raise ValueError("invalid_repair_scope")
    if plan["counts"] != {"runs": len(run_ids), "reports": len(report_ids), "versions": len(version_ids)}:
        raise ValueError("manifest_counts_mismatch")
    column_allowlist = {
        AmwayCircleRun.__tablename__: {"lexicon_hash", "lexicon_version", "extraction_version", "calibration_version"},
        AnalysisSnapshot.__tablename__: {"raw_data"},
        Message.__tablename__: {"output_data"},
        BrandReportVersion.__tablename__: {"payload", "summary"},
        BrandMetricSnapshot.__tablename__: {"metric_payload", "bwvs_index", "mention_rate", "total_questions"},
        BrandIntelligenceFinding.__tablename__: {"title", "summary", "finding_type", "severity", "confidence", "evidence_summary",
                                                "suggested_action_type", "suggested_action_payload", "source_payload"},
        AmwayCircleReport.__tablename__: {"structured_body", "markdown_body", "source_report_input", "source_projection_hash", "status"},
        AmwayCircleProjection.__tablename__: {"association_circle_projection", "sample_scope", "report_input", "data_quality",
                                             "projection_version", "source_run_hash", "compare_summary"},
    }
    for change in plan["changes"]:
        table, old, new = change["table"], change["before"], change["after"]
        if table not in MODEL_BY_TABLE:
            raise ValueError("unapproved_table")
        row = old or new
        if str(row.get("id")) != change["id"]:
            raise ValueError("row_identity_mismatch")
        if row.get("entity_id") and row["entity_id"] != str(ENTITY_ID):
            raise ValueError("cross_entity_change")
        if table == AmwayEntityLexiconOverride.__tablename__:
            if row["lexicon_entity_id"] not in {"strategy_active_health", "touchpoint_sports_area", "touchpoint_national_experience_centers"}:
                raise ValueError("unapproved_lexicon_row")
            continue
        if table in {m.__tablename__ for m in CHILD_MODELS}:
            if row["circle_run_id"] not in run_ids:
                raise ValueError("outside_window_child_change")
            continue
        if old is None or new is None:
            raise ValueError("identity_rows_cannot_be_created_or_deleted")
        if table in plan.get("allowed_ids", {}) and change["id"] not in plan["allowed_ids"][table]:
            raise ValueError(f"outside_target_copy:{table}")
        if set(k for k in old if old[k] != new[k]) - column_allowlist.get(table, set()):
            raise ValueError(f"unapproved_column_change:{table}")
        for field in ("id", "entity_id", "created_at", "updated_at", "completed_at", "started_at",
                      "built_at", "captured_at", "run_sequence", "is_latest", "question_signature",
                      "source_run_ids", "source_run_count"):
            if old.get(field) != new.get(field):
                raise ValueError(f"protected_identity_changed:{table}:{field}")
        if table == AmwayCircleAnswer.__tablename__:
            raise ValueError("original_answer_changed")
        if table == AmwayCircleRun.__tablename__ and change["id"] not in run_ids:
            raise ValueError("outside_window_run_change")
        if table == AmwayCircleReport.__tablename__ and change["id"] not in report_ids:
            raise ValueError("outside_window_report_change")
        if table == BrandReportVersion.__tablename__ and change["id"] not in version_ids:
            raise ValueError("outside_window_version_change")
        if table == AnalysisSnapshot.__tablename__:
            if digest(old["raw_data"].get("fetch_results")) != digest(new["raw_data"].get("fetch_results")):
                raise ValueError("snapshot_original_answers_changed")
        if table == BrandMention.__tablename__:
            raise ValueError("unsupported_report_derivative_change")


def _typed_values(model, values):
    result = deepcopy(values)
    for column in inspect(model).columns:
        value = result.get(column.key)
        if value is None:
            continue
        try:
            kind = column.type.python_type
        except NotImplementedError:
            continue
        if kind is UUID:
            result[column.key] = UUID(value)
        elif kind is datetime:
            result[column.key] = datetime.fromisoformat(value)
        elif isinstance(kind, type) and issubclass(kind, Enum):
            result[column.key] = kind(value)
    return result


async def apply_manifest(db: AsyncSession, plan: dict, *, expected_hash: str, reverse=False) -> dict:
    """Caller owns transaction, secure backup, release check and commit."""
    supplied = plan.get("manifest_hash")
    if supplied != expected_hash or digest({k: v for k, v in plan.items() if k != "manifest_hash"}) != supplied:
        raise ValueError("manifest_hash_mismatch")
    validate_manifest(plan)
    service = AmwayTopicRepairService(db)
    await service.tracking._lock_entity(ENTITY_ID)
    current = await service.capture(lock=True)
    source_hash, target_hash = (plan["after_hash"], plan["before_hash"]) if reverse else (plan["before_hash"], plan["after_hash"])
    if digest(current) == target_hash:
        return {"status": "already_restored" if reverse else "already_applied", "repair_id": plan["repair_id"]}
    if digest(current) != source_hash:
        raise ValueError("source_rows_drifted")
    changes = [{**c, "before": c["after"], "after": c["before"]} for c in plan["changes"]] if reverse else plan["changes"]
    # Delete FK children first, then insert parents before referencing children.
    mutable_models = (*CHILD_MODELS, AmwayEntityLexiconOverride)
    for model in mutable_models:
        for change in changes:
            if change["table"] == model.__tablename__ and change["after"] is None:
                await db.execute(delete(model).where(model.id == UUID(change["id"])))
    for change in changes:
        if change["before"] is not None and change["after"] is not None:
            model = MODEL_BY_TABLE[change["table"]]
            await db.execute(update(model).where(model.id == UUID(change["id"])).values(**_typed_values(model, change["after"])))
    for model in reversed(mutable_models):
        for change in changes:
            if change["table"] == model.__tablename__ and change["before"] is None:
                await db.execute(model.__table__.insert().values(**_typed_values(model, change["after"])))
    await db.flush()
    db.expire_all()
    if digest(await service.capture()) != target_hash:
        raise ValueError("post_apply_verification_failed")
    registry = await AmwayEntityLexiconService(db).registry_for_entity(ENTITY_ID)
    expected_lexicon = plan["source_lexicon_hash"] if reverse else plan["target_lexicon_hash"]
    if registry.effective_hash != expected_lexicon:
        raise ValueError("post_apply_lexicon_hash_mismatch")
    return {"status": "restored" if reverse else "applied", "repair_id": plan["repair_id"],
            "counts": plan["counts"], "changed_rows": len(changes)}
