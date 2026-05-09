"""Cached favicon proxy endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import os
import re
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter(prefix="/favicons", tags=["favicons"])

_HOST_RE = re.compile(r"^[a-z0-9.-]+$")
_MAX_FAVICON_BYTES = 128 * 1024
_POSITIVE_CACHE_TTL_SECONDS = int(os.environ.get("FAVICON_CACHE_TTL_SECONDS", "2592000"))
_NEGATIVE_CACHE_TTL_SECONDS = int(os.environ.get("FAVICON_NEGATIVE_CACHE_TTL_SECONDS", "86400"))
_BROWSER_CACHE_SECONDS = int(os.environ.get("FAVICON_BROWSER_CACHE_SECONDS", "86400"))
_CONTENT_TYPE_BY_EXT = {
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def _runtime_dir() -> Path:
    explicit = os.environ.get("FAVICON_CACHE_DIR")
    if explicit:
        return Path(explicit)

    failure_dir = os.environ.get("A4_FAILURE_EVIDENCE_DIR")
    if failure_dir:
        return Path(failure_dir).resolve().parent / "favicons"

    upload_dir = os.environ.get("UPLOAD_DIR")
    if upload_dir:
        return Path(upload_dir).resolve().parent / "runtime" / "favicons"

    return Path(__file__).resolve().parents[3] / "runtime" / "favicons"


def _normalize_host(raw_domain: str) -> str:
    raw = raw_domain.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Domain is required")

    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]

    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid domain") from exc

    if (
        not host
        or len(host) > 253
        or "." not in host
        or ".." in host
        or not _HOST_RE.fullmatch(host)
        or host.startswith("-")
        or host.endswith("-")
    ):
        raise HTTPException(status_code=400, detail="Invalid domain")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise HTTPException(status_code=400, detail="Invalid domain")

    return host


async def _is_public_host(host: str) -> bool:
    if host in {"localhost", "localhost.localdomain"}:
        return False
    if host.endswith((".localhost", ".local", ".internal")):
        return False

    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        return False

    for info in infos:
        address = info[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
        ):
            return False
    return True


def _cache_digest(host: str) -> str:
    return hashlib.sha256(host.encode("utf-8")).hexdigest()


def _cache_file_paths(host: str) -> list[Path]:
    digest = hashlib.sha256(host.encode("utf-8")).hexdigest()
    cache_dir = _runtime_dir()
    return [cache_dir / f"{digest}{extension}" for extension in _CONTENT_TYPE_BY_EXT]


def _miss_path(host: str) -> Path:
    return _runtime_dir() / f"{_cache_digest(host)}.miss"


def _fresh(path: Path, ttl_seconds: int) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < ttl_seconds


def _extension_from_response(response: httpx.Response) -> str:
    content_type = response.headers.get("content-type", "").lower()
    if "png" in content_type:
        return ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "gif" in content_type:
        return ".gif"
    if "webp" in content_type:
        return ".webp"
    return ".ico"


async def _fetch_candidate(client: httpx.AsyncClient, url: str) -> tuple[bytes, str] | None:
    async with client.stream("GET", url) as response:
        if response.status_code != 200:
            return None

        final_host = response.url.host or ""
        if not final_host or not await _is_public_host(final_host):
            return None

        content_type = response.headers.get("content-type", "").lower()
        if "svg" in content_type:
            return None
        if content_type and not (
            content_type.startswith("image/")
            or "octet-stream" in content_type
            or "x-icon" in content_type
        ):
            return None

        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > _MAX_FAVICON_BYTES:
            return None

        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > _MAX_FAVICON_BYTES:
                return None
            chunks.append(chunk)

        content = b"".join(chunks)
        if not content:
            return None
        return content, _extension_from_response(response)


@router.get("")
async def get_favicon(domain: str = Query(..., min_length=1, max_length=512)):
    """Return a cached favicon for a public brand domain."""
    host = _normalize_host(domain)
    cached_paths = _cache_file_paths(host)
    miss_path = _miss_path(host)
    headers = {"Cache-Control": f"public, max-age={_BROWSER_CACHE_SECONDS}"}

    for path in cached_paths:
        if _fresh(path, _POSITIVE_CACHE_TTL_SECONDS):
            return FileResponse(
                path=path,
                media_type=_CONTENT_TYPE_BY_EXT.get(path.suffix, "image/x-icon"),
                headers=headers,
            )

    if _fresh(miss_path, _NEGATIVE_CACHE_TTL_SECONDS):
        raise HTTPException(status_code=404, detail="Favicon not found", headers=headers)

    candidates = [
        f"https://www.{host}/favicon.ico",
        f"https://{host}/favicon.ico",
        f"https://icons.duckduckgo.com/ip3/{host}.ico",
    ]
    timeout = httpx.Timeout(2.5, connect=1.0)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        max_redirects=3,
        headers={"User-Agent": "SpectaAI-FaviconCache/1.0"},
    ) as client:
        for url in candidates:
            parsed = urlparse(url)
            if not parsed.hostname or not await _is_public_host(parsed.hostname):
                continue
            try:
                fetched = await _fetch_candidate(client, url)
            except (httpx.HTTPError, OSError, ValueError):
                continue
            if not fetched:
                continue

            content, extension = fetched
            cache_dir = _runtime_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            target = cache_dir / f"{_cache_digest(host)}{extension}"
            target.write_bytes(content)
            miss_path.unlink(missing_ok=True)
            return FileResponse(
                path=target,
                media_type=_CONTENT_TYPE_BY_EXT.get(target.suffix, "image/x-icon"),
                headers=headers,
            )

    cache_dir = _runtime_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    miss_path.write_text(str(int(time.time())), encoding="utf-8")
    raise HTTPException(status_code=404, detail="Favicon not found", headers=headers)
