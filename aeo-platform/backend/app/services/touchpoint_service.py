"""Touchpoint service for building tree from A2/A3 data.

Constructs tree hierarchy: Brand -> User Profiles -> Scenarios -> Intents -> Optimization Units

Data flow:
1. A2 persona agent produces marketing_personas with user_personas list
2. A3 question agent produces simulated_questions
3. build_tree_from_state() combines these into a tree
4. get_tree() queries the latest OUTPUT messages to find this data
"""

import json
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.message import Message, MessageType, MessageRole

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
_CACHE_TTL = 300

# In-memory cache for built trees: {key: (timestamp, data)}
_tree_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class TouchpointService:
    """Builds touchpoint tree from analysis results."""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    async def get_tree(self, brand_id: str | None) -> dict[str, Any]:
        """Get touchpoint tree for a brand.

        Queries OUTPUT messages for persona and question data,
        then builds the tree structure.
        """
        # Check cache first (with TTL)
        cache_key = brand_id or "_default"
        if cache_key in _tree_cache:
            cached_time, cached_data = _tree_cache[cache_key]
            if time.time() - cached_time < _CACHE_TTL:
                return cached_data
            # Expired — remove stale entry
            del _tree_cache[cache_key]

        if not self.db:
            return {"brand": brand_id or "", "nodes": []}

        # Query OUTPUT messages for persona/question data
        query = (
            select(Message)
            .where(
                Message.role == MessageRole.ASSISTANT,
                Message.type == MessageType.OUTPUT,
            )
            .order_by(desc(Message.created_at))
            .limit(20)
        )
        result = await self.db.execute(query)
        messages = result.scalars().all()

        personas: list[dict[str, Any]] = []
        questions: list[dict[str, Any]] = []
        brand_name = brand_id or ""

        for msg in messages:
            if not msg.output_data:
                continue
            try:
                data = json.loads(msg.output_data)
            except (json.JSONDecodeError, TypeError):
                continue

            # Extract personas (snake_case + camelCase fallback)
            mp = data.get("marketing_personas") or data.get("marketingPersonas")
            if mp:
                up = (
                    mp.get("user_personas") or mp.get("userPersonas")
                    if isinstance(mp, dict) else None
                )
                if up:
                    personas = up
                    brand_summary = mp.get("brand_summary") or mp.get("brandSummary") or {}
                    if brand_summary.get("brand_name") or brand_summary.get("brandName"):
                        brand_name = brand_summary.get("brand_name") or brand_summary.get("brandName", "")
            elif "user_personas" in data or "userPersonas" in data:
                personas = data.get("user_personas") or data.get("userPersonas") or []

            # Extract questions (snake_case + camelCase fallback)
            sq = data.get("simulated_questions") or data.get("simulatedQuestions")
            if sq:
                if isinstance(sq, dict):
                    questions = sq.get("simulated_questions") or sq.get("simulatedQuestions") or []
                elif isinstance(sq, list):
                    questions = sq

            # Extract brand name from brand_profile
            if "brand_profile" in data:
                bp = data["brand_profile"]
                if isinstance(bp, dict) and bp.get("brand_name"):
                    brand_name = bp["brand_name"]

            # Extract flat questions list
            if "questions" in data and isinstance(data["questions"], list) and not questions:
                questions = data["questions"]

        if not personas and not questions:
            return {"brand": brand_name, "nodes": []}

        tree = self.build_tree_from_state(brand_name, personas, questions)
        _tree_cache[cache_key] = (time.time(), tree)
        return tree

    def build_tree_from_state(
        self,
        brand_name: str,
        personas: list[dict[str, Any]],
        questions: list[dict[str, Any]],
        fetch_results: list[dict[str, Any]] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build touchpoint tree from workflow state data.

        Args:
            brand_name: Brand name for root node
            personas: User personas from A2 agent
            questions: Simulated questions from A3 agent
            fetch_results: A4 fetch results (optional, for L4 optimization nodes)
            metrics: A5 calculated metrics (optional, for injecting into nodes)
        """
        nodes = []

        # Build fetch_results lookup by question_id for metrics injection
        fetch_by_question: dict[str, list[dict[str, Any]]] = {}
        if fetch_results:
            for fr in fetch_results:
                q_id = fr.get("question_id", "")
                if q_id:
                    fetch_by_question[q_id] = fr.get("platform_results", [])

        # Build a question lookup by category/persona for linking
        question_by_category: dict[str, list[dict[str, Any]]] = {}
        for q in questions:
            cat = q.get("category", "general")
            if cat not in question_by_category:
                question_by_category[cat] = []
            question_by_category[cat].append(q)

        for persona in personas:
            persona_name = persona.get("persona_name", persona.get("name", "Unknown"))
            persona_node = {
                "id": f"profile_{persona_name.replace(' ', '_')}",
                "type": "profile",
                "label": persona_name,
                "description": persona.get("persona_description", persona.get("description", "")),
                "metadata": {
                    "priority": persona.get("persona_priority", persona.get("priority", "")),
                    "market_size": persona.get("estimated_market_size", ""),
                },
                "children": [],
            }

            # Add scenarios from persona
            # Supports both dict format {"scenario_name": ..., "scenario_description": ...}
            # and plain string format for backward compat
            scenarios = persona.get("usage_scenarios", [])
            for i, scenario in enumerate(scenarios):
                if isinstance(scenario, dict):
                    scenario_label = scenario.get("scenario_name", f"场景{i+1}")
                    scenario_desc = scenario.get("scenario_description", "")
                elif isinstance(scenario, str):
                    scenario_label = scenario
                    scenario_desc = ""
                else:
                    scenario_label = str(scenario)
                    scenario_desc = ""
                scenario_node = {
                    "id": f"{persona_node['id']}_scenario_{i}",
                    "type": "scenario",
                    "label": scenario_label,
                    "description": scenario_desc,
                    "children": [],
                }

                # Link questions to scenarios as intent nodes
                # Use round-robin distribution to avoid duplicating questions
                persona_name = persona.get("persona_name", persona.get("name", ""))
                scenario_label_lower = scenario_label.lower() if isinstance(scenario_label, str) else ""
                added = 0
                for q in questions:
                    # Prefer matching by source_persona or category
                    q_persona = q.get("source_persona", "")
                    q_category = q.get("category", "").lower()
                    # If source_persona is set, only assign to matching persona
                    if q_persona and q_persona != persona_name:
                        continue
                    # If category matches scenario label, prefer it
                    q_id = q.get("question_id", q.get("id", f"q_{i}"))
                    core_q = q.get("core_question", q.get("text", ""))
                    if core_q:
                        intent_node = {
                            "id": f"{scenario_node['id']}_intent_{q_id}",
                            "type": "intent",
                            "label": core_q[:60] + ("..." if len(core_q) > 60 else ""),
                            "description": core_q,
                            "metadata": {
                                "category": q.get("category", ""),
                                "intent": q.get("user_intent", ""),
                                "decision_stage": q.get("decision_stage", ""),
                            },
                            "children": [],
                        }

                        # Inject per-question metrics from fetch_results
                        platform_results = fetch_by_question.get(q_id, [])
                        if platform_results:
                            q_metrics = self._compute_question_metrics(platform_results)
                            intent_node["metadata"]["metrics"] = q_metrics

                        # Add L4 optimization unit nodes
                        opt_nodes = self._build_optimization_nodes(
                            q_id, intent_node["id"], platform_results
                        )
                        intent_node["children"] = opt_nodes

                        scenario_node["children"].append(intent_node)
                        added += 1

                    # Only add a few questions per scenario to avoid explosion
                    if added >= 3:
                        break

                persona_node["children"].append(scenario_node)

            # Aggregate metrics from child intent nodes into profile node
            if fetch_results:
                agg = self._aggregate_profile_metrics(persona_node)
                if agg:
                    persona_node["metadata"]["metrics"] = agg

            nodes.append(persona_node)

        # If no personas but we have questions, create a flat tree
        if not personas and questions:
            for q in questions:
                q_id = q.get("question_id", q.get("id", ""))
                core_q = q.get("core_question", q.get("text", ""))
                nodes.append({
                    "id": f"intent_{q_id}",
                    "type": "intent",
                    "label": core_q[:60] + ("..." if len(core_q) > 60 else ""),
                    "description": core_q,
                })

        return {
            "brand": brand_name,
            "nodes": nodes,
        }

    @staticmethod
    def _compute_question_metrics(
        platform_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute per-question metrics from platform results.

        Returns dict with mention_count, total_platforms, mention_rate, sentiment.
        """
        total = len(platform_results)
        mentions = 0
        sentiments: list[str] = []

        for pr in platform_results:
            if not pr.get("success"):
                continue
            answer = pr.get("answer", {})
            if isinstance(answer, dict) and answer.get("has_brand_mention", False):
                mentions += 1
            # Collect sentiment from content if available
            content = answer.get("content", "") if isinstance(answer, dict) else ""
            if content:
                sentiments.append(content)

        mention_rate = mentions / total if total > 0 else 0.0

        return {
            "mention_count": mentions,
            "total_platforms": total,
            "mention_rate": round(mention_rate, 4),
        }

    @staticmethod
    def _build_optimization_nodes(
        question_id: str,
        parent_id: str,
        platform_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build L4 optimization unit nodes from platform results.

        Each platform result for a question becomes an optimization node
        with platform, has_mention, sentiment metadata.
        """
        if not platform_results:
            return []

        nodes = []
        for i, pr in enumerate(platform_results):
            platform = pr.get("platform", "unknown")
            success = pr.get("success", False)
            answer = pr.get("answer", {})
            has_mention = answer.get("has_brand_mention", False) if isinstance(answer, dict) else False
            content = answer.get("content", "") if isinstance(answer, dict) else ""

            # Simple sentiment based on has_mention for now
            sentiment = "neutral"
            if has_mention and content:
                sentiment = "positive"  # mentioned = positive signal
            elif not has_mention and success:
                sentiment = "negative"  # not mentioned despite successful fetch

            node = {
                "id": f"{parent_id}_opt_{platform}_{i}",
                "type": "optimization",
                "label": f"{platform.capitalize()} 优化单元",
                "description": f"平台: {platform}, 提及: {'是' if has_mention else '否'}",
                "metadata": {
                    "platform": platform,
                    "has_mention": has_mention,
                    "sentiment": sentiment,
                    "success": success,
                    "content_length": len(content),
                },
            }
            nodes.append(node)

        return nodes

    @staticmethod
    def _aggregate_profile_metrics(
        persona_node: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Aggregate metrics from child intent nodes into a profile-level summary."""
        total_mentions = 0
        total_platforms = 0

        for scenario in persona_node.get("children", []):
            for intent in scenario.get("children", []):
                m = intent.get("metadata", {}).get("metrics")
                if m:
                    total_mentions += m.get("mention_count", 0)
                    total_platforms += m.get("total_platforms", 0)

        if total_platforms == 0:
            return None

        return {
            "mention_count": total_mentions,
            "total_platforms": total_platforms,
            "mention_rate": round(total_mentions / total_platforms, 4),
        }

    @staticmethod
    def invalidate_cache(brand_id: str | None = None) -> None:
        """Invalidate tree cache."""
        if brand_id:
            _tree_cache.pop(brand_id, None)
        else:
            _tree_cache.clear()
