"""Production report-outline repair runner; safe summaries only."""
import argparse
import asyncio
import gzip
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

CURRENT = Path("/srv/ageo-deploy/current")
BACKUP_ROOT = Path("/srv/ageo-deploy/shared/runtime")


def check_release(expected):
    if not re.fullmatch(r"[a-f0-9]{40}", expected):
        raise ValueError("invalid_release")
    release = CURRENT.resolve()
    if (release / ".release-sha").read_text().strip() != expected:
        raise ValueError("release_mismatch")
    pid = subprocess.check_output([
        "systemctl", "show", "ageo-backend.service", "--property=MainPID", "--value",
    ], text=True, timeout=15).strip()
    if not pid.isdigit() or int(pid) <= 0 or Path(f"/proc/{pid}/cwd").resolve() != release / "aeo-platform/backend":
        raise ValueError("service_release_mismatch")
    return release, pid


def configure(args):
    release, pid = check_release(args.expected_release)
    if args.repair_id != "amway-report-outline-20260914-v1":
        raise ValueError("invalid_repair_id")
    destination = Path(args.backup_dir)
    if (not destination.is_absolute() or destination.name != args.repair_id
            or not destination.is_relative_to(BACKUP_ROOT)
            or destination.resolve() != destination):
        raise ValueError("unsafe_backup_directory")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination, 0o700)
    entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    values = dict(item.split(b"=", 1) for item in entries if b"=" in item)
    os.environ.clear()
    os.environ.update({key.decode(): value.decode() for key, value in values.items()})
    os.chdir(release / "aeo-platform/backend")
    sys.path.insert(0, str(release / "aeo-platform/backend"))
    logging.disable(logging.CRITICAL)
    import httpx

    def no_http(*_args, **_kwargs):
        raise RuntimeError("provider_http_disabled_in_outline_repair")

    httpx.Client.send = no_http
    httpx.AsyncClient.send = no_http
    return destination


def service_module():
    # The workflow stages these two exact-reviewed files together outside releases.
    sibling = Path(__file__).resolve().with_name("amway_report_outline_repair_service.py")
    if sibling.is_file():
        spec = importlib.util.spec_from_file_location("amway_report_outline_repair", sibling)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    from app.services import amway_report_outline_repair_service
    return amway_report_outline_repair_service


def source_hashes(module):
    return {"cli_sha256": hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest(),
            "service_sha256": hashlib.sha256(Path(module.__file__).resolve().read_bytes()).hexdigest()}


def load_plan(path):
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("insecure_plan_permissions")
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def publish_plan(directory, plan, module, store):
    path = directory / "plan.json.gz"
    pending = directory / f"plan-pending-{uuid4().hex}.json.gz"
    with os.fdopen(os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as file:
        with gzip.GzipFile(fileobj=file, mode="wb", mtime=0) as compressed:
            for chunk in json.JSONEncoder(ensure_ascii=False, separators=(",", ":")).iterencode(plan):
                compressed.write(chunk.encode())
        file.flush()
        os.fsync(file.fileno())
    module.validate_plan(load_plan(pending), store, expected_hash=plan["manifest_hash"])
    for current, _, _ in os.walk(store.directory, topdown=False):
        descriptor = os.open(current, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    # The ready filename is immutable and published only after complete readback.
    os.link(pending, path)
    pending.unlink()
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run(args, directory):
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal, engine
    module = service_module()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            await db.execute(text("SET LOCAL statement_timeout = '90s'"))
            await db.execute(text("SET LOCAL lock_timeout = '15s'"))
            service = module.AmwayReportOutlineRepairService(db)
            if args.mode == "inventory":
                await db.execute(text("SET TRANSACTION READ ONLY"))
                result = await service.inventory()
                await db.rollback()
                check_release(args.expected_release)
                return result | {"release_sha": args.expected_release}
            plan_path = directory / "plan.json.gz"
            if args.mode == "dry-run":
                await db.execute(text("SET TRANSACTION READ ONLY"))
                if plan_path.exists():
                    raise ValueError("immutable_plan_already_exists")
                import shutil
                if shutil.disk_usage(directory).free < 5 * 1024 ** 3:
                    raise ValueError("insufficient_backup_disk_space")
                store = module.RepairRowStore(directory)
                plan = await service.stage(store, args.expected_release)
                await db.rollback()
                check_release(args.expected_release)
                plan["code_hashes"] = source_hashes(module)
                plan["manifest_hash"] = module.digest({key: value for key, value in plan.items() if key != "manifest_hash"})
                checksum = publish_plan(directory, plan, module, store)
                return module.plan_summary(plan) | {"mode": "dry-run", "database_committed": False,
                    "code_hashes": plan["code_hashes"], "plan_file_sha256": checksum,
                    "backup_storage": plan["row_storage"]}
            if not args.expected_manifest_hash or not re.fullmatch(r"[a-f0-9]{64}", args.expected_manifest_hash):
                raise ValueError("expected_manifest_hash_required")
            plan = load_plan(plan_path)
            if plan["release_sha"] != args.expected_release or plan["code_hashes"] != source_hashes(module):
                raise ValueError("plan_release_or_repair_code_mismatch")
            store = module.RepairRowStore(directory, namespace=plan["row_storage"]["namespace"])
            if args.mode == "verify":
                await db.execute(text("SET TRANSACTION READ ONLY"))
                result = await service.verify(plan, store, expected_hash=args.expected_manifest_hash)
                await db.rollback()
            else:
                result = await service.apply(plan, store, expected_hash=args.expected_manifest_hash,
                                             reverse=args.mode == "restore")
                check_release(args.expected_release)
                await db.commit()
            check_release(args.expected_release)
            return module.plan_summary(plan) | result | {"mode": args.mode,
                    "database_committed": args.mode in {"apply", "restore"},
                    "code_hashes": plan["code_hashes"]}
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("inventory", "dry-run", "apply", "verify", "restore"), required=True)
    parser.add_argument("--expected-release", required=True)
    parser.add_argument("--repair-id", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--expected-manifest-hash")
    args = parser.parse_args()
    try:
        destination = configure(args)

        async def bounded():
            return await asyncio.wait_for(run(args, destination), timeout=780)

        result = asyncio.run(bounded())
        print(json.dumps(result, ensure_ascii=True), flush=True)
    except Exception as exc:
        detail = str(exc) if type(exc) is ValueError else ""
        safe_code = detail if re.fullmatch(r"[a-z0-9_:.-]{1,180}", detail) else None
        print(json.dumps({"failed": True, "failure_type": type(exc).__name__, "failure_code": safe_code}), flush=True)
        raise SystemExit(1)
