"""File-backed Skill Package loader for builtin skill families."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class SkillPackageManifest:
    package_key: str
    family_skill_key: str
    display_name: str
    description: str
    skill_md_path: str
    body: str

    @property
    def tool_hint(self) -> str:
        return self.description.strip()


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE_ROOT = _BACKEND_ROOT / "skill_packages"

_FAMILY_TO_PACKAGE: dict[str, str] = {
    "analysis_report_skill": "analysis-report",
    "confidence_signal_skill": "confidence-signal",
    "post_analysis_skill": "post-analysis",
}


def _parse_frontmatter(raw_text: str) -> tuple[dict[str, str], str]:
    text = raw_text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text.strip()

    closing = text.find("\n---\n", 4)
    if closing == -1:
        return {}, text.strip()

    header_text = text[4:closing]
    body = text[closing + 5 :].strip()
    metadata: dict[str, str] = {}
    for line in header_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, body


@lru_cache(maxsize=16)
def _load_package_manifest(
    package_key: str, family_skill_key: str
) -> SkillPackageManifest | None:
    skill_md_path = _PACKAGE_ROOT / package_key / "SKILL.md"
    if not skill_md_path.exists():
        return None

    raw_text = skill_md_path.read_text(encoding="utf-8")
    metadata, body = _parse_frontmatter(raw_text)
    display_name = metadata.get("name") or package_key
    description = metadata.get("description") or body.splitlines()[0].strip()
    return SkillPackageManifest(
        package_key=package_key,
        family_skill_key=family_skill_key,
        display_name=display_name,
        description=description,
        skill_md_path=str(skill_md_path),
        body=body,
    )


class SkillPackageService:
    """Loads package-style skill guidance for builtin families."""

    def resolve_family_package(
        self, family_skill_key: str
    ) -> SkillPackageManifest | None:
        package_key = _FAMILY_TO_PACKAGE.get(family_skill_key)
        if not package_key:
            return None
        return _load_package_manifest(package_key, family_skill_key)


skill_package_service = SkillPackageService()
