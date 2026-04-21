"""Site confidence assessment artifact builder.

Phase 1 scope:
- accept a root website URL
- discover a bounded set of important first/second-level internal pages
- evaluate structural confidence signals for each page
- emit a report artifact that reuses the existing report/version pipeline

This intentionally keeps runtime simple: HTTP + sitemap + HTML parsing only.
If the default machine path cannot read a page, that page should fail the evaluation.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.services.page_feature_service import fetch_page_features


DEFAULT_SCAN_MODE = "standard"
DEFAULT_MAX_PAGES = 50
HARD_MAX_SCAN_PAGES = 50
HTTP_TIMEOUT_SECONDS = 8.0
INTERNAL_LINK_LIMIT = 48
SITEMAP_URL_LIMIT = 24
PAGE_FETCH_CONCURRENCY = 6
SITE_USER_AGENT = (
    "Mozilla/5.0 (compatible; SpectaSiteConfidence/1.0; +https://specta.ai/)"
)
MIN_BODY_TEXT_LENGTH = 180

_CORE_PAGE_TYPE_PRIORITIES: dict[str, int] = {
    "homepage": 120,
    "product": 108,
    "solution": 106,
    "pricing": 103,
    "docs": 101,
    "faq": 99,
    "about": 96,
    "contact": 94,
    "blog": 88,
    "news": 86,
    "support": 84,
    "generic": 70,
}

_PAGE_TYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "product",
        (
            "product",
            "products",
            "feature",
            "features",
            "platform",
            "service",
            "services",
            "产品",
            "功能",
            "平台",
            "服务",
        ),
    ),
    (
        "solution",
        (
            "solution",
            "solutions",
            "use-case",
            "usecase",
            "industry",
            "industries",
            "解决方案",
            "场景",
            "行业",
        ),
    ),
    ("pricing", ("pricing", "price", "plans", "plan", "报价", "价格", "套餐")),
    (
        "docs",
        (
            "doc",
            "docs",
            "documentation",
            "guide",
            "guides",
            "manual",
            "help",
            "learn",
            "文档",
            "指南",
            "帮助",
            "教程",
        ),
    ),
    ("faq", ("faq", "faqs", "question", "questions", "问答", "常见问题")),
    ("about", ("about", "company", "story", "team", "brand", "关于", "公司", "团队")),
    ("contact", ("contact", "contacts", "demo", "book-demo", "预约", "联系", "咨询")),
    (
        "support",
        (
            "support",
            "customer",
            "customers",
            "case-study",
            "case-studies",
            "support-center",
            "客户",
            "案例",
            "支持",
        ),
    ),
    (
        "blog",
        (
            "blog",
            "blogs",
            "article",
            "articles",
            "insight",
            "insights",
            "博客",
            "文章",
            "洞察",
        ),
    ),
    ("news", ("news", "press", "update", "updates", "媒体", "新闻", "动态")),
)

_EXCLUDED_PATH_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "auth",
        (
            "login",
            "log-in",
            "signin",
            "sign-in",
            "signup",
            "sign-up",
            "register",
            "account",
            "auth",
            "oauth",
            "sso",
            "密码",
            "登录",
            "注册",
        ),
    ),
    (
        "transaction",
        (
            "cart",
            "checkout",
            "billing",
            "payment",
            "order",
            "pay",
            "结账",
            "支付",
            "订单",
        ),
    ),
    (
        "search_or_filter",
        (
            "search",
            "tag",
            "tags",
            "category",
            "categories",
            "filter",
            "sort",
            "query",
            "搜索",
            "标签",
            "分类",
        ),
    ),
    (
        "legal",
        (
            "privacy",
            "terms",
            "policy",
            "cookies",
            "legal",
            "gdpr",
            "隐私",
            "条款",
            "协议",
        ),
    ),
    ("career", ("career", "careers", "job", "jobs", "hiring", "招聘", "岗位")),
    (
        "download",
        (
            "download",
            "downloads",
            "asset",
            "assets",
            "attachment",
            "attachments",
            "资源下载",
            "下载",
        ),
    ),
)

_PAGE_TYPE_BUDGETS: dict[str, int] = {
    "homepage": 1,
    "product": 2,
    "solution": 2,
    "pricing": 1,
    "docs": 1,
    "faq": 1,
    "about": 1,
    "contact": 1,
    "support": 1,
    "blog": 1,
    "news": 1,
    "generic": 2,
}


@dataclass(frozen=True)
class DiscoveredPage:
    url: str
    page_type: str
    source_hint: str
    label: str
    depth: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _normalize_root_url(root_url: str) -> str:
    normalized = (root_url or "").strip()
    if not normalized:
        raise ValueError("请先提供官网地址，再启动官网 AI 友好度评估。")

    if not re.match(r"^https?://", normalized, flags=re.IGNORECASE):
        normalized = f"https://{normalized}"

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("官网地址格式无效，请提供可访问的 http/https 官网地址。")

    normalized = parsed._replace(path="", params="", query="", fragment="").geturl()
    return normalized.rstrip("/")


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _artifact_domain_key(domain: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (domain or "").lower()).strip("_") or "site"


def _normalize_scan_page_limit(max_pages: int | str | None) -> int:
    try:
        requested = int(max_pages or DEFAULT_MAX_PAGES)
    except (TypeError, ValueError):
        requested = DEFAULT_MAX_PAGES
    return max(3, min(requested, HARD_MAX_SCAN_PAGES))


def _path_depth(url: str) -> int:
    path = urlparse(url).path.strip("/")
    if not path:
        return 0
    return len([segment for segment in path.split("/") if segment])


def _path_segments(url: str) -> list[str]:
    path = urlparse(url).path.strip("/").lower()
    return [segment for segment in path.split("/") if segment]


def _is_same_site(url: str, root_domain: str) -> bool:
    candidate_domain = _extract_domain(url)
    if not candidate_domain or not root_domain:
        return False
    return candidate_domain == root_domain or candidate_domain.endswith(
        f".{root_domain}"
    )


def _is_supported_html_path(url: str) -> bool:
    path = urlparse(url).path.lower()
    return not bool(
        re.search(
            r"\.(pdf|zip|rar|7z|png|jpg|jpeg|gif|svg|webp|mp4|mp3|doc|docx|xls|xlsx|ppt|pptx)$",
            path,
        )
    )


def _normalize_internal_url(
    candidate: str, *, base_url: str, root_domain: str
) -> str | None:
    absolute = urljoin(base_url, candidate or "").strip()
    if not absolute:
        return None

    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if not _is_same_site(absolute, root_domain):
        return None
    if not _is_supported_html_path(absolute):
        return None

    normalized = parsed._replace(params="", query="", fragment="").geturl()
    return normalized.rstrip("/") if parsed.path in {"", "/"} else normalized


def _classify_exclusion(url: str, label: str = "") -> str | None:
    parsed = urlparse(url)
    if parsed.query:
        query = parsed.query.lower()
        if any(
            marker in query
            for marker in ("utm_", "session", "token", "replytocom", "sort=", "filter=")
        ):
            return "tracking_or_filter"

    joined = " ".join(_path_segments(url) + [label.lower()]).strip()
    if not joined:
        return None
    for reason, keywords in _EXCLUDED_PATH_RULES:
        if any(keyword in joined for keyword in keywords):
            return reason
    return None


def _url_signature(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/").lower()
    if not path:
        path = "/"
    return f"{parsed.netloc.lower()}::{path}"


def _extract_title(html: str) -> str:
    match = re.search(
        r"<title\b[^>]*>(.*?)</title>", html or "", flags=re.IGNORECASE | re.DOTALL
    )
    return _collapse_text(re.sub(r"<[^>]+>", " ", match.group(1))) if match else ""


async def _fetch_text(url: str) -> dict[str, Any]:
    default = {
        "url": url,
        "final_url": url,
        "status_code": None,
        "text": "",
        "content_type": "",
    }
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": SITE_USER_AGENT},
        ) as client:
            response = await client.get(url)
        return {
            "url": url,
            "final_url": str(response.url),
            "status_code": response.status_code,
            "text": response.text or "",
            "content_type": str(response.headers.get("content-type") or "").lower(),
        }
    except Exception:
        return default


def _parse_anchor_text(tag_html: str) -> str:
    body = re.sub(
        r"^<a\b[^>]*>|</a>$", "", tag_html or "", flags=re.IGNORECASE | re.DOTALL
    )
    return _collapse_text(re.sub(r"<[^>]+>", " ", body))


def _extract_internal_links(
    html: str, *, base_url: str, root_domain: str
) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    full_anchor_matches = re.findall(
        r"(<a\b[^>]*href=['\"](.*?)['\"][^>]*>.*?</a>)",
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for anchor_tag, href in full_anchor_matches[: INTERNAL_LINK_LIMIT * 2]:
        normalized = _normalize_internal_url(
            href, base_url=base_url, root_domain=root_domain
        )
        if not normalized:
            continue
        label = _parse_anchor_text(anchor_tag)
        links.append((normalized, label))

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for url, label in links:
        if url in seen:
            continue
        seen.add(url)
        deduped.append((url, label))
        if len(deduped) >= INTERNAL_LINK_LIMIT:
            break
    return deduped


async def _fetch_html(url: str) -> dict[str, Any]:
    default = {
        "url": url,
        "final_url": url,
        "status_code": None,
        "html": "",
        "title": "",
        "content_type": "",
    }
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": SITE_USER_AGENT},
        ) as client:
            response = await client.get(url)
        content_type = str(response.headers.get("content-type") or "").lower()
        html = response.text or ""
        if not any(
            marker in content_type
            for marker in (
                "text/html",
                "application/xhtml+xml",
                "xml",
                "text/xml",
                "application/xml",
            )
        ):
            return {
                **default,
                "status_code": response.status_code,
                "final_url": str(response.url),
                "content_type": content_type,
            }
        return {
            "url": url,
            "final_url": str(response.url),
            "status_code": response.status_code,
            "html": html,
            "title": _extract_title(html),
            "content_type": content_type,
        }
    except Exception:
        return default


async def _fetch_sitemap_urls(root_url: str, root_domain: str) -> list[str]:
    sitemap_url = urljoin(
        root_url if root_url.endswith("/") else f"{root_url}/", "sitemap.xml"
    )
    payload = await _fetch_html(sitemap_url)
    xml = str(payload.get("html") or "")
    if not xml:
        return []

    urls: list[str] = []
    for loc in re.findall(r"<loc>(.*?)</loc>", xml, flags=re.IGNORECASE | re.DOTALL):
        normalized = _normalize_internal_url(
            loc, base_url=root_url, root_domain=root_domain
        )
        if not normalized:
            continue
        if _path_depth(normalized) > 2:
            continue
        urls.append(normalized)

    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
        if len(deduped) >= SITEMAP_URL_LIMIT:
            break
    return deduped


def _parse_robots_policy(robots_text: str) -> dict[str, Any]:
    active_applies = False
    disallow_rules: list[str] = []
    sitemap_urls: list[str] = []
    for raw_line in (robots_text or "").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, value = line.split(":", 1)
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            active_applies = value == "*"
            continue
        if field == "sitemap" and value:
            sitemap_urls.append(value)
            continue
        if field == "disallow" and active_applies and value:
            disallow_rules.append(value)
    return {
        "disallow_rules": disallow_rules,
        "sitemap_urls": sitemap_urls,
    }


def _is_path_blocked_by_robots(url: str, disallow_rules: list[str]) -> bool:
    path = urlparse(url).path or "/"
    for rule in disallow_rules:
        normalized = str(rule or "").strip()
        if not normalized:
            continue
        if normalized == "/":
            return True
        if path.startswith(normalized):
            return True
    return False


async def _inspect_crawl_governance(
    *,
    root_url: str,
    selected_pages: list[DiscoveredPage],
    discovery_summary: dict[str, Any],
) -> dict[str, Any]:
    sitemap_url = urljoin(
        root_url if root_url.endswith("/") else f"{root_url}/", "sitemap.xml"
    )
    robots_url = urljoin(
        root_url if root_url.endswith("/") else f"{root_url}/", "robots.txt"
    )
    robots_payload = await _fetch_text(robots_url)
    robots_text = str(robots_payload.get("text") or "")
    robots_present = bool(
        robots_payload.get("status_code")
        and int(robots_payload.get("status_code") or 0) < 400
        and robots_text.strip()
    )
    robots_policy = (
        _parse_robots_policy(robots_text)
        if robots_present
        else {"disallow_rules": [], "sitemap_urls": []}
    )
    disallow_rules = list(robots_policy.get("disallow_rules") or [])
    blocked_pages: list[dict[str, str]] = []
    for page in selected_pages:
        if _is_path_blocked_by_robots(page.url, disallow_rules):
            blocked_pages.append(
                {
                    "url": page.url,
                    "page_type": page.page_type,
                    "label": page.label,
                }
            )

    key_types = {"homepage", "product", "solution", "pricing", "docs", "faq", "about"}
    blocked_key_pages = [
        page for page in blocked_pages if str(page.get("page_type") or "") in key_types
    ]
    homepage_blocked = any(
        str(page.get("page_type") or "") == "homepage" for page in blocked_key_pages
    )
    sitemap_present = bool(
        Counter(discovery_summary.get("discovery_sources") or {}).get("sitemap")
    ) or bool(robots_policy.get("sitemap_urls"))

    score = 4
    if sitemap_present:
        score += 3
    if robots_present:
        score += 2
        if not blocked_key_pages:
            score += 1
    if blocked_key_pages:
        score = min(score, 3)
    if homepage_blocked:
        score = min(score, 1)

    if homepage_blocked:
        assessment = "robots.txt 对首页或关键入口存在过度封锁，抓取治理存在明显风险。"
    elif blocked_key_pages:
        assessment = "robots.txt 对部分关键页面存在封锁，抓取治理会直接影响核心内容进入机器视野。"
    elif sitemap_present and robots_present:
        assessment = "站点提供了 sitemap 和 robots.txt，抓取治理基础较完整。"
    elif sitemap_present or robots_present:
        assessment = "站点已具备部分抓取治理信号，但 sitemap 与 robots.txt 仍不够完整。"
    else:
        assessment = "站点缺少 sitemap 和 robots.txt，抓取治理信号偏弱。"

    return {
        "id": "crawl_governance",
        "label": "抓取治理",
        "score": max(0, min(10, score)),
        "assessment": assessment,
        "sitemap_present": sitemap_present,
        "sitemap_url": sitemap_url,
        "robots_present": robots_present,
        "robots_url": robots_url,
        "robots_disallow_rules": disallow_rules[:12],
        "blocked_page_count": len(blocked_pages),
        "blocked_key_page_count": len(blocked_key_pages),
        "homepage_blocked": homepage_blocked,
        "blocked_pages": blocked_pages[:8],
    }


def _guess_page_type(url: str, label: str = "") -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/").lower()
    joined = f"{path} {label.lower()}".strip()
    if not path:
        return "homepage"
    for page_type, keywords in _PAGE_TYPE_PATTERNS:
        if any(keyword in joined for keyword in keywords):
            return page_type
    return "generic"


def _page_priority(url: str, label: str, source_hint: str) -> int:
    page_type = _guess_page_type(url, label)
    priority = _CORE_PAGE_TYPE_PRIORITIES.get(
        page_type, _CORE_PAGE_TYPE_PRIORITIES["generic"]
    )
    depth = _path_depth(url)
    priority -= depth * 8
    if source_hint == "homepage_link":
        priority += 6
    if source_hint == "sitemap":
        priority += 2
    if re.search(r"(utm_|#|/tag/|/category/)", url, flags=re.IGNORECASE):
        priority -= 16
    return priority


def _select_pages(
    candidates: list[DiscoveredPage],
    *,
    max_pages: int,
) -> tuple[list[DiscoveredPage], Counter[str], Counter[str], int]:
    excluded_reason_counts: Counter[str] = Counter()
    eligible_pages: list[DiscoveredPage] = []
    eligible_by_signature: set[str] = set()

    for page in sorted(
        candidates,
        key=lambda item: (
            -_page_priority(item.url, item.label, item.source_hint),
            item.depth,
            item.url,
        ),
    ):
        signature = _url_signature(page.url)
        if signature in eligible_by_signature:
            excluded_reason_counts["duplicate_url"] += 1
            continue

        exclusion_reason = (
            None
            if page.page_type == "homepage"
            else _classify_exclusion(
                page.url,
                page.label,
            )
        )
        if exclusion_reason:
            excluded_reason_counts[exclusion_reason] += 1
            continue

        eligible_pages.append(page)
        eligible_by_signature.add(signature)

    if len(eligible_pages) <= max_pages:
        return (
            eligible_pages,
            Counter(page.page_type for page in eligible_pages),
            excluded_reason_counts,
            len(eligible_pages),
        )

    selected: list[DiscoveredPage] = []
    selected_by_signature: set[str] = set()
    type_counts: Counter[str] = Counter()

    for page in eligible_pages:
        page_budget = _PAGE_TYPE_BUDGETS.get(
            page.page_type, _PAGE_TYPE_BUDGETS["generic"]
        )
        if type_counts[page.page_type] >= page_budget:
            excluded_reason_counts[f"budget_{page.page_type}"] += 1
            continue

        selected.append(page)
        selected_by_signature.add(signature)
        type_counts[page.page_type] += 1
        if len(selected) >= max_pages:
            break

    if len(selected) < max_pages:
        for page in eligible_pages:
            signature = _url_signature(page.url)
            if signature in selected_by_signature:
                continue
            selected.append(page)
            selected_by_signature.add(signature)
            type_counts[page.page_type] += 1
            if len(selected) >= max_pages:
                break

    return selected, type_counts, excluded_reason_counts, len(eligible_pages)


async def discover_site_pages(
    root_url: str,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> tuple[list[DiscoveredPage], dict[str, Any]]:
    normalized_root = _normalize_root_url(root_url)
    root_domain = _extract_domain(normalized_root)
    homepage_payload = await _fetch_html(normalized_root)
    final_root_url = str(homepage_payload.get("final_url") or normalized_root)
    final_root_domain = _extract_domain(final_root_url) or root_domain

    candidates: list[DiscoveredPage] = [
        DiscoveredPage(
            url=final_root_url,
            page_type="homepage",
            source_hint="homepage",
            label=homepage_payload.get("title") or "首页",
            depth=0,
        )
    ]

    homepage_html = str(homepage_payload.get("html") or "")
    if homepage_html:
        for url, label in _extract_internal_links(
            homepage_html,
            base_url=final_root_url,
            root_domain=final_root_domain,
        ):
            depth = _path_depth(url)
            if depth > 2:
                continue
            candidates.append(
                DiscoveredPage(
                    url=url,
                    page_type=_guess_page_type(url, label),
                    source_hint="homepage_link",
                    label=label or urlparse(url).path.strip("/") or "内部页",
                    depth=depth,
                )
            )

    for url in await _fetch_sitemap_urls(final_root_url, final_root_domain):
        candidates.append(
            DiscoveredPage(
                url=url,
                page_type=_guess_page_type(url),
                source_hint="sitemap",
                label=urlparse(url).path.strip("/") or "页面",
                depth=_path_depth(url),
            )
        )

    normalized_max_pages = _normalize_scan_page_limit(max_pages)
    selected_pages, selected_type_counts, excluded_reason_counts, eligible_page_count = _select_pages(
        candidates,
        max_pages=normalized_max_pages,
    )

    discovery_summary = {
        "input_root_url": normalized_root,
        "resolved_root_url": final_root_url,
        "root_domain": final_root_domain,
        "homepage_http_status": homepage_payload.get("status_code"),
        "homepage_title": homepage_payload.get("title") or "",
        "max_pages_requested": max_pages,
        "max_pages_applied": normalized_max_pages,
        "candidate_url_count": len(candidates),
        "eligible_url_count": eligible_page_count,
        "discovered_url_count": len(selected_pages),
        "excluded_url_count": sum(excluded_reason_counts.values()),
        "discovery_sources": Counter(page.source_hint for page in selected_pages),
        "selected_page_type_counts": selected_type_counts,
        "excluded_reason_counts": excluded_reason_counts,
    }
    return selected_pages, discovery_summary


def _build_dimension_scores(
    page: DiscoveredPage,
    features: dict[str, Any],
) -> list[dict[str, Any]]:
    body_text_length = int(features.get("body_text_length") or 0)
    schema_types = list(features.get("schema_types") or [])
    has_title = bool(features.get("fetched_title"))
    has_structure = bool(
        features.get("has_h1")
        and (features.get("has_main") or features.get("has_article"))
    )

    access_score = 10 if features.get("crawl_readable") else 0
    security_score = 10 if page.url.startswith("https://") else 0
    topic_clarity_score = (
        10
        if features.get("has_h1") and has_title
        else 6 if (features.get("has_h1") or has_title) else 2
    )
    semantic_structure_score = (
        10
        if features.get("has_h1")
        and (features.get("has_main") or features.get("has_article"))
        else 7 if (features.get("has_main") or features.get("has_article")) else 2
    )
    structured_data_score = min(10, 4 + len(schema_types) * 2) if schema_types else 0
    freshness_score = 10 if features.get("published_at") else 4
    if body_text_length >= 800:
        content_depth_score = 10
    elif body_text_length >= 400:
        content_depth_score = 8
    elif body_text_length >= MIN_BODY_TEXT_LENGTH:
        content_depth_score = 6
    else:
        content_depth_score = 2
    machine_readability_score = (
        10
        if features.get("crawl_readable")
        and body_text_length >= MIN_BODY_TEXT_LENGTH
        and has_structure
        else 6 if features.get("crawl_readable") else 0
    )

    return [
        {
            "id": "accessibility",
            "label": "可抓取性",
            "score": access_score,
            "assessment": (
                "页面当前可被 HTTP 稳定抓取。"
                if access_score >= 8
                else "页面抓取不稳定或当前不可读。"
            ),
        },
        {
            "id": "security",
            "label": "传输安全",
            "score": security_score,
            "assessment": (
                "页面已统一走 HTTPS。"
                if security_score >= 8
                else "页面未统一走 HTTPS。"
            ),
        },
        {
            "id": "topic_clarity",
            "label": "主题清晰度",
            "score": topic_clarity_score,
            "assessment": (
                "标题层级和页面主题表达较清晰。"
                if topic_clarity_score >= 8
                else "标题或主题表达仍然偏弱。"
            ),
        },
        {
            "id": "semantic_structure",
            "label": "语义结构",
            "score": semantic_structure_score,
            "assessment": (
                "存在明确主体语义区域。"
                if semantic_structure_score >= 8
                else "main/article 等主体语义结构不足。"
            ),
        },
        {
            "id": "structured_data",
            "label": "结构化数据",
            "score": structured_data_score,
            "assessment": (
                "存在可用的 Schema.org 标记。"
                if structured_data_score >= 8
                else "结构化标记仍然不足。"
            ),
        },
        {
            "id": "freshness",
            "label": "时效信号",
            "score": freshness_score,
            "assessment": (
                "页面暴露了发布时间或更新时间。"
                if freshness_score >= 8
                else "页面缺少明显的时间戳信号。"
            ),
        },
        {
            "id": "content_depth",
            "label": "正文厚度",
            "score": content_depth_score,
            "assessment": (
                "正文长度足以支撑基本引用。"
                if content_depth_score >= 8
                else "正文偏薄，信息密度不足。"
            ),
        },
        {
            "id": "machine_readability",
            "label": "机器可读性",
            "score": machine_readability_score,
            "assessment": (
                "默认机器抓取路径可以稳定拿到正文和主体结构。"
                if machine_readability_score >= 8
                else "默认机器抓取路径下的正文或主体结构仍然偏弱。"
            ),
        },
    ]


def _build_gate_scores(
    features: dict[str, Any],
) -> dict[str, Any]:
    body_text_length = int(features.get("body_text_length") or 0)
    schema_types = list(features.get("schema_types") or [])
    c6 = (
        1
        if features.get("crawl_readable") and body_text_length >= MIN_BODY_TEXT_LENGTH
        else 0
    )
    c9a = (
        10
        if features.get("has_h1")
        and (features.get("has_main") or features.get("has_article"))
        else (
            7
            if (
                features.get("has_h1")
                or features.get("has_main")
                or features.get("has_article")
            )
            else 3
        )
    )
    c9b = min(10, 4 + len(schema_types) * 2) if schema_types else 0

    failed_gates: list[str] = []
    if c6 <= 0:
        failed_gates.append("c6")
    if c9a < 5:
        failed_gates.append("c9a")
    if c9b < 5:
        failed_gates.append("c9b")

    return {
        "c6": c6,
        "c9a": c9a,
        "c9b": c9b,
        "gate_pass": c6 > 0 and c9a >= 5 and c9b >= 5,
        "failed_gates": failed_gates,
    }


def _page_confidence_summary(
    page: DiscoveredPage, features: dict[str, Any]
) -> dict[str, Any]:
    score = 34.0
    findings: list[str] = []
    recommendations: list[str] = []
    fetch_failure_reason = str(features.get("fetch_failure_reason") or "").strip()
    body_text_length = int(features.get("body_text_length") or 0)
    dimension_scores = _build_dimension_scores(page, features)
    gate_scores = _build_gate_scores(features)

    if features.get("crawl_readable"):
        score += 20
        if body_text_length < MIN_BODY_TEXT_LENGTH:
            findings.append("页面可抓取，但默认机器路径下正文仍然偏薄。")
            recommendations.append(
                "让核心信息直接出现在默认 HTML 中，减少仅靠前端渲染才能看到的正文。"
            )
    else:
        if fetch_failure_reason:
            findings.append(f"页面未成功抓取，失败原因：{fetch_failure_reason}。")
        else:
            findings.append("页面未成功抓取，当前只能基于 URL 结构做弱判断。")
        recommendations.append(
            "检查该页面的可访问性、重定向链、返回状态和默认抓取路径可读性。"
        )

    if page.url.startswith("https://"):
        score += 6
    else:
        findings.append("页面仍未使用 HTTPS。")
        recommendations.append("优先统一到 HTTPS，减少平台抓取与引用风险。")

    if features.get("has_h1"):
        score += 10
    else:
        findings.append("缺少明确 H1。")
        recommendations.append("为核心页面补充唯一 H1，明确页面主主题。")

    if features.get("has_main") or features.get("has_article"):
        score += 8
    else:
        findings.append("缺少 main/article 等主体语义区域。")
        recommendations.append("补充 main/article 等语义结构，降低页面正文抽取歧义。")

    schema_types = list(features.get("schema_types") or [])
    if schema_types:
        score += min(10, 4 + len(schema_types) * 2)
    else:
        findings.append("暂未发现 Schema.org 结构化数据。")
        recommendations.append(
            "为核心页面补充 Organization、Product、FAQPage 等结构化标记。"
        )

    if features.get("published_at"):
        score += 5

    if page.page_type in {"homepage", "product", "solution", "pricing", "docs", "faq"}:
        score += 4

    if page.depth <= 1:
        score += 3

    score = round(max(0.0, min(100.0, score)), 1)
    if score >= 78:
        page_status = "strong"
    elif score >= 60:
        page_status = "watch"
    else:
        page_status = "risk"

    return {
        "url": page.url,
        "page_type": page.page_type,
        "page_label": page.label,
        "depth": page.depth,
        "source_hint": page.source_hint,
        "http_status": features.get("http_status"),
        "crawl_readable": bool(features.get("crawl_readable")),
        "fetch_failure_reason": fetch_failure_reason,
        "title": features.get("fetched_title") or page.label,
        "has_h1": bool(features.get("has_h1")),
        "h1_count": int(features.get("h1_count") or 0),
        "h2_count": int(features.get("h2_count") or 0),
        "has_main": bool(features.get("has_main")),
        "has_article": bool(features.get("has_article")),
        "body_text_length": int(features.get("body_text_length") or 0),
        "script_count": int(features.get("script_count") or 0),
        "schema_types": schema_types,
        "published_at": features.get("published_at"),
        "dimension_scores": dimension_scores,
        "gate_scores": gate_scores,
        "confidence_score": score,
        "page_status": page_status,
        "findings": findings[:3],
        "recommendations": recommendations[:3],
    }


def _resolve_scan_quality_status(
    evaluated_count: int,
    discovered_count: int,
    readable_count: int,
) -> str:
    coverage_rate = readable_count / discovered_count if discovered_count else 0.0
    if evaluated_count >= 4 and readable_count >= 3 and coverage_rate >= 0.6:
        return "healthy"
    if evaluated_count >= 2 and readable_count >= 1:
        return "degraded"
    return "insufficient"


def _build_findings(
    page_summaries: list[dict[str, Any]],
    scan_quality_status: str,
    crawl_governance_summary: dict[str, Any] | None = None,
) -> list[str]:
    findings: list[str] = []
    unreadable = [page for page in page_summaries if not page.get("crawl_readable")]
    missing_h1 = [
        page
        for page in page_summaries
        if page.get("crawl_readable") and not page.get("has_h1")
    ]
    missing_schema = [
        page
        for page in page_summaries
        if page.get("crawl_readable") and not (page.get("schema_types") or [])
    ]
    thin_body_pages = [
        page
        for page in page_summaries
        if page.get("crawl_readable")
        and int(page.get("body_text_length") or 0) < MIN_BODY_TEXT_LENGTH
    ]

    if scan_quality_status == "insufficient":
        findings.append(
            "当前覆盖样本不足，报告结论应被视为方向性线索而不是完整官网结论。"
        )
    elif scan_quality_status == "degraded":
        findings.append(
            "本轮扫描只拿到部分核心页面，整体结论可用，但仍需补齐更多页面后再做定稿。"
        )

    if unreadable:
        findings.append(
            f"当前有 {len(unreadable)} 个核心页面未成功抓取，包括 {_format_page_names(unreadable)}。"
        )
    if missing_h1:
        findings.append(
            f"当前有 {len(missing_h1)} 个已抓取页面缺少明确主标题，包括 {_format_page_names(missing_h1)}。"
        )
    if missing_schema:
        findings.append(
            f"当前有 {len(missing_schema)} 个已抓取页面没有结构化标记，包括 {_format_page_names(missing_schema)}。"
        )
    if thin_body_pages:
        findings.append(
            f"当前有 {len(thin_body_pages)} 个已抓取页面正文偏薄，包括 {_format_page_names(thin_body_pages)}。"
        )
    governance = crawl_governance_summary or {}
    if governance:
        blocked_key_page_count = int(governance.get("blocked_key_page_count") or 0)
        sitemap_present = bool(governance.get("sitemap_present"))
        robots_present = bool(governance.get("robots_present"))
        if blocked_key_page_count > 0:
            findings.append(
                f"robots.txt 当前封锁了 {blocked_key_page_count} 个关键页面，抓取治理已经开始直接影响核心内容进入机器视野。"
            )
        elif not sitemap_present and not robots_present:
            findings.append("站点目前缺少 sitemap 和 robots.txt，抓取治理信号偏弱。")
        elif not sitemap_present:
            findings.append("站点目前没有稳定暴露 sitemap，页面发现效率仍然偏弱。")
        elif not robots_present:
            findings.append("站点目前没有 robots.txt，抓取治理信号还不完整。")

    if not findings:
        findings.append(
            "首页和核心一二级页面的基础结构信号整体稳定，可作为后续深度评估的良好起点。"
        )
    return findings[:4]


def _build_actions(
    page_summaries: list[dict[str, Any]],
    scan_quality_status: str,
    crawl_governance_summary: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    unreadable = [page for page in page_summaries if not page.get("crawl_readable")]
    missing_h1 = [
        page
        for page in page_summaries
        if page.get("crawl_readable") and not page.get("has_h1")
    ]
    missing_schema = [
        page
        for page in page_summaries
        if page.get("crawl_readable") and not (page.get("schema_types") or [])
    ]
    thin_body_pages = [
        page
        for page in page_summaries
        if page.get("crawl_readable")
        and int(page.get("body_text_length") or 0) < MIN_BODY_TEXT_LENGTH
    ]
    stale_time_pages = [
        page
        for page in page_summaries
        if page.get("crawl_readable") and not page.get("published_at")
    ]
    governance = crawl_governance_summary or {}
    blocked_key_page_count = int(governance.get("blocked_key_page_count") or 0)
    sitemap_present = bool(governance.get("sitemap_present"))
    robots_present = bool(governance.get("robots_present"))

    if scan_quality_status != "healthy" or unreadable:
        actions.append(
            {
                "priority": "P0",
                "title": "先修抓取失败页面",
                "summary": "先把没有稳定抓回的核心页面修到默认抓取方式可用，否则后面的内容优化都落不到机器视野里。",
            }
        )
    if missing_h1 or missing_schema:
        actions.append(
            {
                "priority": "P0",
                "title": "先修页面结构和 Schema 标记",
                "summary": "先把低分页的 H1、H2、main/article 和 Schema 标记补齐，让机器先看懂这页的结构和身份。",
            }
        )
    if thin_body_pages:
        actions.append(
            {
                "priority": "P0",
                "title": "先补关键页面的正文与可读性",
                "summary": "先把首页、产品页和低分专题页的关键信息写进源码，减少只靠前端渲染后才出现的正文。",
            }
        )
    if stale_time_pages:
        actions.append(
            {
                "priority": "P1",
                "title": "补齐关键页面的时间信息",
                "summary": "为新闻页、内容页和活动页直接暴露发布时间或更新时间，减少机器对信息时效的误判。",
            }
        )
    if blocked_key_page_count > 0 or not sitemap_present or not robots_present:
        actions.append(
            {
                "priority": "P1",
                "title": "补齐抓取治理",
                "summary": "补上 sitemap、robots.txt，并避免对首页、产品页、FAQ/文档页等关键页面过度封锁，让机器先稳定发现再稳定理解。",
            }
        )
    if not actions:
        actions.append(
            {
                "priority": "P1",
                "title": "继续扩充高价值场景页",
                "summary": "当前基础结构稳定，下一阶段应围绕 FAQ、产品对比和关键场景页补更强的可引用语料。",
            }
        )
    return actions[:4]


def _build_dimension_summary(
    page_summaries: list[dict[str, Any]],
    crawl_governance_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    totals: dict[str, dict[str, Any]] = {}
    gate_failures = Counter()
    for page in page_summaries:
        for dimension in page.get("dimension_scores") or []:
            dimension_id = str(dimension.get("id") or "unknown")
            entry = totals.setdefault(
                dimension_id,
                {
                    "id": dimension_id,
                    "label": dimension.get("label") or dimension_id,
                    "score_sum": 0.0,
                    "count": 0,
                },
            )
            entry["score_sum"] += float(dimension.get("score") or 0.0)
            entry["count"] += 1
        for gate in (page.get("gate_scores") or {}).get("failed_gates") or []:
            gate_failures[str(gate)] += 1

    dimensions: list[dict[str, Any]] = []
    for item in totals.values():
        count = int(item["count"] or 0)
        average_score = round(float(item["score_sum"]) / count, 1) if count else 0.0
        dimensions.append(
            {
                "id": item["id"],
                "label": item["label"],
                "average_score": average_score,
                "risk_level": (
                    "high"
                    if average_score < 5
                    else "watch" if average_score < 7.5 else "healthy"
                ),
            }
        )

    if crawl_governance_summary:
        governance_score = round(float(crawl_governance_summary.get("score") or 0.0), 1)
        dimensions.append(
            {
                "id": str(crawl_governance_summary.get("id") or "crawl_governance"),
                "label": str(crawl_governance_summary.get("label") or "抓取治理"),
                "average_score": governance_score,
                "risk_level": (
                    "high"
                    if governance_score < 5
                    else "watch" if governance_score < 7.5 else "healthy"
                ),
            }
        )

    dimensions.sort(key=lambda item: (item["average_score"], item["id"]))
    return {
        "dimensions": dimensions,
        "top_risk_dimensions": dimensions[:3],
        "gate_failure_summary": {
            "c6": gate_failures.get("c6", 0),
            "c9a": gate_failures.get("c9a", 0),
            "c9b": gate_failures.get("c9b", 0),
        },
    }


def _scan_quality_label(scan_quality_status: str) -> str:
    if scan_quality_status == "healthy":
        return "覆盖稳定"
    if scan_quality_status == "degraded":
        return "覆盖有限"
    if scan_quality_status == "insufficient":
        return "样本不足"
    return "待确认"


def _page_role_label(page_type: str | None) -> str:
    mapping = {
        "homepage": "首页",
        "product": "产品/交易页",
        "solution": "解决方案页",
        "pricing": "价格页",
        "docs": "文档页",
        "faq": "FAQ 页",
        "about": "品牌介绍页",
        "news": "新闻页",
        "generic": "通用页",
    }
    return mapping.get(str(page_type or "generic"), "通用页")


def _page_status_label(page_status: str | None) -> str:
    mapping = {
        "strong": "较稳",
        "watch": "需处理",
        "risk": "高风险",
    }
    return mapping.get(str(page_status or "watch"), "需处理")


def _looks_like_human_page_title(title: str) -> bool:
    normalized = title.strip()
    if not normalized:
        return False
    if re.search(r"[\u4e00-\u9fff]", normalized):
        return len(normalized) >= 2
    return len(normalized) > 3


def _page_label_is_opaque(page: dict[str, Any]) -> bool:
    title = _collapse_text(str(page.get("title") or "")).strip()
    if title and _looks_like_human_page_title(title):
        return False

    url = str(page.get("url") or "").strip()
    path = urlparse(url).path.strip("/")
    if not path:
        return False

    base = path.split("/")[-1].strip().lower()
    base = re.sub(r"\.(html?|php|aspx?)$", "", base)
    page_role = _page_role_label(page.get("page_type"))
    if page_role not in {"首页", "通用页"}:
        return False
    return base in {"index", "indexhtml", "detail", "productdetail", "xssite", "list"} or bool(
        re.fullmatch(r"[a-z0-9_-]{1,10}", base)
    )


def _page_anchor_label(page: dict[str, Any]) -> str:
    title = _collapse_text(str(page.get("title") or "")).strip()
    page_label = _collapse_text(
        str(page.get("page_label") or page.get("label") or "")
    ).strip()
    url = str(page.get("url") or "").strip()
    page_role = _page_role_label(page.get("page_type"))
    path = urlparse(url).path.strip("/")
    path_base = path.split("/")[-1].replace("-", " ").replace("_", " ").strip() if path else ""
    path_base = re.sub(r"\.(html?|php|aspx?)$", "", path_base, flags=re.IGNORECASE)

    if title and title not in {"页面", "内部页"} and _looks_like_human_page_title(title):
        base = title
    elif page_label and page_label not in {"页面", "内部页"}:
        base = page_label
    elif path:
        base = path_base
        if len(base) <= 3 and page_role not in {"首页", "通用页"}:
            base = page_role
        elif not base:
            base = page_role
    elif page_role == "首页":
        base = "首页"
    else:
        base = page_role

    if page_role == "首页" and "首页" not in base:
        return f"{base}（首页）"
    if page_role not in {"首页", "通用页"} and page_role not in base:
        return f"{base}（{page_role}）"
    return base


def _format_page_examples(pages: list[dict[str, Any]], limit: int = 4) -> str:
    if not pages:
        return "当前没有明确页面样本。"
    labels = []
    for page in pages[:limit]:
        score = float(page.get("confidence_score") or 0.0)
        labels.append(f"{_page_anchor_label(page)}（{score:.1f} 分）")
    if len(pages) > limit:
        return f"{'、'.join(labels)} 等 {len(pages)} 个页面"
    return "、".join(labels)


def _humanize_dimension_label(label: str | None) -> str:
    mapping = {
        "结构化数据": "页面身份表达",
        "时效信号": "时间信息",
        "语义结构": "页面结构",
        "正文厚度": "正文信息",
        "机器可读性": "源码可读性",
        "主题清晰度": "主题表达",
        "可抓取性": "抓取稳定性",
        "传输安全": "HTTPS",
        "抓取治理": "抓取治理",
    }
    normalized = str(label or "").strip()
    return mapping.get(normalized, normalized or "页面表达")


def _page_issue_list(page: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not page.get("crawl_readable"):
        reason = str(page.get("fetch_failure_reason") or "").strip()
        if reason:
            issues.append(f"默认抓取方式下还没有成功拿到这个页面，当前返回是 {reason}。")
        else:
            issues.append("默认抓取方式下还没有成功拿到这个页面。")
        return issues

    if not page.get("has_h1"):
        issues.append("主标题不明确，机器不容易马上判断这页在讲什么。")
    if not (page.get("schema_types") or []):
        issues.append("页面身份表达不够清楚，机器不容易直接识别这是品牌页、产品页还是新闻页。")
    if int(page.get("body_text_length") or 0) < MIN_BODY_TEXT_LENGTH:
        issues.append("正文信息偏薄，抓到页面后可直接引用的信息不够。")
    if not (page.get("has_main") or page.get("has_article")):
        issues.append("页面主体区域不够清楚，重要内容没有被很好地包进主要内容区域。")

    findings = [
        _humanize_report_text(str(item).strip())
        for item in list(page.get("findings") or [])
        if str(item).strip()
    ]
    for finding in findings:
        if len(issues) >= 3:
            break
        if finding not in issues:
            issues.append(finding)

    return issues[:3]


def _page_business_reason(page: dict[str, Any]) -> str:
    page_type = str(page.get("page_type") or "")
    mapping = {
        "homepage": "这是官网入口页，机器通常会先读这页；这页表达不清楚，会直接影响整站第一印象。",
        "product": "这是产品页，直接影响机器能不能正确理解产品卖点、规格和适用场景。",
        "solution": "这是解决方案页，直接影响机器能不能把品牌和具体使用场景连起来。",
        "pricing": "这是价格页，直接影响机器能不能稳定提取价格和购买门槛信息。",
        "docs": "这是文档页，直接影响机器能不能把品牌和可操作信息关联起来。",
        "faq": "这是问答页，直接影响机器能不能快速抓到常见问题的标准答案。",
        "about": "这是品牌介绍页，直接影响机器能不能判断品牌身份和公司背景。",
        "news": "这是新闻页，直接影响机器能不能提取最新动态和时间信息。",
        "blog": "这是内容页，直接影响机器能不能把品牌观点和主题内容关联起来。",
        "contact": "这是联系页，直接影响机器能不能抓到咨询和转化入口。",
    }
    return mapping.get(
        page_type,
        "这页已经进入本轮重点页面，如果它表达不清楚，品牌在这里的信息就更容易被误读或忽略。",
    )


def _format_page_names(pages: list[dict[str, Any]], limit: int = 3) -> str:
    if not pages:
        return "当前没有明确页面样本。"
    labels = [_page_anchor_label(page) for page in pages[:limit]]
    if len(pages) > limit:
        return f"{'、'.join(labels)} 等 {len(pages)} 个页面"
    return "、".join(labels)


def _dedupe_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in pages:
        key = str(page.get("url") or _page_anchor_label(page)).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(page)
    return ordered


def _select_pages_to_fix(page_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _select_priority_pages(page_summaries)


def _select_score_drag_pages(
    page_summaries: list[dict[str, Any]],
    *,
    overall_score: float,
    limit: int = 5,
) -> list[dict[str, Any]]:
    below_average = [
        page
        for page in page_summaries
        if float(page.get("confidence_score") or 0.0) < overall_score
    ]
    pool = below_average or page_summaries

    def _priority_key(page: dict[str, Any]) -> tuple[float, int, int]:
        score = float(page.get("confidence_score") or 0.0)
        depth = int(page.get("depth") or 0)
        importance_bonus = 0 if str(page.get("page_type") or "") in {
            "homepage",
            "product",
            "solution",
            "pricing",
            "faq",
            "docs",
            "about",
            "news",
        } else 1
        return (score, importance_bonus, depth)

    return sorted(pool, key=_priority_key)[:limit]


def _summarize_score_drag_pages(
    page_summaries: list[dict[str, Any]],
    *,
    overall_score: float,
    limit: int = 3,
) -> str:
    pages = _select_score_drag_pages(
        page_summaries,
        overall_score=overall_score,
        limit=limit,
    )
    if not pages:
        return "当前没有明显拖低平均分的页面。"
    return "、".join(
        f"{_page_anchor_label(page)}（**{float(page.get('confidence_score') or 0):.1f} / 100**）"
        for page in pages
    )


def _summarize_repeating_penalty_dimensions(
    page_summaries: list[dict[str, Any]],
    *,
    overall_score: float,
    limit: int = 3,
) -> str:
    focus_pages = _select_score_drag_pages(
        page_summaries,
        overall_score=overall_score,
        limit=5,
    )
    totals: dict[str, dict[str, Any]] = {}
    for page in focus_pages:
        for dimension in _build_page_penalty_items(page, limit=5):
            dimension_id = str(dimension.get("code") or "")
            entry = totals.setdefault(
                dimension_id,
                {
                    "label": str(dimension.get("label") or dimension_id),
                    "max_score": int(dimension.get("max_score") or 10),
                    "score_sum": 0.0,
                    "count": 0,
                },
            )
            entry["score_sum"] += float(dimension.get("score") or 0.0)
            entry["count"] += 1
    ranked: list[tuple[str, float]] = []
    for item in totals.values():
        count = int(item.get("count") or 0)
        if count <= 0:
            continue
        average_score = round(float(item["score_sum"]) / count, 1)
        ranked.append((str(item["label"]), average_score, int(item["max_score"] or 10)))
    ranked.sort(key=lambda item: item[1] / max(item[2], 1))
    if not ranked:
        return "当前没有明显重复的扣分项。"
    return "、".join(
        f"{label}（**{score:.1f} / {max_score}**）"
        for label, score, max_score in ranked[:limit]
    )


def _aice_dimension_label(code: str) -> str:
    mapping = {
        "C6": "C6: Coverage（覆盖度）",
        "C9a": "C9a: Semantic Tagging（语义标签）",
        "C9b": "C9b: Schema Usage（结构化数据）",
        "C8": "C8: Timeliness（时效性）",
        "C5": "C5: Clarity（结构清晰度）",
    }
    return mapping.get(code, code)


def _build_page_penalty_items(
    page: dict[str, Any],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def _append_item(
        code: str,
        score: float,
        max_score: int,
        reason: str,
        fix: str,
    ) -> None:
        items.append(
            {
                "code": code,
                "label": _aice_dimension_label(code),
                "score": round(float(score), 1),
                "max_score": max_score,
                "reason": _humanize_report_text(reason),
                "fix": _humanize_report_text(fix),
            }
        )

    crawl_readable = bool(page.get("crawl_readable"))
    has_h1 = bool(page.get("has_h1"))
    has_semantic_root = bool(page.get("has_main") or page.get("has_article"))
    h2_count = int(page.get("h2_count") or 0)
    schema_types = list(page.get("schema_types") or [])
    body_text_length = int(page.get("body_text_length") or 0)
    published_at = str(page.get("published_at") or "").strip()
    page_type = str(page.get("page_type") or "")
    fetch_failure_reason = str(page.get("fetch_failure_reason") or "").strip()

    if not crawl_readable:
        _append_item(
            "C6",
            0,
            25,
            (
                f"页面默认抓取失败，当前返回为 {fetch_failure_reason}。"
                if fetch_failure_reason
                else "页面默认抓取失败，正文没有被稳定拿到。"
            ),
            "先检查返回状态、重定向链、鉴权限制和默认抓取路径，确保页面源码可直接被抓取。",
        )

    structural_issues: list[str] = []
    if not has_h1:
        structural_issues.append("缺少 H1")
    if h2_count <= 0:
        structural_issues.append("H2 层级不明显")
    if not has_semantic_root:
        structural_issues.append("缺少 main/article")
    if structural_issues:
        c9a_score = 10
        if not has_h1 or not has_semantic_root:
            c9a_score -= 5
        if h2_count <= 0:
            c9a_score -= 2
        _append_item(
            "C9a",
            max(0, c9a_score),
            10,
            f"{'；'.join(structural_issues)}，标准化页面结构不完整。",
            "补齐唯一 H1、清晰的 H2 层级，并用 main/article 包住主体内容。",
        )

    if not schema_types:
        _append_item(
            "C9b",
            5,
            10,
            "未发现 Schema.org 标记，页面 Schema 信息缺失，机器无法直接识别页面身份。",
            "按页面职责补 Product、Organization、NewsArticle、FAQPage 等 Schema 标记。",
        )

    evergreen_types = {"homepage", "about", "product", "solution", "pricing", "docs", "faq"}
    if not published_at and page_type not in evergreen_types:
        _append_item(
            "C8",
            4 if page_type == "news" else 8,
            15,
            "页面没有明确时间信息，机器很难判断这是不是最新内容。",
            "在页面源码里直接暴露发布时间或更新时间，不要只在视觉层显示。",
        )

    if body_text_length < MIN_BODY_TEXT_LENGTH:
        _append_item(
            "C5",
            2 if body_text_length < max(120, MIN_BODY_TEXT_LENGTH // 2) else 3,
            5,
            "页面源码里可直接读取的正文偏薄，重点信息不够集中。",
            "补充首屏正文和关键说明，让核心信息直接出现在页面源码里。",
        )

    ranked = sorted(
        items,
        key=lambda item: (float(item["score"]) / max(int(item["max_score"]), 1), float(item["score"])),
    )
    return ranked[:limit]


def _humanize_report_text(text: str | None) -> str:
    normalized = str(text or "").strip()
    replacements = (
        ("Schema.org 标记", "结构化标记"),
        ("Schema.org", "结构化标记"),
        ("默认 HTML", "页面源码"),
        ("默认机器路径", "默认抓取方式"),
        ("默认机器抓取路径", "默认抓取方式"),
    )
    for source, target in replacements:
        normalized = normalized.replace(source, target)
    cleanup_pairs = (
        ("未发现 结构化标记", "未发现结构化标记"),
        ("页面源码 中", "页面源码中"),
    )
    for source, target in cleanup_pairs:
        normalized = normalized.replace(source, target)
    return normalized


def _select_priority_pages(
    page_summaries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    def _priority_key(page: dict[str, Any]) -> tuple[int, float, int]:
        status_rank = {
            "risk": 0,
            "watch": 1,
            "strong": 2,
        }.get(str(page.get("page_status") or "watch"), 1)
        unreadable_penalty = 0 if not page.get("crawl_readable") else 1
        label_penalty = 1 if _page_label_is_opaque(page) else 0
        score = float(page.get("confidence_score") or 0.0)
        depth = int(page.get("depth") or 0)
        return (unreadable_penalty, status_rank, label_penalty, score + depth)

    ordered = sorted(page_summaries, key=_priority_key)
    return ordered[:5]


def _build_action_plan(
    *,
    action: dict[str, str],
    page_summaries: list[dict[str, Any]],
    coverage_summary: dict[str, Any],
    crawl_governance_summary: dict[str, Any] | None = None,
) -> dict[str, str]:
    title = str(action.get("title") or "").strip()
    readable_pages = [page for page in page_summaries if page.get("crawl_readable")]
    unreadable_pages = [
        page for page in page_summaries if not page.get("crawl_readable")
    ]
    missing_h1 = [page for page in readable_pages if not page.get("has_h1")]
    missing_schema = [
        page for page in readable_pages if not (page.get("schema_types") or [])
    ]
    thin_body_pages = [
        page
        for page in readable_pages
        if int(page.get("body_text_length") or 0) < MIN_BODY_TEXT_LENGTH
    ]
    stale_time_pages = [page for page in readable_pages if not page.get("published_at")]
    overall_score = (
        round(
            sum(float(page.get("confidence_score") or 0.0) for page in page_summaries)
            / len(page_summaries),
            1,
        )
        if page_summaries
        else 0.0
    )

    if title == "先修抓取失败页面":
        focus_pages = _select_score_drag_pages(
            unreadable_pages or page_summaries,
            overall_score=overall_score,
            limit=5,
        )
        return {
            "targets": _format_page_names(focus_pages),
            "fact": (
                f"当前有 {len(unreadable_pages)} 个核心页面未成功抓取，"
                f"其中最该先看的页面是 {_format_page_names(focus_pages)}；本轮实际抓回 {int(coverage_summary.get('fetched_page_count') or 0)} 个页面。"
            ),
            "action": "先检查返回状态、重定向链、鉴权限制和默认抓取路径，保证这些页面能直接被稳定拿到。",
            "metric": "下次扫描时，抓取失败页面数下降，覆盖页面数和覆盖率保持稳定。",
        }
    if title == "先修页面结构和 Schema 标记":
        targets = _dedupe_pages(missing_h1 + missing_schema)
        focus_pages = _select_score_drag_pages(
            targets or page_summaries,
            overall_score=overall_score,
            limit=5,
        )
        return {
            "targets": _format_page_names(focus_pages),
            "fact": (
                f"当前低分页里，缺主标题的页面有 {len(missing_h1)} 个，缺结构化标记的页面有 {len(missing_schema)} 个，"
                f"其中最该先修的是 {_format_page_names(focus_pages)}。"
            ),
            "action": "优先给这些页补唯一 H1、清晰的 H2 层级和 main/article 主体标签，并按页面职责补 Schema 标记。",
            "metric": "下次扫描时，这些页面的 C9a 与 C9b 得分同步抬升，单页总分不再停留在低位。",
        }
    if title == "先补关键页面的正文与可读性":
        focus_pages = _select_score_drag_pages(
            thin_body_pages or page_summaries,
            overall_score=overall_score,
            limit=5,
        )
        return {
            "targets": _format_page_names(focus_pages),
            "fact": f"当前有 {len(thin_body_pages)} 个页面正文偏薄，其中最直接影响平均分的是 {_format_page_names(focus_pages)}。",
            "action": "先补首页、产品页和低分专题页的正文信息，让关键卖点、说明和可引用文本直接出现在页面源码里。",
            "metric": "下次扫描时，正文信息和源码可读性分数抬升，页面的低分项不再集中在正文偏薄。",
        }
    if title == "补齐关键页面的时间信息":
        focus_pages = _select_score_drag_pages(
            stale_time_pages or page_summaries,
            overall_score=overall_score,
            limit=5,
        )
        return {
            "targets": _format_page_names(focus_pages),
            "fact": f"当前有 {len(stale_time_pages)} 个已抓取页面没有明确时间信息，其中最该优先补的是 {_format_page_names(focus_pages)}。",
            "action": "先给新闻页、活动页和内容页补发布时间或更新时间，并把时间直接暴露在页面源码里。",
            "metric": "下次扫描时，时间信息分数抬升，机器能更稳定判断这些页面是不是最新内容。",
        }
    if title == "补齐抓取治理":
        governance = crawl_governance_summary or {}
        blocked_key_page_count = int(governance.get("blocked_key_page_count") or 0)
        sitemap_present = bool(governance.get("sitemap_present"))
        robots_present = bool(governance.get("robots_present"))
        if blocked_key_page_count > 0:
            fact = f"当前 robots.txt 封锁了 {blocked_key_page_count} 个关键页面，抓取治理已经开始直接影响核心页面进入机器视野。"
        elif not sitemap_present and not robots_present:
            fact = (
                "当前站点同时缺少 sitemap 和 robots.txt，页面发现和抓取治理信号都偏弱。"
            )
        elif not sitemap_present:
            fact = "当前站点没有稳定暴露 sitemap，页面发现效率和更新提示都偏弱。"
        else:
            fact = "当前站点没有 robots.txt，抓取治理信号还不完整。"
        return {
            "targets": "首页、产品页、FAQ/文档页等关键入口页",
            "fact": fact,
            "action": "补上 sitemap 与 robots.txt，并复核 robots.txt 是否对首页、产品页、FAQ/文档页等关键页面存在误伤或过度封锁。",
            "metric": "下次扫描时，抓取治理维度评分抬升；关键页面不再被 robots.txt 封锁，且 sitemap 可以被稳定发现。",
        }
    return {
        "targets": _format_page_names(_select_priority_pages(page_summaries)),
        "fact": "当前核心页面已经能形成初步判断，但重点场景页还不够完整。",
        "action": str(action.get("summary") or "").strip()
        or "继续补齐高价值页面的内容表达。",
        "metric": "下次扫描时，新增页面被纳入评估，且重点页面评分不下降。",
    }


def _build_executive_summary(
    *,
    overall_score: float,
    scan_quality_status: str,
    findings: list[str],
    actions: list[dict[str, str]],
) -> str:
    if scan_quality_status == "insufficient":
        base = (
            "这次扫描拿到的样本还不够，先把官网基础可抓取问题修稳，再看更细的内容优化。"
        )
    elif overall_score >= 80:
        base = "官网已经具备较稳定的 AI 读取基础，下一步重点是把关键页面的结构和引用支撑再做扎实。"
    elif overall_score >= 65:
        base = "官网已经能被抓到，也能形成初步判断，但低分主要集中在页面结构、Schema 标记和正文清晰度。"
    else:
        base = "官网当前还没有达到稳定可读的状态，先把核心页面结构和正文做扎实，再谈内容扩展。"

    finding = _humanize_report_text(findings[0] if findings else "")
    action_title = str(actions[0].get("title") or "").strip() if actions else ""
    if finding and action_title:
        return f"{base} 当前最直接的问题是：{finding} 优先处理：{action_title}。"
    if finding:
        return f"{base} 当前最直接的问题是：{finding}"
    if action_title:
        return f"{base} 优先处理：{action_title}。"
    return base


def _build_preview_description(
    *,
    page_summaries: list[dict[str, Any]],
) -> str:
    if not page_summaries:
        return "本轮没有发现需要优先处理的官网页面。"
    overall_score = round(
        sum(float(page.get("confidence_score") or 0.0) for page in page_summaries)
        / len(page_summaries),
        1,
    )
    pages_to_fix = _select_score_drag_pages(
        page_summaries,
        overall_score=overall_score,
        limit=3,
    )
    if not pages_to_fix:
        return "本轮没有发现明显拉低平均分的官网页面。"
    labels = "、".join(
        f"{_page_anchor_label(page)}（{float(page.get('confidence_score') or 0):.1f} / 100）"
        for page in pages_to_fix
    )
    repeated_penalties = _summarize_repeating_penalty_dimensions(
        page_summaries,
        overall_score=overall_score,
        limit=3,
    ).replace("**", "")
    return (
        f"显著拉低平均分的页面主要是：{labels}。"
        f"这些页面反复出现的扣分项主要集中在 {repeated_penalties}。"
    )


def _build_report_markdown(
    *,
    headline: str,
    root_url: str,
    root_domain: str,
    overall_score: float,
    scan_quality_status: str,
    coverage_summary: dict[str, Any],
    findings: list[str],
    actions: list[dict[str, str]],
    page_summaries: list[dict[str, Any]],
    dimension_summary: dict[str, Any],
    crawl_governance_summary: dict[str, Any] | None = None,
) -> str:
    readable_pages = int(coverage_summary.get("fetched_page_count") or 0)
    evaluated_pages = int(
        coverage_summary.get("evaluated_page_count")
        or coverage_summary.get("eligible_url_count")
        or 0
    )
    eligible_pages = int(coverage_summary.get("eligible_url_count") or evaluated_pages)
    page_budget = int(
        coverage_summary.get("page_budget") or evaluated_pages or DEFAULT_MAX_PAGES
    )
    executive_summary = _build_executive_summary(
        overall_score=overall_score,
        scan_quality_status=scan_quality_status,
        findings=findings,
        actions=actions,
    )
    pages_to_fix = _select_score_drag_pages(
        page_summaries,
        overall_score=overall_score,
        limit=5,
    )
    if not pages_to_fix:
        pages_to_fix = _select_pages_to_fix(page_summaries)
    repeated_penalties = _summarize_repeating_penalty_dimensions(
        page_summaries,
        overall_score=overall_score,
        limit=3,
    )
    governance = crawl_governance_summary or {}
    blocked_key_page_count = int(governance.get("blocked_key_page_count") or 0)
    governance_notes: list[str] = []
    if governance:
        if blocked_key_page_count > 0:
            governance_notes.append(
                f"robots.txt 当前封锁了 **{blocked_key_page_count}** 个关键页面。"
            )
        elif not governance.get("sitemap_present") and not governance.get("robots_present"):
            governance_notes.append("站点目前同时缺少 sitemap 和 robots.txt。")
        elif not governance.get("sitemap_present"):
            governance_notes.append("站点目前还没有稳定暴露 sitemap。")
        elif not governance.get("robots_present"):
            governance_notes.append("站点目前还没有 robots.txt。")
    needs_boundary_note = (
        scan_quality_status != "healthy"
        or readable_pages < evaluated_pages
        or eligible_pages > page_budget
    )

    focus_page_summary = "、".join(_page_anchor_label(page) for page in pages_to_fix[:3])
    conclusion_text = f"官网当前的 **AI 友好度为 {overall_score:.1f} / 100**。{executive_summary}"
    if focus_page_summary:
        conclusion_text = (
            f"官网当前的 **AI 友好度为 {overall_score:.1f} / 100**。"
            f" 官网已经能被抓到，也能形成初步判断；当前最值得先看的页面是 {focus_page_summary}，"
            f"这些页面反复出现的扣分项主要集中在 {repeated_penalties}。"
        )
    lines: list[str] = ["## 结论", ""]
    lines.append(conclusion_text)
    lines.append("")
    lines.append("## 为什么会得到这个判断")
    lines.append("")
    lines.append(f"**当前平均分：{overall_score:.1f} / 100**")
    lines.append("")
    lines.append("*评分口径：站点总分 = 本轮纳入评估页面的单页分数平均值。*")
    lines.append("")
    lines.append("*分数说明：九个维度先在单页层面扣分，再统一换算到 100 分制。*")
    lines.append("")
    if eligible_pages > page_budget:
        lines.append(
            f"- 本次共发现 **{eligible_pages}** 个正式内容页；由于超过本轮上限，只评估了其中 **{evaluated_pages}** 个，成功抓回 **{readable_pages}** 个。"
        )
    else:
        lines.append(
            f"- 本次共发现 **{eligible_pages}** 个正式内容页，这 **{evaluated_pages}** 个页面已全部纳入评估，其中 **{readable_pages}** 个成功抓回。"
        )
    if pages_to_fix:
        lines.append(
            f"- 显著拉低平均分的页面：{_summarize_score_drag_pages(page_summaries, overall_score=overall_score, limit=4)}。"
        )
    lines.append(f"- 反复出现的扣分项：{repeated_penalties}。")
    for note in governance_notes:
        lines.append(f"- 抓取治理提醒：{note}")
    lines.append("")
    lines.append("## 直接证据：显著拉低平均分的页面")
    lines.append("")
    lines.append(
        "下面这些页面，是这次判断最直接的证据。每个页面都按“分数 -> 扣分项 -> 为什么扣分 -> 怎么补”的顺序展开。"
    )
    lines.append("")

    for page in pages_to_fix:
        page_score = float(page.get("confidence_score") or 0.0)
        score_gap = round(max(overall_score - page_score, 0.0), 1)
        penalty_items = _build_page_penalty_items(page, limit=3)
        lines.append(
            f"### {_page_anchor_label(page)} · [页面链接]({page.get('url')})"
        )
        lines.append("")
        lines.append(f"- 页面分数：**{page_score:.1f} / 100**")
        if score_gap > 0:
            lines.append(f"- 拉低平均分幅度：比站点平均分低 **{score_gap:.1f}** 分")
        if penalty_items:
            lines.append("- 主要扣分项：")
            for item in penalty_items:
                lines.append(
                    f"  1. **{item['label']}**：**{float(item['score']):.1f} / {int(item['max_score'])}**"
                )
                lines.append(f"     - 为什么扣分：{item['reason']}")
                lines.append(f"     - 怎么填补：{item['fix']}")
        lines.append("")

    lines.append("## 下一步最高优先级解决的建议")
    lines.append("")
    grouped_actions: dict[str, list[dict[str, str]]] = {"P0": [], "P1": []}
    for action in actions:
        priority = str(action.get("priority") or "P1").upper()
        if priority not in grouped_actions:
            grouped_actions[priority] = []
        grouped_actions[priority].append(action)

    for priority in ("P0", "P1"):
        priority_actions = grouped_actions.get(priority) or []
        if not priority_actions:
            continue
        lines.append(f"### **{priority}**")
        lines.append("")
        for index, action in enumerate(priority_actions, start=1):
            plan = _build_action_plan(
                action=action,
                page_summaries=page_summaries,
                coverage_summary=coverage_summary,
                crawl_governance_summary=crawl_governance_summary,
            )
            lines.append(f"{index}. **{action.get('title', '未命名动作')}**")
            lines.append(f"   - **优先页面**：{_humanize_report_text(plan['targets'])}")
            lines.append(f"   - **当前问题**：{_humanize_report_text(plan['fact'])}")
            lines.append(f"   - **建议动作**：{_humanize_report_text(plan['action'])}")
            lines.append(f"   - **完成标志**：{_humanize_report_text(plan['metric'])}")
            lines.append("")

    if needs_boundary_note:
        lines.append("## 本次结果还需要注意")
        lines.append("")
        if scan_quality_status != "healthy":
            lines.append(
                f"- 当前样本状态：{_scan_quality_label(scan_quality_status)}。这份结果适合先排修复优先级，不适合直接当最终盖章结论。"
            )
        if readable_pages < evaluated_pages:
            lines.append(
                f"- 本轮纳入评估的页面里，有 **{evaluated_pages - readable_pages}** 个页面默认抓取方式没有成功拿到；这些页面会直接按风险处理。"
            )
        if eligible_pages > page_budget:
            lines.append(
                f"- 本次正式内容页总量超过单次上限，本轮只评估了前 **{page_budget}** 个优先页面。"
            )
        lines.append(
            "- 这份报告反映的是默认抓取方式下的官网可读性，不等于人工逐页审稿结论。"
        )

    lines.append("")
    lines.append("## 附录：本轮纳入评估的页面")
    lines.append("")
    lines.append("| 页面名称 | 页面类型 | AI友好度评分 | 页面链接 |")
    lines.append("| --- | --- | ---: | --- |")
    appendix_pages = sorted(
        page_summaries,
        key=lambda page: (
            float(page.get("confidence_score") or 0.0),
            _page_anchor_label(page),
        ),
    )
    for page in appendix_pages:
        lines.append(
            f"| {_page_anchor_label(page)} | {_page_role_label(page.get('page_type'))} | **{float(page.get('confidence_score') or 0.0):.1f} / 100** | [查看页面]({page.get('url')}) |"
        )

    return "\n".join(lines).strip()


async def build_site_confidence_report(
    *,
    root_url: str,
    scan_mode: str = DEFAULT_SCAN_MODE,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> dict[str, Any]:
    normalized_root = _normalize_root_url(root_url)
    normalized_max_pages = _normalize_scan_page_limit(max_pages)
    discovered_pages, discovery_summary = await discover_site_pages(
        normalized_root,
        max_pages=normalized_max_pages,
    )
    crawl_governance_summary = await _inspect_crawl_governance(
        root_url=str(discovery_summary.get("resolved_root_url") or normalized_root),
        selected_pages=discovered_pages,
        discovery_summary=discovery_summary,
    )
    semaphore = asyncio.Semaphore(PAGE_FETCH_CONCURRENCY)

    async def _evaluate_page(page: DiscoveredPage) -> dict[str, Any]:
        async with semaphore:
            features = await fetch_page_features(page.url)
        return _page_confidence_summary(page, features)

    page_summaries = list(
        await asyncio.gather(*(_evaluate_page(page) for page in discovered_pages))
    )

    readable_count = sum(1 for page in page_summaries if page.get("crawl_readable"))
    evaluated_count = len(page_summaries)
    discovered_count = int(
        discovery_summary.get("discovered_url_count") or evaluated_count
    )
    coverage_rate = (
        round(readable_count / discovered_count, 2) if discovered_count else 0.0
    )
    scan_quality_status = _resolve_scan_quality_status(
        evaluated_count=evaluated_count,
        discovered_count=discovered_count,
        readable_count=readable_count,
    )

    dashboard_score = (
        round(
            sum(float(page.get("confidence_score") or 0.0) for page in page_summaries)
            / len(page_summaries),
            1,
        )
        if page_summaries
        else 0.0
    )
    overall_score = dashboard_score

    coverage_summary = {
        "discovered_url_count": discovered_count,
        "candidate_url_count": int(
            discovery_summary.get("candidate_url_count") or discovered_count
        ),
        "eligible_url_count": int(
            discovery_summary.get("eligible_url_count") or discovered_count
        ),
        "page_budget": int(
            discovery_summary.get("max_pages_applied") or normalized_max_pages
        ),
        "fetched_page_count": readable_count,
        "evaluated_page_count": evaluated_count,
        "excluded_page_count": int(discovery_summary.get("excluded_url_count") or 0),
        "coverage_rate": coverage_rate,
        "excluded_reason_counts": dict(
            discovery_summary.get("excluded_reason_counts") or {}
        ),
    }
    dimension_summary = _build_dimension_summary(
        page_summaries,
        crawl_governance_summary=crawl_governance_summary,
    )
    findings = _build_findings(
        page_summaries,
        scan_quality_status,
        crawl_governance_summary=crawl_governance_summary,
    )
    actions = _build_actions(
        page_summaries,
        scan_quality_status,
        crawl_governance_summary=crawl_governance_summary,
    )
    root_domain = str(
        discovery_summary.get("root_domain") or _extract_domain(normalized_root)
    )
    headline = "官网 AI 友好度"
    report_markdown = _build_report_markdown(
        headline=headline,
        root_url=str(discovery_summary.get("resolved_root_url") or normalized_root),
        root_domain=root_domain,
        overall_score=overall_score,
        scan_quality_status=scan_quality_status,
        coverage_summary=coverage_summary,
        findings=findings,
        actions=actions,
        page_summaries=page_summaries,
        dimension_summary=dimension_summary,
        crawl_governance_summary=crawl_governance_summary,
    )
    executive_summary = _build_executive_summary(
        overall_score=overall_score,
        scan_quality_status=scan_quality_status,
        findings=findings,
        actions=actions,
    )
    preview_description = _build_preview_description(page_summaries=page_summaries)

    return {
        "report_kind": "site_confidence_report",
        "artifact_kind": "site_confidence_report",
        "headline": headline,
        "subtitle": "基于默认抓取方式的官网可读性评估。",
        "description": preview_description,
        "preview_description": preview_description,
        "brand_name": root_domain,
        "site_root_url": str(
            discovery_summary.get("resolved_root_url") or normalized_root
        ),
        "root_domain": root_domain,
        "scan_mode": scan_mode,
        "max_pages_requested": max_pages,
        "max_pages_applied": int(
            discovery_summary.get("max_pages_applied") or normalized_max_pages
        ),
        "hard_max_scan_pages": HARD_MAX_SCAN_PAGES,
        "scanner_runtime": "http_html_single_path",
        "updated_at": _now_iso(),
        "overall_score": overall_score,
        "dashboard_score": dashboard_score,
        "scan_quality_status": scan_quality_status,
        "coverage_summary": coverage_summary,
        "dimension_summary": dimension_summary,
        "crawl_governance_summary": crawl_governance_summary,
        "pages": page_summaries,
        "key_findings": findings,
        "prioritized_actions": actions,
        "executive_summary": executive_summary,
        "report_markdown": report_markdown,
        "status": {
            "phase": "ready",
            "message": "官网 AI 友好度已完成",
        },
    }


async def generate_site_confidence_artifact(
    *,
    session_id: str,
    root_url: str,
    brand_name: str | None = None,
    scan_mode: str = DEFAULT_SCAN_MODE,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> dict[str, Any]:
    from app.workflow.events import save_and_send_artifact

    report_data = await build_site_confidence_report(
        root_url=root_url,
        scan_mode=scan_mode,
        max_pages=max_pages,
    )
    if brand_name:
        report_data["brand_name"] = brand_name
    domain_key = _artifact_domain_key(str(report_data.get("root_domain") or "site"))
    artifact_key = f"{session_id}_report_site_confidence_{domain_key}"
    artifact_message_id = await save_and_send_artifact(
        session_id=session_id,
        output_type="report",
        title=str(report_data.get("headline") or "官网 AI 友好度"),
        data=report_data,
        artifact_key=artifact_key,
    )
    return {
        "artifact_key": artifact_key,
        "artifact_message_id": artifact_message_id,
        "artifact_kind": "site_confidence_report",
        "report_data": report_data,
    }
