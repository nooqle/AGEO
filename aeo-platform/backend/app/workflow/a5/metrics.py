"""Shared metric helpers for A5 analytics.

This module intentionally keeps only reusable metric-level primitives.
The orchestration flow remains in nodes_a5.py; contract/prompt/persistence are
split elsewhere to avoid a circular dependency while the refactor lands.
"""

from __future__ import annotations

from app.core.constants import SENTIMENT_SCORES
from app.workflow.nodes_a4 import PLATFORMS

BWVS_WEIGHTS = {
    'mention': 40,
    'sentiment': 25,
    'coverage': 20,
    'citation': 15,
}

assert sum(BWVS_WEIGHTS.values()) == 100, 'BWVS weights must sum to 100'

_POSITIVE_KEYWORDS = [
    '推荐', '优秀', '好', '满意', '值得', '安心', '可靠', '高效',
    '有效', '专业', '稳定', '正面', '便捷', '喜欢', '适合', '改善',
    '增强', '领先', '信赖', '精准', '口碑', '权威', '便于',
    '认证', '大奖', '标杆', '突破', '提升', '市场成功', '积极影响',
    'ISO 27001', '信息安全认证', '红点设计', '国际红点', '上下文窗口',
    '准确率提升',
]
_NEGATIVE_KEYWORDS = [
    '差', '不好', '失望', '风险', '问题', '担心', '复杂', '缺失',
    '不稳定', '负面', '慢', '错误', '不推荐', '质疑', '误导',
    '薄弱', '空白', '竞品替代', '缺席', '落后', '不符合', '不达标',
    '虚标', '隐私泄露', '未经授权', '巨额罚款', '召回', '热失控',
    '降频', '严重限制', '硬伤', '缺陷', '公关危机',
    '抽检', 'GB/T 18801', '参数虚标', '监管罚款', '监管机构',
    '未经授权收集', '定位数据', '热失控风险', '主动召回', '性能释放受限',
]


def analyze_sentiment(text: str) -> str:
    """Return positive/negative/neutral using the repo's keyword heuristic."""
    if not text:
        return 'neutral'

    neg_count = 0
    neg_spans: list[tuple[int, int]] = []
    for kw in _NEGATIVE_KEYWORDS:
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx == -1:
                break
            neg_count += 1
            neg_spans.append((idx, idx + len(kw)))
            start = idx + len(kw)

    pos_count = 0
    for kw in _POSITIVE_KEYWORDS:
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx == -1:
                break
            shadowed = any(ns <= idx < ne for ns, ne in neg_spans)
            if not shadowed:
                pos_count += 1
            start = idx + len(kw)

    if pos_count > neg_count:
        return 'positive'
    if neg_count > pos_count:
        return 'negative'
    return 'neutral'


def compute_platform_sentiment(fetch_results: list, platform_key: str) -> float:
    """Compute a 0-100 sentiment score for a given platform from fetch results."""
    scores: list[float] = []
    for result in fetch_results:
        for pr in result.get('platform_results', []):
            if pr.get('platform', '').lower() != platform_key.lower():
                continue
            if not pr.get('success'):
                continue
            answer = pr.get('answer', {})
            content = answer.get('content', '') if isinstance(answer, dict) else str(answer)
            sentiment = analyze_sentiment(content)
            scores.append(SENTIMENT_SCORES.get(sentiment, 0.0))

    if not scores:
        return 50.0

    avg_sentiment = sum(scores) / len(scores)
    return round(max(0.0, min(100.0, (avg_sentiment + 1) * 50)), 1)


def platform_total_count() -> int:
    """Return the current platform denominator used by BWVS-related metrics."""
    return len(PLATFORMS)
