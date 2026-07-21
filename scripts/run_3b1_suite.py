# -*- coding: utf-8 -*-
"""Frozen test entry for blueprint 3b-1 regression (T5).

Usage (from repo root or aeo-platform/backend):
  python scripts/run_3b1_suite.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "aeo-platform" / "backend"

SUITES = [
    "tests/test_topology_resolver.py",
    "tests/test_topology_gate_wiring.py",
    "tests/test_topology_p0_p1_fixes.py",
    "tests/test_node_contracts.py",
    "tests/test_nodes_amway.py",
    "tests/test_amway_flow_custom_nodes.py",
    "tests/test_flow_topology_api.py",
    "tests/test_flow_plan_context.py",
    "tests/test_topology_patch.py",  # 3c-B deterministic ops (shares topology freeze)
    "tests/test_topology_nl_compiler.py",  # 3c-C1 rule NL→ops
    "tests/test_topology_nl_llm.py",  # 3c-C2 hybrid LLM compile
]


def main() -> int:
    cmd = [sys.executable, "-m", "pytest", *SUITES, "-q", "--tb=line"]
    print("cwd=", BACKEND)
    print("cmd=", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(BACKEND))
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
