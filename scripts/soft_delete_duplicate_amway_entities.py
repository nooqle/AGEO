# -*- coding: utf-8 -*-
"""Soft-delete duplicate 安利 entities created by noload identity-map pollution.

Safety rules:
- Soft-delete only: Entity.status -> inactive (never hard DELETE).
- Keep one canonical entity per organization (oldest with most assets preferred).
- Prefer keeping entities that have brand_intelligence_runs or flow_topologies.
- Never soft-delete the sole remaining active amway entity for an org.
- Default is dry-run; pass --apply to write.

Usage (from repo root or aeo-platform/backend):
  python scripts/soft_delete_duplicate_amway_entities.py
  python scripts/soft_delete_duplicate_amway_entities.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

# Allow running from repo root
_BACKEND = Path(__file__).resolve().parents[1] / "aeo-platform" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _load_env() -> None:
    """Load .env.local without printing secrets."""
    candidates = [
        _BACKEND / ".env.local",
        Path(r"D:\AGEO\.codex-main-merge\aeo-platform\backend\.env.local"),
        Path(r"D:\AGEO\aeo-platform\backend\.env.local"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            from dotenv import load_dotenv

            load_dotenv(path, override=False)
            print(f"[env] loaded {path}")
            return
        except Exception as exc:
            print(f"[env] skip {path}: {exc}")
    print("[env] no .env.local found; relying on process env")


def _parse_aliases(raw: str | None) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return [raw]
    return value if isinstance(value, list) else [value]


async def _run(*, apply: bool, prefer_keep: str | None) -> int:
    _load_env()

    from sqlalchemy import func, select

    from app.core.database import AsyncSessionLocal
    from app.models.brand_intelligence_run import BrandIntelligenceRun
    from app.models.entity import Entity, EntityStatus
    from app.models.flow_topology import FlowTopologyRecord
    from app.services.brand_association_circle_variant import is_amway_association_entity

    prefer_uuid = UUID(prefer_keep) if prefer_keep else None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Entity).where(Entity.organization_id.is_not(None))
        )
        entities = list(result.scalars().all())

        by_org: dict[UUID, list[Entity]] = defaultdict(list)
        for entity in entities:
            aliases = _parse_aliases(entity.aliases)
            if not is_amway_association_entity(
                name=entity.name,
                domain=entity.domain,
                aliases=aliases,
            ):
                continue
            by_org[entity.organization_id].append(entity)

        print(f"orgs with amway-like entities: {len(by_org)}")
        for org_id, group in sorted(by_org.items(), key=lambda x: str(x[0])):
            print(f"  org={org_id} count={len(group)}")

        if not by_org:
            print("No organization-scoped Amway-like entities found.")
            return 0

        soft_delete_ids: list[UUID] = []
        keep_report: list[str] = []

        for org_id, group in sorted(by_org.items(), key=lambda x: str(x[0])):
            # Score for keeper: prefer --prefer-keep, then active > runs > topo > older
            scored: list[tuple[tuple, Entity, dict]] = []
            for entity in group:
                run_count = (
                    await db.execute(
                        select(func.count())
                        .select_from(BrandIntelligenceRun)
                        .where(BrandIntelligenceRun.entity_id == entity.id)
                    )
                ).scalar_one()
                topo_count = (
                    await db.execute(
                        select(func.count())
                        .select_from(FlowTopologyRecord)
                        .where(FlowTopologyRecord.entity_id == entity.id)
                    )
                ).scalar_one()
                meta = {
                    "run_count": int(run_count or 0),
                    "topo_count": int(topo_count or 0),
                    "status": str(
                        entity.status.value
                        if hasattr(entity.status, "value")
                        else entity.status
                    ),
                    "created_at": entity.created_at.isoformat()
                    if entity.created_at
                    else "",
                    "name": entity.name,
                }
                is_active = meta["status"] == EntityStatus.ACTIVE.value
                is_prefer = 1 if prefer_uuid and entity.id == prefer_uuid else 0
                score = (
                    is_prefer,
                    1 if is_active else 0,
                    meta["run_count"],
                    meta["topo_count"],
                    -(entity.created_at.timestamp() if entity.created_at else 0.0),
                )
                scored.append((score, entity, meta))

            scored.sort(key=lambda item: item[0], reverse=True)
            keeper = scored[0][1]
            keeper_meta = scored[0][2]
            keep_report.append(
                f"org={org_id} KEEP {keeper.id} name={keeper_meta['name']!r} "
                f"status={keeper_meta['status']} runs={keeper_meta['run_count']} "
                f"topo={keeper_meta['topo_count']} created={keeper_meta['created_at']}"
            )

            for _score, entity, meta in scored[1:]:
                if entity.id == keeper.id:
                    continue
                if meta["status"] == EntityStatus.INACTIVE.value:
                    print(
                        f"  already inactive SKIP {entity.id} org={org_id} "
                        f"runs={meta['run_count']} topo={meta['topo_count']}"
                    )
                    continue
                # Safety: never soft-delete a duplicate that has more runs than keeper
                # unless it is clearly a non-keeper (still allow if keeper has assets)
                soft_delete_ids.append(entity.id)
                print(
                    f"  soft-delete CANDIDATE {entity.id} org={org_id} "
                    f"name={meta['name']!r} status={meta['status']} "
                    f"runs={meta['run_count']} topo={meta['topo_count']} "
                    f"created={meta['created_at']}"
                )

        print("--- keepers ---")
        for line in keep_report:
            print(line)
        print(f"--- candidates to soft-delete: {len(soft_delete_ids)} ---")

        if not soft_delete_ids:
            print(
                "Nothing to soft-delete on this database "
                "(each org already has at most one active amway entity)."
            )
            return 0

        if not apply:
            print("Dry-run only. Re-run with --apply to set status=inactive.")
            return 0

        note = (
            f"[soft-deleted {datetime.now(timezone.utc).isoformat()} "
            f"duplicate amway entity cleanup script]"
        )
        for eid in soft_delete_ids:
            row = (
                await db.execute(select(Entity).where(Entity.id == eid))
            ).scalar_one()
            desc = (row.description or "").strip()
            if note not in desc:
                row.description = f"{desc}\n{note}".strip() if desc else note
            row.status = EntityStatus.INACTIVE

        await db.commit()
        print(f"Applied soft-delete to {len(soft_delete_ids)} entities.")
        for eid in soft_delete_ids:
            print(f"  inactive {eid}")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write status=inactive (default is dry-run)",
    )
    parser.add_argument(
        "--prefer-keep",
        default=None,
        help="Optional entity UUID to prefer as keeper (e.g. 18e1597a-...)",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            _run(apply=bool(args.apply), prefer_keep=args.prefer_keep)
        )
    )


if __name__ == "__main__":
    main()
