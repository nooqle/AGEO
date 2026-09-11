"""Inspect or migrate the fixed DeepSeek model allowlist; dry-run by default."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone


TARGET = Path("/srv/ageo-deploy/shared/backend/.env.local")
RELEASE = Path("/srv/ageo-deploy/current/.release-sha")
SERVICE = "ageo-backend.service"
DESIRED = {
    "LLM_PROVIDER": "deepseek",
    "DEEPSEEK_MODEL_NAME": "deepseek-flash",
    "DEEPSEEK_FLASH_MODEL_NAME": "deepseek-flash",
    "DEEPSEEK_PRO_MODEL_NAME": "deepseek-flash",
    "TEXT_REASONING_LLM_PROVIDER": "deepseek",
    "TEXT_REASONING_MODEL_NAME": "deepseek-flash",
    "TEXT_LIGHT_LLM_PROVIDER": "deepseek",
    "TEXT_LIGHT_MODEL_NAME": "deepseek-flash",
    "MULTIMODAL_LLM_PROVIDER": "deepseek",
    "MULTIMODAL_MODEL_NAME": "deepseek-flash",
    "BROWSER_AGENT_LLM_MODEL_NAME": "deepseek-flash",
}
ASSIGNMENT = re.compile(rb"^[ \t]*(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(.*?)(?:\r?\n)?$")
VALUE = re.compile(rb'''^(?:"([^"\r\n]*)"|'([^'\r\n]*)'|([^\s#'"\r\n]*))[ \t]*(?:\#.*)?$''')
BACKUP_NAME = re.compile(r"\.env\.local\.deepseek41-\d{8}T\d{6}\.\d{6}Z-\d+\.json")


def snapshot(path=None):
    path = TARGET if path is None else path
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("expected a regular file")
        return source.read(), metadata


def identity(metadata):
    return (metadata.st_dev, metadata.st_ino, metadata.st_size,
            metadata.st_mtime_ns, metadata.st_ctime_ns,
            metadata.st_uid, metadata.st_gid, metadata.st_mode)


def model_lines(original):
    found = {}
    for line in original.splitlines(keepends=True):
        assignment = ASSIGNMENT.fullmatch(line)
        if not assignment:
            continue
        key = assignment[1].decode("ascii")
        if key not in DESIRED:
            continue
        value = VALUE.fullmatch(assignment[2])
        if key in found or not value:
            raise RuntimeError("duplicate or unsupported allowlisted assignment")
        raw = next(part for part in value.groups() if part is not None)
        found[key] = (line, raw.decode("utf-8"))
    return found


def transform(original, replacements):
    """Replace only allowlisted lines, preserving all unrelated bytes."""
    found = model_lines(original)
    by_line = {line: replacements[key] for key, (line, _) in found.items()}
    parts = [by_line.get(line, line) for line in original.splitlines(keepends=True)]
    parts = [part for part in parts if part]
    # A formerly final assignment may now precede unrelated lines added later.
    output = b"".join(part if index == len(parts) - 1 or part.endswith(b"\n")
                      else part + b"\n" for index, part in enumerate(parts))
    appended = b"".join(replacements[key] or b"" for key in DESIRED if key not in found)
    if appended:
        if output and not output.endswith(b"\n"):
            output += b"\n"
        output += appended
    return output


def process_models():
    result = subprocess.run(
        ["systemctl", "show", SERVICE, "--property=MainPID", "--value"],
        check=True, capture_output=True, text=True, timeout=15,
    )
    pid = int(result.stdout.strip())
    if pid <= 0:
        raise RuntimeError("backend MainPID unavailable")
    entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    return {key.decode(): value.decode("utf-8")
            for entry in entries if b"=" in entry
            for key, value in [entry.split(b"=", 1)]
            if key in {name.encode() for name in DESIRED}}


def current_release():
    value = RELEASE.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{40}", value):
        raise RuntimeError("invalid current release identity")
    return value


def require_state(expected_release, desired):
    if current_release() != expected_release:
        raise RuntimeError("current release changed or does not match expected release")
    overrides = process_models()
    if any(value != desired.get(key) for key, value in overrides.items()):
        raise RuntimeError("conflicting process model override; refusing mutation")


def backup_payload(original, release):
    found = model_lines(original)
    return {"version": 1, "release": release, "target": str(TARGET),
            "desired": DESIRED,
            "before": {key: base64.b64encode(found[key][0]).decode("ascii")
                       if key in found else None for key in DESIRED}}


def write_backup(original, release):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = TARGET.with_name(f".env.local.deepseek41-{stamp}-{os.getpid()}.json")
    payload = json.dumps(backup_payload(original, release), sort_keys=True).encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as saved:
        os.fchown(saved.fileno(), 0, 0)
        os.fchmod(saved.fileno(), 0o600)
        saved.write(payload)
        saved.flush()
        os.fsync(saved.fileno())
    return path


def load_backup(path):
    if path.parent != TARGET.parent or not BACKUP_NAME.fullmatch(path.name):
        raise RuntimeError("backup must be a generated path in the fixed shared directory")
    raw, metadata = snapshot(path)
    if metadata.st_uid != 0 or metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError("backup must be root-owned mode 0600")
    payload = json.loads(raw)
    if (set(payload) != {"version", "release", "target", "desired", "before"}
            or payload["version"] != 1 or payload["target"] != str(TARGET)
            or payload["desired"] != DESIRED
            or not re.fullmatch(r"[a-f0-9]{40}", payload["release"])
            or not isinstance(payload["before"], dict)
            or set(payload["before"]) != set(DESIRED)):
        raise RuntimeError("invalid migration backup schema")
    before = {}
    for key, encoded in payload["before"].items():
        line = base64.b64decode(encoded, validate=True) if encoded is not None else None
        if line is not None:
            parsed = model_lines(line)
            if len(line.splitlines()) != 1 or set(parsed) != {key} or parsed[key][0] != line:
                raise RuntimeError("backup contains an invalid allowlisted line")
        before[key] = line
    return before, {"path": str(path), "uid": metadata.st_uid,
                    "mode": "0600", "sha256": hashlib.sha256(raw).hexdigest()}


def backup_metadata():
    results = []
    for path in sorted(TARGET.parent.glob(".env.local.deepseek41-*.json"), reverse=True)[:20]:
        metadata = path.lstat()
        if BACKUP_NAME.fullmatch(path.name) and stat.S_ISREG(metadata.st_mode):
            results.append({"path": str(path), "uid": metadata.st_uid,
                            "gid": metadata.st_gid, "mode": oct(stat.S_IMODE(metadata.st_mode)),
                            "bytes": metadata.st_size})
    return results


def atomic_replace(original, updated, metadata, expected_release, desired):
    descriptor, temporary = tempfile.mkstemp(prefix=".env.local.deepseek41-", dir=TARGET.parent)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            os.fchown(destination.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(destination.fileno(), stat.S_IMODE(metadata.st_mode))
            destination.write(updated)
            destination.flush()
            os.fsync(destination.fileno())
        current, current_metadata = snapshot()
        if current != original or identity(current_metadata) != identity(metadata):
            raise RuntimeError("shared environment changed; refusing replacement")
        require_state(expected_release, desired)
        if identity(TARGET.lstat()) != identity(metadata):
            raise RuntimeError("shared environment changed; refusing replacement")
        os.replace(temporary, TARGET)
        directory = os.open(TARGET.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", type=Path)
    parser.add_argument("--expected-release")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("run as root")
    if args.apply and not re.fullmatch(r"[a-f0-9]{40}", args.expected_release or ""):
        raise RuntimeError("apply requires a full expected release SHA")
    original, metadata = snapshot()
    found = model_lines(original)
    replacements = {key: f"{key}={value}\n".encode() for key, value in DESIRED.items()}
    desired = DESIRED
    backup_info = None
    if args.restore:
        replacements, backup_info = load_backup(args.restore)
        if {key: pair[1] for key, pair in found.items()} != DESIRED:
            raise RuntimeError("allowlisted values changed since migration; refusing restore")
        desired = {key: model_lines(line)[key][1] if line is not None else None
                   for key, line in replacements.items()}
    updated = transform(original, replacements)
    release = current_release()
    if args.expected_release and args.expected_release != release:
        raise RuntimeError("current release does not match expected release")
    overrides = process_models()
    previous_file = RELEASE.parent.parent / "previous" / ".release-sha"
    previous = previous_file.read_text(encoding="ascii").strip() if previous_file.exists() else None
    if previous is not None and not re.fullmatch(r"[a-f0-9]{40}", previous):
        raise RuntimeError("invalid previous release identity")
    print(json.dumps({"release": release, "dry_run": not args.apply,
                      "previous_release": previous,
                      "environment_metadata": {"uid": metadata.st_uid, "gid": metadata.st_gid,
                                               "mode": oct(stat.S_IMODE(metadata.st_mode))},
                      "operation": "restore" if args.restore else "migrate",
                      "would_change": updated != original, "backup": backup_info,
                      "available_backups": backup_metadata(),
                      "models": {key: {"file_value": found[key][1] if key in found else None,
                                       "target_value": desired[key], "process_override": key in overrides,
                                       "override_conflict": key in overrides and overrides[key] != desired[key]}
                                 for key in DESIRED}}), flush=True)
    backup = None
    if args.apply:
        require_state(args.expected_release, desired)
        if updated != original:
            if not args.restore:
                backup = write_backup(original, release)
            atomic_replace(original, updated, metadata, args.expected_release, desired)
    print(json.dumps({"changed": args.apply and updated != original,
                      "backup_path": str(backup) if backup else None,
                      "service_restarted": False, "release_changed": False}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(json.dumps({"error": message}))
        raise SystemExit(1)
