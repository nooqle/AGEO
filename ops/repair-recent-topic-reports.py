"""Authorized seven-day report repair runner; plans/backups never leave server."""
import argparse
import asyncio
import gzip
import gc
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import resource

ROOT = Path("/srv/ageo-deploy/shared/runtime/topic-repairs")
CURRENT = Path("/srv/ageo-deploy/current")


def check_release(expected):
    if not re.fullmatch(r"[a-f0-9]{40}", expected):
        raise ValueError("invalid_release")
    release = CURRENT.resolve()
    if (release / ".release-sha").read_text().strip() != expected:
        raise ValueError("release_mismatch")
    pid = subprocess.check_output(["systemctl", "show", "ageo-backend.service",
                                  "--property=MainPID", "--value"], text=True, timeout=15).strip()
    if not pid.isdigit() or int(pid) <= 0 or Path(f"/proc/{pid}/cwd").resolve() != release / "aeo-platform/backend":
        raise ValueError("service_release_mismatch")
    return release, pid


def configure(args):
    release, pid = check_release(args.expected_release)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{8,100}", args.repair_id):
        raise ValueError("invalid_repair_id")
    # A persistent root-owned directory, no arbitrary paths or symlink traversal.
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if ROOT.resolve() != ROOT or ROOT.is_symlink():
        raise ValueError("unsafe_backup_root")
    os.chmod(ROOT, 0o700)
    directory = ROOT / args.repair_id
    if directory.is_symlink():
        raise ValueError("unsafe_backup_directory")
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    values = dict(item.split(b"=", 1) for item in entries if b"=" in item)
    os.environ.clear()
    os.environ.update({k.decode(): v.decode() for k, v in values.items()})
    backend = release / "aeo-platform/backend"
    os.chdir(backend)
    sys.path.insert(0, str(backend))
    logging.disable(logging.CRITICAL)
    memory = {line.split(":", 1)[0]: int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line and len(line.split()) >= 2 and line.split()[1].isdigit()}
    if memory.get("MemAvailable", 0) < 3 * 1024 * 1024:
        raise ValueError("insufficient_memory_for_bounded_repair")
    import httpx
    def no_http(*_args, **_kwargs):
        raise RuntimeError("provider_http_disabled_in_topic_repair")
    httpx.Client.send = no_http
    httpx.AsyncClient.send = no_http
    return directory


def save_exclusive(path, value, *, compressed=False):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
        stream = gzip.GzipFile(fileobj=handle, mode="wb", compresslevel=6, mtime=0) if compressed else handle
        for chunk in json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).iterencode(value):
            stream.write(chunk.encode())
        if compressed:
            stream.close()
        handle.flush()
        os.fsync(handle.fileno())
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def load_plan(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def plan_summary(plan):
    counts = {}
    nodes = []
    for change in plan["changes"]:
        counts[change["table"]] = counts.get(change["table"], 0) + 1
        if change["table"] == "amway_circle_projections":
            old, new = change["before"], change["after"]
            nodes.append({"projection_id": change["id"], "run_id": new.get("circle_run_id"),
                          "scope": new["projection_scope"],
                          "old_nodes": len((old.get("association_circle_projection") or {}).get("nodes") or []),
                          "new_nodes": len((new.get("association_circle_projection") or {}).get("nodes") or [])})
    return {key: plan[key] for key in ("repair_id", "manifest_hash", "start_utc", "end_utc", "counts",
                                      "source_lexicon_hash", "target_lexicon_hash", "run_ids", "report_ids")} | {
        "changed_rows_by_table": counts, "node_changes": nodes,
        "provider_calls": False, "original_answers_changed": False,
        "protected_rows_hash": plan["protected_rows_hash"],
        "backup_contains_complete_before_and_after_rows": True}


async def run(args, directory):
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal, engine
    from app.services.amway_topic_repair_service import AmwayTopicRepairService, apply_manifest, digest, ENTITY_ID
    plan_path = directory / "plan.json.gz"
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            await db.execute(text("SET LOCAL statement_timeout = '90s'"))
            await db.execute(text("SET LOCAL lock_timeout = '15s'"))
            if args.mode == "verify":
                await db.execute(text("SET TRANSACTION READ ONLY"))
            if args.mode == "dry-run":
                if plan_path.exists():
                    raise ValueError("immutable_plan_already_exists")
                package = json.loads(Path(args.package).read_text(encoding="utf-8"))
                inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
                if package["repair_id"] != args.repair_id:
                    raise ValueError("repair_id_mismatch")
                plan = await AmwayTopicRepairService(db).stage(inventory, package)
                await db.rollback()
                check_release(args.expected_release)
                plan["release_sha"] = args.expected_release
                plan["manifest_hash"] = digest({k: v for k, v in plan.items() if k != "manifest_hash"})
                # Manifest includes exact deleted rows/IDs and every overwritten JSON.
                # This is also the inverse restore plan; store before any production apply.
                checksum = save_exclusive(plan_path, plan, compressed=True)
                summary = plan_summary(plan) | {"mode": "dry-run", "database_committed": False,
                                                "plan_file_sha256": checksum,
                                                "release_sha": args.expected_release}
                del plan
                db.expunge_all()
                gc.collect()
                loaded = load_plan(plan_path)
                if loaded["manifest_hash"] != summary["manifest_hash"] or digest({k:v for k,v in loaded.items() if k != "manifest_hash"}) != summary["manifest_hash"]:
                    raise ValueError("backup_manifest_readback_failed")
                del loaded
                save_exclusive(directory / "summary.json", summary)
                return summary
            if not args.expected_manifest_hash:
                raise ValueError("expected_manifest_hash_required")
            if plan_path.is_symlink() or plan_path.stat().st_mode & 0o077:
                raise ValueError("insecure_plan_permissions")
            plan = load_plan(plan_path)
            if plan["repair_id"] != args.repair_id:
                raise ValueError("repair_id_mismatch")
            if plan["release_sha"] != args.expected_release:
                raise ValueError("plan_release_mismatch")
            if args.mode == "verify":
                if plan["manifest_hash"] != args.expected_manifest_hash or digest({k: v for k, v in plan.items() if k != "manifest_hash"}) != args.expected_manifest_hash:
                    raise ValueError("manifest_hash_mismatch")
                service = AmwayTopicRepairService(db)
                if digest(await service.capture()) != plan["after_hash"]:
                    raise ValueError("verification_rows_drifted")
                views = {}
                for period in ("latest_run", "last_7_days"):
                    view = await service.tracking.get_period_view(ENTITY_ID, period_type=period, center_term="\u5b89\u5229")
                    body = view.get("projection") or {}
                    views[period] = {"report_id": view.get("report_id"),
                                     "run_ids": (view.get("current_period") or {}).get("run_ids"),
                                     "valid_answer_count": (view.get("current_period") or {}).get("valid_answer_count"),
                                     "node_count": len(body.get("nodes") or []),
                                     "coverage": {key: (body.get("topic_coverage") or {}).get(key)
                                                  for key in ("total_topic_count", "included_topic_count", "anchor_node_count")}}
                await db.rollback()
                return {"status": "verified", "repair_id": plan["repair_id"], "views": views,
                        "all_persisted_rows_match_plan": True, "counts": plan["counts"],
                        "browser_ui_verified": False, "database_committed": False}
            result = await apply_manifest(db, plan, expected_hash=args.expected_manifest_hash,
                                          reverse=args.mode == "restore")
            check_release(args.expected_release)
            await db.commit()
            return result | {"release_sha": args.expected_release,
                             "manifest_hash": args.expected_manifest_hash,
                             "backup_file": str(plan_path), "database_committed": True}
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dry-run", "apply", "restore", "verify"), required=True)
    parser.add_argument("--expected-release", required=True)
    parser.add_argument("--repair-id", required=True)
    parser.add_argument("--package")
    parser.add_argument("--inventory")
    parser.add_argument("--expected-manifest-hash")
    args = parser.parse_args()
    try:
        destination = configure(args)
        async def bounded():
            return await asyncio.wait_for(run(args, destination), timeout=720)
        result = asyncio.run(bounded())
        result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(json.dumps(result, ensure_ascii=True), flush=True)
    except Exception as exc:
        # Exception strings can include SQL parameters or original answers.
        detail = str(exc) if type(exc) is ValueError else ""
        safe_code = detail if re.fullmatch(r"[a-z0-9_:.-]{1,180}", detail) else None
        print(json.dumps({"failed": True, "failure_type": type(exc).__name__, "failure_code": safe_code}), flush=True)
        raise SystemExit(1)
