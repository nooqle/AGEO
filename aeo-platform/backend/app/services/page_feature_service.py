"""Lightweight page feature extraction for AI-friendly content evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import json
import re
from typing import Any

import httpx


PAGE_FEATURE_CACHE_TTL_SECONDS = 1800
PAGE_FEATURE_FAILURE_TTL_SECONDS = 120
PAGE_FEATURE_CACHE_MAX_ENTRIES = 512

_page_feature_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _strip_html(value: str) -> str:
    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        value or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    return _collapse_text(unescape(text))


def _extract_tag_text(html: str, tag: str) -> str:
    match = re.search(
        rf"<{tag}\b[^>]*>(.*?)</{tag}>",
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    return _strip_html(match.group(1)) if match else ""


def _parse_html_attrs(tag_html: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _quote, value in re.findall(
        r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(['\"])(.*?)\2",
        tag_html or "",
        flags=re.IGNORECASE | re.DOTALL,
    ):
        attrs[key.lower()] = _collapse_text(unescape(value))
    return attrs


def _extract_meta_content(html: str, names: tuple[str, ...]) -> str:
    target_names = {name.lower() for name in names}
    for meta_tag in re.findall(r"<meta\b[^>]*>", html or "", flags=re.IGNORECASE | re.DOTALL):
        attrs = _parse_html_attrs(meta_tag)
        meta_name = attrs.get("name") or attrs.get("property")
        if meta_name and meta_name.lower() in target_names and attrs.get("content"):
            return attrs["content"]
    return ""


def _extract_schema_types(html: str) -> list[str]:
    schema_types: list[str] = []
    scripts = re.findall(
        r"<script\b[^>]*type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for script in scripts:
        try:
            payload = json.loads(unescape(script.strip()))
        except Exception:
            continue

        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                current_type = current.get("@type")
                if isinstance(current_type, str):
                    schema_types.append(current_type)
                elif isinstance(current_type, list):
                    schema_types.extend(str(item) for item in current_type if item)
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(current, list):
                stack.extend(current)

    deduped: list[str] = []
    for schema_type in schema_types:
        normalized = _collapse_text(schema_type)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped[:8]


def _extract_published_at(html: str) -> str:
    meta_date = _extract_meta_content(
        html,
        (
            "article:published_time",
            "article:modified_time",
            "og:updated_time",
            "pubdate",
            "publishdate",
            "date",
            "dc.date",
        ),
    )
    if meta_date:
        return meta_date

    time_match = re.search(
        r"<time\b[^>]*datetime=['\"](.*?)['\"]",
        html or "",
        flags=re.IGNORECASE | re.DOTALL,
    )
    if time_match:
        return _collapse_text(unescape(time_match.group(1)))
    return ""


async def fetch_page_features(url: str) -> dict[str, Any]:
    default = {
        "crawl_readable": False,
        "http_status": None,
        "final_url": url,
        "fetched_title": "",
        "has_h1": False,
        "h1_count": 0,
        "has_main": False,
        "has_article": False,
        "schema_types": [],
        "published_at": "",
    }
    if not url:
        return default

    now = datetime.now(timezone.utc).timestamp()
    stale_keys = [
        cache_key
        for cache_key, (cached_at, _) in _page_feature_cache.items()
        if now - cached_at > PAGE_FEATURE_CACHE_TTL_SECONDS
    ]
    for cache_key in stale_keys:
        _page_feature_cache.pop(cache_key, None)

    cached = _page_feature_cache.get(url)
    if cached:
        cached_at, cached_value = cached
        cached_ttl = (
            PAGE_FEATURE_CACHE_TTL_SECONDS
            if cached_value.get("crawl_readable")
            else PAGE_FEATURE_FAILURE_TTL_SECONDS
        )
        if now - cached_at < cached_ttl:
            return dict(cached_value)
        _page_feature_cache.pop(url, None)

    if len(_page_feature_cache) >= PAGE_FEATURE_CACHE_MAX_ENTRIES:
        oldest_key = min(_page_feature_cache.items(), key=lambda item: item[1][0])[0]
        _page_feature_cache.pop(oldest_key, None)

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; SpectaA7/1.0; "
                "+https://specta.ai/)"
            )
        }
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=8.0,
            headers=headers,
        ) as client:
            response = await client.get(url)
        content_type = response.headers.get("content-type", "").lower()
        is_html_like = (
            "text/html" in content_type
            or "application/xhtml+xml" in content_type
        )
        if response.status_code >= 400 or not is_html_like:
            result = {
                **default,
                "http_status": response.status_code,
                "final_url": str(response.url),
            }
            _page_feature_cache[url] = (now, result)
            return dict(result)

        html = response.text or ""
        has_main = bool(re.search(r"<main\b", html, flags=re.IGNORECASE))
        has_article = bool(re.search(r"<article\b", html, flags=re.IGNORECASE))
        h1_matches = re.findall(
            r"<h1\b[^>]*>.*?</h1>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        result = {
            "crawl_readable": True,
            "http_status": response.status_code,
            "final_url": str(response.url),
            "fetched_title": _extract_tag_text(html, "title"),
            "has_h1": len(h1_matches) > 0,
            "h1_count": len(h1_matches),
            "has_main": has_main,
            "has_article": has_article,
            "schema_types": _extract_schema_types(html),
            "published_at": _extract_published_at(html),
        }
        _page_feature_cache[url] = (now, result)
        return dict(result)
    except Exception:
        _page_feature_cache[url] = (now, default)
        return dict(default)
