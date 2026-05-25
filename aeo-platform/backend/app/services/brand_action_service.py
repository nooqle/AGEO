"""Controlled action records for the AI brand intelligence world."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.models.brand_intelligence import (
    BrandActionRecord,
    BrandIntelligenceFinding,
    BrandUserDecision,
)
from app.models.entity import Entity, EntityVisibilityScope
from app.models.session import Session
from app.models.user import User, UserRole, UserStatus
from app.ontology import OntologyRegistry, load_default_ontology
from app.ontology.schemas import ActionTypeDefinition
from app.services.brand_object_link_service import BrandObjectLinkService
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

VALID_ACTOR_TYPES = frozenset({"user", "agent", "system", "integration"})
VALID_PERMISSION_SCOPES = frozenset({"entity_read", "entity_write", "entity_execute"})
FINDING_FEEDBACK_STATUS_BY_TYPE = {
    "validate": "validated",
    "confirm": "validated",
    "accept": "validated",
    "dismiss": "dismissed",
    "reject": "dismissed",
    "correct": "observed",
    "revise": "observed",
}
SENSITIVE_PAYLOAD_KEYWORDS = (
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "jwt",
    "cookie",
    "system_prompt",
    "runtime_reminder",
    "prompt_layer_manifest",
    "raw_payload",
    "answer_text",
    "full_answer",
)
MAX_PUBLIC_PAYLOAD_TEXT_LENGTH = 500


class BrandActionService:
    """Creates and completes auditable brand intelligence actions."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        registry: OntologyRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or load_default_ontology()
        self.links = BrandObjectLinkService(db, registry=self.registry)

    async def start_action(
        self,
        *,
        entity_id: UUID,
        action_type: str,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        parent_action_record_id: UUID | None = None,
        actor_type: str = "system",
        origin_surface: str | None = None,
        origin_event_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
        decision_type: str | None = None,
        decision_key: str | None = None,
        target_object_type: str | None = None,
        target_object_id: str | None = None,
        feedback_text: str | None = None,
        strict_input_validation: bool = True,
    ) -> BrandActionRecord:
        action_definition = self.registry.require_action_type(action_type)
        normalized_actor_type = _normalize_actor_type(actor_type)
        parent_record = await self._resolve_parent_action(
            entity_id=entity_id,
            parent_action_record_id=parent_action_record_id,
        )
        if parent_record is not None:
            session_id = session_id or parent_record.session_id
            user_id = user_id or parent_record.user_id
        normalized_input_payload = _build_action_input_payload(
            input_payload=input_payload,
            entity_id=entity_id,
            user_id=user_id,
        )
        validation_warnings = self.validate_action_request(
            action_definition=action_definition,
            actor_type=normalized_actor_type,
            user_id=user_id,
            input_payload=normalized_input_payload,
        )
        effective_strict_validation = strict_input_validation or (
            normalized_actor_type == "user"
            and action_definition.permission_scope == "entity_write"
        )
        if validation_warnings and effective_strict_validation:
            raise ValueError(
                "Invalid brand action request: " + "; ".join(validation_warnings)
            )
        self._validate_confirmation_execution(
            action_definition=action_definition,
            actor_type=normalized_actor_type,
            parent_record=parent_record,
        )
        await self._authorize_action_request(
            entity_id=entity_id,
            action_definition=action_definition,
            actor_type=normalized_actor_type,
            user_id=user_id,
        )
        existing_record = await self._find_idempotent_action(
            entity_id=entity_id,
            action_type=action_type,
            actor_type=normalized_actor_type,
            origin_surface=origin_surface,
            origin_event_id=origin_event_id,
        )
        if existing_record is not None:
            return existing_record
        if validation_warnings:
            normalized_input_payload["_action_validation_warnings"] = (
                validation_warnings
            )
        cleaned_origin_surface = _clean_optional(origin_surface)
        cleaned_origin_event_id = _clean_optional(origin_event_id)
        stored_input_payload = redact_action_payload(normalized_input_payload)
        record = BrandActionRecord(
            entity_id=entity_id,
            session_id=session_id,
            user_id=user_id,
            parent_action_record_id=parent_action_record_id,
            actor_type=normalized_actor_type,
            origin_surface=cleaned_origin_surface,
            origin_event_id=cleaned_origin_event_id,
            action_type=action_type,
            status="submitted",
            requires_confirmation=action_definition.requires_confirmation,
            permission_scope=action_definition.permission_scope,
            input_payload=stored_input_payload,
        )
        self.db.add(record)
        await self.db.flush()
        await self.links.ensure_link(
            entity_id=entity_id,
            link_type="action_record_affects_brand",
            from_object_type="action_record",
            from_object_id=str(record.id),
            to_object_type="brand_entity",
            to_object_id=str(entity_id),
            source_action_record_id=record.id,
            extra_metadata={"action_type": action_type},
        )
        if _should_create_user_decision(action_definition, normalized_actor_type):
            decision = await self._create_user_decision(
                record=record,
                decision_type=decision_type,
                decision_key=decision_key,
                target_object_type=target_object_type,
                target_object_id=target_object_id,
                feedback_text=feedback_text,
                input_payload=stored_input_payload,
            )
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="user_decision_confirms_action_record",
                from_object_type="user_decision",
                from_object_id=str(decision.id),
                to_object_type="action_record",
                to_object_id=str(record.id),
                source_action_record_id=record.id,
                extra_metadata={"action_type": action_type},
            )
        return record

    async def complete_action(
        self,
        record: BrandActionRecord,
        *,
        output_payload: dict[str, Any] | None = None,
        status: str = "applied",
    ) -> BrandActionRecord:
        record.status = status
        record.output_payload = redact_action_payload(output_payload)
        record.completed_at = datetime.now(timezone.utc)
        await self._update_user_decision_for_action(
            record=record,
            status=status,
            output_payload=record.output_payload,
        )
        await self.db.flush()
        return record

    async def fail_action(
        self,
        record: BrandActionRecord,
        *,
        error_message: str,
        output_payload: dict[str, Any] | None = None,
    ) -> BrandActionRecord:
        record.status = "failed"
        record.error_message = error_message
        record.output_payload = redact_action_payload(output_payload)
        record.completed_at = datetime.now(timezone.utc)
        await self._update_user_decision_for_action(
            record=record,
            status="failed",
            output_payload=record.output_payload,
        )
        await self.db.flush()
        return record

    async def record_applied_action(
        self,
        *,
        entity_id: UUID,
        action_type: str,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        parent_action_record_id: UUID | None = None,
        actor_type: str = "system",
        origin_surface: str | None = None,
        origin_event_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        decision_type: str | None = None,
        decision_key: str | None = None,
        target_object_type: str | None = None,
        target_object_id: str | None = None,
        feedback_text: str | None = None,
        strict_input_validation: bool = True,
    ) -> BrandActionRecord:
        record = await self.start_action(
            entity_id=entity_id,
            action_type=action_type,
            session_id=session_id,
            user_id=user_id,
            parent_action_record_id=parent_action_record_id,
            actor_type=actor_type,
            origin_surface=origin_surface,
            origin_event_id=origin_event_id,
            input_payload=input_payload,
            decision_type=decision_type,
            decision_key=decision_key,
            target_object_type=target_object_type,
            target_object_id=target_object_id,
            feedback_text=feedback_text,
            strict_input_validation=strict_input_validation,
        )
        if record.completed_at is not None or record.status not in {
            "submitted",
            "running",
        }:
            return record
        return await self.complete_action(record, output_payload=output_payload)

    async def record_intelligence_finding_feedback(
        self,
        *,
        entity_id: UUID,
        finding_id: UUID,
        user_id: UUID,
        feedback_type: str,
        feedback_text: str | None = None,
        origin_surface: str = "dashboard_ontology_home",
        origin_event_id: str | None = None,
    ) -> tuple[BrandActionRecord, BrandIntelligenceFinding]:
        """Persist user feedback against one durable intelligence finding."""

        normalized_feedback_type = _normalize_finding_feedback_type(feedback_type)
        finding = await self.db.get(BrandIntelligenceFinding, finding_id)
        if finding is None or finding.entity_id != entity_id:
            raise ValueError("Intelligence finding not found")

        next_status = FINDING_FEEDBACK_STATUS_BY_TYPE[normalized_feedback_type]
        idempotency_key = _build_finding_feedback_origin_event_id(
            finding_id=finding_id,
            feedback_type=normalized_feedback_type,
            user_id=user_id,
            origin_event_id=origin_event_id,
        )
        record = await self.record_applied_action(
            entity_id=entity_id,
            action_type="record_user_feedback",
            user_id=user_id,
            actor_type="user",
            origin_surface=origin_surface,
            origin_event_id=idempotency_key,
            input_payload={
                "feedback_type": normalized_feedback_type,
                "finding_id": str(finding.id),
                "feedback_text": feedback_text or "",
            },
            output_payload={
                "feedback_type": normalized_feedback_type,
                "finding_id": str(finding.id),
                "finding_status": next_status,
            },
            decision_type=normalized_feedback_type,
            decision_key=f"intelligence_finding:{finding.id}:{normalized_feedback_type}",
            target_object_type="intelligence_finding",
            target_object_id=str(finding.id),
            feedback_text=feedback_text,
            strict_input_validation=True,
        )
        if finding.status != next_status:
            finding.status = next_status
        await self.db.flush()
        decision = (
            await self.db.execute(
                select(BrandUserDecision).where(
                    BrandUserDecision.action_record_id == record.id
                )
            )
        ).scalar_one_or_none()
        if decision is not None:
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="user_decision_updates_intelligence_finding",
                from_object_type="user_decision",
                from_object_id=str(decision.id),
                to_object_type="intelligence_finding",
                to_object_id=str(finding.id),
                source_action_record_id=record.id,
                extra_metadata={"feedback_type": normalized_feedback_type},
            )
        await self.links.ensure_link(
            entity_id=entity_id,
            link_type="action_record_handles_intelligence_finding",
            from_object_type="action_record",
            from_object_id=str(record.id),
            to_object_type="intelligence_finding",
            to_object_id=str(finding.id),
            source_action_record_id=record.id,
            extra_metadata={"feedback_type": normalized_feedback_type},
        )
        await self.db.flush()
        return record, finding

    def validate_action_request(
        self,
        *,
        action_definition: ActionTypeDefinition,
        actor_type: str,
        user_id: UUID | None,
        input_payload: dict[str, Any],
    ) -> list[str]:
        warnings: list[str] = []
        if action_definition.permission_scope not in VALID_PERMISSION_SCOPES:
            warnings.append(
                f"unsupported permission_scope={action_definition.permission_scope}"
            )
        if (
            actor_type == "user"
            and action_definition.permission_scope != "entity_read"
            and user_id is None
        ):
            warnings.append("user actor requires user_id for write or execute action")
        missing_inputs = [
            key
            for key in action_definition.required_inputs
            if not _payload_has_value(input_payload, key)
        ]
        if missing_inputs:
            warnings.append("missing required inputs: " + ", ".join(missing_inputs))
        return warnings

    async def _resolve_parent_action(
        self,
        *,
        entity_id: UUID,
        parent_action_record_id: UUID | None,
    ) -> BrandActionRecord | None:
        if parent_action_record_id is None:
            return None
        parent = await self.db.get(BrandActionRecord, parent_action_record_id)
        if parent is None:
            raise ValueError("Parent action record not found")
        if parent.entity_id != entity_id:
            raise ValueError("Parent action record belongs to another brand entity")
        return parent

    def _validate_confirmation_execution(
        self,
        *,
        action_definition: ActionTypeDefinition,
        actor_type: str,
        parent_record: BrandActionRecord | None,
    ) -> None:
        if not action_definition.requires_confirmation:
            return
        if actor_type == "user":
            return
        if parent_record is None or parent_record.actor_type != "user":
            raise PermissionError(
                "Confirmed action requires a user parent action before execution"
            )

    async def _find_idempotent_action(
        self,
        *,
        entity_id: UUID,
        action_type: str,
        actor_type: str,
        origin_surface: str | None,
        origin_event_id: str | None,
    ) -> BrandActionRecord | None:
        cleaned_origin_surface = _clean_optional(origin_surface)
        cleaned_origin_event_id = _clean_optional(origin_event_id)
        if not cleaned_origin_surface or not cleaned_origin_event_id:
            return None
        return (
            await self.db.execute(
                select(BrandActionRecord).where(
                    BrandActionRecord.entity_id == entity_id,
                    BrandActionRecord.action_type == action_type,
                    BrandActionRecord.actor_type == actor_type,
                    BrandActionRecord.origin_surface == cleaned_origin_surface,
                    BrandActionRecord.origin_event_id == cleaned_origin_event_id,
                )
            )
        ).scalar_one_or_none()

    async def _authorize_action_request(
        self,
        *,
        entity_id: UUID,
        action_definition: ActionTypeDefinition,
        actor_type: str,
        user_id: UUID | None,
    ) -> None:
        if action_definition.permission_scope not in VALID_PERMISSION_SCOPES:
            raise ValueError(
                f"Unsupported action permission_scope: "
                f"{action_definition.permission_scope}"
            )
        if actor_type in {"agent", "system", "integration"} and user_id is None:
            entity_exists = (
                await self.db.execute(select(Entity.id).where(Entity.id == entity_id))
            ).scalar_one_or_none()
            if entity_exists is None:
                raise ValueError("Brand entity not found")
            return

        if user_id is None:
            raise PermissionError(
                f"user_id is required for {action_definition.permission_scope} action"
            )

        user = await self.db.get(User, user_id)
        if user is None or not user.is_active or user.status != UserStatus.ACTIVE:
            raise PermissionError("Action actor is not an active user")

        if action_definition.permission_scope == "entity_read":
            allowed = await self._user_can_read_entity(entity_id=entity_id, user=user)
        else:
            allowed = await self._user_can_manage_entity(entity_id=entity_id, user=user)
        if not allowed:
            raise PermissionError(
                f"User is not allowed to perform {action_definition.permission_scope} "
                "on this brand entity"
            )

    async def _user_can_read_entity(self, *, entity_id: UUID, user: User) -> bool:
        if user.role == UserRole.INTERNAL_ADMIN:
            return True
        filters = [
            Entity.owner_user_id == user.id,
            Entity.sessions.any(Session.user_id == user.id),
        ]
        if user.organization_id:
            filters.append(
                and_(
                    Entity.visibility_scope == EntityVisibilityScope.ORGANIZATION,
                    Entity.organization_id == user.organization_id,
                )
            )
        exists = (
            await self.db.execute(
                select(Entity.id).where(Entity.id == entity_id, or_(*filters))
            )
        ).scalar_one_or_none()
        return exists is not None

    async def _user_can_manage_entity(self, *, entity_id: UUID, user: User) -> bool:
        if user.role == UserRole.INTERNAL_ADMIN:
            return True
        exists = (
            await self.db.execute(
                select(Entity.id).where(
                    Entity.id == entity_id,
                    or_(
                        Entity.owner_user_id == user.id,
                        and_(
                            Entity.owner_user_id.is_(None),
                            Entity.sessions.any(Session.user_id == user.id),
                        ),
                    ),
                )
            )
        ).scalar_one_or_none()
        return exists is not None

    async def _create_user_decision(
        self,
        *,
        record: BrandActionRecord,
        decision_type: str | None,
        decision_key: str | None,
        target_object_type: str | None,
        target_object_id: str | None,
        feedback_text: str | None,
        input_payload: dict[str, Any] | None,
    ) -> BrandUserDecision:
        payload = input_payload or {}
        inferred_target_type, inferred_target_id = _infer_target_object(payload)
        decision = BrandUserDecision(
            entity_id=record.entity_id,
            action_record_id=record.id,
            session_id=record.session_id,
            user_id=record.user_id,
            decision_type=(
                _clean_optional(decision_type)
                or _clean_optional(str(payload.get("feedback_type") or ""))
                or record.action_type
            ),
            decision_key=(
                _clean_optional(decision_key)
                or _clean_optional(str(payload.get("selected_option_id") or ""))
                or _clean_optional(str(payload.get("feedback_type") or ""))
                or record.action_type
            ),
            status="submitted",
            origin_surface=record.origin_surface,
            origin_event_id=record.origin_event_id,
            target_object_type=_clean_optional(target_object_type)
            or inferred_target_type
            or "brand_entity",
            target_object_id=_clean_optional(target_object_id)
            or inferred_target_id
            or str(record.entity_id),
            feedback_text=(
                _clean_optional(feedback_text)
                or _clean_optional(str(payload.get("confirmation_label") or ""))
                or _clean_optional(str(payload.get("selected_option_label") or ""))
                or ""
            ),
            input_payload=input_payload,
        )
        self.db.add(decision)
        await self.db.flush()
        return decision

    async def _update_user_decision_for_action(
        self,
        *,
        record: BrandActionRecord,
        status: str,
        output_payload: dict[str, Any] | None,
    ) -> None:
        decision = (
            await self.db.execute(
                select(BrandUserDecision).where(
                    BrandUserDecision.action_record_id == record.id
                )
            )
        ).scalar_one_or_none()
        if decision is None:
            return
        decision.status = _decision_status_from_action_status(status)
        decision.output_payload = output_payload
        await self.db.flush()


def _normalize_actor_type(value: str) -> str:
    normalized = (value or "system").strip().lower()
    if normalized not in VALID_ACTOR_TYPES:
        raise ValueError(f"Unsupported brand action actor_type: {value!r}")
    return normalized


def _build_action_input_payload(
    *,
    input_payload: dict[str, Any] | None,
    entity_id: UUID,
    user_id: UUID | None,
) -> dict[str, Any]:
    payload = dict(input_payload or {})
    payload.setdefault("brand_entity_id", str(entity_id))
    if user_id is not None:
        payload.setdefault("actor_id", str(user_id))
    return payload


def _payload_has_value(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _should_create_user_decision(
    action_definition: ActionTypeDefinition,
    actor_type: str,
) -> bool:
    return (
        actor_type == "user"
        or "user_decision" in action_definition.writes
        or "user_decision" in action_definition.target_objects
    )


def _decision_status_from_action_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"applied", "completed", "succeeded"}:
        return "applied"
    if normalized in {"failed", "error"}:
        return "failed"
    if normalized in {"reverted", "cancelled", "canceled"}:
        return "reverted"
    return "submitted"


def _infer_target_object(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    target_pairs = (
        (
            "intelligence_finding",
            payload.get("finding_id") or payload.get("intelligence_finding_id"),
        ),
        ("monitoring_plan", payload.get("monitoring_plan_id")),
        ("question_set", payload.get("question_set_id")),
        ("report_artifact", payload.get("report_id") or payload.get("artifact_id")),
    )
    for object_type, object_id in target_pairs:
        cleaned = _clean_optional(str(object_id or ""))
        if cleaned:
            return object_type, cleaned
    return None, None


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalize_finding_feedback_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in FINDING_FEEDBACK_STATUS_BY_TYPE:
        raise ValueError(
            "feedback_type must be one of: validate, dismiss, correct"
        )
    if normalized in {"confirm", "accept"}:
        return "validate"
    if normalized == "reject":
        return "dismiss"
    if normalized == "revise":
        return "correct"
    return normalized


def _build_finding_feedback_origin_event_id(
    *,
    finding_id: UUID,
    feedback_type: str,
    user_id: UUID,
    origin_event_id: str | None,
) -> str:
    raw = ":".join(
        filter(
            None,
            (
                "finding-feedback",
                str(finding_id),
                str(feedback_type),
                str(user_id),
                _clean_optional(origin_event_id),
            ),
        )
    )
    if len(raw) <= 120:
        return raw
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{raw[:103]}:{digest}"


def redact_action_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            normalized_key = key.lower()
            if any(token in normalized_key for token in SENSITIVE_PAYLOAD_KEYWORDS):
                redacted[key] = "[redacted]"
                continue
            redacted[key] = redact_action_payload(raw_value)
        return redacted
    if isinstance(value, list):
        return [redact_action_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_action_payload(item) for item in value]
    if isinstance(value, str):
        return _compact_public_payload_text(value)
    return value


def _compact_public_payload_text(value: str) -> str:
    text = str(value or "")
    if len(text) <= MAX_PUBLIC_PAYLOAD_TEXT_LENGTH:
        return text
    return text[: MAX_PUBLIC_PAYLOAD_TEXT_LENGTH - 3] + "..."
