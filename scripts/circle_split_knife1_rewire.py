# -*- coding: utf-8 -*-
"""Rewire AmwayAssociationCircleDashboardViews to use amway-circle pure modules."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWS = (
    ROOT
    / "frontend"
    / "src"
    / "components"
    / "dashboard"
    / "AmwayAssociationCircleDashboardViews.tsx"
)

REMOVE_FUNCS = {
    "buildAssociationMapGroups",
    "compareAssociationNodesForPriority",
    "normalizeAssociationNodeDisplay",
    "classifyAssociationNode",
    "scoreNumber",
    "nodeClosenessValue",
    "nodeDistanceValue",
    "nodeEvidenceCount",
    "nodeCountMode",
    "nodeCountPhrase",
    "nodeCountMetricLabel",
    "nodeCountShortUnit",
    "nodePlatformCount",
    "isCompetitorNode",
    "isProtectedEvidenceAssetNode",
    "isRiskNodeForMap",
    "buildAssociationProjection",
    "normalizeCenterTerms",
    "sampleQuestionCount",
    "sampleAnswerCount",
    "samplePlatformCount",
    "readLiveExtractionStats",
    "firstSampleNumber",
    "toNumber",
    "platformLabel",
}

IMPORT_BLOCK = """import {
  DEFAULT_CENTER_TERMS,
  DEFAULT_OVERVIEW_HIGHLIGHT_LIMIT,
  FOCUSED_TRACK_LABEL_LIMIT,
  buildAssociationMapGroups,
  buildAssociationProjection,
  classifyAssociationNode,
  isCompetitorNode,
  isProtectedEvidenceAssetNode,
  isRiskNodeForMap,
  nodeClosenessValue,
  nodeCountMetricLabel,
  nodeCountMode,
  nodeCountPhrase,
  nodeCountShortUnit,
  nodeDistanceValue,
  nodeEvidenceCount,
  nodePlatformCount,
  normalizeAssociationNodeDisplay,
  normalizeCenterTerms,
  platformLabel,
  readLiveExtractionStats,
  sampleAnswerCount,
  samplePlatformCount,
  sampleQuestionCount,
  scoreNumber,
  type AssociationMapGroup,
  type AssociationMapGroupKey,
  type AssociationMapMode,
  type AssociationNodeFilterKey,
  type OrbitDistanceBand,
} from './amway-circle';

// Re-export pure helpers for existing importers of this shell file.
export {
  buildAssociationMapGroups,
  buildAssociationProjection,
  normalizeCenterTerms,
  sampleAnswerCount,
};
"""


def remove_function(src: str, name: str) -> str:
    # Match export function name or function name
    pattern = re.compile(
        rf"^(export )?function {re.escape(name)}\b",
        re.M,
    )
    m = pattern.search(src)
    if not m:
        print(f"  skip missing function {name}")
        return src
    start = m.start()
    # find opening brace of function body
    i = m.end()
    while i < len(src) and src[i] != "{":
        i += 1
    if i >= len(src):
        raise RuntimeError(f"no body for {name}")
    depth = 0
    j = i
    while j < len(src):
        ch = src[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                j += 1
                break
        j += 1
    # include trailing newlines
    while j < len(src) and src[j] in "\r\n":
        j += 1
    print(f"  remove {name} chars {start}:{j}")
    return src[:start] + src[j:]


def remove_type_block(src: str, name: str) -> str:
    pattern = re.compile(rf"^type {re.escape(name)}\b[^=]*=.*?;\n", re.M | re.S)
    # single-line types first
    m = re.search(rf"^type {re.escape(name)} = .*;\n", src, re.M)
    if m:
        print(f"  remove type {name}")
        return src[: m.start()] + src[m.end() :]
    # multi-line type NodeCountSource
    m = re.search(
        rf"^type {re.escape(name)} = [\s\S]*?^}};\n",
        src,
        re.M,
    )
    if m:
        print(f"  remove type block {name}")
        return src[: m.start()] + src[m.end() :]
    print(f"  skip missing type {name}")
    return src


def remove_const(src: str, name: str) -> str:
    m = re.search(rf"^const {re.escape(name)} = .*;\n", src, re.M)
    if not m:
        print(f"  skip missing const {name}")
        return src
    print(f"  remove const {name}")
    return src[: m.start()] + src[m.end() :]


def remove_interface(src: str, name: str) -> str:
    m = re.search(rf"^interface {re.escape(name)} \{{[\s\S]*?^\}}\n", src, re.M)
    if not m:
        print(f"  skip missing interface {name}")
        return src
    print(f"  remove interface {name}")
    return src[: m.start()] + src[m.end() :]


def main() -> None:
    text = VIEWS.read_text(encoding="utf-8")
    # strip BOM if present
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    # insert import after ontology import block
    anchor = "} from '@/types/ontology';\n"
    if anchor not in text:
        raise SystemExit("ontology import anchor not found")
    if "./amway-circle" not in text:
        text = text.replace(anchor, anchor + "\n" + IMPORT_BLOCK + "\n", 1)

    # remove local types/constants that moved
    for t in (
        "AssociationMapGroupKey",
        "AssociationMapMode",
        "OrbitDistanceBand",
        "AssociationNodeFilterKey",
    ):
        text = remove_type_block(text, t)
    text = remove_interface(text, "AssociationMapGroup")
    # AssociationNodeFilterOption stays local if present
    text = remove_const(text, "DEFAULT_OVERVIEW_HIGHLIGHT_LIMIT")
    text = remove_const(text, "FOCUSED_TRACK_LABEL_LIMIT")
    text = remove_const(text, "DEFAULT_CENTER_TERMS")
    text = remove_type_block(text, "NodeCountSource")

    # remove functions (repeat until stable order)
    for name in sorted(REMOVE_FUNCS, key=len, reverse=True):
        text = remove_function(text, name)

    # collapse excessive blank lines
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    VIEWS.write_text(text, encoding="utf-8")
    lines = len(text.splitlines())
    print(f"wrote {VIEWS} lines={lines}")


if __name__ == "__main__":
    main()
