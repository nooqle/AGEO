"""Governance checks for the durable ontology world."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.models.brand_intelligence import BrandObjectLink
from app.ontology import OntologyRegistry, load_default_ontology
from app.services.brand_ontology_object_service import BrandOntologyObjectService
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_LINK_AUDIT_LIMIT = 100


class BrandOntologyGovernanceService:
    """Builds machine-readable health checks for one brand object world."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        registry: OntologyRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or load_default_ontology()
        self.objects = BrandOntologyObjectService(db, registry=self.registry)

    async def build_report(
        self,
        *,
        entity_id: UUID,
        snapshot: dict[str, Any],
        action_plan: dict[str, Any] | None = None,
        audit_links: bool = True,
    ) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        checks.extend(_snapshot_warning_checks(snapshot))
        checks.append(_object_coverage_check(self.registry, snapshot))
        checks.append(_brand_presence_check(snapshot))
        if isinstance(action_plan, dict):
            checks.append(_action_plan_safety_check(action_plan))

        link_audit = _empty_link_audit()
        if audit_links:
            link_audit = await self._audit_links(entity_id=entity_id)
            checks.append(_link_audit_check(link_audit))

        return {
            "status": _overall_status(checks),
            "checks": checks,
            "link_audit": link_audit,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _audit_links(self, *, entity_id: UUID) -> dict[str, Any]:
        rows = (
            (
                await self.db.execute(
                    select(BrandObjectLink)
                    .where(BrandObjectLink.entity_id == entity_id)
                    .order_by(desc(BrandObjectLink.created_at))
                    .limit(MAX_LINK_AUDIT_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        issues: list[dict[str, Any]] = []
        for row in rows:
            definition = self.registry.get_link_type(row.link_type)
            if definition is None:
                issues.append(_link_issue(row, "unknown_link_type"))
                continue
            if definition.from_object != row.from_object_type:
                issues.append(_link_issue(row, "from_object_type_mismatch"))
                continue
            if definition.to_object != row.to_object_type:
                issues.append(_link_issue(row, "to_object_type_mismatch"))
                continue

            source_exists = await self._object_exists(
                entity_id=entity_id,
                object_type=row.from_object_type,
                object_id=row.from_object_id,
            )
            if not source_exists:
                issues.append(_link_issue(row, "source_object_missing"))
                continue
            target_exists = await self._object_exists(
                entity_id=entity_id,
                object_type=row.to_object_type,
                object_id=row.to_object_id,
            )
            if not target_exists:
                issues.append(_link_issue(row, "target_object_missing"))

        return {
            "scanned": len(rows),
            "limit": MAX_LINK_AUDIT_LIMIT,
            "issue_count": len(issues),
            "issues": issues[:10],
        }

    async def _object_exists(
        self,
        *,
        entity_id: UUID,
        object_type: str,
        object_id: str,
    ) -> bool:
        try:
            return (
                await self.objects.get_object(
                    entity_id=entity_id,
                    object_type=object_type,
                    object_id=object_id,
                )
            ) is not None
        except Exception:
            await self._recover_read_failure()
            return False

    async def _recover_read_failure(self) -> None:
        try:
            await self.db.rollback()
        except Exception:
            return


def _snapshot_warning_checks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = [
        str(item).strip()
        for item in (snapshot.get("warnings") or [])
        if str(item).strip()
    ]
    if not warnings:
        return [
            _check(
                key="object_read_integrity",
                status="passed",
                severity="info",
                message="对象世界读取完整。",
            )
        ]
    return [
        _check(
            key="object_read_integrity",
            status="warning",
            severity="warning",
            message="对象世界存在可降级读取告警。",
            details=[{"warning": item} for item in warnings[:10]],
        )
    ]


def _object_coverage_check(
    registry: OntologyRegistry,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    expected = {
        definition.key
        for definition in registry.object_types
        if not _is_derived_read_model(definition)
    }
    present = {
        str(summary.get("object_type") or "").strip()
        for summary in (snapshot.get("object_summaries") or [])
        if isinstance(summary, dict)
    }
    missing = sorted(expected - present)
    if not missing:
        return _check(
            key="object_type_coverage",
            status="passed",
            severity="info",
            message="品牌世界声明的对象类型均已进入摘要。",
            details=[{"expected": len(expected), "present": len(present)}],
        )
    return _check(
        key="object_type_coverage",
        status="warning",
        severity="warning",
        message="部分对象类型没有进入世界摘要。",
        details=[
            {
                "expected": len(expected),
                "present": len(present),
                "missing": missing[:10],
            }
        ],
    )


def _is_derived_read_model(definition: Any) -> bool:
    source_systems = getattr(definition, "source_systems", ()) or ()
    return "BrandEvidenceDenoisingService" in set(source_systems)


def _brand_presence_check(snapshot: dict[str, Any]) -> dict[str, Any]:
    brand = snapshot.get("brand") if isinstance(snapshot.get("brand"), dict) else {}
    if str(brand.get("object_id") or "").strip():
        return _check(
            key="brand_object_presence",
            status="passed",
            severity="info",
            message="品牌主对象存在。",
        )
    return _check(
        key="brand_object_presence",
        status="failed",
        severity="blocking",
        message="品牌主对象缺失，不能构建对象世界。",
    )


def _action_plan_safety_check(action_plan: dict[str, Any]) -> dict[str, Any]:
    unsafe: list[dict[str, Any]] = []
    for raw_action in action_plan.get("recommended_actions") or []:
        if not isinstance(raw_action, dict):
            continue
        readiness = str(raw_action.get("readiness") or "").strip()
        missing_inputs = list(raw_action.get("missing_inputs") or [])
        missing_objects = list(raw_action.get("missing_objects") or [])
        requires_confirmation = bool(raw_action.get("requires_confirmation"))
        if readiness in {"ready", "ready_with_defaults"} and (
            missing_inputs or missing_objects or requires_confirmation
        ):
            unsafe.append(
                {
                    "action_key": raw_action.get("action_key"),
                    "readiness": readiness,
                    "requires_confirmation": requires_confirmation,
                    "missing_inputs": missing_inputs[:5],
                    "missing_objects": missing_objects[:5],
                }
            )
    if not unsafe:
        return _check(
            key="action_plan_safety",
            status="passed",
            severity="info",
            message="推荐动作没有越过缺输入、缺对象或需确认边界。",
        )
    return _check(
        key="action_plan_safety",
        status="failed",
        severity="blocking",
        message="行动计划中存在不应直接执行的 ready 动作。",
        details=unsafe[:10],
    )


def _link_audit_check(link_audit: dict[str, Any]) -> dict[str, Any]:
    issue_count = int(link_audit.get("issue_count") or 0)
    if issue_count <= 0:
        return _check(
            key="relationship_integrity",
            status="passed",
            severity="info",
            message="抽样关系符合品牌世界规则，并能找到两端对象。",
            details=[
                {
                    "scanned": int(link_audit.get("scanned") or 0),
                    "limit": int(link_audit.get("limit") or MAX_LINK_AUDIT_LIMIT),
                }
            ],
        )
    return _check(
        key="relationship_integrity",
        status="warning",
        severity="warning",
        message="关系审计发现破损或不合规关系。",
        details=link_audit.get("issues") or [],
    )


def _link_issue(row: BrandObjectLink, reason: str) -> dict[str, Any]:
    return {
        "link_id": str(row.id),
        "reason": reason,
        "link_type": row.link_type,
        "from_object_type": row.from_object_type,
        "from_object_id": row.from_object_id,
        "to_object_type": row.to_object_type,
        "to_object_id": row.to_object_id,
    }


def _empty_link_audit() -> dict[str, Any]:
    return {
        "scanned": 0,
        "limit": 0,
        "issue_count": 0,
        "issues": [],
    }


def _overall_status(checks: list[dict[str, Any]]) -> str:
    if any(
        check.get("status") == "failed" and check.get("severity") == "blocking"
        for check in checks
    ):
        return "blocked"
    if any(check.get("status") in {"warning", "failed"} for check in checks):
        return "degraded"
    return "healthy"


def _check(
    *,
    key: str,
    status: str,
    severity: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "status": status,
        "severity": severity,
        "message": message,
        "details": details or [],
    }
