"""Tencent Hunyuan/TokenHub API client."""

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
    """Tencent Hunyuan API client using the current TokenHub gateway.

    The former Hunyuan gateway started returning HTTP 400/code 2030 for the
    model configured by this project after that model was retired.  TokenHub
    keeps the same OpenAI-compatible protocol, but uses a new gateway, model
    id, and web-search request field.
    """

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
                "Set HUNYUAN_API_KEY to a TokenHub API key or pass api_key parameter."
            )

        super().__init__(api_key, endpoint)
        self.model = model

    @classmethod
    def _resolve_endpoint(cls, configured_url: str | None) -> str:
        """Return a full TokenHub-compatible chat-completions endpoint.

        ``HUNYUAN_BASE_URL`` in existing installations points at the retired
        gateway.  Treat that value as stale so an env-file-only upgrade does
        not keep sending requests to the endpoint that produced code 2030.
        Explicit non-legacy endpoints remain supported for tests and private
        gateways.
        """

        base_url = (configured_url or "").strip().rstrip("/")
        if not base_url:
            base_url = cls.TOKENHUB_BASE_URL

        try:
            host = (urlsplit(base_url).hostname or "").lower()
        except ValueError:
            host = ""
        if host in cls._LEGACY_HOSTS:
            logger.warning(
                "[HunyuanClient] Retired Hunyuan endpoint configured; using TokenHub"
            )
            base_url = cls.TOKENHUB_BASE_URL

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

        The A4 orchestrator can use this signal to choose the already-tested
        Yuanbao browser path when no TokenHub credential has been provisioned.
        The client itself still migrates the request so callers that do have a
        replacement key can continue using the API path.
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
        """Map retired Hunyuan model ids to the current TokenHub model."""

        model = (configured_model or cls.DEFAULT_MODEL).strip()
        return cls._migration_for_model(model) or model

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
                "search_source": "lite",
            },
        }

        # Make request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
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
        search_refs = self._extract_search_references(data)

        duration = time.time() - start_time

        return LLMResponse(
            answer_text=answer_text,
            search_references=search_refs,
            raw_response=data,
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
                detail += "; action=replace HUNYUAN_API_KEY with a TokenHub API key"
            elif code == "401002" or response.status_code == 401:
                detail += (
                    "; action=check that HUNYUAN_API_KEY is a valid TokenHub API key"
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
                    str(part.get("text") or "")
                    for part in content
                    if isinstance(part, dict)
                )
            return str(content or "")
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
                search_results = data.get("search_info", {}).get("search_results", [])
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
