"""Migrate only retired Kimi model overrides; run as root, dry-run by default."""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone


TARGET = Path("/srv/ageo-deploy/shared/backend/.env.local")
SERVICE = "ageo-backend.service"
KEYS = (b"MOONSHOT_MODEL", b"MOONSHOT_FAST_MODEL")
OLD = b"kimi-k2.5"
NEW = b"kimi-k2.6"
LINE = re.compile(
    rb"^(?P<prefix>[ \t]*(?:export[ \t]+)?"
    rb"(?P<key>MOONSHOT_MODEL|MOONSHOT_FAST_MODEL)[ \t]*=[ \t]*)"
    rb"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\r\n]*?)"
    rb"(?P<suffix>[ \t]*(?:(?<=[ \t'\"])\#[^\r\n]*)?)(?P<end>\r?\n)?$"
)


def process_models():
    result = subprocess.run(
        ["systemctl", "show", SERVICE, "--property=MainPID", "--value"],
        check=True, capture_output=True, text=True, timeout=15,
    )
    pid = int(result.stdout.strip())
    if pid <= 0:
        raise RuntimeError("backend MainPID is unavailable")
    entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    return {
        key: value
        for entry in entries if b"=" in entry
        for key, value in [entry.split(b"=", 1)] if key in KEYS
    }


def snapshot():
    with os.fdopen(os.open(TARGET, os.O_RDONLY | os.O_NOFOLLOW), "rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("target must be a regular file")
        return source.read(), metadata


def identity(metadata):
    return (metadata.st_dev, metadata.st_ino, metadata.st_size,
            metadata.st_mtime_ns, metadata.st_ctime_ns,
            metadata.st_uid, metadata.st_gid, metadata.st_mode)


def transform(original):
    output = []
    values = {}
    for line in original.splitlines(keepends=True):
        match = LINE.fullmatch(line)
        if match:
            raw = match["value"]
            quoted = raw[:1] in (b"'", b'"') and raw[-1:] == raw[:1]
            value = raw[1:-1] if quoted else raw
            values[match["key"].decode()] = value.decode("utf-8", errors="replace")
            if value == OLD:
                replacement = raw[:1] + NEW + raw[-1:] if quoted else NEW
                start, end = match.span("value")
                line = line[:start] + replacement + line[end:]
        output.append(line)
    return b"".join(output), values


def apply_change(original, updated, metadata):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup = TARGET.with_name(f".env.local.kimi26-{stamp}-{os.getpid()}.bak")
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as saved:
        os.fchmod(saved.fileno(), 0o600)
        os.fchown(saved.fileno(), 0, 0)
        saved.write(original)
        saved.flush()
        os.fsync(saved.fileno())
    descriptor, temporary = tempfile.mkstemp(prefix=".env.local.kimi26-", dir=TARGET.parent)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            os.fchown(destination.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(destination.fileno(), stat.S_IMODE(metadata.st_mode))
            destination.write(updated)
            destination.flush()
            os.fsync(destination.fileno())
        # Detect changes since the initial read before replacing the shared file.
        current, current_metadata = snapshot()
        if current != original or identity(current_metadata) != identity(metadata):
            raise RuntimeError("target changed during migration; refusing replacement")
        if any(value == OLD for value in process_models().values()):
            raise RuntimeError("retired model process override; refusing replacement")
        if identity(TARGET.lstat()) != identity(metadata):
            raise RuntimeError("target changed during migration; refusing replacement")
        os.replace(temporary, TARGET)
        directory = os.open(TARGET.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return str(backup)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("run as root to inspect the service and preserve a root-only backup")
    if not stat.S_ISREG(TARGET.lstat().st_mode):
        raise RuntimeError("target must be a regular file, not a symlink")
    original, metadata = snapshot()
    updated, values = transform(original)
    process = process_models()
    print(json.dumps({
        "models": {key.decode(): {
            "file_value": values.get(key.decode()),
            "process_override": key in process,
            "process_value": process[key].decode("utf-8", errors="replace") if key in process else None,
        } for key in KEYS},
        "dry_run": not args.apply,
        "would_change": updated != original,
    }), flush=True)
    if any(value == OLD for value in process.values()):
        raise RuntimeError("retired model process override; update service environment first")
    backup = None
    if args.apply and updated != original:
        backup = apply_change(original, updated, metadata)
    print(json.dumps({"changed": backup is not None, "backup_path": backup}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not expose subprocess output or environment contents on failure.
        message = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(json.dumps({"error": message}))
        raise SystemExit(1)
