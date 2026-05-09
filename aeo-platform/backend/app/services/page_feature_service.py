"""Lightweight page feature extraction for AI-friendly content evaluation."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import unescape
import json
import re
from typing import Any

import httpx


PAGE_FEATURE_CACHE_TTL_SECONDS = 1800
PAGE_FEATURE_FAILURE_TTL_SECONDS = 120
PAGE_FEATURE_CACHE_MAX_ENTRIES = 512
PAGE_FEATURE_TIMEOUT_SECONDS = 5.0

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
    for meta_tag in re.findall(
        r"<meta\b[^>]*>", html or "", flags=re.IGNORECASE | re.DOTALL
    ):
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
        "content_type": "",
        "fetch_failure_reason": "",
        "fetched_title": "",
        "meta_description": "",
        "has_h1": False,
        "h1_texts": [],
        "h1_count": 0,
        "h2_texts": [],
        "h2_count": 0,
        "has_main": False,
        "has_article": False,
        "body_text_length": 0,
        "body_text_excerpt": "",
        "script_count": 0,
        "has_noscript": False,
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
                "Mozilla/5.0 (compatible; SpectaSiteConfidence/1.0; "
                "+https://specta.ai/)"
            )
        }
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=PAGE_FEATURE_TIMEOUT_SECONDS,
            headers=headers,
        ) as client:
            response = await asyncio.wait_for(
                client.get(url),
                timeout=PAGE_FEATURE_TIMEOUT_SECONDS,
            )
        content_type = response.headers.get("content-type", "").lower()
        is_html_like = (
            "text/html" in content_type or "application/xhtml+xml" in content_type
        )
        if response.status_code >= 400 or not is_html_like:
            failure_reason = (
                f"http_{response.status_code}"
                if response.status_code >= 400
                else "non_html_content"
            )
            result = {
                **default,
                "http_status": response.status_code,
                "final_url": str(response.url),
                "content_type": content_type,
                "fetch_failure_reason": failure_reason,
            }
            _page_feature_cache[url] = (now, result)
            return dict(result)

        html = response.text or ""
        body_text = _strip_html(html)
        body_text_length = len(body_text)
        has_main = bool(re.search(r"<main\b", html, flags=re.IGNORECASE))
        has_article = bool(re.search(r"<article\b", html, flags=re.IGNORECASE))
        script_count = len(
            re.findall(r"<script\b", html, flags=re.IGNORECASE | re.DOTALL)
        )
        h1_matches = re.findall(
            r"<h1\b[^>]*>.*?</h1>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        h2_matches = re.findall(
            r"<h2\b[^>]*>.*?</h2>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        result = {
            "crawl_readable": True,
            "http_status": response.status_code,
            "final_url": str(response.url),
            "content_type": content_type,
            "fetch_failure_reason": "",
            "fetched_title": _extract_tag_text(html, "title"),
            "meta_description": _extract_meta_content(
                html,
                ("description", "og:description", "twitter:description"),
            ),
            "has_h1": len(h1_matches) > 0,
            "h1_texts": [_strip_html(item) for item in h1_matches[:6]],
            "h1_count": len(h1_matches),
            "h2_texts": [_strip_html(item) for item in h2_matches[:10]],
            "h2_count": len(h2_matches),
            "has_main": has_main,
            "has_article": has_article,
            "body_text_length": body_text_length,
            "body_text_excerpt": body_text[:2400],
            "script_count": script_count,
            "has_noscript": bool(
                re.search(r"<noscript\b", html, flags=re.IGNORECASE | re.DOTALL)
            ),
            "schema_types": _extract_schema_types(html),
            "published_at": _extract_published_at(html),
        }
        _page_feature_cache[url] = (now, result)
        return dict(result)
    except Exception as exc:
        failure_reason = (
            "request_timeout"
            if isinstance(exc, (httpx.TimeoutException, TimeoutError))
            else (
                "too_many_redirects"
                if isinstance(exc, httpx.TooManyRedirects)
                else "request_error"
            )
        )
        result = {
            **default,
            "fetch_failure_reason": failure_reason,
        }
        _page_feature_cache[url] = (now, result)
        return dict(result)
