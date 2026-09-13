"""Replay one official Amway view from persisted answers; no writes or providers."""

import argparse
import asyncio
from collections import Counter
import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import UUID

ENTITY_ID = UUID("70eec83d-a767-4c99-8f28-0a068bfcc8a8")
CENTER = "\u5b89\u5229"
SECRET_VALUES = ()
CONTEXT_KEYS = (
    "audience_segment", "core_anxiety", "life_scene", "opportunity_point",
    "probe_type", "mother_theme", "question_type", "mentions_amway", "life_stage",
    "four_have", "touchpoint", "monitoring_purpose", "center_terms",
    "question_set_version", "metadata_status",
)


def configure(expected, output_dir):
    global SECRET_VALUES
    if not re.fullmatch(r"[a-f0-9]{40}", expected):
        raise ValueError("invalid_release")
    if Path(output_dir).is_symlink():
        raise ValueError("invalid_output_directory")
    output = Path(output_dir).resolve()
    if not re.fullmatch(r"/tmp/ageo-topic-replay\.[A-Za-z0-9]{12}", str(output)):
        raise ValueError("invalid_output_directory")
    if not output.is_dir() or output.is_symlink():
        raise ValueError("invalid_output_directory")
    release = Path("/srv/ageo-deploy/current").resolve()
    if (release / ".release-sha").read_text().strip() != expected:
        raise ValueError("release_mismatch")
    pid = subprocess.check_output(
        ["systemctl", "show", "ageo-backend.service", "--property=MainPID", "--value"],
        text=True, timeout=15,
    ).strip()
    backend = release / "aeo-platform/backend"
    if not pid.isdigit() or int(pid) <= 0:
        raise ValueError("backend_not_running")
    if Path(f"/proc/{pid}/cwd").resolve() != backend:
        raise ValueError("service_release_mismatch")
    entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    process_env = dict(item.split(b"=", 1) for item in entries if b"=" in item)
    SECRET_VALUES = tuple(v.decode() for k, v in process_env.items()
                          if len(v) >= 12 and re.search(r"KEY|TOKEN|SECRET|PASSWORD|DATABASE_URL", k.decode()))
    # Read the running service configuration in-process; never export it.
    os.environ.clear()
    os.environ.update({k.decode(): v.decode() for k, v in process_env.items()})
    os.chdir(backend)
    sys.path.insert(0, str(backend))
    logging.disable(logging.CRITICAL)
    import httpx
    def no_http(*args, **kwargs):
        raise RuntimeError("provider_http_disabled_in_read_only_replay")
    httpx.Client.send = no_http
    httpx.AsyncClient.send = no_http
    return output


def redact_export(value):
    if isinstance(value, dict):
        return {k: redact_export(v) for k, v in value.items()
                if not re.search(r"(^|_)(authorization|password|secret|token|api_key|headers|cookies|raw_response|takeover)(_|$)", str(k), re.I)}
    if isinstance(value, list):
        return [redact_export(v) for v in value]
    if isinstance(value, str):
        for secret in SECRET_VALUES:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value)
        value = re.sub(r"(?i)([?&](?:token|access_token|api_key|key|signature|sig|authorization)=)[^&\s\"<>]+", r"\1[REDACTED]", value)
        return value
    return value


def safe_answers(fetch_results):
    """Allow only collection business fields, excluding raw responses/headers."""
    results = []
    for row in fetch_results:
        clean = {k: row[k] for k in (*CONTEXT_KEYS, "question_id", "id", "question", "question_text", "source") if k in row}
        clean["platform_results"] = []
        for answer in row.get("platform_results") or []:
            item = {k: answer[k] for k in (*CONTEXT_KEYS, "platform", "answer_id", "id", "result_id", "success") if k in answer}
            nested = answer.get("answer") if isinstance(answer.get("answer"), dict) else {}
            item["answer_text"] = nested.get("content") or answer.get("answer_text") or answer.get("content") or answer.get("text") or ""
            # Preserve failure truthiness without copying provider diagnostics.
            item["error"] = bool(answer.get("error"))
            item["error_message"] = bool(answer.get("error_message"))
            clean["platform_results"].append(item)
        results.append(clean)
    return results


def nodes_by_entity(projection):
    result = {}
    for node in projection.get("nodes") or []:
        identifier = node.get("lexicon_entity_id") or node.get("entity_id")
        if not identifier or identifier in result:
            raise ValueError("missing_or_duplicate_node_entity_id")
        result[identifier] = node
    return result


def compare_nodes(expected, actual):
    fields = ("gravity_score", "association_score", "answer_count", "evidence_count", "platform_count", "orbit")
    return {
        "expected_count": len(expected), "actual_count": len(actual),
        "missing": sorted(set(expected) - set(actual)),
        "extra": sorted(set(actual) - set(expected)),
        "field_differences": [{"entity_id": key, "fields": {
            field: {"expected": expected[key].get(field), "actual": actual[key].get(field)}
            for field in fields if expected[key].get(field) != actual[key].get(field)
        }} for key in sorted(set(expected) & set(actual))
            if any(expected[key].get(field) != actual[key].get(field) for field in fields)],
    }


def topic_report(current, frozen, fetch_results, extraction, calibration, page_nodes):
    from app.services import amway_entity_calibration_service as c
    from app.services.amway_entity_extraction_service import _answer_text, _compact, _question_id
    from app.services.amway_topic_projection import project_topic_signals
    raw = c._dedupe_answer_signals(extraction["signals"])
    eligible = [s for s in raw if s.get("relation_type") not in c.EXCLUDED_RELATION_TYPES]
    projected = project_topic_signals(eligible, frozen)
    service = c.AmwayEntityCalibrationService(frozen)
    accumulators = service._build_accumulators(projected)
    raw_counts = Counter(s["entity_id"] for s in raw)
    projected_counts = Counter(s["entity_id"] for s in projected)
    replay_nodes = nodes_by_entity(calibration["association_circle_projection"])
    scope = calibration["sample_scope"]
    platforms = c._valid_platform_names(fetch_results, raw) or c._all_platform_names(fetch_results, raw)
    question_count = len(c._build_question_bank(fetch_results))
    rows = []
    for entity in current.entities:
        if not entity.semantic_definition or entity.semantic_definition.graph_role != "topic":
            continue
        old = frozen.get_entity(entity.entity_id)
        direct_hits = []
        for index, question in enumerate(fetch_results, 1):
            for answer in question.get("platform_results") or []:
                text = _compact(_answer_text(answer))
                terms = [term for term in (entity.canonical_name, *entity.aliases) if _compact(term) and _compact(term) in text]
                if terms:
                    direct_hits.append({"question_id": _question_id(question, index), "platform": answer.get("platform"), "terms": terms})
        score = None
        reason = "included" if entity.entity_id in replay_nodes else "no_extracted_or_mapped_signal"
        acc = accumulators.get(entity.entity_id)
        if old is None:
            reason = "absent_from_frozen_lexicon"
        elif old.review_status != "approved":
            reason = "frozen_entry_not_approved"
        elif old.semantic_definition and old.semantic_definition.match_policy == "disabled":
            reason = "frozen_matching_disabled"
        elif acc is not None:
            acc = service._risk_scoped_accumulator(old, acc)
            parts = c._score_accumulator(acc, total_valid_answers=int(scope.get("valid_answer_count") or 0), total_platforms=max(len(platforms), 1), total_questions=max(question_count, 1))
            stance = c._signal_stance_summary(acc.signals)
            risk = c._is_risk_entity(old, acc) or c._is_contextual_risk_entity(old, acc)
            score = c._context_adjusted_score(raw_score=int(parts["gravity_score"]), entity=old, acc=acc, is_risk=risk, stance_summary=stance)
            score = c._sample_confidence_adjusted_score(score=score, entity=old, acc=acc, is_risk=risk)
            if old.entity_type in {"CenterBrand", "MarketContext"}:
                reason = "entity_type_excluded"
            elif not risk and old.graph_policy.main_orbit == "not_allowed":
                reason = "main_orbit_not_allowed"
            elif score < 12 and not risk and acc.term_origin != "strategy":
                reason = "score_below_12"
        elif raw_counts[entity.entity_id]:
            reason = "raw_signals_excluded_before_topic_projection"
        elif direct_hits:
            reason = "literal_hit_not_extracted_context_or_match_rules"
        extractable = bool(old and "answer" in frozen.require_entity_type(old.entity_type).extractable_from)
        rows.append({
            "entity_id": entity.entity_id, "name": entity.canonical_name,
            "current_present": True, "frozen_present": old is not None,
            "current_status": entity.review_status, "frozen_status": old.review_status if old else None,
            "current_match_policy": entity.semantic_definition.match_policy,
            "frozen_match_policy": old.semantic_definition.match_policy if old and old.semantic_definition else None,
            "answer_extractable": extractable, "direct_current_name_alias_hits": direct_hits,
            "raw_signal_count": raw_counts[entity.entity_id], "projected_signal_count": projected_counts[entity.entity_id],
            "replay_node_present": entity.entity_id in replay_nodes,
            "online_node_present": entity.entity_id in page_nodes,
            "score": score, "replay_reason": reason,
            "page_difference": "" if (entity.entity_id in replay_nodes) == (entity.entity_id in page_nodes) else "page_projection_differs_from_replay",
        })
    return rows


async def collect(expected):
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal, engine
    from app.models.snapshot import AnalysisSnapshot
    from app.models.task import AnalysisTask
    from app.models.brand_intelligence_run import BrandIntelligenceRun
    from app.ontology import AmwayEntityOntologyRegistry
    from app.services.amway_circle_tracking_service import AmwayCircleTrackingService
    from app.services.amway_entity_lexicon_service import AmwayEntityLexiconService
    from app.services.amway_entity_extraction_service import AmwayEntityExtractionService
    from app.services.amway_entity_calibration_service import AmwayEntityCalibrationService
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            await db.execute(text("SET LOCAL statement_timeout = '45s'"))
            if (await db.execute(text("SHOW transaction_read_only"))).scalar_one() != "on":
                raise ValueError("read_only_transaction_required")
            tracking = AmwayCircleTrackingService(db)
            run = await tracking._latest_completed_run(ENTITY_ID, center_term=CENTER)
            if run is None:
                raise ValueError("no_official_run")
            page = await tracking.get_period_view(ENTITY_ID, period_type="latest_run", center_term=CENTER)
            if page.get("current_period", {}).get("run_ids") != [str(run.id)]:
                raise ValueError("period_run_binding_mismatch")
            projections = await tracking._run_projections(ENTITY_ID, [run.id])
            if len(projections) != 1:
                raise ValueError("missing_run_projection")
            brand_run = await db.get(BrandIntelligenceRun, run.brand_intelligence_run_id) if run.brand_intelligence_run_id else None
            snapshot_id = (brand_run.output_refs or {}).get("snapshot_id") if brand_run else None
            if not snapshot_id and run.analysis_task_id:
                task = await db.get(AnalysisTask, run.analysis_task_id)
                snapshot_id = task.snapshot_id if task else None
            if not snapshot_id:
                raise ValueError("missing_bound_snapshot")
            snapshot = await db.get(AnalysisSnapshot, UUID(str(snapshot_id)))
            if snapshot is None or snapshot.entity_id != ENTITY_ID:
                raise ValueError("snapshot_scope_mismatch")
            raw = snapshot.raw_data or {}
            fetch = raw["fetch_results"]
            stored_extraction = raw["entity_extraction_result"]
            stored_calibration = raw["entity_calibration_result"]
            frozen = AmwayEntityOntologyRegistry.from_snapshot(stored_extraction["effective_lexicon_snapshot"])
            current = await AmwayEntityLexiconService(db).registry_for_entity(ENTITY_ID)
            extraction = AmwayEntityExtractionService(frozen).extract_from_fetch_results(fetch)
            calibration = AmwayEntityCalibrationService(frozen).calibrate(fetch_results=fetch, extraction_result=extraction, center_terms=stored_calibration["association_map"]["center_terms"])
            safe_fetch = safe_answers(fetch)
            safe_extraction = AmwayEntityExtractionService(frozen).extract_from_fetch_results(safe_fetch)
            if safe_extraction != extraction:
                raise ValueError("safe_answer_export_changes_extraction")
            safe_calibration = AmwayEntityCalibrationService(frozen).calibrate(fetch_results=safe_fetch, extraction_result=safe_extraction, center_terms=stored_calibration["association_map"]["center_terms"])
            replay_nodes = nodes_by_entity(calibration["association_circle_projection"])
            safe_comparison = compare_nodes(replay_nodes, nodes_by_entity(safe_calibration["association_circle_projection"]))
            if any(safe_comparison[key] for key in ("missing", "extra", "field_differences")):
                raise ValueError("safe_answer_export_changes_scores")
            page_nodes = nodes_by_entity(page["projection"])
            topics = topic_report(current, frozen, fetch, extraction, calibration, page_nodes)
            report = {
                "release_sha": expected, "database_writes": False, "provider_calls": False,
                "entity_id": str(ENTITY_ID), "circle_run_id": str(run.id),
                "brand_run_id": str(run.brand_intelligence_run_id), "analysis_task_id": str(run.analysis_task_id),
                "snapshot_id": str(snapshot.id), "run_projection_id": str(projections[0].id),
                "period_report_id": page.get("report_id"), "period_scope": page.get("current_period"),
                "run_completed_at": str(run.completed_at), "run_status": run.status,
                "current_lexicon": current.snapshot(), "frozen_lexicon": frozen.snapshot(),
                "stored_extraction": stored_extraction, "replayed_extraction": extraction,
                "stored_calibration": stored_calibration, "replayed_calibration": calibration,
                "page_projection": page["projection"], "run_projection": projections[0].association_circle_projection,
                "comparisons": {
                    "stored_extraction_equal": stored_extraction == extraction,
                    "stored_calibration_vs_replay": compare_nodes(nodes_by_entity(stored_calibration["association_circle_projection"]), replay_nodes),
                    "run_projection_vs_replay": compare_nodes(nodes_by_entity(projections[0].association_circle_projection), replay_nodes),
                    "page_vs_replay": compare_nodes(page_nodes, replay_nodes),
                }, "topics": topics,
            }
            await db.rollback()
            return safe_fetch, report
    finally:
        await engine.dispose()


def write_output(output, answers, report):
    answers, report = redact_export(answers), redact_export(report)
    owner = output.stat()
    for filename, value in (("answers.json", answers), ("replay.json", report)):
        path = output / filename
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
        os.chown(path, owner.st_uid, owner.st_gid)
    rows = report["topics"]
    csv_path = output / "topics.csv"
    with os.fdopen(os.open(csv_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows)
    os.chown(csv_path, owner.st_uid, owner.st_gid)
    print(json.dumps({
        "release_sha": report["release_sha"], "database_writes": False, "provider_calls": False,
        "circle_run_id": report["circle_run_id"], "snapshot_id": report["snapshot_id"],
        "question_count": len(answers), "current_topic_count": len(rows),
        "page_node_count": len(report["page_projection"].get("nodes") or []),
        "replayed_node_count": len(report["replayed_calibration"]["association_circle_projection"]["nodes"]),
        "reasons": dict(Counter(row["replay_reason"] for row in rows)),
        "files": {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in ("answers.json", "replay.json", "topics.csv")},
    }, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-release", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        destination = configure(args.expected_release, args.output_dir)
        answers, report = asyncio.run(collect(args.expected_release))
        if Path("/srv/ageo-deploy/current/.release-sha").read_text().strip() != args.expected_release:
            raise ValueError("release_changed_during_replay")
        write_output(destination, answers, report)
    except Exception as exc:
        # Tracebacks or arbitrary provider/configuration strings must not enter CI logs.
        failure = {"failed": True, "failure_type": type(exc).__name__}
        if isinstance(exc, ValueError) and re.fullmatch(r"[a-z_]{1,80}", str(exc)):
            failure["failure_code"] = str(exc)
        print(json.dumps(failure))
        raise SystemExit(1)
