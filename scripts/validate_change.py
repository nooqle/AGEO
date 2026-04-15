from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


SOURCE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".css",
    ".scss",
    ".yml",
    ".yaml",
}


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def run_windows_cmd(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return run(["cmd", "/c", command], cwd)


def print_block(title: str, body: str) -> None:
    print(f"\n=== {title} ===")
    if body.strip():
        print(body.rstrip())


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "AGENTS.md").exists() and (candidate / ".git").exists():
            return candidate
    raise RuntimeError("Could not locate repo root from current directory.")


def changed_tracked_files(repo_root: Path) -> list[Path]:
    result = run(["git", "status", "--porcelain"], repo_root)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)

    changed: list[Path] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        status = line[:2]
        path_text = line[3:].strip()
        if status == "??":
            continue
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1]
        changed.append(repo_root / path_text)
    return changed


def scan_for_question_marks(repo_root: Path, paths: list[Path]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        if path.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        if not path.exists() or not path.is_file():
            continue
        diff_result = run(
            ["git", "diff", "--unified=0", "--", str(path.relative_to(repo_root))],
            repo_root,
        )
        if diff_result.returncode != 0:
            hits.append(f"{path}: failed to diff for encoding scan")
            continue
        for raw_line in diff_result.stdout.splitlines():
            if raw_line.startswith("+++") or raw_line.startswith("@@"):
                continue
            if raw_line.startswith("+") and "???" in raw_line:
                hits.append(f"{path}: {raw_line[:160]}")
                break
    return hits


def maybe_run_backend_checks(repo_root: Path, changed: list[Path]) -> list[tuple[str, subprocess.CompletedProcess[str]]]:
    backend_py = [
        path.relative_to(repo_root)
        for path in changed
        if path.suffix == ".py" and "aeo-platform\\backend" in str(path)
    ]
    if not backend_py:
        return []

    commands = [
        ("ruff", ["python", "-m", "ruff", "check", *[str(p) for p in backend_py]]),
        ("compileall", ["python", "-m", "compileall", *[str(p) for p in backend_py]]),
    ]
    results: list[tuple[str, subprocess.CompletedProcess[str]]] = []
    for label, command in commands:
        results.append((label, run(command, repo_root)))
    return results


def maybe_run_frontend_checks(repo_root: Path, changed: list[Path]) -> list[tuple[str, subprocess.CompletedProcess[str]]]:
    frontend_changed = any(
        "frontend\\" in str(path) and path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx"}
        for path in changed
    )
    if not frontend_changed:
        return []

    frontend_root = repo_root / "frontend"
    return [
        ("tsc", run_windows_cmd("npx tsc --noEmit", frontend_root)),
        ("lint", run_windows_cmd("npm run lint", frontend_root)),
    ]


def run_pytest_targets(repo_root: Path, targets: list[str]) -> list[tuple[str, subprocess.CompletedProcess[str]]]:
    results: list[tuple[str, subprocess.CompletedProcess[str]]] = []
    for target in targets:
        results.append(
            (
                f"pytest {target}",
                run(["python", "-m", "pytest", *target.split()], repo_root),
            )
        )
    return results


def check_urls(urls: list[str]) -> list[str]:
    outcomes: list[str] = []
    for url in urls:
        try:
            with urlopen(url, timeout=10) as response:
                outcomes.append(f"{url} -> {response.status}")
        except URLError as exc:
            outcomes.append(f"{url} -> ERROR: {exc}")
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AGEO shared validation checks.")
    parser.add_argument("--pytest", action="append", default=[], help="Repeatable pytest target.")
    parser.add_argument("--url", action="append", default=[], help="Repeatable health-check URL.")
    args = parser.parse_args()

    repo_root = find_repo_root(Path.cwd())

    branch = run(["git", "branch", "--show-current"], repo_root)
    status = run(["git", "status", "--short", "--branch"], repo_root)
    print_block("worktree", f"repo={repo_root}\nbranch={branch.stdout.strip()}\n{status.stdout.strip()}")

    if repo_root.name.lower() == "ageo-main":
        print_block("guard", "Refusing to validate from D:\\AGEO-main. Use a feature worktree.")
        return 2
    if branch.stdout.strip() == "main":
        print_block("guard", "Refusing to validate feature changes on branch 'main'.")
        return 2

    changed = changed_tracked_files(repo_root)
    changed_lines = "\n".join(str(path.relative_to(repo_root)) for path in changed) or "(no tracked changes)"
    print_block("changed tracked files", changed_lines)

    encoding_hits = scan_for_question_marks(repo_root, changed)
    if encoding_hits:
        print_block("encoding scan", "Blocking hits:\n" + "\n".join(encoding_hits))
        return 3
    print_block("encoding scan", "No '???' hits in changed tracked source files.")

    failures = 0

    for label, result in maybe_run_backend_checks(repo_root, changed):
        print_block(label, (result.stdout + "\n" + result.stderr).strip())
        if result.returncode != 0:
            failures += 1

    for label, result in maybe_run_frontend_checks(repo_root, changed):
        print_block(label, (result.stdout + "\n" + result.stderr).strip())
        if result.returncode != 0:
            failures += 1

    for label, result in run_pytest_targets(repo_root, args.pytest):
        print_block(label, (result.stdout + "\n" + result.stderr).strip())
        if result.returncode != 0:
            failures += 1

    if args.url:
        print_block("health checks", "\n".join(check_urls(args.url)))

    if failures:
        print_block("result", f"FAILED with {failures} failing check group(s).")
        return 1

    print_block("result", "PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
