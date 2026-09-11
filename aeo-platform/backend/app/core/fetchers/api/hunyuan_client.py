"""Tencent HY3 API client with explicit endpoint and credential configuration."""

import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.core.fetchers.api.base_client import BaseAPIClient
from app.schemas.fetch import LLMResponse, SearchReference

logger = logging.getLogger(__name__)


class HunyuanClient(BaseAPIClient):
    """HY3 Chat Completions client; never migrate credentials across gateways."""

    TOKENHUB_BASE_URL = "https://tokenhub.tencentmaas.com/v1"
    DEFAULT_ENDPOINT = f"{TOKENHUB_BASE_URL}/chat/completions"
    DEFAULT_MODEL = "hy3"
    ROLE_MODEL = "hunyuan-role-latest"
    TRANSLATION_MODEL = "hy-mt2-pro"

    _LEGACY_HOSTS = frozenset({"api.hunyuan.cloud.tencent.com"})
    _RETIRED_MODEL_MIGRATIONS = {
        "deepsearch": DEFAULT_MODEL,
        "hunyuan-2.0-instruct-20251111": DEFAULT_MODEL,
        "hunyuan-role": ROLE_MODEL,
        "hunyuan-turbos-role": ROLE_MODEL,
        "hunyuan-translation-preview": TRANSLATION_MODEL,
    }
    _CURRENT_MODELS = frozenset({DEFAULT_MODEL, ROLE_MODEL, TRANSLATION_MODEL})
    _RETIRED_MODEL_PATTERNS = (
        (re.compile(r"^hunyuan-turbos-role(?:$|[-_.].*)"), ROLE_MODEL),
        (re.compile(r"^hunyuan-role(?:$|[-_.].*)"), ROLE_MODEL),
        (
            re.compile(r"^hunyuan-translation-preview(?:$|[-_.].*)"),
            TRANSLATION_MODEL,
        ),
        (re.compile(r"^hunyuan-translation(?:$|[-_.].*)"), TRANSLATION_MODEL),
        (re.compile(r"^hunyuan-deepsearch(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-2(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-t1(?:$|[-_.].*)"), DEFAULT_MODEL),
        (
            re.compile(r"^hunyuan-turbos(?:$|-(?!role(?:$|-)).*)"),
            DEFAULT_MODEL,
        ),
        (re.compile(r"^hunyuan-turbo(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-standard(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-pro(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-code(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-funcall(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-large-role(?:$|[-_.].*)"), ROLE_MODEL),
        (re.compile(r"^hunyuan-large-longcontext(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-large(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-customized(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan-lite(?:$|[-_.].*)"), DEFAULT_MODEL),
        (re.compile(r"^hunyuan$"), DEFAULT_MODEL),
    )

    _REDACTION_PATTERNS = (
        (
            re.compile(
                r"(?i)(\bauthorization\b\s*['\"]?\s*[:=]\s*['\"]?)"
                r"(?:bearer\s+)?[^\s,;}\]'\"]+"
            ),
            r"\1[REDACTED]",
        ),
        (
            re.compile(
                r"(?i)(\b(?:api[\s_-]*key|token|secret)\b"
                r"\s*['\"]?\s*[:=]\s*['\"]?)[^\s,;}\]'\"]+"
            ),
            r"\1[REDACTED]",
        ),
        (
            re.compile(
                r"(?i)(\bapi[\s_-]*key\b\s+)" r"(?![A-Za-z0-9._-]+=)[A-Za-z0-9._~+/-]+"
            ),
            r"\1[REDACTED]",
        ),
        (
            re.compile(
                r"(?i)(\b(?:token|secret)\b\s+)"
                r"(?![A-Za-z0-9._-]+=)[A-Za-z0-9._~+/-]+"
            ),
            r"\1[REDACTED]",
        ),
        (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
        (re.compile(r"(?i)\bsk-[A-Za-z0-9][A-Za-z0-9._-]*"), "sk-[REDACTED]"),
    )

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
    ):
        """Initialize Hunyuan client.

        Args:
            api_key: API key (optional, defaults to settings.HUNYUAN_API_KEY)
            endpoint: API endpoint (optional, defaults to settings.HUNYUAN_BASE_URL)
            model: Model name (optional, defaults to settings.HUNYUAN_MODEL)
        """
        # Read from settings (which loads from .env.local) if not provided.
        api_key = (api_key or settings.HUNYUAN_API_KEY or "").strip()
        endpoint = self._resolve_endpoint(endpoint or settings.HUNYUAN_BASE_URL)
        model = self._resolve_model(model or settings.HUNYUAN_MODEL)

        if not api_key:
            raise ValueError(
                "Hunyuan API key is required. "
                "Configure HUNYUAN_API_KEY with a key issued for the configured HY3 endpoint."
            )

        search_source = getattr(settings, "HUNYUAN_SEARCH_SOURCE", "lite")
        if search_source not in {"lite", "standard"}:
            raise ValueError("HUNYUAN_SEARCH_SOURCE must be lite or standard")
        super().__init__(api_key, endpoint)
        self.model = model
        self.search_source = search_source

    @classmethod
    def _resolve_endpoint(cls, configured_url: str | None) -> str:
        """Normalize the path without silently changing the configured gateway."""

        base_url = (configured_url or "").strip().rstrip("/")
        if not base_url:
            base_url = cls.TOKENHUB_BASE_URL

        try:
            host = (urlsplit(base_url).hostname or "").lower()
        except ValueError:
            host = ""
        if host in cls._LEGACY_HOSTS:
            raise ValueError(
                "Legacy HUNYUAN_BASE_URL cannot serve HY3. Explicitly configure the "
                "HY3 endpoint, HUNYUAN_MODEL=hy3 and a matching HUNYUAN_API_KEY; "
                "no request was sent and no credential was migrated."
            )

        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    @classmethod
    def has_legacy_configuration(
        cls,
        configured_url: str | None = None,
        configured_model: str | None = None,
    ) -> bool:
        """Report whether settings still point at the retired Hunyuan API.

        A4 retains this signal for legacy default browser routing. Explicit API
        requests must configure a current endpoint/model and matching credential.
        """

        base_url = (
            configured_url if configured_url is not None else settings.HUNYUAN_BASE_URL
        )
        model = (
            configured_model if configured_model is not None else settings.HUNYUAN_MODEL
        )
        try:
            host = (urlsplit((base_url or "").strip()).hostname or "").lower()
        except ValueError:
            host = ""
        return host in cls._LEGACY_HOSTS or cls._is_retired_model(model)

    @classmethod
    def _is_retired_model(cls, model: str | None) -> bool:
        """Recognize retired Hunyuan models without matching current targets."""

        normalized_model = (model or "").strip().lower()
        return cls._migration_for_model(normalized_model) is not None

    @classmethod
    def _migration_for_model(cls, model: str | None) -> str | None:
        """Return the official replacement for one retired model id."""

        normalized_model = (model or "").strip().lower()
        if not normalized_model or normalized_model in cls._CURRENT_MODELS:
            return None
        migration = cls._RETIRED_MODEL_MIGRATIONS.get(normalized_model)
        if migration is not None:
            return migration
        for pattern, replacement in cls._RETIRED_MODEL_PATTERNS:
            if pattern.fullmatch(normalized_model):
                return replacement
        return None

    @classmethod
    def _resolve_model(cls, configured_model: str | None) -> str:
        """Reject retired models instead of silently selecting a replacement."""

        model = (configured_model or cls.DEFAULT_MODEL).strip()
        if cls._is_retired_model(model):
            raise ValueError(
                "Retired HUNYUAN_MODEL or HUNYUAN_FAST_MODEL configured. Explicitly "
                "set the collection model to hy3 with its endpoint and authorized "
                "HUNYUAN_API_KEY; no request was sent."
            )
        return model

    async def ask_with_search(self, question: str) -> LLMResponse:
        """Send question and get answer with search references.

        Args:
            question: Question to ask

        Returns:
            LLMResponse with answer and references
        """
        start_time = time.time()

        # TokenHub's search extension replaces the retired Hunyuan fields
        # enable_enhancement/search_info/citation.
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self._build_system_prompt(),
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
            "stream": False,
            "web_search_options": {
                "enable": True,
                "search_source": self.search_source,
            },
        }

        # Make request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = self._format_http_error(response)
                logger.error(
                    "[HunyuanClient] HTTP %s from %s (model=%s): %s",
                    response.status_code,
                    self._redact_error_text(self.endpoint),
                    self._redact_error_text(self.model),
                    detail,
                )
                safe_error = self._redact_error_text(
                    f"{exc} response={detail} model={self.model}"
                )
                raise httpx.HTTPStatusError(
                    safe_error,
                    request=exc.request,
                    response=exc.response,
                ) from exc
            data = response.json()

        # Parse response
        answer_text = self._extract_answer(data)
        # Preserve provider usage on empty responses; A4 rejects them before success.
        search_refs = self._extract_search_references(data)

        duration = time.time() - start_time

        return LLMResponse(
            answer_text=answer_text,
            search_references=search_refs,
            raw_response={**data, "protocol": "hunyuan_chat_search"},
            duration=duration,
        )

    @staticmethod
    def _format_http_error(response: httpx.Response) -> str:
        """Extract a bounded, actionable provider error without secrets."""

        try:
            body = response.json()
        except (ValueError, TypeError):
            body = None

        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            code = str(error.get("code") or "").strip()
            message = str(
                error.get("message")
                or error.get("message_zh")
                or error.get("type")
                or "provider error"
            ).strip()
            detail = f"code={code or 'unknown'} message={message}"
            if code == "2030":
                detail += "; action=verify model availability at the configured endpoint"
            elif code == "401002" or response.status_code == 401:
                detail += (
                    "; action=verify HUNYUAN_API_KEY belongs to the configured "
                    "endpoint and is authorized for the requested model"
                )
            return HunyuanClient._redact_error_text(detail)

        text = (response.text or "").strip().replace("\n", " ")
        return HunyuanClient._redact_error_text(text[:1000]) or (
            f"HTTP {response.status_code}"
        )

    @classmethod
    def _redact_error_text(cls, value: Any) -> str:
        """Remove credentials from provider text before logging or re-raising."""

        text = str(value or "")
        for pattern, replacement in cls._REDACTION_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _extract_answer(self, data: dict[str, Any]) -> str:
        """Extract answer text from response.

        Args:
            data: Raw API response

        Returns:
            Answer text
        """
        try:
            choices = data.get("choices", [])
            if not choices:
                return ""
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part["text"]
                    for part in content
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                )
            return ""
        except Exception:
            return ""

    def _extract_search_references(self, data: dict[str, Any]) -> list[SearchReference]:
        """Extract search references from response.

        Args:
            data: Raw API response

        Returns:
            List of search references
        """
        references: list[SearchReference] = []
        seen_urls: set[str] = set()
        try:
            # TokenHub puts search results on the assistant message.  Keep
            # the old top-level shape as a read-compatible fallback.
            choices = data.get("choices", [])
            message = choices[0].get("message", {}) if choices else {}
            search_results = message.get("search_results", [])
            if not search_results:
                search_info = data.get("search_info")
                search_results = (
                    search_info.get("search_results") or []
                    if isinstance(search_info, dict) else []
                )
            for idx, result in enumerate(search_results, 1):
                if not isinstance(result, dict):
                    continue
                url = str(result.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                references.append(
                    SearchReference(
                        index=result.get("index", idx),
                        title=result.get("title") or result.get("name", ""),
                        url=url,
                        snippet=(
                            result.get("snippet")
                            or result.get("summary")
                            or result.get("text")
                        ),
                        site_name=(
                            result.get("site_name")
                            or result.get("sitename")
                            or result.get("site")
                        ),
                        is_official=result.get("is_official", False),
                    )
                )
        except Exception:
            pass
        return references
