"""Brand Space board runtime and graph-update service."""

from __future__ import annotations

import difflib
import logging
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_intelligence import (
    BrandReportVersion,
    BrandIntelligenceQuestion,
    BrandPlatformAnswer,
)
from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.brand_space import (
    BoardArtifact,
    BoardNodeRun,
    BoardRun,
    BoardRuntimeEvent,
    GraphPatch,
    GraphUpdate,
    ReportGuardrailResult,
)
from app.models.entity import Entity
from app.models.snapshot import AnalysisSnapshot
from app.models.user import User
from app.services.brand_intelligence_run_service import BrandIntelligenceRunService
from app.services.brand_knowledge_graph_projection_service import (
    BrandKnowledgeGraphProjectionService,
)
from app.services.entity_service import EntityService


logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


BOARD_EDGES: list[dict[str, Any]] = [
    {"id": "edge-seed-question", "from": "brand-seed", "to": "question-set", "active": True},
    {"id": "edge-question-platform", "from": "question-set", "to": "platform-rack", "active": True},
    {"id": "edge-platform-normalize", "from": "platform-rack", "to": "answer-normalize", "active": True},
    {"id": "edge-platform-match", "from": "platform-rack", "to": "entity-match", "active": True},
    {"id": "edge-normalize-patch", "from": "answer-normalize", "to": "graph-patch", "active": True},
    {"id": "edge-match-patch", "from": "entity-match", "to": "graph-patch", "active": True},
    {"id": "edge-patch-update", "from": "graph-patch", "to": "graph-update", "active": True},
    {"id": "edge-review-update", "from": "anomaly-review", "to": "graph-update", "active": False, "dashed": True},
]

NODE_TEMPLATES: list[dict[str, Any]] = [
    {
        "node_id": "brand-seed",
        "node_type": "input",
        "title": "品牌实体种子",
        "subtitle": "实体词表与品牌基础资料",
        "position": {"x": 10, "y": 38},
        "artifact_keys": ["artifact-lexicon"],
    },
    {
        "node_id": "question-set",
        "node_type": "prepare",
        "title": "问题集",
        "subtitle": "人群画像 + 场景问题",
        "position": {"x": 30, "y": 38},
        "artifact_keys": ["artifact-questions"],
    },
    {
        "node_id": "platform-rack",
        "node_type": "fetch",
        "title": "AI 平台抓取组",
        "subtitle": "四个平台并行抓取",
        "position": {"x": 55, "y": 36},
        "artifact_keys": ["artifact-raw-answers"],
    },
    {
        "node_id": "answer-normalize",
        "node_type": "extract",
        "title": "回答标准化",
        "subtitle": "去重、清洗、结构化",
        "position": {"x": 78, "y": 31},
        "artifact_keys": ["artifact-parsed-answers"],
    },
    {
        "node_id": "entity-match",
        "node_type": "extract",
        "title": "实体匹配",
        "subtitle": "匹配实体词表",
        "position": {"x": 78, "y": 49},
        "artifact_keys": ["artifact-relation-set"],
    },
    {
        "node_id": "graph-patch",
        "node_type": "extract",
        "title": "图谱补丁",
        "subtitle": "新增、更新、连接",
        "position": {"x": 78, "y": 67},
        "artifact_keys": ["artifact-patch-set"],
    },
    {
        "node_id": "anomaly-review",
        "node_type": "review",
        "title": "异常审阅",
        "subtitle": "新实体 + 低置信关系",
        "position": {"x": 55, "y": 88},
        "artifact_keys": ["artifact-review-list"],
    },
    {
        "node_id": "graph-update",
        "node_type": "graph_update",
        "title": "品牌图谱更新",
        "subtitle": "生成圈层状态更新",
        "position": {"x": 78, "y": 88},
        "artifact_keys": ["artifact-graph-update"],
    },
]

PLATFORM_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "fetch-chatgpt",
        "platformKey": "chatgpt",
        "label": "ChatGPT 抓取",
        "model": "gpt-4o · 网页",
        "progress": 72,
        "answers": 256,
        "failures": 0,
    },
    {
        "id": "fetch-deepseek",
        "platformKey": "deepseek",
        "label": "DeepSeek 抓取",
        "model": "deepseek-v3 · 网页",
        "progress": 54,
        "answers": 228,
        "failures": 0,
    },
    {
        "id": "fetch-kimi",
        "platformKey": "kimi",
        "label": "Kimi 抓取",
        "model": "kimi-k2 · 网页",
        "progress": 38,
        "answers": 198,
        "failures": 2,
    },
    {
        "id": "fetch-doubao",
        "platformKey": "doubao",
        "label": "豆包抓取",
        "model": "doubao-pro · 网页",
        "progress": 81,
        "answers": 312,
        "failures": 1,
    },
]

EXPLICIT_COMPETITOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"替代|替换|可选|不如选|更推荐|相比之下|对比.*(选择|推荐)|竞品|竞争"),
    re.compile(r"alternative|instead of|versus|vs\.?|better than|competitor", re.IGNORECASE),
)

POSITIVE_HEALTH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"健康管理|营养补充|免疫|纽崔莱|蛋白|维生素|膳食补充|家庭健康"),
)

RISK_SIGNAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"监管|顾虑|质疑|争议|投诉|价格|直销|安全|副作用|负面|风险"),
)

SCENARIO_SIGNAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"职场|熬夜|精力|运动|备孕|银发|中老年|家庭"),
)

COMPETITOR_CANDIDATES: tuple[dict[str, str], ...] = (
    {"id": "by-health", "label": "汤臣倍健"},
    {"id": "swisse", "label": "Swisse"},
    {"id": "gnc", "label": "GNC"},
    {"id": "blackmores", "label": "Blackmores"},
)

POSITIVE_LEXICON_TYPES = {
    "brandstrategy",
    "community",
    "digitaltool",
    "evidenceasset",
    "flowerdimension",
    "fourvalue",
    "healthylifestyle",
    "marketcontext",
    "productcategory",
    "productfeature",
    "product_line",
    "solution",
    "subbrand",
    "touchpoint",
}

SUPPORTS_LEXICON_TYPES = {
    "evidenceasset",
    "productcategory",
    "productfeature",
    "product_line",
    "subbrand",
}

RISK_LEXICON_TYPES = {"risk_signal", "risklabel"}
COMPETITOR_LEXICON_TYPES = {"competitor", "competitor_candidate"}
LEXICON_SPLIT_PATTERN = re.compile(r"[、,，/|;；\s]+")

REAL_EXECUTION_MODE = "real"
SCAFFOLD_EXECUTION_MODE = "scaffold"
REAL_SYNC_MIN_INTERVAL_SECONDS = 30

REVIEWABLE_PATCH_STATUSES = {"needs_review", "blocked"}
IMMUTABLE_PATCH_STATUSES = {"auto_applied", "accepted", "rejected"}

REAL_RUN_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

REAL_RUN_STATUS_TO_BOARD_STATUS = {
    "not_started": "idle",
    "planning_questions": "running",
    "waiting_scope_confirmation": "paused",
    "fetching_answers": "running",
    "waiting_takeover": "paused",
    "analyzing_metrics": "running",
    "building_world": "running",
    "generating_recommendations": "running",
    "waiting_user": "paused",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "stopped",
}

REAL_RUN_STATUS_EVENT_MESSAGES = {
    "not_started": ("runtime_waiting", "info", "真实运行已创建，等待启动后台执行器。"),
    "planning_questions": ("runtime_stage_changed", "info", "正在生成问题集与样本范围。"),
    "waiting_scope_confirmation": ("runtime_waiting_user", "warning", "运行需要用户确认问题范围。"),
    "fetching_answers": ("runtime_stage_changed", "info", "四个平台抓取正在执行。"),
    "waiting_takeover": ("runtime_waiting_user", "warning", "运行等待平台接管或登录确认。"),
    "analyzing_metrics": ("runtime_stage_changed", "info", "正在清洗回答并计算指标。"),
    "building_world": ("runtime_stage_changed", "info", "正在写入品牌对象图谱。"),
    "generating_recommendations": ("runtime_stage_changed", "info", "正在生成图谱更新解读基础材料。"),
    "waiting_user": ("runtime_waiting_user", "warning", "运行暂停在用户确认节点。"),
    "completed": ("runtime_completed", "success", "真实运行已完成。"),
    "failed": ("runtime_failed", "error", "真实运行失败。"),
    "cancelled": ("runtime_cancelled", "warning", "真实运行已取消。"),
}


@dataclass(frozen=True)
class EntityLexiconEntry:
    entity_id: str
    label: str
    entity_type: str
    aliases: tuple[str, ...] = ()

    @property
    def normalized_type(self) -> str:
        return re.sub(r"[^a-z0-9_]+", "", self.entity_type.lower())

    @property
    def terms(self) -> tuple[str, ...]:
        seen: set[str] = set()
        terms: list[str] = []
        for term in (self.label, *self.aliases):
            normalized = str(term or "").strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            terms.append(normalized)
        return tuple(terms)

    def to_payload(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "label": self.label,
            "type": self.entity_type,
            "aliases": list(self.aliases),
        }


class GraphPatchBuilderService:
    """Build graph patches from persisted questions and captured platform answers.

    The first MVP slice stays deterministic on purpose: it turns durable A3/A4
    outputs into reviewable patches without introducing another LLM extraction
    path. Later slices can replace the signal matchers with entity-lexicon
    matching while keeping the same GraphPatch contract.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(
        self,
        *,
        entity: Entity,
        board_run: BoardRun,
        intelligence_run: BrandIntelligenceRun,
        graph_update: GraphUpdate,
        current_graph_projection: dict[str, Any] | None = None,
        allocate_graph_zone: Callable[..., dict[str, Any]],
        detect_competitor_context: Callable[..., dict[str, Any]],
    ) -> list[GraphPatch]:
        answers = await self._answers_for_run(
            entity_id=entity.id,
            intelligence_run=intelligence_run,
        )
        question_lookup = await self._question_lookup(
            entity_id=entity.id,
            intelligence_run=intelligence_run,
            answers=answers,
        )
        lexicon_entries = self._lexicon_entries(board_run=board_run, entity=entity)
        graph_index = self._graph_projection_index(current_graph_projection or {})
        if not answers:
            return [
                self._insufficient_data_patch(
                    entity=entity,
                    graph_update=graph_update,
                    board_run=board_run,
                )
            ]

        patches: list[GraphPatch] = []
        positive_entry_matches = self._matched_entries(
            entries=[
                entry
                for entry in lexicon_entries
                if entry.normalized_type in POSITIVE_LEXICON_TYPES
            ],
            answers=answers,
            question_lookup=question_lookup,
        )
        has_positive_signal = bool(positive_entry_matches)
        if positive_entry_matches:
            patches.extend(
                self._positive_entity_patches(
                    entity=entity,
                    graph_update=graph_update,
                    matches=positive_entry_matches,
                    question_lookup=question_lookup,
                    graph_index=graph_index,
                    allocate_graph_zone=allocate_graph_zone,
                )
            )
        else:
            positive_answers = self._answers_matching(
                answers=answers,
                question_lookup=question_lookup,
                patterns=POSITIVE_HEALTH_PATTERNS,
            )
            if positive_answers:
                has_positive_signal = True
                patches.append(
                    self._positive_health_patch(
                        entity=entity,
                        graph_update=graph_update,
                        answers=positive_answers,
                        question_lookup=question_lookup,
                        allocate_graph_zone=allocate_graph_zone,
                    )
                )

        risk_entry_matches = self._matched_entries(
            entries=[
                entry
                for entry in lexicon_entries
                if entry.normalized_type in RISK_LEXICON_TYPES
            ],
            answers=answers,
            question_lookup=question_lookup,
        )
        risk_answers = self._answer_union(
            self._answers_matching(
                answers=answers,
                question_lookup=question_lookup,
                patterns=RISK_SIGNAL_PATTERNS,
            ),
            *[entry_answers for _, entry_answers in risk_entry_matches],
        )
        if risk_answers:
            risk_entry = risk_entry_matches[0][0] if risk_entry_matches else None
            patches.append(
                self._risk_patch(
                    entity=entity,
                    graph_update=graph_update,
                    answers=risk_answers,
                    question_lookup=question_lookup,
                    lexicon_entry=risk_entry,
                    graph_index=graph_index,
                    allocate_graph_zone=allocate_graph_zone,
                )
            )

        competitor_entries = [
            entry
            for entry in lexicon_entries
            if entry.normalized_type in COMPETITOR_LEXICON_TYPES
        ] or [
            EntityLexiconEntry(
                entity_id=str(candidate["id"]),
                label=str(candidate["label"]),
                entity_type="Competitor",
            )
            for candidate in COMPETITOR_CANDIDATES
        ]

        patches.extend(
            self._competitor_patches(
                entity=entity,
                graph_update=graph_update,
                answers=answers,
                question_lookup=question_lookup,
                candidates=competitor_entries,
                graph_index=graph_index,
                allocate_graph_zone=allocate_graph_zone,
                detect_competitor_context=detect_competitor_context,
            )
        )

        scenario_answers = self._answers_matching(
            answers=answers,
            question_lookup=question_lookup,
            patterns=SCENARIO_SIGNAL_PATTERNS,
        )
        if scenario_answers and not has_positive_signal:
            patches.append(
                self._weak_scenario_patch(
                    entity=entity,
                    graph_update=graph_update,
                    answers=scenario_answers,
                    question_lookup=question_lookup,
                    allocate_graph_zone=allocate_graph_zone,
                )
            )

        if patches:
            return patches
        return [
            self._insufficient_data_patch(
                entity=entity,
                graph_update=graph_update,
                board_run=board_run,
            )
        ]

    async def _answers_for_run(
        self,
        *,
        entity_id: UUID,
        intelligence_run: BrandIntelligenceRun,
    ) -> list[BrandPlatformAnswer]:
        conditions = [
            BrandPlatformAnswer.entity_id == entity_id,
            BrandPlatformAnswer.success.is_(True),
        ]
        if intelligence_run.origin_session_id is not None:
            conditions.append(
                BrandPlatformAnswer.session_id == intelligence_run.origin_session_id
            )
        result = await self.db.execute(
            select(BrandPlatformAnswer)
            .where(*conditions)
            .order_by(desc(BrandPlatformAnswer.captured_at), desc(BrandPlatformAnswer.created_at))
            .limit(200)
        )
        return list(result.scalars().all())

    async def _question_lookup(
        self,
        *,
        entity_id: UUID,
        intelligence_run: BrandIntelligenceRun,
        answers: list[BrandPlatformAnswer],
    ) -> dict[str, str]:
        lookup: dict[str, str] = {}
        object_ids = {
            answer.question_object_id
            for answer in answers
            if answer.question_object_id is not None
        }
        if object_ids:
            result = await self.db.execute(
                select(BrandIntelligenceQuestion).where(
                    BrandIntelligenceQuestion.id.in_(object_ids)
                )
            )
            for question in result.scalars().all():
                lookup[str(question.id)] = question.question_text
                lookup[question.question_id] = question.question_text

        question_ids = {
            answer.question_id
            for answer in answers
            if answer.question_id and answer.question_id not in lookup
        }
        if question_ids:
            conditions = [
                BrandIntelligenceQuestion.entity_id == entity_id,
                BrandIntelligenceQuestion.question_id.in_(question_ids),
            ]
            if intelligence_run.origin_session_id is not None:
                conditions.append(
                    BrandIntelligenceQuestion.session_id
                    == intelligence_run.origin_session_id
                )
            result = await self.db.execute(
                select(BrandIntelligenceQuestion).where(*conditions)
            )
            for question in result.scalars().all():
                lookup[str(question.id)] = question.question_text
                lookup[question.question_id] = question.question_text
        return lookup

    def _answers_matching(
        self,
        *,
        answers: list[BrandPlatformAnswer],
        question_lookup: dict[str, str],
        patterns: tuple[re.Pattern[str], ...],
    ) -> list[BrandPlatformAnswer]:
        return [
            answer
            for answer in answers
            if any(
                pattern.search(self._combined_text(answer, question_lookup))
                for pattern in patterns
            )
        ]

    def _lexicon_entries(
        self,
        *,
        board_run: BoardRun,
        entity: Entity,
    ) -> list[EntityLexiconEntry]:
        input_scope = board_run.input_scope or {}
        raw_entries = (
            input_scope.get("entity_lexicon")
            or input_scope.get("lexicon")
            or input_scope.get("brand_entity_lexicon")
            or []
        )
        entries: list[EntityLexiconEntry] = [
            EntityLexiconEntry(
                entity_id=str(entity.id),
                label=entity.name,
                entity_type="CenterBrand",
                aliases=tuple(
                    alias
                    for alias in [entity.domain, f"{entity.name}品牌"]
                    if alias
                ),
            )
        ]
        if not isinstance(raw_entries, list):
            return entries
        seen: set[str] = {entity.name.lower()}
        for row in raw_entries:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or row.get("entity_name") or row.get("name") or "").strip()
            if not label:
                continue
            entity_id = str(row.get("entity_id") or row.get("id") or label).strip()
            entity_type = str(row.get("type") or row.get("entity_type") or "Concept").strip()
            aliases = self._alias_terms(row)
            identity = f"{entity_id.lower()}:{label.lower()}"
            if identity in seen:
                continue
            seen.add(identity)
            entries.append(
                EntityLexiconEntry(
                    entity_id=entity_id,
                    label=label,
                    entity_type=entity_type,
                    aliases=aliases,
                )
            )
        return entries

    @staticmethod
    def _alias_terms(row: dict[str, Any]) -> tuple[str, ...]:
        raw_aliases = (
            row.get("aliases")
            or row.get("alias")
            or row.get("trigger_terms")
            or row.get("terms")
            or row.get("triggers")
            or []
        )
        if isinstance(raw_aliases, str):
            candidates = LEXICON_SPLIT_PATTERN.split(raw_aliases)
        elif isinstance(raw_aliases, list):
            candidates = []
            for item in raw_aliases:
                if isinstance(item, str):
                    candidates.extend(LEXICON_SPLIT_PATTERN.split(item))
                else:
                    candidates.append(str(item))
        else:
            candidates = [str(raw_aliases)] if raw_aliases else []
        aliases: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            alias = str(candidate or "").strip()
            if not alias:
                continue
            lowered = alias.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            aliases.append(alias)
        return tuple(aliases)

    def _matched_entries(
        self,
        *,
        entries: list[EntityLexiconEntry],
        answers: list[BrandPlatformAnswer],
        question_lookup: dict[str, str],
    ) -> list[tuple[EntityLexiconEntry, list[BrandPlatformAnswer]]]:
        matches: list[tuple[EntityLexiconEntry, list[BrandPlatformAnswer]]] = []
        for entry in entries:
            matched_answers = [
                answer
                for answer in answers
                if self._answer_mentions_entry(
                    answer=answer,
                    question_lookup=question_lookup,
                    entry=entry,
                )
            ]
            if matched_answers:
                matches.append((entry, matched_answers))
        return sorted(
            matches,
            key=lambda item: (len(item[1]), len({answer.platform for answer in item[1]})),
            reverse=True,
        )

    def _answer_mentions_entry(
        self,
        *,
        answer: BrandPlatformAnswer,
        question_lookup: dict[str, str],
        entry: EntityLexiconEntry,
    ) -> bool:
        text = self._combined_text(answer, question_lookup)
        return any(self._contains_term(text, term) for term in entry.terms)

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        if not term:
            return False
        if term.isascii():
            return term.lower() in (text or "").lower()
        return term in (text or "")

    @staticmethod
    def _answer_union(
        *answer_groups: list[BrandPlatformAnswer],
    ) -> list[BrandPlatformAnswer]:
        seen: set[UUID] = set()
        merged: list[BrandPlatformAnswer] = []
        for answers in answer_groups:
            for answer in answers:
                if answer.id in seen:
                    continue
                seen.add(answer.id)
                merged.append(answer)
        return merged

    @staticmethod
    def _graph_projection_index(graph_projection: dict[str, Any]) -> dict[str, set[str]]:
        labels: set[str] = set()
        ids: set[str] = set()
        for node in graph_projection.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "").strip()
            label = str(node.get("label") or node.get("name") or "").strip()
            if node_id:
                ids.add(node_id.lower())
            if label:
                labels.add(label.lower())
        return {"ids": ids, "labels": labels}

    @staticmethod
    def _existing_graph_match(
        *,
        entry: EntityLexiconEntry,
        graph_index: dict[str, set[str]],
    ) -> bool:
        ids = graph_index.get("ids") or set()
        labels = graph_index.get("labels") or set()
        return entry.entity_id.lower() in ids or entry.label.lower() in labels

    @staticmethod
    def _relation_type_for_entry(entry: EntityLexiconEntry) -> str:
        if entry.normalized_type in SUPPORTS_LEXICON_TYPES:
            return "supports"
        return "associated_with"

    def _positive_entity_patches(
        self,
        *,
        entity: Entity,
        graph_update: GraphUpdate,
        matches: list[tuple[EntityLexiconEntry, list[BrandPlatformAnswer]]],
        question_lookup: dict[str, str],
        graph_index: dict[str, set[str]],
        allocate_graph_zone: Callable[..., dict[str, Any]],
    ) -> list[GraphPatch]:
        patches: list[GraphPatch] = []
        for entry, entry_answers in matches[:3]:
            relation_type = self._relation_type_for_entry(entry)
            strength = self._score_from_answers(
                entry_answers,
                base=74 if relation_type == "supports" else 70,
                per_answer=3,
                per_platform=4,
                cap=92,
            )
            confidence = self._confidence_from_answers(entry_answers, base=0.68)
            allocation = allocate_graph_zone(
                connection_strength=strength,
                sentiment_or_risk_score=8.0,
                relation_type=relation_type,
                confidence=confidence,
            )
            graph_match = self._existing_graph_match(
                entry=entry,
                graph_index=graph_index,
            )
            patches.append(
                GraphPatch(
                    graph_update_id=graph_update.id,
                    entity_id=entity.id,
                    patch_type="add_entity_relation",
                    status=allocation["status"],
                    title=f"连接{entry.label}关系",
                    description=f"真实回答命中词表实体“{entry.label}”，生成 {relation_type} 关系候选。",
                    affected_object_type=entry.entity_type,
                    affected_object_id=entry.entity_id,
                    relation_type=relation_type,
                    connection_strength=strength,
                    confidence=confidence,
                    sentiment_or_risk_score=8.0,
                    after_payload={
                        "zone": allocation["zone"],
                        "label": entry.label,
                        "lexicon_entry": entry.to_payload(),
                        "existing_graph_match": graph_match,
                    },
                    score_breakdown={
                        "connection_strength": strength,
                        "sentiment": 8.0,
                        "confidence": confidence,
                        "allocation_reason": allocation["reason"],
                        "matched_answer_count": len(entry_answers),
                        "matched_platform_count": len(
                            {answer.platform for answer in entry_answers if answer.platform}
                        ),
                    },
                    evidence_refs=self._evidence_refs(
                        answers=entry_answers,
                        question_lookup=question_lookup,
                        polarity="positive",
                        matched_entry=entry,
                    ),
                )
            )
        return patches

    def _positive_health_patch(
        self,
        *,
        entity: Entity,
        graph_update: GraphUpdate,
        answers: list[BrandPlatformAnswer],
        question_lookup: dict[str, str],
        allocate_graph_zone: Callable[..., dict[str, Any]],
    ) -> GraphPatch:
        strength = self._score_from_answers(answers, base=76, per_answer=3, per_platform=4, cap=92)
        confidence = self._confidence_from_answers(answers, base=0.68)
        allocation = allocate_graph_zone(
            connection_strength=strength,
            sentiment_or_risk_score=8.1,
            relation_type="associated_with",
            confidence=confidence,
        )
        platforms = self._platform_label(answers)
        return GraphPatch(
            graph_update_id=graph_update.id,
            entity_id=entity.id,
            patch_type="update_strength",
            status=allocation["status"],
            title="增强健康管理关系",
            description=f"{platforms} 的真实回答中出现健康管理、营养补充或家庭健康正向证据。",
            affected_object_type="brand_concept",
            affected_object_id="health-management",
            relation_type="associated_with",
            connection_strength=strength,
            confidence=confidence,
            sentiment_or_risk_score=8.1,
            after_payload={"zone": allocation["zone"], "label": "健康管理"},
            score_breakdown={
                "connection_strength": strength,
                "sentiment": 8.1,
                "confidence": confidence,
                "allocation_reason": allocation["reason"],
            },
            evidence_refs=self._evidence_refs(
                answers=answers,
                question_lookup=question_lookup,
                polarity="positive",
            ),
        )

    def _risk_patch(
        self,
        *,
        entity: Entity,
        graph_update: GraphUpdate,
        answers: list[BrandPlatformAnswer],
        question_lookup: dict[str, str],
        lexicon_entry: EntityLexiconEntry | None,
        graph_index: dict[str, set[str]],
        allocate_graph_zone: Callable[..., dict[str, Any]],
    ) -> GraphPatch:
        strength = self._score_from_answers(answers, base=58, per_answer=4, per_platform=5, cap=78)
        confidence = self._confidence_from_answers(answers, base=0.62)
        allocation = allocate_graph_zone(
            connection_strength=strength,
            sentiment_or_risk_score=4.2,
            relation_type="risk_related",
            confidence=confidence,
        )
        label = lexicon_entry.label if lexicon_entry else "监管与价格顾虑"
        affected_object_id = lexicon_entry.entity_id if lexicon_entry else "regulatory-price-risk"
        affected_object_type = lexicon_entry.entity_type if lexicon_entry else "risk_signal"
        return GraphPatch(
            graph_update_id=graph_update.id,
            entity_id=entity.id,
            patch_type="add_risk_relation",
            status=allocation["status"],
            title=f"{label}进入风险层",
            description="真实回答出现监管、价格、直销或安全顾虑，情绪/风险闸门阻止其进入内圈。",
            affected_object_type=affected_object_type,
            affected_object_id=affected_object_id,
            relation_type="risk_related",
            connection_strength=strength,
            confidence=confidence,
            sentiment_or_risk_score=4.2,
            after_payload={
                "zone": allocation["zone"],
                "label": label,
                "lexicon_entry": lexicon_entry.to_payload() if lexicon_entry else None,
                "existing_graph_match": self._existing_graph_match(
                    entry=lexicon_entry,
                    graph_index=graph_index,
                )
                if lexicon_entry
                else False,
            },
            score_breakdown={
                "connection_strength": strength,
                "sentiment": 4.2,
                "confidence": confidence,
                "allocation_reason": allocation["reason"],
            },
            evidence_refs=self._evidence_refs(
                answers=answers,
                question_lookup=question_lookup,
                polarity="questioning",
                matched_entry=lexicon_entry,
            ),
        )

    def _competitor_patches(
        self,
        *,
        entity: Entity,
        graph_update: GraphUpdate,
        answers: list[BrandPlatformAnswer],
        question_lookup: dict[str, str],
        candidates: list[EntityLexiconEntry],
        graph_index: dict[str, set[str]],
        allocate_graph_zone: Callable[..., dict[str, Any]],
        detect_competitor_context: Callable[..., dict[str, Any]],
    ) -> list[GraphPatch]:
        patches: list[GraphPatch] = []
        for candidate in candidates:
            candidate_answers = [
                answer
                for answer in answers
                if self._answer_mentions_entry(
                    answer=answer,
                    question_lookup=question_lookup,
                    entry=candidate,
                )
            ]
            if not candidate_answers:
                continue
            confidence = self._confidence_from_answers(candidate_answers, base=0.58)
            joined_text = " ".join(
                self._combined_text(answer, question_lookup)
                for answer in candidate_answers
            )
            detection = detect_competitor_context(text=joined_text, confidence=confidence)
            if not detection["is_competitor"]:
                continue
            strength = self._score_from_answers(
                candidate_answers,
                base=56,
                per_answer=3,
                per_platform=5,
                cap=76,
            )
            allocation = allocate_graph_zone(
                connection_strength=strength,
                sentiment_or_risk_score=6.2,
                relation_type="competes_with",
                confidence=confidence,
            )
            patches.append(
                GraphPatch(
                    graph_update_id=graph_update.id,
                    entity_id=entity.id,
                    patch_type="add_competitor_relation",
                    status=allocation["status"],
                    title=f"新增{candidate.label}竞品候选",
                    description="真实回答包含明确替代、推荐或对比信号，非同品类共现。",
                    affected_object_type=candidate.entity_type,
                    affected_object_id=candidate.entity_id,
                    relation_type="competes_with",
                    connection_strength=strength,
                    confidence=confidence,
                    sentiment_or_risk_score=6.2,
                    after_payload={
                        "zone": allocation["zone"],
                        "label": candidate.label,
                        "lexicon_entry": candidate.to_payload(),
                        "existing_graph_match": self._existing_graph_match(
                            entry=candidate,
                            graph_index=graph_index,
                        ),
                    },
                    score_breakdown={
                        "connection_strength": strength,
                        "sentiment": 6.2,
                        "confidence": confidence,
                        "allocation_reason": allocation["reason"],
                        "competitor_reason": detection["reason"],
                    },
                    evidence_refs=self._evidence_refs(
                        answers=candidate_answers,
                        question_lookup=question_lookup,
                        polarity="neutral",
                        matched_entry=candidate,
                    ),
                )
            )
        return patches[:2]

    def _weak_scenario_patch(
        self,
        *,
        entity: Entity,
        graph_update: GraphUpdate,
        answers: list[BrandPlatformAnswer],
        question_lookup: dict[str, str],
        allocate_graph_zone: Callable[..., dict[str, Any]],
    ) -> GraphPatch:
        strength = self._score_from_answers(answers, base=42, per_answer=2, per_platform=2, cap=56)
        confidence = self._confidence_from_answers(answers, base=0.48)
        allocation = allocate_graph_zone(
            connection_strength=strength,
            sentiment_or_risk_score=5.8,
            relation_type="scenario_for",
            confidence=confidence,
        )
        status = "blocked" if len(answers) < 2 else allocation["status"]
        return GraphPatch(
            graph_update_id=graph_update.id,
            entity_id=entity.id,
            patch_type="add_entity",
            status=status,
            title="新增弱证据场景候选",
            description="真实回答出现新使用场景，但证据量不足时不会直接进入正式圈层。",
            affected_object_type="usage_scenario",
            affected_object_id="emerging-usage-scenario",
            relation_type="scenario_for",
            connection_strength=strength,
            confidence=confidence,
            sentiment_or_risk_score=5.8,
            after_payload={"zone": allocation["zone"], "label": "新兴使用场景"},
            score_breakdown={
                "connection_strength": strength,
                "sentiment": 5.8,
                "confidence": confidence,
                "allocation_reason": allocation["reason"],
            },
            evidence_refs=self._evidence_refs(
                answers=answers,
                question_lookup=question_lookup,
                polarity="neutral",
            ),
        )

    def _insufficient_data_patch(
        self,
        *,
        entity: Entity,
        graph_update: GraphUpdate,
        board_run: BoardRun,
    ) -> GraphPatch:
        return GraphPatch(
            graph_update_id=graph_update.id,
            entity_id=entity.id,
            patch_type="insufficient_data",
            status="needs_review",
            title="真实运行缺少可用回答",
            description="未读取到成功抓取的 AI 平台回答，图谱更新需要人工检查运行产物。",
            affected_object_type="runtime_input",
            affected_object_id=f"board-run-{board_run.id}",
            relation_type="evidence_missing",
            connection_strength=0,
            confidence=0,
            sentiment_or_risk_score=5.0,
            after_payload={"zone": "pending_review", "label": "缺少可用回答"},
            score_breakdown={
                "connection_strength": 0,
                "sentiment": 5.0,
                "confidence": 0,
                "allocation_reason": "no_successful_answers",
            },
            evidence_refs=[],
        )

    def _evidence_refs(
        self,
        *,
        answers: list[BrandPlatformAnswer],
        question_lookup: dict[str, str],
        polarity: str,
        matched_entry: EntityLexiconEntry | None = None,
    ) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for answer in answers[:5]:
            ref = {
                "id": f"answer:{answer.id}",
                "answer_id": str(answer.id),
                "question_id": answer.question_id,
                "question": self._question_text(answer, question_lookup),
                "platform": answer.platform,
                "excerpt": self._clip(answer.answer_text, 180),
                "polarity": polarity,
            }
            if matched_entry is not None:
                ref.update(
                    {
                        "matched_entity_id": matched_entry.entity_id,
                        "matched_entity_label": matched_entry.label,
                        "matched_entity_type": matched_entry.entity_type,
                    }
                )
            refs.append(ref)
        return refs

    @staticmethod
    def _combined_text(
        answer: BrandPlatformAnswer,
        question_lookup: dict[str, str],
    ) -> str:
        question = GraphPatchBuilderService._question_text(answer, question_lookup)
        return f"{question}\n{answer.answer_text or ''}"

    @staticmethod
    def _question_text(
        answer: BrandPlatformAnswer,
        question_lookup: dict[str, str],
    ) -> str:
        if answer.question_object_id is not None:
            by_object_id = question_lookup.get(str(answer.question_object_id))
            if by_object_id:
                return by_object_id
        return question_lookup.get(answer.question_id) or answer.question_id or "未记录问题"

    @staticmethod
    def _clip(text: str, limit: int) -> str:
        normalized = " ".join((text or "").split())
        return normalized if len(normalized) <= limit else f"{normalized[:limit]}..."

    @staticmethod
    def _score_from_answers(
        answers: list[BrandPlatformAnswer],
        *,
        base: int,
        per_answer: int,
        per_platform: int,
        cap: int,
    ) -> int:
        platforms = {answer.platform for answer in answers if answer.platform}
        return min(cap, base + len(answers) * per_answer + len(platforms) * per_platform)

    @staticmethod
    def _confidence_from_answers(
        answers: list[BrandPlatformAnswer],
        *,
        base: float,
    ) -> float:
        platforms = {answer.platform for answer in answers if answer.platform}
        confidence = base + len(answers) * 0.02 + len(platforms) * 0.06
        return round(min(0.9, confidence), 2)

    @staticmethod
    def _platform_label(answers: list[BrandPlatformAnswer]) -> str:
        platforms = sorted({answer.platform for answer in answers if answer.platform})
        return "、".join(platforms[:4]) if platforms else "AI 平台"


class BrandSpaceService:
    """Persistent state source for the Brand Space MVP."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_space(self, *, entity_id: str | UUID, current_user: User) -> dict[str, Any]:
        entity = await self._require_entity(entity_id, current_user)
        board_run = await self._latest_board_run(entity.id)
        if board_run is not None:
            await self._sync_real_board_run(board_run=board_run, current_user=current_user)
        return await self._space_payload(entity=entity, board_run=board_run)

    async def get_graph(self, *, entity_id: str | UUID, current_user: User) -> dict[str, Any]:
        entity = await self._require_entity(entity_id, current_user)
        latest_update = await self._latest_graph_update(entity.id)
        if latest_update and latest_update.graph_snapshot:
            return {
                "graph": latest_update.graph_snapshot,
                "graph_update": self._graph_update_to_dict(latest_update),
            }
        return {
            "graph": await self._fallback_graph(entity=entity, patches=[]),
            "graph_update": None,
        }

    async def get_review_items(
        self,
        *,
        entity_id: str | UUID,
        current_user: User,
        status: str | None = None,
        category: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        entity = await self._require_entity(entity_id, current_user)
        normalized_status = (status or "").strip().lower()
        normalized_category = (category or "").strip().lower()
        safe_limit = max(1, min(int(limit or 100), 200))
        allowed_statuses = {
            "all",
            "auto_applied",
            "needs_review",
            "accepted",
            "rejected",
            "blocked",
        }
        if normalized_status and normalized_status not in allowed_statuses:
            raise ValueError(f"Unsupported review item status: {status}")

        query = (
            select(GraphPatch, GraphUpdate)
            .join(GraphUpdate, GraphPatch.graph_update_id == GraphUpdate.id)
            .where(GraphUpdate.entity_id == entity.id)
            .order_by(desc(GraphPatch.updated_at), desc(GraphPatch.created_at))
        )
        if not normalized_status:
            query = query.where(GraphPatch.status.in_(REVIEWABLE_PATCH_STATUSES))
        elif normalized_status != "all":
            query = query.where(GraphPatch.status == normalized_status)
        query = query.limit(safe_limit * 3 if normalized_category else safe_limit)

        result = await self.db.execute(query)
        rows = list(result.all())
        items = [
            self._review_item_to_dict(patch=patch, graph_update=graph_update)
            for patch, graph_update in rows
        ]
        if normalized_category:
            items = [item for item in items if item["category"] == normalized_category]
        items = items[:safe_limit]
        return {
            "review_items": items,
            "summary": self._review_items_summary(items),
        }

    async def create_board_run(
        self,
        *,
        entity_id: str | UUID,
        current_user: User,
        board_id: str = "ai_visibility_monitor",
        template_id: str = "ai_visibility_monitor:v0.1",
        input_scope: dict[str, Any] | None = None,
        execution_mode: str = SCAFFOLD_EXECUTION_MODE,
    ) -> dict[str, Any]:
        entity = await self._require_entity(entity_id, current_user)
        normalized_execution_mode = str(execution_mode or SCAFFOLD_EXECUTION_MODE).strip().lower()
        is_scaffold = normalized_execution_mode != REAL_EXECUTION_MODE
        effective_input_scope = input_scope or {"platforms": ["chatgpt", "deepseek", "kimi", "doubao"]}
        intelligence_run = await BrandIntelligenceRunService(self.db).create_or_reuse_run(
            entity_id=entity.id,
            current_user=current_user,
            run_goal="通过 Brand Space 画布更新品牌实体关系图谱",
            analysis_mode="panorama",
            input_scope=effective_input_scope,
            origin_surface="brand_space",
            origin_event_id=f"brand-space:scaffold:{entity.id}" if is_scaffold else None,
            start_immediately=not is_scaffold,
        )

        board_run = BoardRun(
            entity_id=entity.id,
            created_by_user_id=current_user.id,
            brand_intelligence_run_id=intelligence_run.id,
            analysis_task_id=intelligence_run.analysis_task_id,
            board_id=board_id,
            template_id=template_id,
            status=(
                "running"
                if is_scaffold
                else REAL_RUN_STATUS_TO_BOARD_STATUS.get(intelligence_run.status, "running")
            ),
            is_scaffold=is_scaffold,
            progress=0.86 if is_scaffold else float(intelligence_run.progress or 0.0),
            summary=(
                "AI 能见度监测画布已生成一组待审阅图谱更新。"
                if is_scaffold
                else intelligence_run.message or "真实运行已创建，等待后台执行器。"
            ),
            input_scope=effective_input_scope,
            active_node_ids=(
                ["platform-rack", "graph-patch", "graph-update"]
                if is_scaffold
                else self._active_node_ids_for_real_status(intelligence_run.status)
            ),
            started_at=_now(),
        )
        self.db.add(board_run)
        await self.db.flush()

        node_runs = self._build_initial_nodes(
            board_run=board_run,
            scaffold=is_scaffold,
            intelligence_run=intelligence_run,
        )
        self.db.add_all(node_runs)
        await self.db.flush()
        node_by_id = {node.node_id: node for node in node_runs}

        artifacts = self._build_initial_artifacts(
            entity=entity,
            board_run=board_run,
            node_by_id=node_by_id,
            scaffold=is_scaffold,
        )
        self.db.add_all(artifacts)

        board_run.output_refs = {
            "brand_intelligence_run_id": str(intelligence_run.id),
            "execution_mode": REAL_EXECUTION_MODE if not is_scaffold else SCAFFOLD_EXECUTION_MODE,
            "intelligence_status": intelligence_run.status,
            "intelligence_stage": intelligence_run.stage,
        }

        patches: list[GraphPatch] = []
        if is_scaffold:
            graph_update, patches = await self._build_graph_update(
                entity=entity,
                board_run=board_run,
                current_user=current_user,
            )
            self.db.add(graph_update)
            await self.db.flush()
            for patch in patches:
                patch.graph_update_id = graph_update.id
            self.db.add_all(patches)
            await self.db.flush()

            graph_update.graph_snapshot = await self._fallback_graph(entity=entity, patches=patches)
            graph_update.summary = self._graph_update_summary(patches)
            graph_update.status = (
                "needs_review"
                if any(patch.status == "needs_review" for patch in patches)
                else "applied"
            )
            board_run.output_refs = {
                **(board_run.output_refs or {}),
                "graph_update_id": str(graph_update.id),
            }

        events = self._build_initial_events(
            entity=entity,
            board_run=board_run,
            patches=patches,
            scaffold=is_scaffold,
        )
        self.db.add_all(events)
        await self.db.commit()
        return await self._space_payload(entity=entity, board_run=board_run)

    async def submit_board_run_runtime(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
    ) -> tuple[dict[str, Any], str | None]:
        board_run = await self._require_board_run(run_id, current_user)
        if board_run.brand_intelligence_run_id is None:
            raise ValueError("Board run is not linked to a brand intelligence run")
        intelligence_service = BrandIntelligenceRunService(self.db)
        intelligence_run = await intelligence_service.get_run(
            run_id=board_run.brand_intelligence_run_id,
            current_user=current_user,
        )
        if intelligence_run is None:
            raise LookupError("Brand intelligence run not found")
        original_output_refs = dict(intelligence_run.output_refs or {})
        had_runtime_context = bool(
            intelligence_run.analysis_task_id and original_output_refs.get("task_run_id")
        )
        intelligence_run = await intelligence_service.ensure_runtime_submitted(
            run=intelligence_run,
            current_user=current_user,
        )
        runtime_context_ready = bool(
            intelligence_run.analysis_task_id
            and (intelligence_run.output_refs or {}).get("task_run_id")
        )
        output_refs = dict(board_run.output_refs or {})
        dispatch_key = self._runtime_dispatch_key(intelligence_run)
        should_dispatch = (
            runtime_context_ready
            and intelligence_run.status not in REAL_RUN_TERMINAL_STATUSES
            and (
                not had_runtime_context
                or (
                    intelligence_run.status
                    in {"waiting_user", "waiting_scope_confirmation", "waiting_takeover"}
                    and output_refs.get("last_dispatched_runtime_key") != dispatch_key
                )
            )
        )
        board_run.is_scaffold = False
        board_run.analysis_task_id = intelligence_run.analysis_task_id
        board_run.started_at = board_run.started_at or intelligence_run.started_at or _now()
        board_run.output_refs = {
            **output_refs,
            "brand_intelligence_run_id": str(intelligence_run.id),
            "analysis_task_id": str(intelligence_run.analysis_task_id)
            if intelligence_run.analysis_task_id
            else None,
            "execution_mode": REAL_EXECUTION_MODE,
            "session_id": str(intelligence_run.origin_session_id)
            if intelligence_run.origin_session_id
            else None,
            "task_run_id": (intelligence_run.output_refs or {}).get("task_run_id"),
        }
        if should_dispatch:
            board_run.output_refs = {
                **(board_run.output_refs or {}),
                "last_dispatched_runtime_key": dispatch_key,
                "last_dispatched_at": _now().isoformat(),
            }
            await self._append_event(
                entity_id=board_run.entity_id,
                board_run_id=board_run.id,
                event_type="runtime_dispatch_requested",
                severity="info",
                message="真实后台运行已提交，画布将按阶段同步节点状态。",
                node_id="brand-seed",
                payload={"brand_intelligence_run_id": str(intelligence_run.id)},
            )
        await self._sync_real_board_run(board_run=board_run, current_user=current_user, force=True)
        entity = await self._entity_by_id(board_run.entity_id)
        return (
            await self._space_payload(entity=entity, board_run=board_run),
            str(intelligence_run.id) if should_dispatch else None,
        )

    async def get_board_run(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
    ) -> dict[str, Any]:
        board_run = await self._require_board_run(run_id, current_user)
        await self._sync_real_board_run(board_run=board_run, current_user=current_user)
        entity = await self._entity_by_id(board_run.entity_id)
        return await self._space_payload(entity=entity, board_run=board_run)

    async def update_board_run_status(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
        status: str,
    ) -> dict[str, Any]:
        board_run = await self._require_board_run(run_id, current_user)
        if not board_run.is_scaffold:
            await self._sync_real_board_run(board_run=board_run, current_user=current_user, force=True)
        if status == "pause_requested":
            board_run.status = "paused"
            board_run.active_node_ids = []
            message = "画布已在节点边界暂停。"
            node_status = "paused"
        elif status == "running":
            board_run.status = "running"
            board_run.active_node_ids = ["platform-rack", "graph-patch", "graph-update"]
            message = "画布运行已继续。"
            node_status = "running"
        elif status == "stopped":
            board_run.status = "stopped"
            board_run.active_node_ids = []
            board_run.completed_at = _now()
            message = "画布运行已停止，已保留当前图谱更新草稿。"
            node_status = "paused"
            if not board_run.is_scaffold and board_run.brand_intelligence_run_id:
                await BrandIntelligenceRunService(self.db).cancel_run(
                    run_id=board_run.brand_intelligence_run_id,
                    current_user=current_user,
                )
        else:
            raise ValueError(f"Unsupported board run status: {status}")

        nodes = await self._node_runs(board_run.id)
        for node in nodes:
            if node.status == "running":
                node.status = node_status
        await self._append_event(
            entity_id=board_run.entity_id,
            board_run_id=board_run.id,
            event_type=f"run_{board_run.status}",
            severity="info",
            message=message,
        )
        await self.db.commit()
        entity = await self._entity_by_id(board_run.entity_id)
        return await self._space_payload(entity=entity, board_run=board_run)

    async def get_events(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
    ) -> dict[str, Any]:
        board_run = await self._require_board_run(run_id, current_user)
        await self._sync_real_board_run(board_run=board_run, current_user=current_user)
        events = await self._events(board_run.id)
        return {"events": [self._event_to_dict(event) for event in events]}

    async def get_assets(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
    ) -> dict[str, Any]:
        board_run = await self._require_board_run(run_id, current_user)
        await self._sync_real_board_run(board_run=board_run, current_user=current_user)
        artifacts = await self._artifacts(board_run.id)
        return {"artifacts": [self._artifact_to_dict(artifact) for artifact in artifacts]}

    async def get_graph_update(
        self,
        *,
        graph_update_id: str | UUID,
        current_user: User,
    ) -> dict[str, Any]:
        graph_update = await self._require_graph_update(graph_update_id, current_user)
        patches = await self._patches(graph_update.id)
        guardrails = await self._guardrails(graph_update.id)
        return {
            "graph_update": self._graph_update_to_dict(graph_update),
            "patches": [self._patch_to_dict(patch) for patch in patches],
            "guardrails": [self._guardrail_to_dict(item) for item in guardrails],
        }

    async def decide_graph_patch(
        self,
        *,
        patch_id: str | UUID,
        status: str,
        reason: str | None,
        current_user: User,
    ) -> dict[str, Any]:
        patch = await self._require_patch(patch_id, current_user)
        graph_update = await self._require_graph_update(patch.graph_update_id, current_user)
        previous_status = patch.status
        normalized_reason = reason or ""

        if previous_status in IMMUTABLE_PATCH_STATUSES:
            if previous_status == status:
                return await self.get_graph_update(
                    graph_update_id=graph_update.id,
                    current_user=current_user,
                )
            raise ValueError("Graph patch already has a terminal decision")

        no_change = (
            previous_status == status
            and (patch.review_reason or "") == normalized_reason
            and patch.reviewed_at is not None
        )
        if no_change:
            return await self.get_graph_update(
                graph_update_id=graph_update.id,
                current_user=current_user,
            )

        patch.status = status
        patch.review_reason = normalized_reason
        patch.reviewed_by_user_id = current_user.id
        patch.reviewed_at = _now()

        patches = await self._patches(graph_update.id)
        previous_graph_update_status = graph_update.status
        if all(item.status in IMMUTABLE_PATCH_STATUSES | {"blocked"} for item in patches):
            graph_update.status = "applied"
        elif any(item.status == "needs_review" for item in patches):
            graph_update.status = "needs_review"
        else:
            graph_update.status = "partial"
        entity = await self._entity_by_id(graph_update.entity_id)
        graph_update.summary = self._graph_update_summary(patches)
        graph_update.graph_snapshot = await self._fallback_graph(
            entity=entity,
            patches=self._patches_for_graph_snapshot(patches),
        )

        event_type_by_status = {
            "accepted": "graph_patch_accepted",
            "rejected": "graph_patch_rejected",
            "needs_review": "graph_patch_kept_review",
        }
        severity_by_status = {
            "accepted": "success",
            "rejected": "info",
            "needs_review": "warning",
        }
        await self._append_event(
            entity_id=patch.entity_id,
            board_run_id=graph_update.board_run_id,
            node_id="anomaly-review",
            event_type=event_type_by_status.get(status, "graph_patch_reviewed"),
            severity=severity_by_status.get(status, "info"),
            message=f"图谱补丁已标记为{self._decision_label(status)}。",
            payload={
                "patch_id": str(patch.id),
                "previous_status": previous_status,
                "status": status,
                "reason": normalized_reason,
                "category": self._patch_review_category(patch),
            },
        )
        if previous_graph_update_status != "applied" and graph_update.status == "applied":
            await self.db.flush()
            await self._append_event(
                entity_id=patch.entity_id,
                board_run_id=graph_update.board_run_id,
                node_id="graph-update",
                event_type="graph_update_applied",
                severity="success",
                message="图谱更新已进入已应用状态。",
                payload={"graph_update_id": str(graph_update.id)},
            )
        await self.db.commit()
        return await self.get_graph_update(graph_update_id=graph_update.id, current_user=current_user)

    async def generate_report(
        self,
        *,
        graph_update_id: str | UUID,
        current_user: User,
        report_kind: str = "graph_update_interpretation",
        publish_requested: bool = False,
    ) -> dict[str, Any]:
        graph_update = await self._require_graph_update(graph_update_id, current_user)
        patches = await self._patches(graph_update.id)
        entity = await self._entity_by_id(graph_update.entity_id)
        report_payload = self._build_report_payload(
            brand_name=entity.name,
            graph_update=graph_update,
            patches=patches,
        )
        guardrails = self.validate_report_payload(report_payload, patches)
        has_block = any(item["severity"] == "block" for item in guardrails)
        report_payload["publication_status"] = (
            "needs_review" if has_block or publish_requested is False else "publishable"
        )

        version = await self._next_report_version(
            entity_id=graph_update.entity_id,
            report_id=f"brand-space-{graph_update.id}",
        )
        report = BrandReportVersion(
            entity_id=graph_update.entity_id,
            session_id=None,
            evidence_set_id=None,
            message_id=None,
            report_id=f"brand-space-{graph_update.id}",
            version=version,
            report_kind=report_kind,
            artifact_id=f"graph-update-report:{graph_update.id}:{version}",
            title=f"{report_payload['brand_name']}圈层状态更新",
            summary=str(report_payload.get("summary") or ""),
            payload=report_payload,
        )
        self.db.add(report)
        await self.db.flush()

        for item in guardrails:
            self.db.add(
                ReportGuardrailResult(
                    graph_update_id=graph_update.id,
                    report_version_id=report.id,
                    guardrail_key=item["guardrail_key"],
                    severity=item["severity"],
                    title=item["title"],
                    message=item["message"],
                    payload=item.get("payload"),
                )
            )
        if graph_update.board_run_id:
            await self._append_event(
                entity_id=graph_update.entity_id,
                board_run_id=graph_update.board_run_id,
                node_id="graph-update",
                event_type="report_guardrails_checked",
                severity="warning" if has_block else "success",
                message="图谱更新报告已生成并完成结构化校验。",
                payload={"report_version_id": str(report.id), "has_block": has_block},
            )
        await self.db.commit()
        return {
            "report": self._report_to_dict(report),
            "guardrails": guardrails,
        }

    @staticmethod
    def allocate_graph_zone(
        *,
        connection_strength: float,
        sentiment_or_risk_score: float | None,
        relation_type: str = "",
        confidence: float | None = None,
        positive_evidence_streak: int = 0,
    ) -> dict[str, Any]:
        sentiment = 5.0 if sentiment_or_risk_score is None else float(sentiment_or_risk_score)
        normalized_confidence = 1.0 if confidence is None else float(confidence)
        if relation_type == "competes_with" and normalized_confidence < 0.7:
            return {"zone": "pending_review", "status": "needs_review", "reason": "low_competitor_confidence"}
        if sentiment < 3:
            return {"zone": "risk", "status": "blocked", "reason": "risk_score_below_3"}
        if sentiment < 5:
            if positive_evidence_streak >= 2:
                return {"zone": "middle", "status": "needs_review", "reason": "risk_score_3_to_5_requires_review"}
            return {"zone": "risk", "status": "needs_review", "reason": "risk_score_3_to_5"}
        if connection_strength >= 80:
            return {"zone": "inner", "status": "auto_applied", "reason": "strong_positive_connection"}
        if connection_strength >= 60:
            return {"zone": "middle", "status": "auto_applied", "reason": "medium_positive_connection"}
        return {"zone": "outer", "status": "needs_review", "reason": "weak_connection"}

    @staticmethod
    def detect_competitor_context(*, text: str, confidence: float) -> dict[str, Any]:
        has_explicit_signal = any(pattern.search(text or "") for pattern in EXPLICIT_COMPETITOR_PATTERNS)
        if not has_explicit_signal:
            return {"is_competitor": False, "status": "ignored", "reason": "co_mention_only"}
        if confidence < 0.7:
            return {"is_competitor": True, "status": "needs_review", "reason": "confidence_below_0_7"}
        return {"is_competitor": True, "status": "auto_applied", "reason": "explicit_comparison"}

    @staticmethod
    def validate_report_payload(
        report_payload: dict[str, Any],
        patches: list[GraphPatch],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        strategic_terms = [str(item.get("reason") or "") for item in report_payload.get("strategic_terms", [])]
        max_similarity = 0.0
        for left_index, left in enumerate(strategic_terms):
            for right in strategic_terms[left_index + 1 :]:
                max_similarity = max(max_similarity, difflib.SequenceMatcher(None, left, right).ratio())
        results.append(
            {
                "guardrail_key": "strategic_term_similarity",
                "severity": "block" if max_similarity > 0.8 and len(strategic_terms) > 1 else "pass",
                "title": "战略词结论差异度",
                "message": (
                    "战略词结论过于雷同，需要人工改写。"
                    if max_similarity > 0.8 and len(strategic_terms) > 1
                    else "战略词结论具备可区分表述。"
                ),
                "payload": {"max_similarity": max_similarity},
            }
        )

        competitor_claims = list(report_payload.get("competitor_claims") or [])
        competitor_patch_by_id = {
            str(patch.id): patch
            for patch in patches
            if patch.patch_type == "add_competitor_relation"
        }
        claim_without_evidence = False
        pending_competitor_review = False
        for claim in competitor_claims:
            patch = competitor_patch_by_id.get(str(claim.get("patch_id") or ""))
            evidence_refs = claim.get("evidence_refs") or []
            if not evidence_refs:
                claim_without_evidence = True
            if patch is not None and patch.status == "needs_review":
                pending_competitor_review = True
        results.append(
            {
                "guardrail_key": "competitor_claim_evidence",
                "severity": "block" if claim_without_evidence or pending_competitor_review else "pass",
                "title": "竞品声明证据",
                "message": (
                    "竞品声明缺少证据或仍有竞品补丁待审，不能发布为正式结论。"
                    if claim_without_evidence or pending_competitor_review
                    else "竞品声明均有证据片段支撑。"
                ),
                "payload": {
                    "claim_without_evidence": claim_without_evidence,
                    "pending_competitor_review": pending_competitor_review,
                },
            }
        )

        evidence_questions: list[str] = []
        for patch in patches:
            for evidence in patch.evidence_refs or []:
                evidence_questions.append(str(evidence.get("question") or ""))
        concentration = 0.0
        if evidence_questions:
            counts = Counter(evidence_questions)
            concentration = max(counts.values()) / len(evidence_questions)
        results.append(
            {
                "guardrail_key": "evidence_concentration",
                "severity": "warn" if concentration > 0.8 else "pass",
                "title": "证据来源集中度",
                "message": (
                    "80% 以上证据来自同一问题，需要补充问题覆盖。"
                    if concentration > 0.8
                    else "证据来源未过度集中。"
                ),
                "payload": {"concentration": concentration},
            }
        )

        platform_names = ("ChatGPT", "DeepSeek", "Kimi", "豆包", "Doubao")
        actions = [str(item) for item in report_payload.get("recommended_actions") or []]
        missing_platform = bool(actions) and any(
            not any(platform in action for platform in platform_names) for action in actions
        )
        results.append(
            {
                "guardrail_key": "action_platform_specificity",
                "severity": "block" if missing_platform else "pass",
                "title": "行动建议平台指向",
                "message": (
                    "行动建议缺少具体平台名。"
                    if missing_platform
                    else "行动建议包含具体平台指向。"
                ),
                "payload": {"missing_platform": missing_platform},
            }
        )
        return results

    async def _require_entity(self, entity_id: str | UUID, current_user: User) -> Entity:
        entity = await EntityService(self.db).get_entity_model(
            str(entity_id),
            current_user,
            allow_internal_admin_bypass=False,
        )
        if entity is None:
            raise LookupError("Entity not found")
        return entity

    async def _entity_by_id(self, entity_id: UUID) -> Entity:
        entity = await self.db.get(Entity, entity_id)
        if entity is None:
            raise LookupError("Entity not found")
        return entity

    async def _require_board_run(self, run_id: str | UUID, current_user: User) -> BoardRun:
        run_uuid = self._coerce_uuid(run_id, "run_id")
        result = await self.db.execute(select(BoardRun).where(BoardRun.id == run_uuid))
        board_run = result.scalar_one_or_none()
        if board_run is None:
            raise LookupError("Board run not found")
        await self._require_entity(board_run.entity_id, current_user)
        return board_run

    async def _require_graph_update(self, graph_update_id: str | UUID, current_user: User) -> GraphUpdate:
        update_uuid = self._coerce_uuid(graph_update_id, "graph_update_id")
        result = await self.db.execute(select(GraphUpdate).where(GraphUpdate.id == update_uuid))
        graph_update = result.scalar_one_or_none()
        if graph_update is None:
            raise LookupError("Graph update not found")
        await self._require_entity(graph_update.entity_id, current_user)
        return graph_update

    async def _require_patch(self, patch_id: str | UUID, current_user: User) -> GraphPatch:
        patch_uuid = self._coerce_uuid(patch_id, "patch_id")
        result = await self.db.execute(select(GraphPatch).where(GraphPatch.id == patch_uuid))
        patch = result.scalar_one_or_none()
        if patch is None:
            raise LookupError("Graph patch not found")
        await self._require_entity(patch.entity_id, current_user)
        return patch

    @staticmethod
    def _coerce_uuid(value: str | UUID, field_name: str) -> UUID:
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid UUID for {field_name}: {value}") from exc

    @staticmethod
    def _assign_if_changed(target: Any, field_name: str, value: Any) -> bool:
        if getattr(target, field_name) == value:
            return False
        setattr(target, field_name, value)
        return True

    @staticmethod
    def _elapsed_seconds(start: datetime, end: datetime) -> float:
        normalized_start = start
        normalized_end = end
        if normalized_start.tzinfo is None and normalized_end.tzinfo is not None:
            normalized_end = normalized_end.replace(tzinfo=None)
        elif normalized_start.tzinfo is not None and normalized_end.tzinfo is None:
            normalized_start = normalized_start.replace(tzinfo=None)
        return max((normalized_end - normalized_start).total_seconds(), 0.0)

    @staticmethod
    def _runtime_dispatch_key(intelligence_run: BrandIntelligenceRun) -> str:
        task_run_id = (intelligence_run.output_refs or {}).get("task_run_id") or ""
        return f"{intelligence_run.id}:{task_run_id}:{intelligence_run.status}"

    async def _sync_real_board_run(
        self,
        *,
        board_run: BoardRun,
        current_user: User,
        force: bool = False,
    ) -> bool:
        if board_run.is_scaffold or board_run.brand_intelligence_run_id is None:
            return False
        sync_started_at = _now()
        if (
            not force
            and board_run.last_synced_at is not None
            and self._elapsed_seconds(board_run.last_synced_at, sync_started_at)
            < REAL_SYNC_MIN_INTERVAL_SECONDS
        ):
            return False

        intelligence_service = BrandIntelligenceRunService(self.db)
        intelligence_run = await intelligence_service.get_run(
            run_id=board_run.brand_intelligence_run_id,
            current_user=current_user,
        )
        if intelligence_run is None:
            logger.warning(
                "Intelligence run %s not found for board run %s",
                board_run.brand_intelligence_run_id,
                board_run.id,
            )
            output_refs = dict(board_run.output_refs or {})
            missing_event_written = bool(output_refs.get("missing_intelligence_event_written"))
            board_run.status = "failed"
            board_run.error_code = "intelligence_run_missing"
            board_run.error_message = "关联的智能运行已不存在"
            board_run.active_node_ids = []
            board_run.last_synced_at = sync_started_at
            board_run.output_refs = {
                **output_refs,
                "missing_intelligence_event_written": True,
            }
            if not missing_event_written:
                await self._append_event(
                    entity_id=board_run.entity_id,
                    board_run_id=board_run.id,
                    event_type="runtime_missing",
                    severity="error",
                    message="关联的智能运行已不存在，画布运行已标记失败。",
                    payload={"brand_intelligence_run_id": str(board_run.brand_intelligence_run_id)},
                )
            await self.db.commit()
            return True

        counts = await self._real_artifact_counts(
            entity_id=board_run.entity_id,
            intelligence_run=intelligence_run,
        )
        board_status = REAL_RUN_STATUS_TO_BOARD_STATUS.get(
            intelligence_run.status,
            board_run.status,
        )
        active_node_ids = self._active_node_ids_for_real_status(intelligence_run.status)
        output_refs = dict(board_run.output_refs or {})
        previous_stage_key = output_refs.get("last_synced_intelligence_stage")
        current_stage_key = f"{intelligence_run.status}:{intelligence_run.stage}"

        changed = False
        changed |= self._assign_if_changed(board_run, "status", board_status)
        changed |= self._assign_if_changed(
            board_run,
            "progress",
            max(0.0, min(1.0, float(intelligence_run.progress or 0.0))),
        )
        changed |= self._assign_if_changed(
            board_run,
            "summary",
            intelligence_run.message or board_run.summary,
        )
        changed |= self._assign_if_changed(board_run, "analysis_task_id", intelligence_run.analysis_task_id)
        changed |= self._assign_if_changed(board_run, "active_node_ids", active_node_ids)
        changed |= self._assign_if_changed(board_run, "error_code", intelligence_run.error_code)
        changed |= self._assign_if_changed(board_run, "error_message", intelligence_run.error_message)
        changed |= self._assign_if_changed(
            board_run,
            "completed_at",
            intelligence_run.completed_at
            if intelligence_run.status in REAL_RUN_TERMINAL_STATUSES
            else board_run.completed_at,
        )
        next_output_refs = {
            **output_refs,
            "brand_intelligence_run_id": str(intelligence_run.id),
            "analysis_task_id": str(intelligence_run.analysis_task_id)
            if intelligence_run.analysis_task_id
            else None,
            "execution_mode": REAL_EXECUTION_MODE,
            "intelligence_status": intelligence_run.status,
            "intelligence_stage": intelligence_run.stage,
            "intelligence_message": intelligence_run.message,
            "last_synced_intelligence_stage": current_stage_key,
            "session_id": str(intelligence_run.origin_session_id)
            if intelligence_run.origin_session_id
            else None,
            "snapshot_id": (intelligence_run.output_refs or {}).get("snapshot_id"),
            "task_run_id": (intelligence_run.output_refs or {}).get("task_run_id"),
            "real_counts": counts,
        }
        changed |= self._assign_if_changed(board_run, "output_refs", next_output_refs)

        changed |= await self._sync_real_nodes(
            board_run=board_run,
            intelligence_run=intelligence_run,
            counts=counts,
        )
        changed |= await self._sync_real_artifacts(
            board_run=board_run,
            intelligence_run=intelligence_run,
            counts=counts,
        )
        changed |= await self._ensure_real_graph_update(
            board_run=board_run,
            intelligence_run=intelligence_run,
            current_user=current_user,
        )
        if previous_stage_key != current_stage_key:
            event_type, severity, default_message = REAL_RUN_STATUS_EVENT_MESSAGES.get(
                intelligence_run.status,
                ("runtime_stage_changed", "info", "真实运行状态已更新。"),
            )
            await self._append_event(
                entity_id=board_run.entity_id,
                board_run_id=board_run.id,
                event_type=event_type,
                severity=severity,
                message=intelligence_run.message or default_message,
                node_id=active_node_ids[0] if active_node_ids else None,
                payload={
                    "brand_intelligence_run_id": str(intelligence_run.id),
                    "status": intelligence_run.status,
                    "stage": intelligence_run.stage,
                    "progress": intelligence_run.progress,
                },
            )
            changed = True
        changed |= self._assign_if_changed(board_run, "last_synced_at", sync_started_at)
        if changed:
            await self.db.commit()
        return changed

    async def _ensure_real_graph_update(
        self,
        *,
        board_run: BoardRun,
        intelligence_run: BrandIntelligenceRun,
        current_user: User,
    ) -> bool:
        if board_run.is_scaffold or intelligence_run.status != "completed":
            return False
        existing = await self._graph_update_for_run(board_run.id)
        if existing is not None:
            return False

        entity = await self._entity_by_id(board_run.entity_id)
        graph_update, patches = await self._build_graph_update(
            entity=entity,
            board_run=board_run,
            current_user=current_user,
            intelligence_run=intelligence_run,
        )
        self.db.add(graph_update)
        await self.db.flush()
        for patch in patches:
            patch.graph_update_id = graph_update.id
        self.db.add_all(patches)
        await self.db.flush()

        graph_update.graph_snapshot = await self._fallback_graph(
            entity=entity,
            patches=patches,
        )
        graph_update.summary = self._graph_update_summary(patches)
        graph_update.status = (
            "needs_review"
            if any(patch.status == "needs_review" for patch in patches)
            else "applied"
        )
        board_run.output_refs = {
            **(board_run.output_refs or {}),
            "graph_update_id": str(graph_update.id),
        }
        await self._sync_real_graph_artifact_counts(
            board_run=board_run,
            patches=patches,
        )
        await self._append_event(
            entity_id=board_run.entity_id,
            board_run_id=board_run.id,
            node_id="graph-update",
            event_type="graph_update_created",
            severity="success",
            message=f"真实抓取答案已生成 {len(patches)} 个图谱补丁。",
            payload={
                "graph_update_id": str(graph_update.id),
                "patch_count": len(patches),
                "needs_review": sum(
                    1 for patch in patches if patch.status in REVIEWABLE_PATCH_STATUSES
                ),
            },
        )
        return True

    async def _real_artifact_counts(
        self,
        *,
        entity_id: UUID,
        intelligence_run: BrandIntelligenceRun,
    ) -> dict[str, int]:
        session_id = intelligence_run.origin_session_id
        question_conditions = [BrandIntelligenceQuestion.entity_id == entity_id]
        answer_conditions = [BrandPlatformAnswer.entity_id == entity_id]
        snapshot_conditions = [AnalysisSnapshot.entity_id == entity_id]
        if session_id is not None:
            question_conditions.append(BrandIntelligenceQuestion.session_id == session_id)
            answer_conditions.append(BrandPlatformAnswer.session_id == session_id)
            snapshot_conditions.append(AnalysisSnapshot.session_id == session_id)
        question_count = await self.db.scalar(
            select(func.count(BrandIntelligenceQuestion.id)).where(*question_conditions)
        )
        answer_count = await self.db.scalar(
            select(func.count(BrandPlatformAnswer.id)).where(*answer_conditions)
        )
        snapshot_count = await self.db.scalar(
            select(func.count(AnalysisSnapshot.id)).where(*snapshot_conditions)
        )
        return {
            "questions": int(question_count or 0),
            "answers": int(answer_count or 0),
            "snapshots": int(snapshot_count or 0),
        }

    async def _sync_real_nodes(
        self,
        *,
        board_run: BoardRun,
        intelligence_run: BrandIntelligenceRun,
        counts: dict[str, int],
    ) -> bool:
        changed = False
        node_states = self._real_node_state_map(intelligence_run)
        nodes = await self._node_runs(board_run.id)
        for node in nodes:
            state = node_states.get(node.node_id)
            if state is None:
                continue
            changed |= self._assign_if_changed(node, "status", state["status"])
            changed |= self._assign_if_changed(node, "progress", state["progress"])
            changed |= self._assign_if_changed(
                node,
                "metrics",
                self._real_node_metrics(node.node_id, intelligence_run, counts),
            )
            if node.status == "running":
                if node.started_at is None:
                    node.started_at = _now()
                    changed = True
                changed |= self._assign_if_changed(node, "completed_at", None)
            elif node.status in {"completed", "needs_review", "failed"}:
                if node.started_at is None:
                    node.started_at = board_run.started_at
                    changed = True
                if node.completed_at is None:
                    node.completed_at = _now()
                    changed = True
        return changed

    async def _sync_real_artifacts(
        self,
        *,
        board_run: BoardRun,
        intelligence_run: BrandIntelligenceRun,
        counts: dict[str, int],
    ) -> bool:
        changed = False
        row_counts = {
            "artifact-lexicon": 1,
            "artifact-questions": counts["questions"],
            "artifact-raw-answers": counts["answers"],
            "artifact-parsed-answers": counts["answers"],
            "artifact-relation-set": counts["answers"],
            "artifact-patch-set": 0,
            "artifact-review-list": 0,
            "artifact-graph-update": counts["snapshots"],
        }
        artifacts = await self._artifacts(board_run.id)
        for artifact in artifacts:
            new_row_count = row_counts.get(artifact.artifact_key, artifact.row_count)
            changed |= self._assign_if_changed(artifact, "row_count", new_row_count)
            next_metadata = {
                **(artifact.extra_metadata or {}),
                "execution_mode": REAL_EXECUTION_MODE,
                "brand_intelligence_run_id": str(intelligence_run.id),
                "session_id": str(intelligence_run.origin_session_id)
                if intelligence_run.origin_session_id
                else None,
                "analysis_task_id": str(intelligence_run.analysis_task_id)
                if intelligence_run.analysis_task_id
                else None,
            }
            changed |= self._assign_if_changed(artifact, "extra_metadata", next_metadata)
        return changed

    async def _sync_real_graph_artifact_counts(
        self,
        *,
        board_run: BoardRun,
        patches: list[GraphPatch],
    ) -> bool:
        row_counts = {
            "artifact-patch-set": len(patches),
            "artifact-review-list": sum(
                1 for patch in patches if patch.status in REVIEWABLE_PATCH_STATUSES
            ),
            "artifact-graph-update": 1,
        }
        changed = False
        for artifact in await self._artifacts(board_run.id):
            if artifact.artifact_key not in row_counts:
                continue
            changed |= self._assign_if_changed(
                artifact,
                "row_count",
                row_counts[artifact.artifact_key],
            )
            changed |= self._assign_if_changed(
                artifact,
                "extra_metadata",
                {
                    **(artifact.extra_metadata or {}),
                    "graph_update_generated": True,
                },
            )
        return changed

    def _real_node_state_map(self, intelligence_run: BrandIntelligenceRun) -> dict[str, dict[str, Any]]:
        status = intelligence_run.status
        progress = int(max(0.0, min(1.0, float(intelligence_run.progress or 0.0))) * 100)
        queued = {"status": "queued", "progress": 0.0}
        completed = {"status": "completed", "progress": 100.0}
        states: dict[str, dict[str, Any]] = {
            "brand-seed": completed,
            "question-set": queued,
            "platform-rack": queued,
            "answer-normalize": queued,
            "entity-match": queued,
            "graph-patch": queued,
            "anomaly-review": queued,
            "graph-update": queued,
        }
        if status == "not_started":
            states["brand-seed"] = {"status": "running", "progress": 35.0}
        elif status in {"planning_questions", "waiting_scope_confirmation"}:
            states["question-set"] = {
                "status": "needs_review" if status == "waiting_scope_confirmation" else "running",
                "progress": max(12.0, float(progress)),
            }
        elif status in {"fetching_answers", "waiting_takeover"}:
            states["question-set"] = completed
            states["platform-rack"] = {
                "status": "paused" if status == "waiting_takeover" else "running",
                "progress": max(35.0, float(progress)),
            }
        elif status == "analyzing_metrics":
            states["question-set"] = completed
            states["platform-rack"] = completed
            states["answer-normalize"] = {"status": "running", "progress": max(55.0, float(progress))}
            states["entity-match"] = {"status": "running", "progress": max(55.0, float(progress))}
        elif status == "building_world":
            states["question-set"] = completed
            states["platform-rack"] = completed
            states["answer-normalize"] = completed
            states["entity-match"] = completed
            states["graph-patch"] = {"status": "running", "progress": max(72.0, float(progress))}
        elif status == "generating_recommendations":
            states["question-set"] = completed
            states["platform-rack"] = completed
            states["answer-normalize"] = completed
            states["entity-match"] = completed
            states["graph-patch"] = completed
            states["graph-update"] = {"status": "running", "progress": max(86.0, float(progress))}
        elif status == "waiting_user":
            states["question-set"] = completed
            states["platform-rack"] = completed
            states["answer-normalize"] = completed
            states["entity-match"] = completed
            states["graph-patch"] = {"status": "needs_review", "progress": 100.0}
            states["anomaly-review"] = {"status": "needs_review", "progress": 100.0}
        elif status == "completed":
            states = {node_id: completed for node_id in states}
        elif status == "failed":
            failed_nodes = self._active_node_ids_for_real_status(intelligence_run.stage)
            for node_id in failed_nodes or ["platform-rack"]:
                states[node_id] = {"status": "failed", "progress": float(progress)}
        elif status == "cancelled":
            for node_id in self._active_node_ids_for_real_status(intelligence_run.stage):
                states[node_id] = {"status": "paused", "progress": float(progress)}
        return states

    def _real_node_metrics(
        self,
        node_id: str,
        intelligence_run: BrandIntelligenceRun,
        counts: dict[str, int],
    ) -> list[dict[str, str]]:
        if node_id == "brand-seed":
            return [{"label": "模式", "value": "真实"}, {"label": "状态", "value": intelligence_run.status}]
        if node_id == "question-set":
            return [{"label": "问题", "value": str(counts["questions"])}, {"label": "阶段", "value": intelligence_run.stage or "-"}]
        if node_id == "platform-rack":
            return [{"label": "平台", "value": "4"}, {"label": "回答", "value": str(counts["answers"])}]
        if node_id in {"answer-normalize", "entity-match"}:
            return [{"label": "回答", "value": str(counts["answers"])}, {"label": "状态", "value": intelligence_run.status}]
        if node_id == "graph-update":
            return [{"label": "快照", "value": str(counts["snapshots"])}, {"label": "进度", "value": f"{intelligence_run.progress:.0%}"}]
        return [{"label": "状态", "value": intelligence_run.status}]

    def _active_node_ids_for_real_status(self, status: str) -> list[str]:
        normalized = str(status or "").strip()
        if normalized in {
            "not_started",
            "planning_questions",
            "waiting_scope_confirmation",
            "A3",
            "question_simulation",
        }:
            return ["question-set"]
        if normalized in {"fetching_answers", "waiting_takeover", "A4", "answer_fetch"}:
            return ["platform-rack"]
        if normalized in {"analyzing_metrics", "A5", "analysis_report", "analysis_report_skill"}:
            return ["answer-normalize", "entity-match"]
        if normalized == "building_world":
            return ["graph-patch"]
        if normalized in {"generating_recommendations", "completed"}:
            return ["graph-update"]
        if normalized == "waiting_user":
            return ["anomaly-review"]
        return []

    async def _latest_board_run(self, entity_id: UUID) -> BoardRun | None:
        result = await self.db.execute(
            select(BoardRun)
            .where(BoardRun.entity_id == entity_id)
            .order_by(desc(BoardRun.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_graph_update(self, entity_id: UUID) -> GraphUpdate | None:
        result = await self.db.execute(
            select(GraphUpdate)
            .where(GraphUpdate.entity_id == entity_id)
            .order_by(desc(GraphUpdate.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _space_payload(self, *, entity: Entity, board_run: BoardRun | None) -> dict[str, Any]:
        if board_run is None:
            return self._empty_space_payload(entity)
        nodes = await self._node_runs(board_run.id)
        artifacts = await self._artifacts(board_run.id)
        events = await self._events(board_run.id)
        graph_update = await self._graph_update_for_run(board_run.id)
        patches = await self._patches(graph_update.id) if graph_update else []
        graph = (
            graph_update.graph_snapshot
            if graph_update and graph_update.graph_snapshot
            else await self._fallback_graph(
                entity=entity,
                patches=patches,
                runtime_pending=not board_run.is_scaffold and graph_update is None,
            )
        )
        guardrails = await self._guardrails(graph_update.id) if graph_update else []
        return {
            "context": self._context_to_dict(entity=entity, board_run=board_run, graph_update=graph_update),
            "run": self._board_run_to_dict(board_run),
            "nodes": [self._node_to_dict(node) for node in nodes],
            "edges": BOARD_EDGES,
            "platforms": self._platforms_for_run(board_run),
            "artifacts": [self._artifact_to_dict(artifact) for artifact in artifacts],
            "events": [self._event_to_dict(event) for event in events],
            "graph": graph,
            "graph_update": self._graph_update_to_dict(graph_update) if graph_update else None,
            "patches": [self._patch_to_dict(patch) for patch in patches],
            "guardrails": [self._guardrail_to_dict(item) for item in guardrails],
        }

    def _empty_space_payload(self, entity: Entity) -> dict[str, Any]:
        context = {
            "brandName": f"{entity.name}品牌空间",
            "graphVersion": "v0.0.0",
            "boardName": "AI 能见度监测画布",
            "runId": "",
            "startedAt": "",
            "duration": "00:00:00",
        }
        return {
            "context": context,
            "run": None,
            "nodes": [
                self._template_node_to_dict(template, status="idle", progress=0.0)
                for template in NODE_TEMPLATES
            ],
            "edges": BOARD_EDGES,
            "platforms": [
                {**platform, "status": "idle", "progress": 0, "answers": 0, "failures": 0}
                for platform in PLATFORM_TEMPLATES
            ],
            "artifacts": [],
            "events": [],
            "graph": {
                "entities": [
                    {
                        "id": str(entity.id),
                        "label": entity.name,
                        "zone": "center",
                        "x": 50,
                        "y": 50,
                        "strength": 100,
                        "evidenceCount": 0,
                    }
                ],
                "relations": [],
                "evidenceRefs": [],
            },
            "graph_update": None,
            "patches": [],
            "guardrails": [],
        }

    def _build_initial_nodes(
        self,
        *,
        board_run: BoardRun,
        scaffold: bool,
        intelligence_run: BrandIntelligenceRun,
    ) -> list[BoardNodeRun]:
        node_runs: list[BoardNodeRun] = []
        if scaffold:
            status_by_id = {
                "brand-seed": ("completed", 100.0),
                "question-set": ("completed", 100.0),
                "platform-rack": ("running", 61.0),
                "answer-normalize": ("completed", 100.0),
                "entity-match": ("completed", 100.0),
                "graph-patch": ("running", 74.0),
                "anomaly-review": ("needs_review", 100.0),
                "graph-update": ("running", 68.0),
            }
            metrics_by_id = {
                "brand-seed": [{"label": "实体", "value": "126"}, {"label": "别名", "value": "342"}],
                "question-set": [{"label": "问题", "value": "1,248"}, {"label": "场景", "value": "42"}],
                "platform-rack": [{"label": "运行中", "value": "4 / 4"}, {"label": "回答", "value": "994"}],
                "answer-normalize": [{"label": "回答", "value": "1,248"}, {"label": "失败", "value": "3"}],
                "entity-match": [{"label": "已映射", "value": "2,193"}, {"label": "新实体", "value": "36"}],
                "graph-patch": [{"label": "变更", "value": "4"}, {"label": "待审阅", "value": "2"}],
                "anomaly-review": [{"label": "条目", "value": "2"}, {"label": "优先级", "value": "高"}],
                "graph-update": [{"label": "已应用", "value": "1"}, {"label": "待处理", "value": "2"}],
            }
        else:
            real_states = self._real_node_state_map(intelligence_run)
            status_by_id = {
                node_id: (state["status"], state["progress"])
                for node_id, state in real_states.items()
            }
            metrics_by_id = {
                template["node_id"]: self._real_node_metrics(
                    template["node_id"],
                    intelligence_run,
                    {"questions": 0, "answers": 0, "snapshots": 0},
                )
                for template in NODE_TEMPLATES
            }
        for template in NODE_TEMPLATES:
            status, progress = status_by_id[template["node_id"]]
            node_runs.append(
                BoardNodeRun(
                    board_run_id=board_run.id,
                    node_id=template["node_id"],
                    node_type=template["node_type"],
                    title=template["title"],
                    subtitle=template["subtitle"],
                    status=status,
                    progress=progress,
                    position=template["position"],
                    metrics=metrics_by_id.get(template["node_id"], []),
                    output_artifact_ids=template["artifact_keys"],
                    started_at=board_run.started_at,
                    completed_at=_now() if status in {"completed", "needs_review"} else None,
                )
            )
        return node_runs

    def _build_initial_artifacts(
        self,
        *,
        entity: Entity,
        board_run: BoardRun,
        node_by_id: dict[str, BoardNodeRun],
        scaffold: bool,
    ) -> list[BoardArtifact]:
        base = f"assets/{entity.id}/{board_run.id}"
        rows = [
            ("artifact-lexicon", "brand-seed", "entity_lexicon", f"{entity.name}实体词表", f"{base}/entity_lexicon/entity-lexicon.json", 126),
            ("artifact-questions", "question-set", "question_set", "AI 能见度监测问题集", f"{base}/question_set/questions.jsonl", 1248),
            ("artifact-raw-answers", "platform-rack", "raw_answers", "平台原始回答", f"{base}/raw_answers/", 994),
            ("artifact-parsed-answers", "answer-normalize", "parsed_answers", "标准化回答表", f"{base}/parsed_answers/answers.parquet", 1248),
            ("artifact-relation-set", "entity-match", "entity_relation_set", "实体关系集", f"{base}/entity_relation_set/relations.json", 2193),
            ("artifact-patch-set", "graph-patch", "graph_patch_set", "图谱补丁集", f"{base}/graph_patch_set/patches.json", 4),
            ("artifact-review-list", "anomaly-review", "review_queue", "待审阅补丁队列", f"{base}/review_queue/items.json", 2),
            ("artifact-graph-update", "graph-update", "graph_update", "图谱更新草稿", f"{base}/graph_update/update.json", 1),
        ]
        artifacts: list[BoardArtifact] = []
        for key, node_id, artifact_type, label, path, row_count in rows:
            artifacts.append(
                BoardArtifact(
                    artifact_key=key,
                    entity_id=entity.id,
                    board_run_id=board_run.id,
                    node_run_id=node_by_id[node_id].id,
                    artifact_type=artifact_type,
                    label=label,
                    path=path,
                    mime_type="application/json",
                    row_count=row_count if scaffold else 0,
                    extra_metadata={
                        "node_id": node_id,
                        "execution_mode": SCAFFOLD_EXECUTION_MODE if scaffold else REAL_EXECUTION_MODE,
                    },
                )
            )
        return artifacts

    async def _build_graph_update(
        self,
        *,
        entity: Entity,
        board_run: BoardRun,
        current_user: User,
        intelligence_run: BrandIntelligenceRun | None = None,
    ) -> tuple[GraphUpdate, list[GraphPatch]]:
        graph_update = GraphUpdate(
            entity_id=entity.id,
            board_run_id=board_run.id,
            created_by_user_id=current_user.id,
            before_graph_version="v0.0.0",
            after_graph_version="v0.1.0",
            status="needs_review",
        )
        if board_run.is_scaffold or intelligence_run is None:
            patches = self._default_patches(entity=entity, graph_update=graph_update)
        else:
            current_graph_projection = await self._current_graph_projection(entity.id)
            patches = await GraphPatchBuilderService(self.db).build(
                entity=entity,
                board_run=board_run,
                intelligence_run=intelligence_run,
                graph_update=graph_update,
                current_graph_projection=current_graph_projection,
                allocate_graph_zone=self.allocate_graph_zone,
                detect_competitor_context=self.detect_competitor_context,
            )
        return graph_update, patches

    async def _current_graph_projection(self, entity_id: UUID) -> dict[str, Any]:
        try:
            projection = await BrandKnowledgeGraphProjectionService(self.db).build(entity_id=entity_id)
        except Exception as exc:
            logger.warning(
                "Knowledge graph projection lookup failed for graph patch builder %s: %s",
                entity_id,
                exc,
            )
            return {}
        return projection.get("graph_projection") or {}

    def _default_patches(self, *, entity: Entity, graph_update: GraphUpdate) -> list[GraphPatch]:
        brand_name = entity.name
        positive_allocation = self.allocate_graph_zone(
            connection_strength=86,
            sentiment_or_risk_score=8.2,
            relation_type="associated_with",
            confidence=0.86,
        )
        risk_allocation = self.allocate_graph_zone(
            connection_strength=71,
            sentiment_or_risk_score=4.2,
            relation_type="risk_of",
            confidence=0.74,
        )
        competitor_allocation = self.allocate_graph_zone(
            connection_strength=64,
            sentiment_or_risk_score=6.2,
            relation_type="competes_with",
            confidence=0.64,
        )
        weak_allocation = self.allocate_graph_zone(
            connection_strength=48,
            sentiment_or_risk_score=5.8,
            relation_type="scenario_for",
            confidence=0.51,
        )
        return [
            GraphPatch(
                graph_update_id=graph_update.id,
                entity_id=entity.id,
                patch_type="update_strength",
                status=positive_allocation["status"],
                title="增强核心产品内圈关系",
                description=f"ChatGPT、Kimi 和 DeepSeek 均出现{brand_name}与健康管理的正向证据。",
                affected_object_type="brand_concept",
                affected_object_id="core-health-management",
                relation_type="associated_with",
                connection_strength=86,
                confidence=0.86,
                sentiment_or_risk_score=8.2,
                after_payload={"zone": positive_allocation["zone"], "label": "健康管理"},
                score_breakdown={"connection_strength": 86, "sentiment": 8.2, "confidence": 0.86},
                evidence_refs=[
                    {
                        "id": "ev-health-001",
                        "question": "哪些营养品牌适合日常健康管理？",
                        "platform": "Kimi",
                        "excerpt": f"{brand_name}经常在营养补充和健康管理语境中被提及。",
                        "polarity": "positive",
                    }
                ],
            ),
            GraphPatch(
                graph_update_id=graph_update.id,
                entity_id=entity.id,
                patch_type="add_risk_relation",
                status=risk_allocation["status"],
                title="监管信息保留在风险层",
                description="情绪/风险分落在 3-5 区间，不允许因连接强度高而进入内圈。",
                affected_object_type="risk_signal",
                affected_object_id="regulatory",
                relation_type="risk_of",
                connection_strength=71,
                confidence=0.74,
                sentiment_or_risk_score=4.2,
                after_payload={"zone": risk_allocation["zone"], "label": "监管信息"},
                score_breakdown={"connection_strength": 71, "sentiment": 4.2, "confidence": 0.74},
                evidence_refs=[
                    {
                        "id": "ev-risk-001",
                        "question": "直销类营养品牌是否存在用户顾虑？",
                        "platform": "DeepSeek",
                        "excerpt": "回答提到价格和监管相关疑问，需要更多澄清证据。",
                        "polarity": "questioning",
                    }
                ],
            ),
            GraphPatch(
                graph_update_id=graph_update.id,
                entity_id=entity.id,
                patch_type="add_competitor_relation",
                status=competitor_allocation["status"],
                title="新增竞品候选关系",
                description="存在明确比较语境，但置信度低于 0.7，必须进入待审阅。",
                affected_object_type="competitor_entity",
                affected_object_id="by-health",
                relation_type="competes_with",
                connection_strength=64,
                confidence=0.64,
                sentiment_or_risk_score=6.2,
                after_payload={"zone": competitor_allocation["zone"], "label": "汤臣倍健"},
                score_breakdown={"connection_strength": 64, "sentiment": 6.2, "confidence": 0.64},
                evidence_refs=[
                    {
                        "id": "ev-competitor-001",
                        "question": "用户购买营养补充品前通常会比较什么？",
                        "platform": "ChatGPT",
                        "excerpt": f"用户会把{brand_name}与汤臣倍健进行对比后再选择。",
                        "polarity": "neutral",
                    }
                ],
            ),
            GraphPatch(
                graph_update_id=graph_update.id,
                entity_id=entity.id,
                patch_type="add_entity",
                status="blocked",
                title="新增弱证据场景被阻断",
                description="回答中出现新场景，但证据量不足，不能直接进入圈层。",
                affected_object_type="usage_scenario",
                affected_object_id="workplace-energy",
                relation_type="scenario_for",
                connection_strength=48,
                confidence=0.51,
                sentiment_or_risk_score=5.8,
                after_payload={"zone": weak_allocation["zone"], "label": "职场精力"},
                score_breakdown={"connection_strength": 48, "sentiment": 5.8, "confidence": 0.51},
                evidence_refs=[],
            ),
        ]

    async def _fallback_graph(
        self,
        *,
        entity: Entity,
        patches: list[GraphPatch],
        runtime_pending: bool = False,
    ) -> dict[str, Any]:
        try:
            projection = await BrandKnowledgeGraphProjectionService(self.db).build(entity_id=entity.id)
            graph_projection = projection.get("graph_projection") or {}
            existing_nodes = graph_projection.get("nodes") or []
            existing_edges = graph_projection.get("edges") or []
        except Exception as exc:
            logger.warning(
                "Knowledge graph projection failed for entity %s: %s",
                entity.id,
                exc,
            )
            existing_nodes = []
            existing_edges = []

        entities = [
            {
                "id": str(entity.id),
                "label": entity.name,
                "zone": "center",
                "x": 50,
                "y": 50,
                "strength": 100,
                "evidenceCount": 0,
            }
        ]
        relations: list[dict[str, Any]] = []
        evidence_refs: list[dict[str, Any]] = []
        coordinates = [(42, 35), (47, 78), (77, 72), (61, 18)]
        for index, patch in enumerate(patches):
            after_payload = patch.after_payload or {}
            entities.append(
                {
                    "id": patch.affected_object_id or str(patch.id),
                    "patchId": str(patch.id),
                    "patchStatus": patch.status,
                    "patchType": patch.patch_type,
                    "category": self._patch_review_category(patch),
                    "priority": self._patch_review_priority(patch),
                    "label": after_payload.get("label") or patch.title,
                    "zone": after_payload.get("zone") or "pending_review",
                    "x": coordinates[index % len(coordinates)][0],
                    "y": coordinates[index % len(coordinates)][1],
                    "strength": int(patch.connection_strength or 0),
                    "evidenceCount": len(patch.evidence_refs or []),
                }
            )
            relations.append(
                {
                    "id": f"rel-{patch.id}",
                    "from": str(entity.id),
                    "to": patch.affected_object_id or str(patch.id),
                    "kind": patch.relation_type or patch.patch_type,
                    "strength": float((patch.connection_strength or 0) / 100),
                    "patchId": str(patch.id),
                    "patchStatus": patch.status,
                }
            )
            evidence_refs.extend(patch.evidence_refs or [])

        if existing_nodes and len(entities) == 1:
            entities.extend(existing_nodes[:12])
        if existing_edges and not relations:
            relations.extend(existing_edges[:20])
        if runtime_pending and len(entities) == 1:
            entities.append(
                {
                    "id": "runtime-pending",
                    "label": "真实运行进行中",
                    "zone": "pending_review",
                    "x": 64,
                    "y": 42,
                    "strength": 35,
                    "evidenceCount": 0,
                }
            )
            relations.append(
                {
                    "id": "rel-runtime-pending",
                    "from": str(entity.id),
                    "to": "runtime-pending",
                    "kind": "runtime_pending",
                    "strength": 0.35,
                }
            )
            evidence_refs.append(
                {
                    "id": "runtime-pending",
                    "question": "真实运行进行中",
                    "platform": "Brand Space",
                    "excerpt": "真实运行进行中，图谱将在抓取和分析完成后更新。",
                    "polarity": "neutral",
                }
            )
        return {
            "entities": entities,
            "relations": relations,
            "evidenceRefs": evidence_refs,
            "meta": {
                "state": "runtime_pending" if runtime_pending else "ready",
                "message": "真实运行进行中，图谱将在完成后更新。" if runtime_pending else "",
            },
        }

    def _graph_update_summary(self, patches: list[GraphPatch]) -> dict[str, Any]:
        counts = Counter(patch.status for patch in patches)
        return {
            "auto_applied": counts.get("auto_applied", 0),
            "needs_review": counts.get("needs_review", 0),
            "accepted": counts.get("accepted", 0),
            "rejected": counts.get("rejected", 0),
            "blocked": counts.get("blocked", 0),
            "total": len(patches),
        }

    @staticmethod
    def _patches_for_graph_snapshot(patches: list[GraphPatch]) -> list[GraphPatch]:
        return [patch for patch in patches if patch.status != "rejected"]

    @staticmethod
    def _patch_review_category(patch: GraphPatch) -> str:
        patch_type = patch.patch_type or ""
        relation_type = patch.relation_type or ""
        if patch_type == "add_competitor_relation" or relation_type == "competes_with":
            return "competitor"
        if patch_type == "add_risk_relation" or "risk" in patch_type or "risk" in relation_type:
            return "risk"
        if patch_type == "add_entity":
            return "new_entity"
        if patch.confidence is not None and float(patch.confidence) < 0.7:
            return "low_confidence"
        if patch.status == "blocked":
            return "conflict"
        return "graph_change"

    @staticmethod
    def _patch_review_priority(patch: GraphPatch) -> str:
        if patch.status == "blocked":
            return "high"
        if patch.patch_type == "add_competitor_relation" or patch.relation_type == "competes_with":
            return "high" if (patch.confidence or 0) < 0.7 else "medium"
        sentiment = patch.sentiment_or_risk_score
        if sentiment is not None and float(sentiment) < 5:
            return "high"
        if patch.confidence is not None and float(patch.confidence) < 0.7:
            return "medium"
        return "low"

    @staticmethod
    def _review_suggested_action(patch: GraphPatch) -> str:
        if patch.status == "blocked":
            return "保留阻断，除非补充了更强证据。"
        if patch.patch_type == "add_competitor_relation":
            return "确认是否存在明确替代、推荐或对比信号。"
        if patch.patch_type == "add_risk_relation":
            return "确认风险语境是否应停留在风险层。"
        if patch.patch_type == "add_entity":
            return "确认新实体是否应进入品牌圈层。"
        return "确认该图谱变化是否应应用。"

    def _review_items_summary(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        status_counts = Counter(str(item.get("status") or "") for item in items)
        category_counts = Counter(str(item.get("category") or "") for item in items)
        return {
            "total": len(items),
            "needs_review": status_counts.get("needs_review", 0),
            "blocked": status_counts.get("blocked", 0),
            "accepted": status_counts.get("accepted", 0),
            "rejected": status_counts.get("rejected", 0),
            "by_category": dict(category_counts),
        }

    def _build_initial_events(
        self,
        *,
        entity: Entity,
        board_run: BoardRun,
        patches: list[GraphPatch],
        scaffold: bool,
    ) -> list[BoardRuntimeEvent]:
        review_count = sum(1 for patch in patches if patch.status == "needs_review")
        if scaffold:
            rows = [
                ("run_started", "info", "已从 AI 能见度监测模板启动画布运行。", None),
                ("scaffold_data_loaded", "warning", "当前运行使用脚手架数据预览，尚未触发真实 AI 抓取。", None),
                ("artifact_written", "success", "问题集资产已写入，共 1,248 条问题。", "question-set"),
                ("node_progress", "info", "ChatGPT、DeepSeek、Kimi、豆包正在并行抓取。", "platform-rack"),
                ("artifact_written", "success", "标准化回答表已生成，可以进入实体抽取。", "answer-normalize"),
                ("graph_patch_needs_review", "warning", f"{review_count} 个图谱补丁需要审阅。", "graph-patch"),
            ]
        else:
            rows = [
                ("run_started", "info", f"{entity.name}真实画布运行已创建。", "brand-seed"),
                ("runtime_waiting", "info", "等待后台执行器提交并推进问题生成节点。", "question-set"),
            ]
        return [
            BoardRuntimeEvent(
                entity_id=entity.id,
                board_run_id=board_run.id,
                node_id=node_id,
                sequence=index + 1,
                event_type=event_type,
                severity=severity,
                message=message,
                payload={},
            )
            for index, (event_type, severity, message, node_id) in enumerate(rows)
        ]

    async def _append_event(
        self,
        *,
        entity_id: UUID,
        board_run_id: UUID | None,
        event_type: str,
        severity: str,
        message: str,
        node_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if board_run_id is None:
            return
        result = await self.db.execute(
            select(func.max(BoardRuntimeEvent.sequence)).where(
                BoardRuntimeEvent.board_run_id == board_run_id
            )
        )
        sequence = int(result.scalar_one_or_none() or 0) + 1
        self.db.add(
            BoardRuntimeEvent(
                entity_id=entity_id,
                board_run_id=board_run_id,
                node_id=node_id,
                sequence=sequence,
                event_type=event_type,
                severity=severity,
                message=message,
                payload=payload or {},
            )
        )

    async def _node_runs(self, board_run_id: UUID) -> list[BoardNodeRun]:
        result = await self.db.execute(
            select(BoardNodeRun).where(BoardNodeRun.board_run_id == board_run_id)
        )
        rows = list(result.scalars().all())
        order = {template["node_id"]: index for index, template in enumerate(NODE_TEMPLATES)}
        return sorted(rows, key=lambda row: order.get(row.node_id, 999))

    async def _artifacts(self, board_run_id: UUID) -> list[BoardArtifact]:
        result = await self.db.execute(
            select(BoardArtifact)
            .where(BoardArtifact.board_run_id == board_run_id)
            .order_by(BoardArtifact.created_at)
        )
        return list(result.scalars().all())

    async def _events(self, board_run_id: UUID) -> list[BoardRuntimeEvent]:
        result = await self.db.execute(
            select(BoardRuntimeEvent)
            .where(BoardRuntimeEvent.board_run_id == board_run_id)
            .order_by(BoardRuntimeEvent.sequence)
        )
        return list(result.scalars().all())

    async def _graph_update_for_run(self, board_run_id: UUID) -> GraphUpdate | None:
        result = await self.db.execute(
            select(GraphUpdate)
            .where(GraphUpdate.board_run_id == board_run_id)
            .order_by(desc(GraphUpdate.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _patches(self, graph_update_id: UUID) -> list[GraphPatch]:
        result = await self.db.execute(
            select(GraphPatch)
            .where(GraphPatch.graph_update_id == graph_update_id)
            .order_by(GraphPatch.created_at)
        )
        return list(result.scalars().all())

    async def _guardrails(self, graph_update_id: UUID) -> list[ReportGuardrailResult]:
        result = await self.db.execute(
            select(ReportGuardrailResult)
            .where(ReportGuardrailResult.graph_update_id == graph_update_id)
            .order_by(ReportGuardrailResult.created_at)
        )
        return list(result.scalars().all())

    async def _next_report_version(self, *, entity_id: UUID, report_id: str) -> int:
        result = await self.db.execute(
            select(func.max(BrandReportVersion.version)).where(
                BrandReportVersion.entity_id == entity_id,
                BrandReportVersion.report_id == report_id,
            )
        )
        return int(result.scalar_one_or_none() or 0) + 1

    def _platforms_for_run(self, board_run: BoardRun) -> list[dict[str, Any]]:
        if not board_run.is_scaffold:
            if board_run.status == "completed":
                status = "completed"
            elif board_run.status in {"paused", "stopped"}:
                status = "paused"
            elif "platform-rack" in (board_run.active_node_ids or []):
                status = "running"
            else:
                status = "queued"
            progress = int(max(0.0, min(1.0, float(board_run.progress or 0.0))) * 100)
            real_counts = (board_run.output_refs or {}).get("real_counts") or {}
            total_answers = int(real_counts.get("answers") or 0)
            base_answers, remainder = divmod(total_answers, len(PLATFORM_TEMPLATES))
            return [
                {
                    **platform,
                    "status": status,
                    "progress": 100 if status == "completed" else progress,
                    "answers": base_answers + (1 if index < remainder else 0),
                    "failures": 0,
                }
                for index, platform in enumerate(PLATFORM_TEMPLATES)
            ]
        status = "paused" if board_run.status in {"paused", "stopped"} else "running"
        return [{**platform, "status": status} for platform in PLATFORM_TEMPLATES]

    def _context_to_dict(
        self,
        *,
        entity: Entity,
        board_run: BoardRun,
        graph_update: GraphUpdate | None,
    ) -> dict[str, Any]:
        return {
            "brandName": f"{entity.name}品牌空间",
            "graphVersion": graph_update.after_graph_version if graph_update else "v0.0.0",
            "boardName": "AI 能见度监测画布",
            "runId": str(board_run.id),
            "startedAt": board_run.started_at.isoformat() if board_run.started_at else "",
            "duration": self._duration_label(board_run),
        }

    def _template_node_to_dict(self, template: dict[str, Any], *, status: str, progress: float) -> dict[str, Any]:
        return {
            "id": template["node_id"],
            "title": template["title"],
            "subtitle": template["subtitle"],
            "kind": template["node_type"],
            "status": status,
            "progress": int(progress),
            "position": template["position"],
            "metrics": [],
            "outputArtifactIds": template["artifact_keys"],
        }

    def _board_run_to_dict(self, board_run: BoardRun) -> dict[str, Any]:
        return {
            "id": str(board_run.id),
            "entity_id": str(board_run.entity_id),
            "brand_intelligence_run_id": str(board_run.brand_intelligence_run_id) if board_run.brand_intelligence_run_id else None,
            "analysis_task_id": str(board_run.analysis_task_id) if board_run.analysis_task_id else None,
            "board_id": board_run.board_id,
            "template_id": board_run.template_id,
            "status": board_run.status,
            "is_scaffold": board_run.is_scaffold,
            "progress": board_run.progress,
            "summary": board_run.summary,
            "input_scope": board_run.input_scope,
            "active_node_ids": board_run.active_node_ids or [],
            "output_refs": board_run.output_refs or {},
            "error_code": board_run.error_code,
            "error_message": board_run.error_message,
            "started_at": board_run.started_at.isoformat() if board_run.started_at else None,
            "completed_at": board_run.completed_at.isoformat() if board_run.completed_at else None,
            "last_synced_at": board_run.last_synced_at.isoformat() if board_run.last_synced_at else None,
            "created_at": board_run.created_at.isoformat(),
            "updated_at": board_run.updated_at.isoformat(),
        }

    def _node_to_dict(self, node: BoardNodeRun) -> dict[str, Any]:
        return {
            "id": node.node_id,
            "title": node.title,
            "subtitle": node.subtitle,
            "kind": node.node_type,
            "status": node.status,
            "progress": int(node.progress),
            "position": node.position or {"x": 0, "y": 0},
            "metrics": node.metrics or [],
            "outputArtifactIds": node.output_artifact_ids or [],
        }

    def _artifact_to_dict(self, artifact: BoardArtifact) -> dict[str, Any]:
        return {
            "id": artifact.artifact_key,
            "type": artifact.artifact_type,
            "label": artifact.label,
            "path": artifact.path,
            "rowCount": artifact.row_count,
            "createdAt": artifact.created_at.isoformat(),
            "linkedNodeId": (artifact.extra_metadata or {}).get("node_id"),
        }

    def _event_to_dict(self, event: BoardRuntimeEvent) -> dict[str, Any]:
        return {
            "id": str(event.id),
            "timestamp": event.created_at.isoformat(),
            "type": event.event_type,
            "severity": event.severity,
            "message": event.message,
            "nodeId": event.node_id,
            "payload": event.payload or {},
        }

    def _graph_update_to_dict(self, graph_update: GraphUpdate | None) -> dict[str, Any] | None:
        if graph_update is None:
            return None
        return {
            "id": str(graph_update.id),
            "entity_id": str(graph_update.entity_id),
            "board_run_id": str(graph_update.board_run_id) if graph_update.board_run_id else None,
            "before_graph_version": graph_update.before_graph_version,
            "after_graph_version": graph_update.after_graph_version,
            "status": graph_update.status,
            "summary": graph_update.summary or {},
            "created_at": graph_update.created_at.isoformat(),
            "updated_at": graph_update.updated_at.isoformat(),
        }

    def _patch_to_dict(self, patch: GraphPatch) -> dict[str, Any]:
        return {
            "id": str(patch.id),
            "graphUpdateId": str(patch.graph_update_id),
            "title": patch.title,
            "description": patch.description,
            "status": patch.status,
            "patchType": patch.patch_type,
            "relationType": patch.relation_type,
            "score": int(patch.connection_strength or 0),
            "evidenceRefIds": [str(item.get("id")) for item in patch.evidence_refs or [] if item.get("id")],
            "affectedEntityId": patch.affected_object_id,
            "affectedObjectType": patch.affected_object_type,
            "affectedObjectId": patch.affected_object_id,
            "evidenceRefs": patch.evidence_refs or [],
            "confidence": patch.confidence,
            "sentimentOrRiskScore": patch.sentiment_or_risk_score,
            "category": self._patch_review_category(patch),
            "priority": self._patch_review_priority(patch),
            "reviewReason": patch.review_reason,
            "reviewedByUserId": str(patch.reviewed_by_user_id) if patch.reviewed_by_user_id else None,
            "reviewedAt": patch.reviewed_at.isoformat() if patch.reviewed_at else None,
            "suggestedAction": self._review_suggested_action(patch),
            "createdAt": patch.created_at.isoformat(),
            "updatedAt": patch.updated_at.isoformat(),
        }

    def _review_item_to_dict(self, *, patch: GraphPatch, graph_update: GraphUpdate) -> dict[str, Any]:
        item = self._patch_to_dict(patch)
        item.update(
            {
                "graphUpdateId": str(graph_update.id),
                "graphUpdateStatus": graph_update.status,
                "boardRunId": str(graph_update.board_run_id) if graph_update.board_run_id else None,
                "beforeGraphVersion": graph_update.before_graph_version,
                "afterGraphVersion": graph_update.after_graph_version,
                "graphUpdateCreatedAt": graph_update.created_at.isoformat(),
            }
        )
        return item

    def _guardrail_to_dict(self, item: ReportGuardrailResult) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "severity": item.severity,
            "title": item.title,
            "message": item.message,
            "guardrailKey": item.guardrail_key,
            "payload": item.payload or {},
        }

    def _report_to_dict(self, report: BrandReportVersion) -> dict[str, Any]:
        return {
            "id": str(report.id),
            "report_id": report.report_id,
            "version": report.version,
            "report_kind": report.report_kind,
            "artifact_id": report.artifact_id,
            "title": report.title,
            "summary": report.summary,
            "payload": report.payload or {},
            "created_at": report.created_at.isoformat(),
        }

    def _build_report_payload(
        self,
        *,
        brand_name: str,
        graph_update: GraphUpdate,
        patches: list[GraphPatch],
    ) -> dict[str, Any]:
        # Scaffold report copy keeps the MVP contract stable until real
        # extraction and synthesis replace these deterministic sections.
        competitor_claims = [
            {
                "patch_id": str(patch.id),
                "label": (patch.after_payload or {}).get("label") or patch.affected_object_id,
                "evidence_refs": patch.evidence_refs or [],
                "status": patch.status,
            }
            for patch in patches
            if patch.patch_type == "add_competitor_relation"
        ]
        return {
            "brand_name": brand_name,
            "graph_update_id": str(graph_update.id),
            "summary": f"{brand_name}本次圈层更新增强了健康管理相关连接，同时保留风险和竞品候选审阅。",
            "strategic_terms": [
                {"word": "健康管理", "state": "已增强", "reason": "多平台正向证据支撑核心关联。"},
                {"word": "监管信息", "state": "留在风险层", "reason": "风险分处于 3-5 区间，需要审阅后再升级。"},
                {"word": "竞品候选", "state": "待审阅", "reason": "比较语境存在，但置信度低于自动入圈阈值。"},
            ],
            "competitor_claims": competitor_claims,
            "recommended_actions": [
                "在 ChatGPT 与 Kimi 上补充健康管理场景澄清问题。",
                "在 DeepSeek 上补充监管信息澄清问题，降低风险误读。",
            ],
        }

    @staticmethod
    def _decision_label(status: str) -> str:
        return {
            "accepted": "接受",
            "rejected": "拒绝",
            "needs_review": "继续审阅",
        }.get(status, status)

    @staticmethod
    def _duration_label(board_run: BoardRun) -> str:
        if board_run.started_at is None:
            return "00:00:00"
        end = board_run.completed_at or _now()
        seconds = int(BrandSpaceService._elapsed_seconds(board_run.started_at, end))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
