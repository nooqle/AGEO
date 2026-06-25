"""Brand Space board runtime and graph-update service."""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
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

_BACKEND_DIR = Path(__file__).resolve().parents[2]


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
        "subtitle": "多平台并行抓取",
        "position": {"x": 55, "y": 36},
        "artifact_keys": ["artifact-raw-answers"],
    },
    {
        "node_id": "answer-normalize",
        "node_type": "extract",
        "title": "回答标准化",
        "subtitle": "去重、清洗、结构化",
        "position": {"x": 78, "y": 24},
        "artifact_keys": ["artifact-parsed-answers"],
    },
    {
        "node_id": "entity-match",
        "node_type": "extract",
        "title": "实体匹配",
        "subtitle": "匹配实体词表",
        "position": {"x": 78, "y": 45},
        "artifact_keys": ["artifact-relation-set"],
    },
    {
        "node_id": "graph-patch",
        "node_type": "extract",
        "title": "图谱补丁",
        "subtitle": "新增、更新、连接",
        "position": {"x": 78, "y": 66},
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

BRAND_SPACE_DEFAULT_REAL_PLATFORMS: tuple[str, ...] = ("doubao", "kimi", "yuanbao")
BRAND_SPACE_DEFAULT_SCAFFOLD_PLATFORMS: tuple[str, ...] = (
    "chatgpt",
    "deepseek",
    "kimi",
    "doubao",
)

PLATFORM_TEMPLATE_BY_KEY: dict[str, dict[str, Any]] = {
    str(platform["platformKey"]).lower(): platform for platform in PLATFORM_TEMPLATES
}

PLATFORM_TEMPLATE_BY_KEY.update(
    {
        "yuanbao": {
            "id": "fetch-yuanbao",
            "platformKey": "yuanbao",
            "label": "元宝抓取",
            "model": "hunyuan · API",
            "progress": 0,
            "answers": 0,
            "failures": 0,
        },
        "hunyuan": {
            "id": "fetch-yuanbao",
            "platformKey": "yuanbao",
            "label": "元宝抓取",
            "model": "hunyuan · API",
            "progress": 0,
            "answers": 0,
            "failures": 0,
        },
    }
)

PLATFORM_KEY_ALIASES: dict[str, str] = {
    "豆包": "doubao",
    "抖音豆包": "doubao",
    "元宝": "yuanbao",
    "腾讯元宝": "yuanbao",
    "混元": "yuanbao",
    "hunyuan": "yuanbao",
    "gpt": "chatgpt",
    "openai": "chatgpt",
}

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
RISK_CONTEXT_TERMS: tuple[str, ...] = (
    "传销",
    "拉人头",
    "过度推销",
    "夸大",
    "智商税",
    "风险",
    "质疑",
    "投诉",
    "失败",
    "价格高",
    "熟人压力",
    "违规",
    "处罚",
    "非法",
    "骗局",
    "不靠谱",
)
RISK_NEGATIVE_CONTEXT_TERMS: tuple[str, ...] = (
    "涉嫌",
    "像传销",
    "容易变成传销",
    "拉人头",
    "过度推销",
    "熟人压力",
    "不建议",
    "谨慎",
    "警惕",
    "争议",
    "违规",
    "处罚",
    "非法",
    "骗局",
)
RISK_CLARIFICATION_TERMS: tuple[str, ...] = (
    "不是传销",
    "并非传销",
    "不属于传销",
    "区别于传销",
    "合法合规",
    "合规经营",
    "直销经营许可证",
    "监管许可",
    "正规直销",
    "并不等于传销",
    "避免夸大",
)

SCENARIO_SIGNAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"职场|熬夜|精力|运动|备孕|银发|中老年|家庭"),
)
CHINESE_NEGATION_PREFIXES = {"不", "非", "无", "没", "未"}
CHINESE_GLUE_SUFFIXES = {"用", "化", "性", "型"}

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
GRAPH_VERSION_BASE = "v0.0.0"
GRAPH_VERSION_PATTERN = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
GRAPH_REPORT_PUBLICATION_STATUSES = {
    "draft",
    "needs_review",
    "publishable",
    "published",
}

REVIEWABLE_PATCH_STATUSES = {"needs_review", "blocked"}
IMMUTABLE_PATCH_STATUSES = {"auto_applied", "accepted", "rejected"}
CONFIRMED_COMPETITOR_PATCH_STATUSES = {"auto_applied", "accepted"}
GRAPH_UPDATE_BUILD_ACTIVE_STATUSES = {"pending", "queued", "building"}

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
    "fetching_answers": ("runtime_stage_changed", "info", "AI 平台抓取正在执行。"),
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
        answers = await self.answers_for_run(
            entity_id=entity.id,
            intelligence_run=intelligence_run,
        )
        question_lookup = await self.question_lookup(
            entity_id=entity.id,
            intelligence_run=intelligence_run,
            answers=answers,
        )
        lexicon_entries = self.lexicon_entries(board_run=board_run, entity=entity)
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
        confirmed_competitor_ids = await self._confirmed_competitor_object_ids(
            entity_id=entity.id,
            candidate_ids=[entry.entity_id for entry in competitor_entries],
        )

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
                confirmed_competitor_ids=confirmed_competitor_ids,
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

    async def answers_for_run(
        self,
        *,
        entity_id: UUID,
        intelligence_run: BrandIntelligenceRun,
        limit: int = 200,
    ) -> list[BrandPlatformAnswer]:
        return await self._answers_for_run(
            entity_id=entity_id,
            intelligence_run=intelligence_run,
            limit=limit,
        )

    async def _answers_for_run(
        self,
        *,
        entity_id: UUID,
        intelligence_run: BrandIntelligenceRun,
        limit: int = 200,
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
            .limit(max(1, int(limit)))
        )
        return list(result.scalars().all())

    async def question_lookup(
        self,
        *,
        entity_id: UUID,
        intelligence_run: BrandIntelligenceRun,
        answers: list[BrandPlatformAnswer],
    ) -> dict[str, str]:
        return await self.question_lookup_for_answers(
            entity_id=entity_id,
            answers=answers,
            session_id=intelligence_run.origin_session_id,
        )

    async def question_lookup_for_answers(
        self,
        *,
        entity_id: UUID,
        answers: list[BrandPlatformAnswer],
        session_id: UUID | None = None,
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
                    BrandIntelligenceQuestion.entity_id == entity_id,
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
            if session_id is not None:
                conditions.append(BrandIntelligenceQuestion.session_id == session_id)
            result = await self.db.execute(
                select(BrandIntelligenceQuestion).where(*conditions)
            )
            for question in result.scalars().all():
                lookup[str(question.id)] = question.question_text
                lookup[question.question_id] = question.question_text
        return lookup

    async def _confirmed_competitor_object_ids(
        self,
        *,
        entity_id: UUID,
        candidate_ids: list[str],
    ) -> set[str]:
        normalized_ids = {
            str(candidate_id).strip().lower()
            for candidate_id in candidate_ids
            if str(candidate_id).strip()
        }
        if not normalized_ids:
            return set()
        result = await self.db.execute(
            select(GraphPatch.affected_object_id).where(
                GraphPatch.entity_id == entity_id,
                GraphPatch.relation_type == "competes_with",
                GraphPatch.status.in_(CONFIRMED_COMPETITOR_PATCH_STATUSES),
                GraphPatch.affected_object_id.in_(normalized_ids),
            )
        )
        return {
            str(item).strip().lower()
            for item in result.scalars().all()
            if str(item).strip()
        }

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

    def lexicon_entries(
        self,
        *,
        board_run: BoardRun,
        entity: Entity,
    ) -> list[EntityLexiconEntry]:
        return self._lexicon_entries(board_run=board_run, entity=entity)

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
        return any(self.contains_term(text, term) for term in entry.terms)

    @staticmethod
    def contains_term(text: str, term: str) -> bool:
        return GraphPatchBuilderService._contains_term(text, term)

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        needle = str(term or "").strip()
        if not needle:
            return False
        haystack = text or ""
        if needle.isascii():
            return needle.lower() in haystack.lower()

        start = 0
        while True:
            index = haystack.find(needle, start)
            if index < 0:
                return False
            previous_char = haystack[index - 1] if index > 0 else ""
            next_index = index + len(needle)
            next_char = haystack[next_index] if next_index < len(haystack) else ""
            if previous_char in CHINESE_NEGATION_PREFIXES:
                start = next_index
                continue
            if len(needle) <= 2 and next_char in CHINESE_GLUE_SUFFIXES:
                start = next_index
                continue
            return True

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
        confirmed_competitor_ids: set[str],
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
            confidence = self._competitor_confidence_from_answers(candidate_answers, base=0.58)
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
            is_confirmed_competitor = candidate.entity_id.lower() in confirmed_competitor_ids
            patch_type = "update_strength" if is_confirmed_competitor else "add_competitor_relation"
            patches.append(
                GraphPatch(
                    graph_update_id=graph_update.id,
                    entity_id=entity.id,
                    patch_type=patch_type,
                    status=allocation["status"],
                    title=(
                        f"更新{candidate.label}竞品关系强度"
                        if is_confirmed_competitor
                        else f"新增{candidate.label}竞品候选"
                    ),
                    description=(
                        "已确认竞品关系在本次抓取中再次出现，当前补丁只更新连接强度。"
                        if is_confirmed_competitor
                        else "真实回答包含明确替代、推荐或对比信号，非同品类共现。"
                    ),
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
                        "existing_competitor_relation": is_confirmed_competitor,
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
    def question_text(
        answer: BrandPlatformAnswer,
        question_lookup: dict[str, str],
    ) -> str:
        return GraphPatchBuilderService._question_text(answer, question_lookup)

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
    def clip(text: str, limit: int) -> str:
        return GraphPatchBuilderService._clip(text, limit)

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
        answer_score = per_answer * math.log2(1 + len(answers))
        platform_score = per_platform * math.log2(1 + len(platforms))
        return min(cap, int(base + answer_score + platform_score))

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
    def _competitor_confidence_from_answers(
        answers: list[BrandPlatformAnswer],
        *,
        base: float,
    ) -> float:
        platforms = {answer.platform for answer in answers if answer.platform}
        confidence = base + len(answers) * 0.015 + len(platforms) * 0.04
        return round(min(0.9, confidence), 2)

    @staticmethod
    def _platform_label(answers: list[BrandPlatformAnswer]) -> str:
        platforms = sorted({answer.platform for answer in answers if answer.platform})
        return "、".join(platforms[:4]) if platforms else "AI 平台"


class BrandSpaceService:
    """Persistent state source for the Brand Space MVP."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        asset_storage_root: str | Path | None = None,
    ) -> None:
        self.db = db
        self.asset_storage_root = Path(asset_storage_root) if asset_storage_root else None

    async def get_space(self, *, entity_id: str | UUID, current_user: User) -> dict[str, Any]:
        entity = await self._require_entity(entity_id, current_user)
        entity_uuid = entity.id
        board_run = await self._default_board_run_for_space(entity.id)
        if board_run is not None:
            if await self._safe_sync_real_board_run(board_run=board_run, current_user=current_user):
                entity = await self._entity_by_id(entity_uuid)
                board_run = await self._default_board_run_for_space(entity_uuid)
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

        current_run = await self._default_board_run_for_space(entity.id)
        current_graph_update = (
            await self._graph_update_for_run(current_run.id)
            if current_run is not None
            else None
        )
        if current_graph_update is None:
            return {
                "review_items": [],
                "summary": self._review_items_summary([]),
            }

        query = (
            select(GraphPatch, GraphUpdate)
            .join(GraphUpdate, GraphPatch.graph_update_id == GraphUpdate.id)
            .where(GraphUpdate.id == current_graph_update.id)
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
        default_platforms = (
            BRAND_SPACE_DEFAULT_SCAFFOLD_PLATFORMS
            if is_scaffold
            else BRAND_SPACE_DEFAULT_REAL_PLATFORMS
        )
        effective_input_scope = input_scope or {"platforms": list(default_platforms)}
        intelligence_run = await BrandIntelligenceRunService(self.db).create_or_reuse_run(
            entity_id=entity.id,
            current_user=current_user,
            run_goal="通过 Brand Space 画布更新品牌实体关系图谱",
            analysis_mode="panorama",
            input_scope=effective_input_scope,
            origin_surface="brand_space",
            origin_event_id=f"brand-space:scaffold:{entity.id}" if is_scaffold else None,
            start_immediately=not is_scaffold,
            commit=False,
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
        await self.db.flush()
        try:
            payload = await self._space_payload(entity=entity, board_run=board_run)
        except Exception:
            await self.db.rollback()
            raise
        await self.db.commit()
        return payload

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
        await self._safe_sync_real_board_run(board_run=board_run, current_user=current_user, force=True)
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
        await self._safe_sync_real_board_run(board_run=board_run, current_user=current_user)
        entity = await self._entity_by_id(board_run.entity_id)
        return await self._space_payload(entity=entity, board_run=board_run)

    async def claim_graph_update_build(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
    ) -> bool:
        board_run = await self._require_board_run(run_id, current_user)
        output_refs = dict(board_run.output_refs or {})
        if output_refs.get("graph_update_build_status") != "pending":
            return False
        board_run.output_refs = {
            **output_refs,
            "graph_update_build_status": "queued",
            "graph_update_build_queued_at": _now().isoformat(),
        }
        await self.db.commit()
        return True

    async def update_board_run_status(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
        status: str,
    ) -> dict[str, Any]:
        board_run = await self._require_board_run(run_id, current_user)
        if not board_run.is_scaffold:
            await self._safe_sync_real_board_run(board_run=board_run, current_user=current_user, force=True)
        intelligence_run_to_cancel: UUID | None = None
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
                intelligence_run_to_cancel = board_run.brand_intelligence_run_id
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
        entity = await self._entity_by_id(board_run.entity_id)
        await self.db.flush()
        try:
            payload = await self._space_payload(entity=entity, board_run=board_run)
        except Exception:
            await self.db.rollback()
            raise
        if intelligence_run_to_cancel is not None:
            await BrandIntelligenceRunService(self.db).cancel_run(
                run_id=intelligence_run_to_cancel,
                current_user=current_user,
            )
        await self.db.commit()
        return payload

    async def get_events(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
        limit: int = 100,
        offset: int = 0,
        after_sequence: int | None = None,
        sync: bool = False,
    ) -> dict[str, Any]:
        board_run = await self._require_board_run(run_id, current_user)
        if sync:
            await self._safe_sync_real_board_run(board_run=board_run, current_user=current_user)
        bounded_limit = self._bounded_limit(limit, default=100, maximum=500)
        if after_sequence is not None:
            bounded_after_sequence = self._bounded_offset(after_sequence)
            events, has_more = await self._events_after(
                board_run.id,
                after_sequence=bounded_after_sequence,
                limit=bounded_limit,
            )
            next_sequence = max(
                [
                    bounded_after_sequence,
                    *[
                        sequence
                        for sequence in (self._event_sequence_value(event) for event in events)
                        if sequence is not None
                    ],
                ]
            )
            return {
                "events": [self._event_to_dict(event) for event in events],
                "pagination": {
                    "limit": bounded_limit,
                    "offset": 0,
                    "total": None,
                    "has_more": has_more,
                },
                "cursor": {
                    "after_sequence": bounded_after_sequence,
                    "next_sequence": next_sequence,
                    "has_more": has_more,
                },
            }
        events = await self._events(board_run.id, limit=bounded_limit, offset=offset)
        total = await self._event_count(board_run.id)
        next_sequence = max(
            [
                0,
                *[
                    sequence
                    for sequence in (self._event_sequence_value(event) for event in events)
                    if sequence is not None
                ],
            ]
        )
        return {
            "events": [self._event_to_dict(event) for event in events],
            "pagination": self._pagination(limit=bounded_limit, offset=offset, total=total, maximum=500),
            "cursor": {
                "after_sequence": None,
                "next_sequence": next_sequence,
                "has_more": self._bounded_offset(offset) + bounded_limit < total,
            },
        }

    async def get_assets(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sync: bool = False,
    ) -> dict[str, Any]:
        board_run = await self._require_board_run(run_id, current_user)
        if sync:
            await self._safe_sync_real_board_run(board_run=board_run, current_user=current_user)
        artifacts = await self._artifacts(
            board_run.id,
            artifact_type=artifact_type,
            limit=limit,
            offset=offset,
        )
        total = await self._artifact_count(board_run.id, artifact_type=artifact_type)
        by_type = await self._artifact_type_counts(board_run.id)
        return {
            "artifacts": [
                await self._artifact_to_dict_for_run(artifact, board_run)
                for artifact in artifacts
            ],
            "summary": {
                "total": total,
                "returned": len(artifacts),
                "by_type": by_type,
            },
            "pagination": self._pagination(limit=limit, offset=offset, total=total),
        }

    async def get_artifact_detail(
        self,
        *,
        artifact_id: str | UUID,
        current_user: User,
        sync: bool = False,
    ) -> dict[str, Any]:
        artifact = await self._require_artifact(artifact_id, current_user)
        board_run = await self._require_board_run(artifact.board_run_id, current_user)
        if sync:
            await self._safe_sync_real_board_run(board_run=board_run, current_user=current_user)
        node_run = await self.db.get(BoardNodeRun, artifact.node_run_id) if artifact.node_run_id else None
        graph_update = await self._graph_update_for_run(board_run.id)
        latest_report = (
            await self._latest_report_for_graph_update(graph_update.id)
            if graph_update is not None
            else None
        )
        report_for_artifact = await self._report_for_artifact(
            artifact=artifact,
            fallback=latest_report,
        )
        preview = await self._artifact_preview(
            artifact=artifact,
            board_run=board_run,
            graph_update=graph_update,
            latest_report=report_for_artifact,
        )
        artifact_payload = await self._artifact_to_dict_for_run(artifact, board_run)
        if artifact.artifact_type in {"raw_answers", "parsed_answers"}:
            artifact_payload["rowCount"] = max(
                int(artifact_payload.get("rowCount") or 0),
                int(preview.get("rowCount") or 0),
            )
        return {
            "artifact": artifact_payload,
            "preview": preview,
            "trace": self._artifact_trace(
                artifact=artifact,
                board_run=board_run,
                node_run=node_run,
                graph_update=graph_update,
                latest_report=report_for_artifact,
            ),
            "access": self._public_artifact_access_descriptor(
                self._artifact_access_descriptor(artifact)
            ),
        }

    async def get_artifact_access(
        self,
        *,
        artifact_id: str | UUID,
        current_user: User,
    ) -> dict[str, Any]:
        artifact = await self._require_artifact(artifact_id, current_user)
        return {
            "artifact_id": str(artifact.id),
            "artifact_key": artifact.artifact_key,
            "access": self._public_artifact_access_descriptor(
                self._artifact_access_descriptor(artifact)
            ),
        }

    async def resolve_artifact_download(
        self,
        *,
        artifact_id: str | UUID,
        current_user: User,
    ) -> dict[str, Any]:
        artifact = await self._require_artifact(artifact_id, current_user)
        descriptor = self._artifact_access_descriptor(artifact, include_local_path=True)
        if not descriptor.get("available"):
            reason = descriptor.get("reason") or "object_not_available"
            raise LookupError(f"Artifact object is not available: {reason}")
        object_path = descriptor.get("_local_path")
        if not isinstance(object_path, Path) or not object_path.is_file():
            raise LookupError("Artifact object file not found")
        return {
            "path": object_path,
            "filename": descriptor.get("filename") or object_path.name,
            "media_type": artifact.mime_type or "application/octet-stream",
        }

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
        all_patches_terminal = all(
            item.status in IMMUTABLE_PATCH_STATUSES | {"blocked"} for item in patches
        )
        version_conflict = (
            await self._graph_update_apply_conflict(graph_update)
            if all_patches_terminal
            else None
        )
        if version_conflict:
            graph_update.status = "failed"
        elif all_patches_terminal:
            graph_update.status = "applied"
        elif any(item.status == "needs_review" for item in patches):
            graph_update.status = "needs_review"
        else:
            graph_update.status = "partial"
        entity = await self._entity_by_id(graph_update.entity_id)
        graph_update.summary = self._graph_update_summary(patches)
        if version_conflict:
            graph_update.summary = {
                **(graph_update.summary or {}),
                "version_conflict": version_conflict,
            }
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
        if version_conflict:
            await self.db.flush()
            await self._append_event(
                entity_id=patch.entity_id,
                board_run_id=graph_update.board_run_id,
                node_id="graph-update",
                event_type="graph_update_version_conflict",
                severity="error",
                message="图谱更新基线已过期，已阻止应用。",
                payload={
                    "graph_update_id": str(graph_update.id),
                    **version_conflict,
                },
            )
        elif previous_graph_update_status != "applied" and graph_update.status == "applied":
            await self.db.flush()
            await self._append_event(
                entity_id=patch.entity_id,
                board_run_id=graph_update.board_run_id,
                node_id="graph-update",
                event_type="graph_update_applied",
                severity="success",
                message="图谱更新已进入已应用状态。",
                payload={
                    "graph_update_id": str(graph_update.id),
                    "before_graph_version": graph_update.before_graph_version,
                    "after_graph_version": graph_update.after_graph_version,
                },
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
        report_payload = await self._build_report_payload(
            entity=entity,
            graph_update=graph_update,
            patches=patches,
        )
        guardrails = self.validate_report_payload(report_payload, patches)
        has_block = any(item["severity"] == "block" for item in guardrails)
        blocking_guardrail_keys = [
            item["guardrail_key"] for item in guardrails if item["severity"] == "block"
        ]
        publication_status = (
            "needs_review" if has_block else "publishable" if publish_requested else "draft"
        )
        report_payload["publication_status"] = publication_status
        report_payload["blocking_guardrail_keys"] = blocking_guardrail_keys

        await self._lock_report_version_scope(graph_update.id)
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
            title=str(report_payload.get("report_title") or f"{entity.name}圈层状态更新"),
            summary=str(report_payload.get("summary") or ""),
            payload=report_payload,
            publication_status=publication_status,
        )
        self.db.add(report)
        await self.db.flush()
        await self._register_report_artifact(
            graph_update=graph_update,
            report=report,
        )

        guardrail_records = await self._replace_report_guardrails(
            report=report,
            graph_update_id=graph_update.id,
            guardrails=guardrails,
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
            "guardrails": [self._guardrail_to_dict(item) for item in guardrail_records],
        }

    async def list_reports(
        self,
        *,
        entity_id: str | UUID,
        current_user: User,
        report_kind: str | None = None,
        publication_status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        entity = await self._require_entity(entity_id, current_user)
        should_scope_to_current_update = report_kind is None and publication_status is None
        if publication_status == "pre_graph_update" or not should_scope_to_current_update:
            reports = await self._reports_for_entity(
                entity_id=entity.id,
                report_kind=report_kind,
                publication_status=publication_status,
                limit=limit,
            )
        else:
            current_graph_update = await self._default_graph_update_for_entity(entity.id)
            reports = (
                await self._reports_for_entity(
                    entity_id=entity.id,
                    report_kind=report_kind,
                    publication_status=publication_status,
                    limit=limit,
                )
                if current_graph_update is not None
                else []
            )
            if current_graph_update is not None:
                reports = [
                    report
                    for report in reports
                    if self._report_matches_graph_update(report, current_graph_update.id)
                ]
        return {
            "reports": [self._report_summary_to_dict(report) for report in reports],
            "summary": {
                "total": len(reports),
                "graph_update": sum(1 for report in reports if self._report_source_type(report) == "graph_update"),
                "pre_graph_update": sum(
                    1 for report in reports if self._report_source_type(report) == "pre_graph_update"
                ),
            },
        }

    async def get_report(
        self,
        *,
        report_version_id: str | UUID,
        current_user: User,
    ) -> dict[str, Any]:
        report = await self._require_report(report_version_id, current_user)
        guardrails = await self._guardrails_for_report(report.id)
        return {
            "report": self._report_to_dict(report),
            "guardrails": [self._guardrail_to_dict(item) for item in guardrails],
        }

    async def publish_report(
        self,
        *,
        report_version_id: str | UUID,
        current_user: User,
    ) -> dict[str, Any]:
        report = await self._require_report(report_version_id, current_user)
        payload = dict(report.payload or {})
        if self._report_source_type(report) != "graph_update":
            raise ValueError("Pre-GraphUpdate reports cannot be published from Brand Space")
        graph_update_id = payload.get("graph_update_id")
        if not graph_update_id:
            raise ValueError("GraphUpdate-backed report is missing graph_update_id")
        graph_update_uuid = self._coerce_uuid(graph_update_id, "graph_update_id")
        patches = await self._patches(graph_update_uuid)
        live_guardrails = self.validate_report_payload(payload, patches)
        guardrails = await self._replace_report_guardrails(
            report=report,
            graph_update_id=graph_update_uuid,
            guardrails=live_guardrails,
        )
        blocking_guardrail_keys = [
            item.guardrail_key for item in guardrails if item.severity == "block"
        ]
        if blocking_guardrail_keys:
            payload["publication_status"] = "needs_review"
            payload["blocking_guardrail_keys"] = blocking_guardrail_keys
            report.payload = payload
            report.publication_status = "needs_review"
            await self.db.commit()
            raise ValueError("Report has blocking guardrails and cannot be published")
        payload["publication_status"] = "published"
        payload["blocking_guardrail_keys"] = []
        payload["published_at"] = _now().isoformat()
        payload["published_by_user_id"] = str(current_user.id)
        report.payload = payload
        report.publication_status = "published"
        await self.db.commit()
        return {
            "report": self._report_to_dict(report),
            "guardrails": [self._guardrail_to_dict(item) for item in guardrails],
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
            if patch.relation_type == "competes_with"
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

        platform_names = BrandSpaceService._report_known_platform_names(patches)
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
        patch_ids = {str(patch.id) for patch in patches}
        referenced_patch_ids = {
            str(item.get("patch_id") or "")
            for collection_key in ("claims", "strategic_terms", "competitor_claims")
            for item in list(report_payload.get(collection_key) or [])
            if str(item.get("patch_id") or "").strip()
        }
        out_of_scope_patch_ids = sorted(
            patch_id for patch_id in referenced_patch_ids if patch_id not in patch_ids
        )
        results.append(
            {
                "guardrail_key": "graph_update_scope",
                "severity": "block" if out_of_scope_patch_ids else "pass",
                "title": "Graph Update 范围一致性",
                "message": (
                    "报告引用了本次 Graph Update 之外的补丁，不能发布。"
                    if out_of_scope_patch_ids
                    else "报告结论均限定在本次 Graph Update 范围内。"
                ),
                "payload": {"out_of_scope_patch_ids": out_of_scope_patch_ids},
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

    async def _require_artifact(self, artifact_id: str | UUID, current_user: User) -> BoardArtifact:
        artifact: BoardArtifact | None = None
        try:
            artifact_uuid = self._coerce_uuid(artifact_id, "artifact_id")
        except ValueError:
            result = await self.db.execute(
                select(BoardArtifact)
                .where(BoardArtifact.artifact_key == str(artifact_id))
                .order_by(desc(BoardArtifact.created_at))
                .limit(1)
            )
            artifact = result.scalar_one_or_none()
        else:
            result = await self.db.execute(
                select(BoardArtifact).where(BoardArtifact.id == artifact_uuid)
            )
            artifact = result.scalar_one_or_none()
        if artifact is None:
            raise LookupError("Artifact not found")
        await self._require_board_run(artifact.board_run_id, current_user)
        return artifact

    async def _require_report(self, report_version_id: str | UUID, current_user: User) -> BrandReportVersion:
        report_uuid = self._coerce_uuid(report_version_id, "report_version_id")
        result = await self.db.execute(
            select(BrandReportVersion).where(BrandReportVersion.id == report_uuid)
        )
        report = result.scalar_one_or_none()
        if report is None:
            raise LookupError("Report version not found")
        await self._require_entity(report.entity_id, current_user)
        return report

    @staticmethod
    def _coerce_uuid(value: str | UUID, field_name: str) -> UUID:
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid UUID for {field_name}: {value}") from exc

    @staticmethod
    def _bounded_limit(limit: int | None, *, default: int = 50, maximum: int = 200) -> int:
        try:
            value = int(limit if limit is not None else default)
        except (TypeError, ValueError):
            value = default
        return max(1, min(value, maximum))

    @staticmethod
    def _bounded_offset(offset: int | None) -> int:
        try:
            value = int(offset if offset is not None else 0)
        except (TypeError, ValueError):
            value = 0
        return max(0, value)

    def _pagination(
        self,
        *,
        limit: int,
        offset: int,
        total: int,
        maximum: int = 200,
    ) -> dict[str, int | bool]:
        bounded_limit = self._bounded_limit(limit, maximum=maximum)
        bounded_offset = self._bounded_offset(offset)
        return {
            "limit": bounded_limit,
            "offset": bounded_offset,
            "total": int(total),
            "has_more": bounded_offset + bounded_limit < int(total),
        }

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

    async def _safe_sync_real_board_run(
        self,
        *,
        board_run: BoardRun,
        current_user: User,
        force: bool = False,
    ) -> bool:
        try:
            return await self._sync_real_board_run(
                board_run=board_run,
                current_user=current_user,
                force=force,
            )
        except Exception as exc:
            run_id = board_run.id
            entity_id = board_run.entity_id
            logger.exception("Brand Space runtime sync failed for board run %s", run_id)
            await self.db.rollback()

            failed_run = await self.db.get(BoardRun, run_id)
            if failed_run is None:
                return False
            if (
                failed_run.status == "failed"
                and failed_run.error_code == "runtime_sync_failed"
            ):
                return True

            failed_run.status = "failed"
            failed_run.active_node_ids = []
            failed_run.error_code = "runtime_sync_failed"
            failed_run.error_message = "真实运行同步失败，已保留画布状态。"
            failed_run.last_synced_at = _now()
            await self._append_event(
                entity_id=entity_id,
                board_run_id=run_id,
                event_type="runtime_sync_failed",
                severity="error",
                message="真实运行同步失败，画布运行已标记失败。",
                payload={"error_type": exc.__class__.__name__},
            )
            await self.db.commit()
            return True

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
            build_immediately=force,
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
        build_immediately: bool = False,
    ) -> bool:
        if board_run.is_scaffold or intelligence_run.status != "completed":
            return False
        existing = await self._graph_update_for_run(board_run.id)
        if existing is not None:
            output_refs = dict(board_run.output_refs or {})
            if output_refs.get("graph_update_build_status") != "ready":
                board_run.output_refs = {
                    **output_refs,
                    "graph_update_id": str(existing.id),
                    "graph_update_build_status": "ready",
                }
                return True
            return False
        output_refs = dict(board_run.output_refs or {})
        if not build_immediately:
            if output_refs.get("graph_update_build_status") in GRAPH_UPDATE_BUILD_ACTIVE_STATUSES:
                return False
            board_run.output_refs = {
                **output_refs,
                "graph_update_build_status": "pending",
                "graph_update_build_requested_at": _now().isoformat(),
            }
            await self._append_event(
                entity_id=board_run.entity_id,
                board_run_id=board_run.id,
                node_id="graph-update",
                event_type="graph_update_build_pending",
                severity="info",
                message="真实抓取已完成，图谱更新构建已进入后台队列。",
                payload={
                    "brand_intelligence_run_id": str(intelligence_run.id),
                    "status": "pending",
                },
            )
            return True

        board_run.output_refs = {
            **output_refs,
            "graph_update_build_status": "building",
            "graph_update_build_started_at": _now().isoformat(),
        }

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
            "graph_update_build_status": "ready",
            "graph_update_build_completed_at": _now().isoformat(),
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
    ) -> dict[str, Any]:
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
        successful_answer_count = await self.db.scalar(
            select(func.count(BrandPlatformAnswer.id)).where(
                *answer_conditions,
                BrandPlatformAnswer.success.is_(True),
            )
        )
        platform_rows = (
            await self.db.execute(
                select(
                    BrandPlatformAnswer.platform,
                    BrandPlatformAnswer.success,
                    func.count(BrandPlatformAnswer.id),
                )
                .where(*answer_conditions)
                .group_by(BrandPlatformAnswer.platform, BrandPlatformAnswer.success)
            )
        ).all()
        platform_counts: dict[str, dict[str, int | str]] = {}
        for raw_platform, success, count in platform_rows:
            key = self._platform_key(raw_platform)
            item = platform_counts.setdefault(
                key,
                {
                    "platform": key,
                    "answers": 0,
                    "failures": 0,
                    "total": 0,
                },
            )
            row_count = int(count or 0)
            item["total"] = int(item["total"]) + row_count
            if success is True:
                item["answers"] = int(item["answers"]) + row_count
            else:
                item["failures"] = int(item["failures"]) + row_count
        return {
            "questions": int(question_count or 0),
            "answers": int(answer_count or 0),
            "successful_answers": int(successful_answer_count or 0),
            "snapshots": int(snapshot_count or 0),
            "platforms": platform_counts,
        }

    async def _sync_real_nodes(
        self,
        *,
        board_run: BoardRun,
        intelligence_run: BrandIntelligenceRun,
        counts: dict[str, Any],
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
        counts: dict[str, Any],
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

    async def _answer_asset_scope(self, board_run: BoardRun) -> dict[str, str | None]:
        output_refs = dict(board_run.output_refs or {})
        session_id: str | None = None
        output_session_id = output_refs.get("session_id")
        brand_intelligence_run_id = (
            str(board_run.brand_intelligence_run_id)
            if board_run.brand_intelligence_run_id
            else output_refs.get("brand_intelligence_run_id")
        )
        # Legacy BoardRuns can carry the run id only in output_refs; prefer the
        # normalized column when present, then fall back to the older payload.
        if board_run.brand_intelligence_run_id:
            intelligence_run = await self.db.get(
                BrandIntelligenceRun,
                board_run.brand_intelligence_run_id,
            )
            if intelligence_run is not None and intelligence_run.origin_session_id is not None:
                session_id = str(intelligence_run.origin_session_id)
        elif output_session_id:
            try:
                session_id = str(UUID(str(output_session_id)))
            except ValueError:
                logger.warning(
                    "Ignoring invalid answer asset session_id %s for board run %s",
                    output_session_id,
                    board_run.id,
                )
        mode = "run_session_answers" if session_id else "brand_recent_answers"
        return {
            "mode": mode,
            "session_id": session_id,
            "brand_intelligence_run_id": brand_intelligence_run_id,
        }

    async def _answer_conditions_for_board_run(self, board_run: BoardRun) -> list[Any]:
        conditions: list[Any] = [
            BrandPlatformAnswer.entity_id == board_run.entity_id,
            BrandPlatformAnswer.success.is_(True),
        ]
        scope = await self._answer_asset_scope(board_run)
        if scope.get("session_id"):
            conditions.append(BrandPlatformAnswer.session_id == UUID(str(scope["session_id"])))
        return conditions

    async def _answers_for_board_run(
        self,
        *,
        board_run: BoardRun,
        limit: int = 8,
    ) -> list[BrandPlatformAnswer]:
        result = await self.db.execute(
            select(BrandPlatformAnswer)
            .where(*(await self._answer_conditions_for_board_run(board_run)))
            .order_by(desc(BrandPlatformAnswer.captured_at), desc(BrandPlatformAnswer.created_at))
            .limit(max(1, int(limit)))
        )
        return list(result.scalars().all())

    def _answer_count_hint(self, board_run: BoardRun) -> int:
        real_counts = (board_run.output_refs or {}).get("real_counts")
        if not isinstance(real_counts, dict):
            return 0
        try:
            return max(0, int(real_counts.get("answers") or 0))
        except (TypeError, ValueError):
            return 0

    async def _question_lookup_for_answers(
        self,
        *,
        board_run: BoardRun,
        answers: list[BrandPlatformAnswer],
    ) -> dict[str, str]:
        scope = await self._answer_asset_scope(board_run)
        session_id = UUID(str(scope["session_id"])) if scope.get("session_id") else None
        return await GraphPatchBuilderService(self.db).question_lookup_for_answers(
            entity_id=board_run.entity_id,
            answers=answers,
            session_id=session_id,
        )

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
        counts: dict[str, Any],
    ) -> list[dict[str, str]]:
        if node_id == "brand-seed":
            return [{"label": "模式", "value": "真实"}, {"label": "状态", "value": intelligence_run.status}]
        if node_id == "question-set":
            return [{"label": "问题", "value": str(counts["questions"])}, {"label": "阶段", "value": intelligence_run.stage or "-"}]
        if node_id == "platform-rack":
            platform_count = len(counts.get("platforms") or {})
            return [{"label": "平台", "value": str(platform_count or "-")}, {"label": "回答", "value": str(counts["answers"])}]
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
            .order_by(desc(BoardRun.created_at), desc(BoardRun.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _default_board_run_for_space(self, entity_id: UUID) -> BoardRun | None:
        latest_run = await self._latest_board_run(entity_id)
        if latest_run is None:
            return None
        if latest_run.status in {"running", "paused", "pause_requested"}:
            return latest_run
        if await self._graph_update_for_run(latest_run.id):
            return latest_run

        latest_update = (
            await self._latest_graph_update(entity_id)
            or await self._latest_non_failed_graph_update(entity_id)
        )
        if latest_update is None or latest_update.board_run_id == latest_run.id:
            return latest_run
        result = await self.db.execute(
            select(BoardRun).where(
                BoardRun.id == latest_update.board_run_id,
                BoardRun.entity_id == entity_id,
            )
        )
        fallback_run = result.scalar_one_or_none()
        if fallback_run is not None and not fallback_run.is_scaffold:
            return fallback_run
        return latest_run

    async def _default_graph_update_for_entity(self, entity_id: UUID) -> GraphUpdate | None:
        board_run = await self._default_board_run_for_space(entity_id)
        if board_run is None:
            return None
        return await self._graph_update_for_run(board_run.id)

    async def _latest_graph_update(self, entity_id: UUID) -> GraphUpdate | None:
        latest_applied = await self._latest_applied_graph_update(entity_id)
        current_version = (
            latest_applied.after_graph_version if latest_applied else GRAPH_VERSION_BASE
        )
        # Bound the recent-update scan for the UI projection. Older non-failed updates
        # are still available through direct detail endpoints; this method chooses the
        # current working update or latest applied version for the brand overview.
        result = await self.db.execute(
            select(GraphUpdate)
            .where(GraphUpdate.entity_id == entity_id, GraphUpdate.status != "failed")
            .order_by(desc(GraphUpdate.created_at))
            .limit(50)
        )
        updates = list(result.scalars().all())
        for update in updates:
            if update.status == "applied":
                return update
            if update.before_graph_version == current_version:
                return update
        return latest_applied

    async def _latest_non_failed_graph_update(self, entity_id: UUID) -> GraphUpdate | None:
        result = await self.db.execute(
            select(GraphUpdate)
            .where(GraphUpdate.entity_id == entity_id, GraphUpdate.status != "failed")
            .order_by(desc(GraphUpdate.updated_at), desc(GraphUpdate.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_applied_graph_update(
        self,
        entity_id: UUID,
        *,
        exclude_update_id: UUID | None = None,
        for_update: bool = False,
    ) -> GraphUpdate | None:
        conditions = [GraphUpdate.entity_id == entity_id, GraphUpdate.status == "applied"]
        if exclude_update_id is not None:
            conditions.append(GraphUpdate.id != exclude_update_id)
        query = (
            select(GraphUpdate)
            .where(*conditions)
            .order_by(desc(GraphUpdate.updated_at), desc(GraphUpdate.created_at))
            .limit(1)
        )
        if for_update:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _lock_graph_update_entity_scope(self, entity_id: UUID) -> None:
        await self.db.execute(
            select(Entity.id)
            .where(Entity.id == entity_id)
            .with_for_update()
        )

    async def _next_graph_version_pair(self, entity_id: UUID) -> tuple[str, str]:
        latest_applied = await self._latest_applied_graph_update(entity_id)
        before_version = (
            latest_applied.after_graph_version if latest_applied else GRAPH_VERSION_BASE
        )
        return before_version, self._next_graph_version(before_version)

    @staticmethod
    def _next_graph_version(version: str | None) -> str:
        # MVP version policy: each applied GraphUpdate increments the minor version.
        # Major bumps are reserved for future explicit reset/rebrand flows.
        match = GRAPH_VERSION_PATTERN.match(str(version or ""))
        if not match:
            return "v0.1.0"
        major = int(match.group("major"))
        minor = int(match.group("minor"))
        return f"v{major}.{minor + 1}.0"

    async def _latest_report(self, entity_id: UUID) -> BrandReportVersion | None:
        result = await self.db.execute(
            select(BrandReportVersion)
            .where(BrandReportVersion.entity_id == entity_id)
            .order_by(desc(BrandReportVersion.created_at), desc(BrandReportVersion.version))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _latest_graph_update_report(self, entity_id: UUID) -> BrandReportVersion | None:
        reports = await self._reports_for_entity(entity_id=entity_id, limit=1)
        return reports[0] if reports else None

    async def _reports_for_entity(
        self,
        *,
        entity_id: UUID,
        report_kind: str | None = None,
        publication_status: str | None = None,
        limit: int = 50,
    ) -> list[BrandReportVersion]:
        bounded_limit = max(1, min(int(limit or 50), 200))
        conditions = [BrandReportVersion.entity_id == entity_id]
        if report_kind:
            conditions.append(BrandReportVersion.report_kind == report_kind)
        if publication_status and publication_status != "pre_graph_update":
            return await self._reports_for_publication_status(
                conditions=conditions,
                publication_status=publication_status,
                limit=bounded_limit,
            )
        if publication_status == "pre_graph_update":
            result = await self.db.execute(
                select(BrandReportVersion)
                .where(
                    *conditions,
                    BrandReportVersion.publication_status == "pre_graph_update",
                )
                .order_by(desc(BrandReportVersion.created_at), desc(BrandReportVersion.version))
                .limit(bounded_limit)
            )
            filtered = list(result.scalars().all())
            if len(filtered) >= bounded_limit:
                return filtered[:bounded_limit]
            fallback = await self._legacy_pre_graph_update_reports(
                conditions=conditions,
                existing_ids={report.id for report in filtered},
                limit=bounded_limit - len(filtered),
            )
            return [*filtered, *fallback][:bounded_limit]
        return await self._graph_update_reports(
            conditions=conditions,
            limit=bounded_limit,
        )

    async def _graph_update_reports(
        self,
        *,
        conditions: list[Any],
        limit: int,
    ) -> list[BrandReportVersion]:
        filtered: list[BrandReportVersion] = []
        scanned = 0
        page_size = 200
        max_scan = 5000
        while True:
            result = await self.db.execute(
                select(BrandReportVersion)
                .where(*conditions)
                .order_by(desc(BrandReportVersion.created_at), desc(BrandReportVersion.version))
                .limit(page_size)
                .offset(scanned)
            )
            reports = list(result.scalars().all())
            if not reports:
                break
            scanned += len(reports)
            filtered.extend(
                report for report in reports if self._report_source_type(report) == "graph_update"
            )
            if len(filtered) >= limit or len(reports) < page_size or scanned >= max_scan:
                break
        return filtered[:limit]

    async def _reports_for_publication_status(
        self,
        *,
        conditions: list[Any],
        publication_status: str,
        limit: int,
    ) -> list[BrandReportVersion]:
        filtered: list[BrandReportVersion] = []
        scanned = 0
        page_size = 200
        max_scan = 5000
        while True:
            result = await self.db.execute(
                select(BrandReportVersion)
                .where(
                    *conditions,
                    BrandReportVersion.publication_status == publication_status,
                )
                .order_by(desc(BrandReportVersion.created_at), desc(BrandReportVersion.version))
                .limit(page_size)
                .offset(scanned)
            )
            reports = list(result.scalars().all())
            if not reports:
                break
            scanned += len(reports)
            # SQL narrows by the denormalized status column; this final check
            # rejects legacy rows whose column default is stale but source type
            # still resolves to pre_graph_update from report_id/artifact payload.
            filtered.extend(
                report
                for report in reports
                if self._report_publication_status(report) == publication_status
            )
            if len(filtered) >= limit or len(reports) < page_size or scanned >= max_scan:
                break
        return filtered[:limit]

    async def _legacy_pre_graph_update_reports(
        self,
        *,
        conditions: list[Any],
        existing_ids: set[UUID],
        limit: int,
    ) -> list[BrandReportVersion]:
        if limit <= 0:
            return []
        filtered: list[BrandReportVersion] = []
        scanned = 0
        page_size = 200
        max_scan = 5000
        while True:
            result = await self.db.execute(
                select(BrandReportVersion)
                .where(*conditions)
                .order_by(desc(BrandReportVersion.created_at), desc(BrandReportVersion.version))
                .limit(page_size)
                .offset(scanned)
            )
            reports = list(result.scalars().all())
            if not reports:
                break
            scanned += len(reports)
            filtered.extend(
                report
                for report in reports
                if report.id not in existing_ids
                and self._report_source_type(report) == "pre_graph_update"
            )
            if len(filtered) >= limit or len(reports) < page_size or scanned >= max_scan:
                break
        return filtered[:limit]

    async def _space_payload(self, *, entity: Entity, board_run: BoardRun | None) -> dict[str, Any]:
        if board_run is None:
            return self._empty_space_payload(entity)
        nodes = await self._node_runs(board_run.id)
        artifacts = await self._artifacts(board_run.id)
        events = await self._latest_events(board_run.id, limit=240)
        graph_update = await self._graph_update_for_run(board_run.id)
        patches = await self._patches(graph_update.id) if graph_update else []
        graph = (
            graph_update.graph_snapshot
            if graph_update and graph_update.graph_snapshot
            else await self._fallback_graph(
                entity=entity,
                patches=patches,
                runtime_pending=(
                    not board_run.is_scaffold
                    and graph_update is None
                    and board_run.status in {"running", "pause_requested"}
                ),
            )
        )
        latest_report = (
            await self._latest_report_for_graph_update(graph_update.id)
            if graph_update
            else None
        )
        if latest_report:
            guardrails = await self._guardrails_for_report(latest_report.id)
        elif graph_update:
            guardrails = await self._guardrails(graph_update.id)
        else:
            guardrails = []
        reports = await self._reports_for_entity(entity_id=entity.id, limit=20)
        reports = (
            [report for report in reports if self._report_matches_graph_update(report, graph_update.id)]
            if graph_update
            else []
        )
        return {
            "context": self._context_to_dict(entity=entity, board_run=board_run, graph_update=graph_update),
            "run": self._board_run_to_dict(board_run),
            "nodes": [self._node_to_dict(node) for node in nodes],
            "edges": BOARD_EDGES,
            "platforms": self._platforms_for_run(board_run),
            "artifacts": [
                await self._artifact_to_dict_for_run(artifact, board_run)
                for artifact in artifacts
            ],
            "events": [self._event_to_dict(event) for event in events],
            "graph": graph,
            "graph_update": self._graph_update_to_dict(graph_update) if graph_update else None,
            "patches": [self._patch_to_dict(patch) for patch in patches],
            "guardrails": [self._guardrail_to_dict(item) for item in guardrails],
            "report": self._report_to_dict(latest_report) if latest_report else None,
            "reports": [self._report_summary_to_dict(report) for report in reports],
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
            "report": None,
            "reports": [],
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
                "platform-rack": [{"label": "运行中", "value": "多平台"}, {"label": "回答", "value": "994"}],
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
        before_graph_version, after_graph_version = await self._next_graph_version_pair(entity.id)
        graph_update = GraphUpdate(
            entity_id=entity.id,
            board_run_id=board_run.id,
            created_by_user_id=current_user.id,
            before_graph_version=before_graph_version,
            after_graph_version=after_graph_version,
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

    async def _graph_update_apply_conflict(
        self,
        graph_update: GraphUpdate,
    ) -> dict[str, Any] | None:
        await self._lock_graph_update_entity_scope(graph_update.entity_id)
        expected_version = graph_update.before_graph_version or GRAPH_VERSION_BASE
        latest_applied = await self._latest_applied_graph_update(
            graph_update.entity_id,
            exclude_update_id=graph_update.id,
            for_update=True,
        )
        current_version = (
            latest_applied.after_graph_version if latest_applied else GRAPH_VERSION_BASE
        )
        if current_version == expected_version:
            return None
        return {
            "expected_before_graph_version": expected_version,
            "current_graph_version": current_version,
            "latest_applied_graph_update_id": str(latest_applied.id)
            if latest_applied
            else None,
        }

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
                ("node_progress", "info", "AI 平台正在并行抓取。", "platform-rack"),
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

    async def _artifacts(
        self,
        board_run_id: UUID,
        *,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BoardArtifact]:
        conditions = [BoardArtifact.board_run_id == board_run_id]
        if artifact_type:
            conditions.append(BoardArtifact.artifact_type == artifact_type)
        result = await self.db.execute(
            select(BoardArtifact)
            .where(*conditions)
            .order_by(BoardArtifact.created_at)
            .limit(self._bounded_limit(limit, default=50, maximum=200))
            .offset(self._bounded_offset(offset))
        )
        return list(result.scalars().all())

    async def _artifact_count(
        self,
        board_run_id: UUID,
        *,
        artifact_type: str | None = None,
    ) -> int:
        conditions = [BoardArtifact.board_run_id == board_run_id]
        if artifact_type:
            conditions.append(BoardArtifact.artifact_type == artifact_type)
        result = await self.db.execute(
            select(func.count(BoardArtifact.id)).where(*conditions)
        )
        return int(result.scalar_one() or 0)

    async def _artifact_type_counts(self, board_run_id: UUID) -> dict[str, int]:
        result = await self.db.execute(
            select(BoardArtifact.artifact_type, func.count(BoardArtifact.id))
            .where(BoardArtifact.board_run_id == board_run_id)
            .group_by(BoardArtifact.artifact_type)
        )
        return {str(artifact_type): int(count) for artifact_type, count in result.all()}

    async def _events(
        self,
        board_run_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BoardRuntimeEvent]:
        result = await self.db.execute(
            select(BoardRuntimeEvent)
            .where(BoardRuntimeEvent.board_run_id == board_run_id)
            .order_by(BoardRuntimeEvent.sequence)
            .limit(self._bounded_limit(limit, default=100, maximum=500))
            .offset(self._bounded_offset(offset))
        )
        return list(result.scalars().all())

    async def _latest_events(
        self,
        board_run_id: UUID,
        *,
        limit: int = 100,
    ) -> list[BoardRuntimeEvent]:
        result = await self.db.execute(
            select(BoardRuntimeEvent)
            .where(BoardRuntimeEvent.board_run_id == board_run_id)
            .order_by(desc(BoardRuntimeEvent.sequence))
            .limit(self._bounded_limit(limit, default=100, maximum=500))
        )
        return list(reversed(list(result.scalars().all())))

    async def _events_after(
        self,
        board_run_id: UUID,
        *,
        after_sequence: int,
        limit: int = 100,
    ) -> tuple[list[BoardRuntimeEvent], bool]:
        bounded_limit = self._bounded_limit(limit, default=100, maximum=500)
        result = await self.db.execute(
            select(BoardRuntimeEvent)
            .where(
                BoardRuntimeEvent.board_run_id == board_run_id,
                BoardRuntimeEvent.sequence > self._bounded_offset(after_sequence),
            )
            .order_by(BoardRuntimeEvent.sequence)
            .limit(bounded_limit + 1)
        )
        rows = list(result.scalars().all())
        return rows[:bounded_limit], len(rows) > bounded_limit

    async def _event_count(self, board_run_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(BoardRuntimeEvent.id)).where(
                BoardRuntimeEvent.board_run_id == board_run_id
            )
        )
        return int(result.scalar_one() or 0)

    async def _artifact_preview(
        self,
        *,
        artifact: BoardArtifact,
        board_run: BoardRun,
        graph_update: GraphUpdate | None,
        latest_report: BrandReportVersion | None,
    ) -> dict[str, Any]:
        artifact_type = artifact.artifact_type
        row_count = int(artifact.row_count or 0)
        if artifact_type == "graph_patch_set" or artifact_type == "review_queue":
            patches = await self._patches(graph_update.id) if graph_update is not None else []
            rows = [
                {
                    "title": patch.title,
                    "status": patch.status,
                    "relation": patch.relation_type or patch.patch_type,
                    "score": int(patch.connection_strength or 0),
                    "evidence": len(patch.evidence_refs or []),
                }
                for patch in patches[:12]
            ]
            if artifact_type == "review_queue":
                rows = [row for row in rows if row["status"] in {"needs_review", "blocked"}]
            if graph_update is None:
                empty_summary = "本次运行尚未生成 GraphUpdate，补丁集资产暂无预览内容。"
            elif artifact_type == "review_queue":
                empty_summary = "当前 GraphUpdate 没有需要人工审阅的补丁。"
            else:
                empty_summary = "当前 GraphUpdate 尚未产生图谱补丁。"
            return self._table_preview(
                title=artifact.label,
                columns=[
                    {"key": "title", "label": "补丁"},
                    {"key": "status", "label": "状态"},
                    {"key": "relation", "label": "关系"},
                    {"key": "score", "label": "强度"},
                    {"key": "evidence", "label": "证据"},
                ],
                rows=rows,
                row_count=row_count or len(rows),
                truncated=len(patches) > len(rows),
                empty_summary=empty_summary,
            )
        if artifact_type == "graph_update":
            return {
                "kind": "json",
                "title": artifact.label,
                "json": self._graph_update_to_dict(graph_update) if graph_update else {},
                "rowCount": 1 if graph_update else 0,
                "truncated": False,
            }
        if artifact_type == "report":
            return {
                "kind": "summary",
                "title": artifact.label,
                "summary": latest_report.summary if latest_report else "当前运行还没有生成图谱解读报告。",
                "items": (
                    [
                        {"label": "报告版本", "value": f"v{latest_report.version}"},
                        {"label": "发布状态", "value": self._report_publication_status(latest_report)},
                    ]
                    if latest_report
                    else []
                ),
                "rowCount": 1 if latest_report else 0,
                "truncated": False,
            }
        if artifact_type == "entity_lexicon":
            entries = board_run.input_scope.get("entity_lexicon", []) if board_run.input_scope else []
            rows = [
                {
                    "label": str(item.get("label") or item.get("name") or ""),
                    "type": str(item.get("entity_type") or item.get("type") or ""),
                    "aliases": ", ".join(str(alias) for alias in item.get("aliases", [])[:4])
                    if isinstance(item, dict)
                    else "",
                }
                for item in entries[:12]
                if isinstance(item, dict)
            ]
            return self._table_preview(
                title=artifact.label,
                columns=[
                    {"key": "label", "label": "实体"},
                    {"key": "type", "label": "类型"},
                    {"key": "aliases", "label": "别名"},
                ],
                rows=rows,
                row_count=row_count or len(entries),
                truncated=len(entries) > len(rows),
                empty_summary="实体词表来自本次运行的 input_scope；当前资产只有登记信息，没有内联词表内容。",
            )
        if artifact_type == "question_set":
            questions = board_run.input_scope.get("questions", []) if board_run.input_scope else []
            if not questions:
                return {
                    "kind": "summary",
                    "title": artifact.label,
                    "summary": "问题集资产已登记；大批量问题不在列表接口中内联。",
                    "items": [{"label": "登记问题数", "value": row_count}],
                    "rowCount": row_count,
                    "truncated": False,
                }
            return {
                "kind": "jsonl",
                "title": artifact.label,
                "lines": self._question_preview_lines(questions),
                "rowCount": row_count,
                "truncated": row_count > 6,
            }
        if artifact_type in {"raw_answers", "parsed_answers"}:
            return await self._answer_artifact_preview(
                artifact=artifact,
                board_run=board_run,
                parsed=artifact_type == "parsed_answers",
            )
        if artifact_type == "entity_relation_set":
            graph_snapshot = graph_update.graph_snapshot if graph_update is not None else {}
            rows = [
                {
                    "from": relation.get("from"),
                    "to": relation.get("to"),
                    "kind": relation.get("kind"),
                    "strength": relation.get("strength"),
                }
                for relation in (graph_snapshot or {}).get("relations", [])[:12]
            ]
            return self._table_preview(
                title=artifact.label,
                columns=[
                    {"key": "from", "label": "起点"},
                    {"key": "to", "label": "终点"},
                    {"key": "kind", "label": "关系"},
                    {"key": "strength", "label": "强度"},
                ],
                rows=rows,
                row_count=row_count or len(rows),
                truncated=len((graph_snapshot or {}).get("relations", [])) > len(rows),
            )
        return {
            "kind": "summary",
            "title": artifact.label,
            "summary": "该资产当前只有登记信息。大文件或外部对象不会在详情中直接内联。",
            "items": [
                {"label": "类型", "value": artifact.artifact_type},
                {"label": "MIME", "value": artifact.mime_type},
                {"label": "记录数", "value": row_count},
            ],
            "rowCount": row_count,
            "truncated": False,
        }

    def _artifact_trace(
        self,
        *,
        artifact: BoardArtifact,
        board_run: BoardRun,
        node_run: BoardNodeRun | None,
        graph_update: GraphUpdate | None,
        latest_report: BrandReportVersion | None,
    ) -> dict[str, Any]:
        links: list[dict[str, Any]] = [
            {
                "kind": "board_run",
                "id": str(board_run.id),
                "label": f"画布运行 {board_run.board_id}",
                "targetView": "boards",
            }
        ]
        if node_run is not None:
            links.append(
                {
                    "kind": "node_run",
                    "id": str(node_run.id),
                    "label": node_run.title,
                    "nodeId": node_run.node_id,
                    "targetView": "boards",
                }
            )
        if graph_update is not None and artifact.artifact_type in {
            "entity_relation_set",
            "graph_patch_set",
            "review_queue",
            "graph_update",
            "report",
        }:
            links.append(
                {
                    "kind": "graph_update",
                    "id": str(graph_update.id),
                    "label": f"{graph_update.before_graph_version} → {graph_update.after_graph_version}",
                    "targetView": "graph",
                }
            )
        if latest_report is not None and artifact.artifact_type in {"report", "graph_update", "graph_patch_set"}:
            links.append(
                {
                    "kind": "report_version",
                    "id": str(latest_report.id),
                    "label": f"{latest_report.title} v{latest_report.version}",
                    "targetView": "reports",
                    "reportVersionId": str(latest_report.id),
                }
            )
        return {
            "links": links,
            "boardRun": self._board_run_to_dict(board_run),
            "nodeRun": self._node_to_dict(node_run) if node_run is not None else None,
            "graphUpdate": self._graph_update_to_dict(graph_update),
            "report": self._report_summary_to_dict(latest_report) if latest_report else None,
        }

    async def _answer_artifact_preview(
        self,
        *,
        artifact: BoardArtifact,
        board_run: BoardRun,
        parsed: bool,
    ) -> dict[str, Any]:
        answers = await self._answers_for_board_run(board_run=board_run, limit=9)
        question_lookup = await self._question_lookup_for_answers(
            board_run=board_run,
            answers=answers,
        )
        preview_answers = answers[:8]
        row_count = max(int(artifact.row_count or 0), self._answer_count_hint(board_run), len(answers))
        truncated = row_count > len(preview_answers)
        rows = [
            {
                "platform": answer.platform,
                "question": GraphPatchBuilderService.question_text(answer, question_lookup),
                "brand": "是" if answer.brand_mentioned else "否",
                "excerpt": GraphPatchBuilderService.clip(answer.answer_text or "", 120),
            }
            for answer in preview_answers
        ]
        if parsed:
            return self._table_preview(
                title=artifact.label,
                columns=[
                    {"key": "platform", "label": "平台"},
                    {"key": "question", "label": "问题"},
                    {"key": "brand", "label": "提及品牌"},
                    {"key": "excerpt", "label": "摘要"},
                ],
                rows=rows,
                row_count=row_count,
                truncated=truncated,
                empty_summary="标准化答案表已登记，但当前运行没有可内联预览的回答样本。",
            )
        return {
            "kind": "jsonl",
            "title": artifact.label,
            "lines": [
                json.dumps(
                    {
                        "platform": row["platform"],
                        "question": row["question"],
                        "answer_excerpt": row["excerpt"],
                    },
                    ensure_ascii=False,
                )
                for row in rows
            ],
            "rowCount": row_count,
            "truncated": truncated,
            "emptySummary": "原始答案已登记，但当前运行没有可内联预览的回答样本。",
        }

    @staticmethod
    def _question_preview_lines(questions: list[Any]) -> list[str]:
        return [
            json.dumps({"question": str(question)}, ensure_ascii=False)
            for question in questions[:6]
        ]

    @staticmethod
    def _table_preview(
        *,
        title: str,
        columns: list[dict[str, str]],
        rows: list[dict[str, Any]],
        row_count: int,
        truncated: bool,
        empty_summary: str | None = None,
    ) -> dict[str, Any]:
        if not rows and empty_summary:
            return {
                "kind": "summary",
                "title": title,
                "summary": empty_summary,
                "items": [{"label": "记录数", "value": row_count}],
                "rowCount": row_count,
                "truncated": False,
            }
        return {
            "kind": "table",
            "title": title,
            "columns": columns,
            "rows": rows,
            "rowCount": row_count,
            "truncated": truncated,
        }

    async def _latest_report_for_graph_update(
        self,
        graph_update_id: UUID,
    ) -> BrandReportVersion | None:
        graph_update = await self.db.get(GraphUpdate, graph_update_id)
        if graph_update is None:
            return None
        result = await self.db.execute(
            select(BrandReportVersion)
            .where(
                BrandReportVersion.entity_id == graph_update.entity_id,
                BrandReportVersion.report_id == f"brand-space-{graph_update_id}",
            )
            .order_by(desc(BrandReportVersion.version), desc(BrandReportVersion.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _report_for_artifact(
        self,
        *,
        artifact: BoardArtifact,
        fallback: BrandReportVersion | None,
    ) -> BrandReportVersion | None:
        if artifact.artifact_type != "report":
            return fallback
        report_version_id = str(
            (artifact.extra_metadata or {}).get("report_version_id") or ""
        ).strip()
        if not report_version_id:
            logger.warning(
                "Report artifact %s is missing report_version_id metadata",
                artifact.id,
            )
            return None
        try:
            report_uuid = UUID(report_version_id)
        except ValueError:
            logger.warning(
                "Report artifact %s has invalid report_version_id metadata: %s",
                artifact.id,
                report_version_id,
            )
            return None
        report = await self.db.get(BrandReportVersion, report_uuid)
        if report is None or report.entity_id != artifact.entity_id:
            logger.warning(
                "Report artifact %s points to a missing or foreign report version: %s",
                artifact.id,
                report_version_id,
            )
            return None
        return report

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

    async def _guardrails_for_report(self, report_version_id: UUID) -> list[ReportGuardrailResult]:
        result = await self.db.execute(
            select(ReportGuardrailResult)
            .where(ReportGuardrailResult.report_version_id == report_version_id)
            .order_by(ReportGuardrailResult.created_at)
        )
        return list(result.scalars().all())

    async def _replace_report_guardrails(
        self,
        *,
        report: BrandReportVersion,
        graph_update_id: UUID,
        guardrails: list[dict[str, Any]],
    ) -> list[ReportGuardrailResult]:
        await self.db.execute(
            delete(ReportGuardrailResult).where(
                ReportGuardrailResult.report_version_id == report.id
            )
        )
        records: list[ReportGuardrailResult] = []
        for item in guardrails:
            record = ReportGuardrailResult(
                graph_update_id=graph_update_id,
                report_version_id=report.id,
                guardrail_key=item["guardrail_key"],
                severity=item["severity"],
                title=item["title"],
                message=item["message"],
                payload=item.get("payload"),
            )
            self.db.add(record)
            records.append(record)
        await self.db.flush()
        return records

    async def _register_report_artifact(
        self,
        *,
        graph_update: GraphUpdate,
        report: BrandReportVersion,
    ) -> None:
        if not graph_update.board_run_id:
            return
        result = await self.db.execute(
            select(BoardNodeRun)
            .where(
                BoardNodeRun.board_run_id == graph_update.board_run_id,
                BoardNodeRun.node_id == "graph-update",
            )
            .limit(1)
        )
        node_run = result.scalar_one_or_none()
        artifact_key = f"report-{report.id}"
        existing = await self.db.execute(
            select(BoardArtifact)
            .where(
                BoardArtifact.board_run_id == graph_update.board_run_id,
                BoardArtifact.artifact_key == artifact_key,
            )
            .limit(1)
        )
        if existing.scalar_one_or_none() is not None:
            return
        payload = report.payload or {}
        base = f"assets/{graph_update.entity_id}/{graph_update.board_run_id}"
        artifact = BoardArtifact(
            artifact_key=artifact_key,
            entity_id=graph_update.entity_id,
            board_run_id=graph_update.board_run_id,
            node_run_id=node_run.id if node_run else None,
            artifact_type="report",
            label=f"{report.title} v{report.version}",
            path=f"{base}/reports/{report.id}.md",
            mime_type="text/markdown",
            row_count=max(
                1,
                len(payload.get("claims") or []),
                len(payload.get("trace_chains") or []),
            ),
            extra_metadata={
                "node_id": "graph-update",
                "graph_update_id": str(graph_update.id),
                "report_version_id": str(report.id),
                "report_kind": report.report_kind,
                "publication_status": self._report_publication_status(report),
                "storage_provider": "local",
                "object_key": f"{base}/reports/{report.id}.md",
            },
        )
        await self._materialize_report_artifact_object(artifact=artifact, report=report)
        self.db.add(artifact)
        await self.db.flush()

    async def _materialize_report_artifact_object(
        self,
        *,
        artifact: BoardArtifact,
        report: BrandReportVersion,
    ) -> None:
        object_key, reason = self._artifact_object_key(artifact)
        if reason or object_key is None:
            raise ValueError(
                f"Cannot materialize report artifact {artifact.id}: "
                f"{reason or 'missing_object_key'}"
            )
        object_path = self._artifact_storage_path(object_key)
        await asyncio.to_thread(
            self._write_text_object,
            object_path,
            self._report_artifact_markdown(report),
        )

    @staticmethod
    def _write_text_object(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _report_artifact_markdown(report: BrandReportVersion) -> str:
        payload = report.payload or {}
        markdown = str(payload.get("report_markdown") or "").strip()
        if markdown:
            return markdown
        summary = str(report.summary or payload.get("summary") or "").strip()
        lines = [
            f"# {report.title}",
            "",
            summary or "该报告尚未生成可读正文。",
            "",
            "## 版本信息",
            "",
            f"- 报告版本：v{report.version}",
            f"- 发布状态：{BrandSpaceService._report_publication_status(report)}",
        ]
        graph_update_id = payload.get("graph_update_id")
        if graph_update_id:
            lines.append(f"- 图谱更新：{graph_update_id}")
        return "\n".join(lines).strip() + "\n"

    async def _lock_report_version_scope(self, graph_update_id: UUID) -> None:
        await self.db.execute(
            select(GraphUpdate.id)
            .where(GraphUpdate.id == graph_update_id)
            .with_for_update()
        )

    async def _next_report_version(self, *, entity_id: UUID, report_id: str) -> int:
        result = await self.db.execute(
            select(BrandReportVersion)
            .where(
                BrandReportVersion.entity_id == entity_id,
                BrandReportVersion.report_id == report_id,
            )
            .order_by(desc(BrandReportVersion.version))
            .limit(1)
            .with_for_update()
        )
        latest_report = result.scalar_one_or_none()
        return int(latest_report.version if latest_report else 0) + 1

    @staticmethod
    def _platform_key(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "unknown"
        lower = raw.lower()
        alias = PLATFORM_KEY_ALIASES.get(raw) or PLATFORM_KEY_ALIASES.get(lower)
        if alias:
            return alias
        if lower in PLATFORM_TEMPLATE_BY_KEY:
            return str(PLATFORM_TEMPLATE_BY_KEY[lower]["platformKey"])
        for known_key, template in PLATFORM_TEMPLATE_BY_KEY.items():
            if known_key in lower:
                return str(template["platformKey"])
        ascii_key = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
        return ascii_key or raw

    @classmethod
    def _platform_template_for_key(cls, key: str) -> dict[str, Any]:
        normalized = cls._platform_key(key)
        template = PLATFORM_TEMPLATE_BY_KEY.get(normalized)
        if template:
            return dict(template)
        safe_id = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-") or "custom"
        label = str(key or normalized).strip() or "未知平台"
        if "抓取" not in label:
            label = f"{label} 抓取"
        return {
            "id": f"fetch-{safe_id}",
            "platformKey": normalized,
            "label": label,
            "model": "API",
            "progress": 0,
            "answers": 0,
            "failures": 0,
        }

    @classmethod
    def _platform_keys_for_run(cls, board_run: BoardRun) -> list[str]:
        input_scope = board_run.input_scope or {}
        raw_platforms = (
            input_scope.get("platforms")
            or input_scope.get("platform_keys")
            or input_scope.get("target_platforms")
        )
        if isinstance(raw_platforms, str):
            platform_items: Iterable[Any] = [
                item for item in re.split(r"[,，;；\s]+", raw_platforms) if item
            ]
        elif isinstance(raw_platforms, dict):
            platform_items = [raw_platforms]
        elif isinstance(raw_platforms, Iterable):
            platform_items = raw_platforms
        else:
            platform_items = []

        keys: list[str] = []
        seen: set[str] = set()
        for item in platform_items:
            if isinstance(item, dict):
                raw_value = (
                    item.get("platformKey")
                    or item.get("platform")
                    or item.get("key")
                    or item.get("name")
                )
            else:
                raw_value = item
            key = cls._platform_key(raw_value)
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
        return keys

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
            platform_counts = real_counts.get("platforms") or {}
            if not isinstance(platform_counts, dict):
                platform_counts = {}
            total_answers = int(real_counts.get("answers") or 0)
            question_count = int(real_counts.get("questions") or 0)
            platform_keys = self._platform_keys_for_run(board_run)
            if not platform_keys:
                platform_keys = [str(key) for key in platform_counts.keys()]
            for raw_key in platform_counts.keys():
                key = self._platform_key(raw_key)
                if key not in platform_keys:
                    platform_keys.append(key)
            if not platform_keys:
                platform_keys = [str(platform["platformKey"]) for platform in PLATFORM_TEMPLATES]

            fallback_answers: dict[str, int] = {}
            if total_answers and not platform_counts and platform_keys:
                base_answers, remainder = divmod(total_answers, len(platform_keys))
                fallback_answers = {
                    key: base_answers + (1 if index < remainder else 0)
                    for index, key in enumerate(platform_keys)
                }

            platforms: list[dict[str, Any]] = []
            for key in platform_keys:
                template = self._platform_template_for_key(key)
                normalized_key = str(template["platformKey"])
                counts = platform_counts.get(normalized_key) or platform_counts.get(key) or {}
                answers = int(counts.get("answers") or fallback_answers.get(key, 0))
                failures = int(counts.get("failures") or 0)
                observed_total = int(counts.get("total") or answers + failures)
                platform_progress = progress
                if status == "completed":
                    platform_progress = 100
                elif question_count > 0 and observed_total > 0:
                    platform_progress = min(100, int((observed_total / question_count) * 100))
                platforms.append(
                    {
                        **template,
                        "status": status,
                        "progress": platform_progress,
                        "answers": answers,
                        "failures": failures,
                    }
                )
            return platforms
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
        metadata = artifact.extra_metadata or {}
        return {
            "id": artifact.artifact_key,
            "artifactId": str(artifact.id),
            "entityId": str(artifact.entity_id),
            "boardRunId": str(artifact.board_run_id),
            "nodeRunId": str(artifact.node_run_id) if artifact.node_run_id else None,
            "type": artifact.artifact_type,
            "label": artifact.label,
            "path": artifact.path,
            "mimeType": artifact.mime_type,
            "rowCount": artifact.row_count,
            "createdAt": artifact.created_at.isoformat(),
            "linkedNodeId": metadata.get("node_id"),
            "metadata": metadata,
        }

    async def _artifact_to_dict_for_run(
        self,
        artifact: BoardArtifact,
        board_run: BoardRun,
    ) -> dict[str, Any]:
        payload = self._artifact_to_dict(artifact)
        if artifact.artifact_type not in {"raw_answers", "parsed_answers"}:
            return payload

        scope = await self._answer_asset_scope(board_run)
        metadata = {
            **(payload.get("metadata") or {}),
            "answer_asset_scope": scope["mode"],
            "session_id": scope.get("session_id"),
            "brand_intelligence_run_id": scope.get("brand_intelligence_run_id"),
            "legacy_answer_mapping": scope["mode"] == "brand_recent_answers",
        }
        payload["metadata"] = metadata
        row_count_hint = self._answer_count_hint(board_run)
        if row_count_hint > 0 and int(payload.get("rowCount") or 0) <= 0:
            payload["rowCount"] = row_count_hint
        return payload

    def _asset_storage_root(self) -> Path:
        root = self.asset_storage_root
        if root is None:
            root = Path(settings.BRAND_SPACE_ASSET_STORAGE_ROOT)
        if not root.is_absolute():
            root = _BACKEND_DIR / root
        return root.resolve()

    @staticmethod
    def _artifact_object_key(artifact: BoardArtifact) -> tuple[str | None, str | None]:
        raw_path = str(artifact.path or "").strip()
        if not raw_path:
            return None, "missing_object_key"
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", raw_path):
            return None, "external_url_not_supported"
        if re.match(r"^[A-Za-z]:", raw_path) or raw_path.startswith(("/", "\\")):
            return None, "absolute_path_not_allowed"

        normalized = raw_path.replace("\\", "/").strip("/")
        parts = PurePosixPath(normalized).parts
        if not parts or parts[0] != "assets" or any(part in {"", ".", ".."} for part in parts):
            return None, "unsafe_or_unsupported_object_key"
        return PurePosixPath(*parts).as_posix(), None

    def _artifact_storage_path(self, object_key: str) -> Path:
        root = self._asset_storage_root()
        candidate = root.joinpath(*PurePosixPath(object_key).parts).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("Artifact object key escapes the configured storage root")
        return candidate

    @staticmethod
    def _artifact_download_filename(
        *,
        artifact: BoardArtifact,
        object_key: str | None,
    ) -> str:
        candidate = PurePosixPath(object_key or "").name or artifact.artifact_key or str(artifact.id)
        return re.sub(r'[\\/:*?"<>|]+', "-", candidate)

    def _artifact_access_descriptor(
        self,
        artifact: BoardArtifact,
        *,
        include_local_path: bool = False,
    ) -> dict[str, Any]:
        object_key, reason = self._artifact_object_key(artifact)
        descriptor: dict[str, Any] = {
            "canPreview": True,
            "mode": "object_storage",
            "provider": "local",
            "objectKey": object_key,
            "available": False,
            "downloadUrl": None,
            "filename": self._artifact_download_filename(
                artifact=artifact,
                object_key=object_key,
            ),
            "sizeBytes": None,
            "reason": reason,
        }
        if reason or object_key is None:
            return descriptor

        try:
            object_path = self._artifact_storage_path(object_key)
        except ValueError:
            descriptor["reason"] = "object_key_escapes_storage_root"
            return descriptor

        if object_path.is_file():
            descriptor.update(
                {
                    "available": True,
                    "downloadUrl": f"/api/v1/brand-space/artifacts/{artifact.id}/download",
                    "sizeBytes": object_path.stat().st_size,
                    "reason": None,
                }
            )
            if include_local_path:
                descriptor["_local_path"] = object_path
            return descriptor

        descriptor["reason"] = (
            "object_is_directory" if object_path.exists() else "object_not_materialized"
        )
        return descriptor

    @staticmethod
    def _public_artifact_access_descriptor(descriptor: dict[str, Any]) -> dict[str, Any]:
        public_descriptor = dict(descriptor)
        public_descriptor.pop("_local_path", None)
        return public_descriptor

    @staticmethod
    def _event_sequence_value(event: BoardRuntimeEvent) -> int | None:
        if event.sequence is None:
            return None
        return int(event.sequence)

    def _event_to_dict(self, event: BoardRuntimeEvent) -> dict[str, Any]:
        return {
            "id": str(event.id),
            "sequence": self._event_sequence_value(event),
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
        payload = report.payload or {}
        return {
            "id": str(report.id),
            "entity_id": str(report.entity_id),
            "report_id": report.report_id,
            "version": report.version,
            "report_kind": report.report_kind,
            "artifact_id": report.artifact_id,
            "title": report.title,
            "summary": report.summary,
            "payload": payload,
            "source_type": BrandSpaceService._report_source_type(report),
            "graph_update_id": payload.get("graph_update_id"),
            "publication_status": BrandSpaceService._report_publication_status(report),
            "created_at": report.created_at.isoformat(),
            "updated_at": report.updated_at.isoformat(),
        }

    @staticmethod
    def _report_summary_to_dict(report: BrandReportVersion) -> dict[str, Any]:
        payload = report.payload or {}
        return {
            "id": str(report.id),
            "report_id": report.report_id,
            "version": report.version,
            "report_kind": report.report_kind,
            "title": report.title,
            "summary": report.summary,
            "source_type": BrandSpaceService._report_source_type(report),
            "graph_update_id": payload.get("graph_update_id"),
            "publication_status": BrandSpaceService._report_publication_status(report),
            "created_at": report.created_at.isoformat(),
            "updated_at": report.updated_at.isoformat(),
        }

    @staticmethod
    def _report_source_type(report: BrandReportVersion) -> str:
        payload = report.payload or {}
        report_id = str(report.report_id or "")
        artifact_id = str(report.artifact_id or "")
        if (
            payload.get("graph_update_id")
            or report_id.startswith("brand-space-")
            or artifact_id.startswith("graph-update-report:")
        ):
            return "graph_update"
        return "pre_graph_update"

    @staticmethod
    def _report_matches_graph_update(
        report: BrandReportVersion,
        graph_update_id: UUID,
    ) -> bool:
        payload = report.payload or {}
        graph_update_key = str(graph_update_id)
        return (
            str(payload.get("graph_update_id") or "") == graph_update_key
            or str(report.report_id or "") == f"brand-space-{graph_update_key}"
            or str(report.artifact_id or "").startswith(
                f"graph-update-report:{graph_update_key}:"
            )
        )

    @staticmethod
    def _report_publication_status(report: BrandReportVersion) -> str:
        if BrandSpaceService._report_source_type(report) == "pre_graph_update":
            return "pre_graph_update"
        column_status = str(getattr(report, "publication_status", "") or "").strip()
        if column_status and column_status in GRAPH_REPORT_PUBLICATION_STATUSES:
            return column_status
        payload = report.payload or {}
        payload_status = str(payload.get("publication_status") or "draft")
        return (
            payload_status
            if payload_status in GRAPH_REPORT_PUBLICATION_STATUSES
            else "draft"
        )

    async def _build_report_payload(
        self,
        *,
        entity: Entity,
        graph_update: GraphUpdate,
        patches: list[GraphPatch],
    ) -> dict[str, Any]:
        brand_name = entity.name
        active_patches = [patch for patch in patches if patch.status != "rejected"]
        claims = [self._report_claim_from_patch(patch) for patch in active_patches]
        trace_chains = [self._trace_chain_from_patch(patch) for patch in active_patches]
        competitor_claims = [
            claim
            for claim, patch in zip(claims, active_patches, strict=False)
            if patch.relation_type == "competes_with"
        ]
        recommended_actions = self._report_recommended_actions(active_patches)
        board_run, answers, question_lookup, lexicon_entries = await self._report_corpus_inputs(
            entity=entity,
            graph_update=graph_update,
        )
        storyline_report = self._build_storyline_report(
            brand_name=brand_name,
            graph_update=graph_update,
            patches=active_patches,
            answers=answers,
            question_lookup=question_lookup,
            lexicon_entries=lexicon_entries,
        )
        summary = (
            storyline_report.get("summary")
            or f"{brand_name}本次图谱更新包含 {len(active_patches)} 项有效变化。"
        )
        return {
            "brand_name": brand_name,
            "graph_update_id": str(graph_update.id),
            "board_run_id": str(board_run.id) if board_run else None,
            "source_type": "graph_update",
            "summary": summary,
            "report_title": storyline_report.get("title") or f"{brand_name}品牌 AI 认知图景",
            "storyline_report": storyline_report,
            "sample_scope": storyline_report.get("sample_scope", {}),
            "structural_judgments": storyline_report.get("structural_judgments", []),
            "value_pillars": storyline_report.get("value_pillars", []),
            "blind_spot": storyline_report.get("blind_spot", {}),
            "platform_profiles": storyline_report.get("platform_profiles", []),
            "evidence_quotes": storyline_report.get("evidence_quotes", []),
            "action_plan": storyline_report.get("action_plan", []),
            "report_markdown": storyline_report.get("markdown", ""),
            "strategic_terms": [
                {
                    "word": claim["label"],
                    "state": claim["state"],
                    "reason": claim["statement"],
                    "patch_id": claim["patch_id"],
                    "trace_chain_id": claim["trace_chain_id"],
                }
                for claim in claims[:6]
            ],
            "claims": claims,
            "trace_chains": trace_chains,
            "platform_differences": self._report_platform_differences(active_patches),
            "competitor_claims": competitor_claims,
            "recommended_actions": recommended_actions,
        }

    async def _report_corpus_inputs(
        self,
        *,
        entity: Entity,
        graph_update: GraphUpdate,
    ) -> tuple[BoardRun | None, list[BrandPlatformAnswer], dict[str, str], list[EntityLexiconEntry]]:
        board_run = await self.db.get(BoardRun, graph_update.board_run_id) if graph_update.board_run_id else None
        builder = GraphPatchBuilderService(self.db)
        lexicon_entries = (
            builder.lexicon_entries(board_run=board_run, entity=entity)
            if board_run is not None
            else [EntityLexiconEntry(entity_id=str(entity.id), label=entity.name, entity_type="CenterBrand")]
        )
        answers: list[BrandPlatformAnswer] = []
        question_lookup: dict[str, str] = {}
        if board_run is None or board_run.brand_intelligence_run_id is None:
            return board_run, answers, question_lookup, lexicon_entries

        intelligence_run = await self.db.get(BrandIntelligenceRun, board_run.brand_intelligence_run_id)
        if intelligence_run is None:
            return board_run, answers, question_lookup, lexicon_entries

        answers = await builder.answers_for_run(
            entity_id=entity.id,
            intelligence_run=intelligence_run,
            limit=1200,
        )
        question_lookup = await builder.question_lookup(
            entity_id=entity.id,
            intelligence_run=intelligence_run,
            answers=answers,
        )
        return board_run, answers, question_lookup, lexicon_entries

    def _build_storyline_report(
        self,
        *,
        brand_name: str,
        graph_update: GraphUpdate,
        patches: list[GraphPatch],
        answers: list[BrandPlatformAnswer],
        question_lookup: dict[str, str],
        lexicon_entries: list[EntityLexiconEntry],
    ) -> dict[str, Any]:
        records = self._report_answer_records(
            brand_name=brand_name,
            answers=answers,
            question_lookup=question_lookup,
            patches=patches,
            lexicon_entries=lexicon_entries,
        )
        sample_scope = self._report_sample_scope(
            brand_name=brand_name,
            records=records,
            lexicon_entries=lexicon_entries,
        )
        entity_stats = self._report_entity_stats(records=records, lexicon_entries=lexicon_entries, patches=patches)
        structural_judgments = self._report_structural_judgments(
            brand_name=brand_name,
            records=records,
            sample_scope=sample_scope,
            entity_stats=entity_stats,
            patches=patches,
        )
        value_pillars = self._report_value_pillars(
            brand_name=brand_name,
            records=records,
            sample_scope=sample_scope,
        )
        blind_spot = self._report_blind_spot(brand_name=brand_name, sample_scope=sample_scope, records=records)
        platform_profiles = self._report_platform_profiles(
            brand_name=brand_name,
            records=records,
            sample_scope=sample_scope,
        )
        action_plan = self._report_action_plan(
            brand_name=brand_name,
            structural_judgments=structural_judgments,
            value_pillars=value_pillars,
            blind_spot=blind_spot,
            platform_profiles=platform_profiles,
        )
        evidence_quotes = self._report_evidence_quotes(
            records=records,
            judgments=structural_judgments,
            pillars=value_pillars,
        )
        summary = self._report_storyline_summary(
            brand_name=brand_name,
            sample_scope=sample_scope,
            structural_judgments=structural_judgments,
            blind_spot=blind_spot,
        )
        title = f"{brand_name}品牌 AI 认知图景"
        report = {
            "title": title,
            "subtitle": f"{sample_scope['round_label']} / {sample_scope['question_count']} 个问题 / {sample_scope['answer_count']} 条有效回答",
            "summary": summary,
            "sample_scope": sample_scope,
            "structural_judgments": structural_judgments,
            "value_pillars": value_pillars,
            "blind_spot": blind_spot,
            "platform_profiles": platform_profiles,
            "entity_ranking": entity_stats[:12],
            "evidence_quotes": evidence_quotes,
            "action_plan": action_plan,
            "graph_update_id": str(graph_update.id),
        }
        report["markdown"] = self._storyline_markdown(report)
        return report

    def _report_answer_records(
        self,
        *,
        brand_name: str,
        answers: list[BrandPlatformAnswer],
        question_lookup: dict[str, str],
        patches: list[GraphPatch],
        lexicon_entries: list[EntityLexiconEntry],
    ) -> list[dict[str, Any]]:
        brand_terms = self._brand_terms(brand_name=brand_name, lexicon_entries=lexicon_entries)
        records: list[dict[str, Any]] = []
        if answers:
            for answer in answers:
                question = GraphPatchBuilderService.question_text(answer, question_lookup)
                answer_text = answer.answer_text or ""
                question_has_brand = self._mentions_any(question, brand_terms)
                answer_has_brand = bool(answer.brand_mentioned) if answer.brand_mentioned is not None else self._mentions_any(answer_text, brand_terms)
                risk_context_state = self._classify_brand_risk_context(
                    question=question,
                    answer_text=answer_text,
                    brand_terms=brand_terms,
                    question_has_brand=question_has_brand,
                    answer_has_brand=answer_has_brand,
                )
                records.append(
                    {
                        "answer_id": str(answer.id),
                        "question_id": answer.question_id or str(answer.question_object_id or ""),
                        "question": question,
                        "platform": answer.platform or "未记录平台",
                        "text": answer_text,
                        "question_has_brand": question_has_brand,
                        "answer_has_brand": answer_has_brand,
                        "risk_context_state": risk_context_state,
                        "source": "answer",
                    }
                )
            return records

        seen: set[str] = set()
        for patch in patches:
            for evidence in patch.evidence_refs or []:
                answer_id = str(evidence.get("answer_id") or evidence.get("id") or "")
                dedupe_key = answer_id or f"{patch.id}:{len(seen)}"
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                question = str(evidence.get("question") or "未记录问题")
                excerpt = str(evidence.get("excerpt") or "")
                question_has_brand = self._mentions_any(question, brand_terms)
                answer_has_brand = self._mentions_any(excerpt, brand_terms)
                risk_context_state = self._classify_brand_risk_context(
                    question=question,
                    answer_text=excerpt,
                    brand_terms=brand_terms,
                    question_has_brand=question_has_brand,
                    answer_has_brand=answer_has_brand,
                )
                records.append(
                    {
                        "answer_id": answer_id,
                        "question_id": str(evidence.get("question_id") or ""),
                        "question": question,
                        "platform": str(evidence.get("platform") or "未记录平台"),
                        "text": excerpt,
                        "question_has_brand": question_has_brand,
                        "answer_has_brand": answer_has_brand,
                        "risk_context_state": risk_context_state,
                        "source": "patch_evidence",
                    }
                )
        return records

    def _report_sample_scope(
        self,
        *,
        brand_name: str,
        records: list[dict[str, Any]],
        lexicon_entries: list[EntityLexiconEntry],
    ) -> dict[str, Any]:
        brand_terms = self._brand_terms(brand_name=brand_name, lexicon_entries=lexicon_entries)
        platform_counts = Counter(str(record["platform"]) for record in records)
        question_ids = {
            str(record.get("question_id") or record.get("question") or "")
            for record in records
            if str(record.get("question_id") or record.get("question") or "").strip()
        }
        brand_question_records = [record for record in records if record["question_has_brand"]]
        open_question_records = [record for record in records if not record["question_has_brand"]]
        brand_mentions = [record for record in records if record["answer_has_brand"]]
        open_mentions = [record for record in open_question_records if record["answer_has_brand"]]
        active_rate = len(open_mentions) / len(open_question_records) if open_question_records else 0.0
        return {
            "round_label": "Graph Update",
            "answer_count": len(records),
            "question_count": len(question_ids),
            "platform_count": len(platform_counts),
            "platform_distribution": [
                {"platform": platform, "count": count}
                for platform, count in platform_counts.most_common()
            ],
            "brand_mention_count": len(brand_mentions),
            "brand_mention_rate": round(len(brand_mentions) / len(records), 4) if records else 0.0,
            "brand_named_answer_count": len(brand_question_records),
            "open_answer_count": len(open_question_records),
            "open_brand_mention_count": len(open_mentions),
            "active_mention_rate": round(active_rate, 4),
            "brand_terms": list(brand_terms),
        }

    def _report_entity_stats(
        self,
        *,
        records: list[dict[str, Any]],
        lexicon_entries: list[EntityLexiconEntry],
        patches: list[GraphPatch],
    ) -> list[dict[str, Any]]:
        entries_by_key: dict[str, EntityLexiconEntry] = {
            f"{entry.entity_id}:{entry.label}": entry for entry in lexicon_entries
        }
        for patch in patches:
            label = self._patch_label(patch)
            key = f"{patch.affected_object_id or label}:{label}"
            entries_by_key.setdefault(
                key,
                EntityLexiconEntry(
                    entity_id=str(patch.affected_object_id or label),
                    label=label,
                    entity_type=str(patch.affected_object_type or patch.relation_type or "Concept"),
                ),
            )
        rows: list[dict[str, Any]] = []
        for entry in entries_by_key.values():
            matched = [
                record for record in records if self._record_mentions_entry(record, entry)
            ]
            if not matched:
                continue
            risk_count = sum(1 for record in matched if self._record_has_negative_risk(record))
            question_count = len({str(record.get("question_id") or record.get("question")) for record in matched})
            platforms = sorted({str(record.get("platform") or "") for record in matched if record.get("platform")})
            rows.append(
                {
                    "entity_id": entry.entity_id,
                    "label": entry.label,
                    "type": entry.entity_type,
                    "mention_count": len(matched),
                    "question_count": question_count,
                    "platform_count": len(platforms),
                    "risk_context_count": risk_count,
                    "risk_context_rate": round(risk_count / len(matched), 4) if matched else 0.0,
                    "platforms": platforms,
                }
            )
        return sorted(
            rows,
            key=lambda item: (
                -int(item["mention_count"]),
                -int(item["platform_count"]),
                str(item["label"]),
            ),
        )

    def _report_structural_judgments(
        self,
        *,
        brand_name: str,
        records: list[dict[str, Any]],
        sample_scope: dict[str, Any],
        entity_stats: list[dict[str, Any]],
        patches: list[GraphPatch],
    ) -> list[dict[str, Any]]:
        risk_records = [record for record in records if self._record_has_negative_risk(record)]
        risk_rate = len(risk_records) / len(records) if records else 0.0
        active_rate = float(sample_scope.get("active_mention_rate") or 0)
        top_entities = [str(item["label"]) for item in entity_stats[:3]]
        risk_patches = [patch for patch in patches if patch.relation_type == "risk_related"]
        competitor_patches = [patch for patch in patches if patch.relation_type == "competes_with"]
        archive_body = (
            f"回答最常带出的标签是{'、'.join(top_entities)}。"
            "这些标签说明 AI 有材料可用，但品牌战略还没有被组织成一个稳定故事。"
            if top_entities
            else "本轮回答还没有形成稳定标签聚类。报告应先把可见事实和缺口分开，避免把零散线索包装成已经稳定的品牌故事。"
        )
        judgments = [
            {
                "id": "archive-label-mismatch",
                "title": f"{brand_name}已经有 AI 档案，核心标签仍需重排",
                "severity": "high",
                "gap_type": "archive_label_mismatch",
                "body": archive_body,
                "data_points": [
                    {"label": "有效回答", "value": sample_scope.get("answer_count", 0)},
                    {"label": "提及品牌", "value": sample_scope.get("brand_mention_count", 0)},
                    {"label": "风险语境", "value": len(risk_records)},
                ],
                "keywords": top_entities,
            },
            {
                "id": "asked-not-recommended",
                "title": "开放问题里的主动提及仍是关键盲区",
                "severity": "high" if active_rate < 0.1 else "medium",
                "gap_type": "active_mention_gap",
                "body": (
                    f"不含品牌名的问题产生 {sample_scope.get('open_answer_count', 0)} 条回答，"
                    f"其中 {sample_scope.get('open_brand_mention_count', 0)} 条主动提到{brand_name}。"
                    "这决定品牌是否进入 AI 的默认推荐列表。"
                ),
                "data_points": [
                    {"label": "主动提及率", "value": f"{round(active_rate * 100, 1)}%"},
                    {"label": "开放回答", "value": sample_scope.get("open_answer_count", 0)},
                    {"label": "主动提及", "value": sample_scope.get("open_brand_mention_count", 0)},
                ],
                "keywords": [brand_name],
            },
        ]
        if risk_patches or risk_rate > 0.25:
            judgments.append(
                {
                    "id": "risk-context-envelope",
                    "title": "风险语境会改写正向联想的解释路径",
                    "severity": "high",
                    "gap_type": "risk_context",
                    "body": (
                        f"{len(risk_records)} 条回答出现风险或质疑语境。"
                        "报告需要判断这些语境是在澄清品牌，还是把品牌重新带回旧认知。"
                    ),
                    "data_points": [
                        {"label": "风险语境率", "value": f"{round(risk_rate * 100, 1)}%"},
                        {"label": "风险补丁", "value": len(risk_patches)},
                    ],
                    "keywords": [self._patch_label(patch) for patch in risk_patches[:4]],
                }
            )
        if competitor_patches:
            judgments.append(
                {
                    "id": "competitor-reference",
                    "title": "竞品出现时要回到替代场景判断",
                    "severity": "medium",
                    "gap_type": "competitor_reference",
                    "body": (
                        "竞品名称本身不等于风险。只有在推荐、替代、比较和决策语境中出现，"
                        "才说明品牌正在被挤出某个用户场景。"
                    ),
                    "data_points": [
                        {"label": "竞品关系", "value": len(competitor_patches)},
                    ],
                    "keywords": [self._patch_label(patch) for patch in competitor_patches[:4]],
                }
            )
        return judgments[:5]

    def _report_value_pillars(
        self,
        *,
        brand_name: str,
        records: list[dict[str, Any]],
        sample_scope: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self._is_amway_brand(brand_name):
            pillar_configs = [
                {
                    "id": "healthy",
                    "name": "有健康",
                    "headline": "站稳了，但还停在产品层",
                    "keywords": ("健康", "营养", "纽崔莱", "抗衰", "体重", "蛋白", "植物"),
                    "target": "从产品组合升级到长寿时代的健康管理方案。",
                },
                {
                    "id": "companionship",
                    "name": "有陪伴",
                    "headline": "有可见度，可信度仍被旧认知牵制",
                    "keywords": ("社群", "陪伴", "关系", "朋友", "美好生活", "圈子"),
                    "target": "让社群从内部热闹变成外部可感知的生活场景。",
                },
                {
                    "id": "security",
                    "name": "有保障",
                    "headline": "先处理信任，再承接保障",
                    "keywords": ("保障", "直销", "事业", "收入", "合规", "监管", "传销", "认证"),
                    "target": "用清晰规则和认证材料替代模糊的事业机会表述。",
                },
                {
                    "id": "value",
                    "name": "有价值",
                    "headline": "仍在萌芽，需要借相邻资产进入",
                    "keywords": ("价值", "公益", "被需要", "人生", "再出发", "成长", "贡献"),
                    "target": "从社会价值和人生再出发故事切入，而非直接讲宏大意义。",
                },
            ]
        else:
            pillar_configs = [
                {
                    "id": "stable-assets",
                    "name": "稳定资产",
                    "headline": "哪些资产已经被 AI 接住",
                    "keywords": tuple(),
                    "target": "继续巩固已形成稳定联想的资产。",
                },
                {
                    "id": "opportunity",
                    "name": "机会叙事",
                    "headline": "哪些机会有信号但还不稳定",
                    "keywords": tuple(),
                    "target": "把弱信号变成可引用的稳定内容。",
                },
                {
                    "id": "risk",
                    "name": "风险防守",
                    "headline": "哪些语境正在牵制品牌解释",
                    "keywords": tuple(RISK_CONTEXT_TERMS),
                    "target": "先补澄清材料，再观察风险语境是否下降。",
                },
            ]
        total = max(1, int(sample_scope.get("brand_mention_count") or sample_scope.get("answer_count") or 1))
        pillars: list[dict[str, Any]] = []
        for config in pillar_configs:
            keywords = tuple(config["keywords"])
            if keywords:
                matched = [record for record in records if self._mentions_any(str(record.get("text") or ""), keywords)]
            elif config["id"] == "stable-assets":
                matched = [record for record in records if not self._record_has_negative_risk(record)]
            elif config["id"] == "opportunity":
                matched = [record for record in records if record.get("answer_has_brand")]
            else:
                matched = records
            risk_count = sum(1 for record in matched if self._record_has_negative_risk(record))
            visibility = len(matched) / total if total else 0.0
            credibility = (len(matched) - risk_count) / len(matched) if matched else 0.0
            gap_type = self._gap_type_for_pillar(visibility=visibility, credibility=credibility, risk_count=risk_count)
            pillars.append(
                {
                    "id": config["id"],
                    "name": config["name"],
                    "headline": config["headline"],
                    "target": config["target"],
                    "mention_count": len(matched),
                    "risk_context_count": risk_count,
                    "visibility": round(visibility, 4),
                    "credibility": round(credibility, 4),
                    "gap_type": gap_type["key"],
                    "gap_label": gap_type["label"],
                    "reading": self._pillar_reading(
                        name=str(config["name"]),
                        headline=str(config["headline"]),
                        mention_count=len(matched),
                        risk_count=risk_count,
                        visibility=visibility,
                        credibility=credibility,
                    ),
                    "quotes": self._select_quotes(records=matched, keywords=keywords, limit=3),
                }
            )
        return pillars

    def _report_blind_spot(
        self,
        *,
        brand_name: str,
        sample_scope: dict[str, Any],
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        active_rate = float(sample_scope.get("active_mention_rate") or 0)
        open_records = [record for record in records if not record.get("question_has_brand")]
        missed_examples = [
            {
                "question": str(record.get("question") or ""),
                "platform": str(record.get("platform") or ""),
                "excerpt": GraphPatchBuilderService.clip(
                    str(record.get("text") or ""), 180
                ),
            }
            for record in open_records
            if not record.get("answer_has_brand")
        ][:3]
        if active_rate < 0.05:
            diagnosis = f"{brand_name}仍在 AI 默认推荐列表之外。"
        elif active_rate < 0.1:
            diagnosis = f"{brand_name}只有少量场景会被 AI 主动带出。"
        else:
            diagnosis = f"{brand_name}已经在部分开放场景中形成主动提及。"
        return {
            "diagnosis": diagnosis,
            "active_mention_rate": active_rate,
            "open_answer_count": sample_scope.get("open_answer_count", 0),
            "open_brand_mention_count": sample_scope.get("open_brand_mention_count", 0),
            "brand_named_answer_count": sample_scope.get("brand_named_answer_count", 0),
            "examples": missed_examples,
        }

    def _report_platform_profiles(
        self,
        *,
        brand_name: str,
        records: list[dict[str, Any]],
        sample_scope: dict[str, Any],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for platform, total in Counter(str(record["platform"]) for record in records).most_common():
            platform_records = [record for record in records if record["platform"] == platform]
            risk_count = sum(1 for record in platform_records if self._record_has_negative_risk(record))
            active_mentions = sum(1 for record in platform_records if not record["question_has_brand"] and record["answer_has_brand"])
            transformation_count = sum(
                1
                for record in platform_records
                if self._mentions_any(str(record.get("text") or ""), ("转型", "升级", "方案", "社群", "科技", "大健康"))
            )
            quote = self._select_quotes(records=platform_records, keywords=(brand_name,), limit=1)
            rows.append(
                {
                    "platform": platform,
                    "answer_count": total,
                    "risk_context_count": risk_count,
                    "risk_context_rate": round(risk_count / total, 4) if total else 0.0,
                    "active_mentions": active_mentions,
                    "transformation_mentions": transformation_count,
                    "profile": self._platform_profile_label(
                        risk_count=risk_count,
                        total=total,
                        active_mentions=active_mentions,
                        transformation_count=transformation_count,
                    ),
                    "quote": quote[0] if quote else None,
                }
            )
        return rows

    def _report_action_plan(
        self,
        *,
        brand_name: str,
        structural_judgments: list[dict[str, Any]],
        value_pillars: list[dict[str, Any]],
        blind_spot: dict[str, Any],
        platform_profiles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        active_rate = float(blind_spot.get("active_mention_rate") or 0)
        risk_pillar = next((pillar for pillar in value_pillars if pillar["risk_context_count"] > 0), None)
        actions = [
            {
                "title": "把已被 AI 接住的资产升级成方案叙事",
                "why": "稳定资产已经有认知基础，下一轮要观察 AI 是否能从单点资产讲到完整解决路径。",
                "do": f"围绕{brand_name}已被提及的核心资产发布方案级内容，补齐路径、适用人群和证据材料。",
                "validation": "下一轮看方案类表达的提及率是否上升，且是否进入稳定轨。",
            }
        ]
        if active_rate < 0.1:
            actions.append(
                {
                    "title": "让品牌进入开放问题的默认推荐列表",
                    "why": "主动提及率低说明 AI 只有被点名时才回答品牌。",
                    "do": "在官网、公众号、问答社区发布品牌与通用场景的可引用内容。",
                    "validation": "下一轮看不含品牌名问题中的主动提及率是否超过 10%。",
                }
            )
        if risk_pillar is not None:
            actions.append(
                {
                    "title": "先拆解风险语境，再铺新叙事",
                    "why": f"{risk_pillar['name']}相关回答里仍出现质疑语境，正向表达会被旧认知拉回去。",
                    "do": "补充合规、标准、认证、边界说明和真实场景案例，让 AI 有替代表达可引用。",
                    "validation": "下一轮看风险语境占比下降，正向替代表达是否上升。",
                }
            )
        if len(actions) < 3 and platform_profiles:
            top_platform = platform_profiles[0]["platform"]
            actions.append(
                {
                    "title": f"优先经营 {top_platform} 上已经出现的解释路径",
                    "why": f"{top_platform} 在本轮样本里贡献最多回答，适合作为第一轮复测入口。",
                    "do": f"针对 {top_platform} 的代表问题补充问答素材，确认它是否继续使用同一套品牌解释。",
                    "validation": f"下一轮比较 {top_platform} 的核心标签是否更接近品牌战略表达。",
                }
            )
        return actions[:3]

    def _report_evidence_quotes(
        self,
        *,
        records: list[dict[str, Any]],
        judgments: list[dict[str, Any]],
        pillars: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*judgments, *pillars]:
            keywords = tuple(str(keyword) for keyword in item.get("keywords", []) if keyword)
            for quote in self._select_quotes(records=records, keywords=keywords, limit=2):
                key = f"{quote.get('platform')}:{quote.get('question')}:{quote.get('excerpt')}"
                if key in seen:
                    continue
                seen.add(key)
                selected.append(quote)
                if len(selected) >= 8:
                    return selected
        if not selected:
            selected = self._select_quotes(records=records, keywords=tuple(), limit=6)
        return selected

    @staticmethod
    def _report_storyline_summary(
        *,
        brand_name: str,
        sample_scope: dict[str, Any],
        structural_judgments: list[dict[str, Any]],
        blind_spot: dict[str, Any],
    ) -> str:
        first = structural_judgments[0]["title"] if structural_judgments else f"{brand_name}已有可解读信号"
        active_rate = float(blind_spot.get("active_mention_rate") or 0)
        return (
            f"{first}。本轮覆盖 {sample_scope.get('answer_count', 0)} 条有效回答，"
            f"开放问题主动提及率为 {round(active_rate * 100, 1)}%。"
        )

    def _storyline_markdown(self, report: dict[str, Any]) -> str:
        lines = [
            f"# {report['title']}",
            "",
            str(report.get("subtitle") or ""),
            "",
            "## 核心判断",
            "",
            str(report.get("summary") or ""),
            "",
        ]
        for judgment in report.get("structural_judgments", [])[:4]:
            lines.extend([
                f"### {judgment.get('title')}",
                "",
                str(judgment.get("body") or ""),
                "",
            ])
        lines.extend(["## 价值支柱状态", ""])
        for pillar in report.get("value_pillars", []):
            lines.extend([
                f"### {pillar.get('name')}｜{pillar.get('headline')}",
                "",
                str(pillar.get("reading") or ""),
                "",
            ])
            for quote in pillar.get("quotes", [])[:2]:
                lines.extend([
                    f"> {quote.get('platform')}：{quote.get('excerpt')}",
                    "",
                ])
        blind_spot = report.get("blind_spot") or {}
        lines.extend([
            "## AI 盲区",
            "",
            str(blind_spot.get("diagnosis") or ""),
            "",
        ])
        examples = blind_spot.get("examples") or []
        if examples:
            lines.extend(["### 未提及示例", ""])
            for example in examples[:4]:
                lines.extend([
                    f"- {example.get('platform', '未记录平台')}｜{example.get('question', '未记录问题')}",
                    f"  - {example.get('excerpt', '')}",
                ])
            lines.append("")
        lines.extend(["## 本轮行动", ""])
        for index, action in enumerate(report.get("action_plan", []), start=1):
            lines.extend([
                f"{index}. **{action.get('title')}**",
                f"   - 做法：{action.get('do')}",
                f"   - 验证：{action.get('validation')}",
            ])
        return "\n".join(lines).strip()

    @staticmethod
    def _is_amway_brand(brand_name: str) -> bool:
        normalized = str(brand_name or "").lower()
        return "安利" in normalized or "amway" in normalized

    @staticmethod
    def _brand_terms(
        *,
        brand_name: str,
        lexicon_entries: list[EntityLexiconEntry],
    ) -> tuple[str, ...]:
        terms: list[str] = [brand_name]
        for entry in lexicon_entries:
            if entry.normalized_type == "centerbrand":
                terms.extend(entry.terms)
        seen: set[str] = set()
        unique: list[str] = []
        for term in terms:
            normalized = str(term or "").strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(normalized)
        return tuple(unique)

    @staticmethod
    def _mentions_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
        return any(GraphPatchBuilderService.contains_term(text or "", term) for term in terms)

    def _record_mentions_entry(
        self,
        record: dict[str, Any],
        entry: EntityLexiconEntry,
    ) -> bool:
        text = f"{record.get('question') or ''}\n{record.get('text') or ''}"
        return self._mentions_any(text, entry.terms)

    def _classify_brand_risk_context(
        self,
        *,
        question: str,
        answer_text: str,
        brand_terms: tuple[str, ...],
        question_has_brand: bool,
        answer_has_brand: bool,
    ) -> str:
        brand_anchored = question_has_brand or answer_has_brand
        if not brand_anchored and brand_terms:
            combined = f"{question}\n{answer_text}"
            brand_anchored = self._mentions_any(combined, brand_terms)
        if not brand_anchored:
            return "none"

        question_has_risk = self._has_risk_context(question)
        answer_has_risk = self._has_risk_context(answer_text)
        if not question_has_risk and not answer_has_risk:
            return "none"

        has_clarification = self._mentions_any(answer_text, RISK_CLARIFICATION_TERMS)
        has_negative_association = self._mentions_any(
            answer_text,
            RISK_NEGATIVE_CONTEXT_TERMS,
        )
        if has_clarification and not has_negative_association:
            return "clarified"
        if answer_has_risk and has_negative_association:
            return "negative"
        if answer_has_risk and not has_clarification:
            return "negative"
        return "inquiry"

    @staticmethod
    def _record_has_negative_risk(record: dict[str, Any]) -> bool:
        return record.get("risk_context_state") == "negative"

    def _has_risk_context(self, text: str) -> bool:
        return self._mentions_any(text or "", RISK_CONTEXT_TERMS)

    @staticmethod
    def _gap_type_for_pillar(
        *,
        visibility: float,
        credibility: float,
        risk_count: int,
    ) -> dict[str, str]:
        if visibility < 0.15:
            return {"key": "absent", "label": "叙事缺位"}
        if risk_count and credibility < 0.45:
            return {"key": "inverted", "label": "叙事被反转"}
        if risk_count and credibility < 0.7:
            return {"key": "hijacked", "label": "叙事被牵制"}
        if visibility >= 0.45:
            return {"key": "level_gap", "label": "层级待升级"}
        return {"key": "weak_signal", "label": "弱信号"}

    @staticmethod
    def _pillar_reading(
        *,
        name: str,
        headline: str,
        mention_count: int,
        risk_count: int,
        visibility: float,
        credibility: float,
    ) -> str:
        if mention_count == 0:
            return f"{name}在本轮回答中几乎没有形成可见联想，需要先补可被 AI 引用的内容入口。"
        risk_sentence = (
            f"其中 {risk_count} 条伴随风险或质疑语境，说明这个方向已经被旧认知牵制。"
            if risk_count
            else "回答没有明显风险伴随，可以作为下一轮稳定资产继续放大。"
        )
        return (
            f"{headline}。本轮有 {mention_count} 条回答触达这个方向，"
            f"可见度 {round(visibility * 100, 1)}%，可信度 {round(credibility * 100, 1)}%。"
            f"{risk_sentence}"
        )

    def _select_quotes(
        self,
        *,
        records: list[dict[str, Any]],
        keywords: tuple[str, ...],
        limit: int,
    ) -> list[dict[str, Any]]:
        candidates = [
            record
            for record in records
            if str(record.get("text") or "").strip()
            and (not keywords or self._mentions_any(str(record.get("text") or ""), keywords))
        ]
        if not candidates and keywords:
            candidates = [record for record in records if str(record.get("text") or "").strip()]

        def quote_from_record(record: dict[str, Any]) -> dict[str, Any]:
            return {
                "platform": str(record.get("platform") or "未记录平台"),
                "question": str(record.get("question") or ""),
                "excerpt": GraphPatchBuilderService.clip(
                    str(record.get("text") or ""), 220
                ),
                "answer_id": str(record.get("answer_id") or ""),
                "question_id": str(record.get("question_id") or ""),
            }

        selected: list[dict[str, Any]] = []
        selected_keys: set[str] = set()
        used_platforms: set[str] = set()
        for record in candidates:
            platform = str(record.get("platform") or "未记录平台")
            if platform in used_platforms:
                continue
            quote = quote_from_record(record)
            key = quote["answer_id"] or f"{quote['platform']}:{quote['question']}:{quote['excerpt']}"
            selected.append(quote)
            selected_keys.add(key)
            used_platforms.add(platform)
            if len(selected) >= limit:
                return selected
        for record in candidates:
            quote = quote_from_record(record)
            key = quote["answer_id"] or f"{quote['platform']}:{quote['question']}:{quote['excerpt']}"
            if key in selected_keys:
                continue
            selected.append(quote)
            selected_keys.add(key)
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _platform_profile_label(
        *,
        risk_count: int,
        total: int,
        active_mentions: int,
        transformation_count: int,
    ) -> str:
        risk_rate = risk_count / total if total else 0.0
        if active_mentions:
            return "主动带出品牌的概率更高"
        if transformation_count >= max(1, total // 4):
            return "更容易展开转型和方案叙事"
        if risk_rate >= 0.45:
            return "风险提醒更密集"
        if risk_rate <= 0.15:
            return "回答更偏正向叙事"
        return "正反信息并置"

    @staticmethod
    def _report_claim_from_patch(patch: GraphPatch) -> dict[str, Any]:
        label = BrandSpaceService._patch_label(patch)
        platforms = BrandSpaceService._patch_platforms(patch)
        evidence_count = len(patch.evidence_refs or [])
        status_label = {
            "auto_applied": "已自动应用",
            "accepted": "已接受",
            "needs_review": "待审阅",
            "blocked": "已阻断",
        }.get(patch.status, patch.status)
        relation_label = {
            "supports": "支持关系",
            "associated_with": "关联关系",
            "risk_related": "风险关系",
            "competes_with": "竞品关系",
            "scenario_for": "场景关系",
            "evidence_missing": "证据缺口",
        }.get(patch.relation_type or "", patch.relation_type or "图谱关系")
        platform_label = "、".join(platforms) if platforms else "未记录平台"
        statement = (
            f"{label}在{platform_label}中形成{relation_label}，"
            f"当前状态为{status_label}，证据片段 {evidence_count} 条。"
        )
        return {
            "claim_id": f"claim:{patch.id}",
            "patch_id": str(patch.id),
            "trace_chain_id": f"trace:{patch.id}",
            "label": label,
            "statement": statement,
            "state": status_label,
            "category": BrandSpaceService._patch_review_category(patch),
            "relation_type": patch.relation_type,
            "status": patch.status,
            "affected_object_id": patch.affected_object_id,
            "platforms": platforms,
            "evidence_refs": patch.evidence_refs or [],
        }

    @staticmethod
    def _trace_chain_from_patch(patch: GraphPatch) -> dict[str, Any]:
        label = BrandSpaceService._patch_label(patch)
        evidence = (patch.evidence_refs or [{}])[0] or {}
        return {
            "trace_chain_id": f"trace:{patch.id}",
            "patch_id": str(patch.id),
            "label": label,
            "steps": [
                {
                    "type": "report_claim",
                    "label": "报告结论",
                    "value": patch.title,
                },
                {
                    "type": "graph_patch",
                    "label": "Graph Patch",
                    "value": f"{patch.patch_type} / {patch.status}",
                    "id": str(patch.id),
                },
                {
                    "type": "entity_relation",
                    "label": "实体关系",
                    "value": f"{patch.relation_type or 'relation'} → {label}",
                    "id": patch.affected_object_id,
                },
                {
                    "type": "answer",
                    "label": "回答片段",
                    "value": str(evidence.get("excerpt") or "无回答片段"),
                    "id": evidence.get("answer_id"),
                },
                {
                    "type": "question",
                    "label": "问题",
                    "value": str(evidence.get("question") or "未记录问题"),
                    "id": evidence.get("question_id"),
                },
                {
                    "type": "platform",
                    "label": "平台",
                    "value": str(evidence.get("platform") or "未记录平台"),
                },
            ],
        }

    @staticmethod
    def _report_platform_differences(patches: list[GraphPatch]) -> list[dict[str, Any]]:
        platform_stats: dict[str, dict[str, Any]] = {}
        for patch in patches:
            for evidence in patch.evidence_refs or []:
                platform = str(evidence.get("platform") or "未记录平台")
                stats = platform_stats.setdefault(
                    platform,
                    {
                        "platform": platform,
                        "evidence_count": 0,
                        "patch_ids": set(),
                        "question_ids": set(),
                        "categories": set(),
                    },
                )
                stats["evidence_count"] += 1
                stats["patch_ids"].add(str(patch.id))
                if evidence.get("question_id"):
                    stats["question_ids"].add(str(evidence.get("question_id")))
                stats["categories"].add(BrandSpaceService._patch_review_category(patch))
        rows: list[dict[str, Any]] = []
        for stats in platform_stats.values():
            rows.append(
                {
                    "platform": stats["platform"],
                    "evidence_count": stats["evidence_count"],
                    "patch_count": len(stats["patch_ids"]),
                    "question_count": len(stats["question_ids"]),
                    "categories": sorted(stats["categories"]),
                }
            )
        return sorted(rows, key=lambda item: (-int(item["evidence_count"]), str(item["platform"])))

    @staticmethod
    def _report_recommended_actions(patches: list[GraphPatch]) -> list[str]:
        reviewable = [patch for patch in patches if patch.status in REVIEWABLE_PATCH_STATUSES]
        if not reviewable:
            platforms = BrandSpaceService._report_platforms_from_patches(patches)
            if not platforms:
                platforms = [
                    BrandSpaceService._platform_display_name(platform)
                    for platform in BRAND_SPACE_DEFAULT_REAL_PLATFORMS[:2]
                ]
            first_platform = platforms[0]
            second_platform = platforms[1] if len(platforms) > 1 else first_platform
            return [
                f"在 {first_platform} 上复测已接受关系，确认核心圈层表述稳定。",
                f"在 {second_platform} 上复测风险问题，确认没有新的质疑语境。",
            ]
        actions: list[str] = []
        for patch in reviewable[:3]:
            platforms = BrandSpaceService._patch_platforms(patch)
            platform = platforms[0] if platforms else BrandSpaceService._platform_display_name(BRAND_SPACE_DEFAULT_REAL_PLATFORMS[0])
            label = BrandSpaceService._patch_label(patch)
            if patch.relation_type == "competes_with":
                actions.append(f"在 {platform} 上补充{label}对比澄清问题，确认是否保留竞品关系。")
            elif patch.relation_type == "risk_related":
                actions.append(f"在 {platform} 上补充{label}风险澄清问题，确认是否继续留在风险层。")
            else:
                actions.append(f"在 {platform} 上补充{label}证据问题，确认是否升级为正式圈层关系。")
        return actions

    @staticmethod
    def _patch_label(patch: GraphPatch) -> str:
        return str((patch.after_payload or {}).get("label") or patch.affected_object_id or patch.title)

    @staticmethod
    def _patch_platforms(patch: GraphPatch) -> list[str]:
        platforms = {
            str(evidence.get("platform") or "").strip()
            for evidence in patch.evidence_refs or []
            if str(evidence.get("platform") or "").strip()
        }
        return sorted(platforms)

    @staticmethod
    def _platform_display_name(platform: Any) -> str:
        key = BrandSpaceService._platform_key(platform)
        template = PLATFORM_TEMPLATE_BY_KEY.get(key)
        if template:
            return str(template["label"]).replace(" 抓取", "").replace("抓取", "").strip()
        raw = str(platform or "").strip()
        return raw or "AI 平台"

    @staticmethod
    def _report_platforms_from_patches(patches: list[GraphPatch]) -> list[str]:
        display_by_key: dict[str, str] = {}
        for patch in patches:
            for platform in BrandSpaceService._patch_platforms(patch):
                key = BrandSpaceService._platform_key(platform)
                display_by_key.setdefault(key, BrandSpaceService._platform_display_name(platform))
        return [
            display_by_key[key]
            for key in sorted(display_by_key.keys())
            if display_by_key.get(key)
        ]

    @staticmethod
    def _report_known_platform_names(patches: list[GraphPatch]) -> tuple[str, ...]:
        names: set[str] = set()
        for key in PLATFORM_TEMPLATE_BY_KEY:
            names.add(key)
            names.add(BrandSpaceService._platform_display_name(key))
        names.update(PLATFORM_KEY_ALIASES.keys())
        names.update(PLATFORM_KEY_ALIASES.values())
        names.update(BrandSpaceService._report_platforms_from_patches(patches))
        return tuple(sorted({name for name in names if name}, key=len, reverse=True))

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


async def build_real_graph_update_for_board_run(run_id: str | UUID, user_id: str | UUID) -> None:
    """Build a completed real-run graph update outside the polling request path."""

    async with AsyncSessionLocal() as db:
        service = BrandSpaceService(db)
        user = await db.get(User, BrandSpaceService._coerce_uuid(user_id, "user_id"))
        if user is None:
            logger.warning("Cannot build graph update for board run %s: user %s missing", run_id, user_id)
            return
        board_run = await service._require_board_run(run_id, user)
        try:
            await service._sync_real_board_run(
                board_run=board_run,
                current_user=user,
                force=True,
            )
        except Exception:
            logger.exception("Brand Space graph update build failed for board run %s", run_id)
            output_refs = dict(board_run.output_refs or {})
            board_run.output_refs = {
                **output_refs,
                "graph_update_build_status": "failed",
                "graph_update_build_failed_at": _now().isoformat(),
            }
            await service._append_event(
                entity_id=board_run.entity_id,
                board_run_id=board_run.id,
                node_id="graph-update",
                event_type="graph_update_build_failed",
                severity="error",
                message="图谱更新后台构建失败，请检查运行产物后重试。",
                payload={"status": "failed"},
            )
            await db.commit()
