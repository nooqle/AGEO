"""Fetch schemas for answer fetching from public LLM platforms."""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Platform(str, Enum):
    """Supported platforms for answer fetching."""

    DOUBAO = "doubao"
    HUNYUAN = "hunyuan"
    KIMI = "kimi"
    DEEPSEEK = "deepseek"


class FetchMethod(str, Enum):
    """Methods for fetching answers."""

    API = "api"
    BROWSER = "browser"


class SearchReference(BaseModel):
    """Search reference from LLM response.

    Contains information about a source cited by the LLM.
    """

    index: int = Field(..., description="引用序号")
    title: str = Field(..., description="标题")
    url: str = Field(..., description="URL")
    snippet: Optional[str] = Field(None, description="摘要片段")
    site_name: Optional[str] = Field(None, description="网站名称")
    is_official: bool = Field(False, description="是否为品牌官网")


class FetchResult(BaseModel):
    """Single fetch result in unified format.

    Contains the answer and search references from one platform.
    """

    # Identification
    id: str = Field(..., description="结果ID")
    question_id: str = Field(..., description="问题ID")
    question_text: str = Field(..., description="问题文本")

    # Platform info
    platform: Platform = Field(..., description="平台")
    fetch_method: FetchMethod = Field(..., description="抓取方式")
    status: Literal["success", "failed"] = Field(..., description="状态")

    # Success data
    answer_text: Optional[str] = Field(None, description="回答内容")
    search_references: list[SearchReference] = Field(
        default_factory=list,
        description="搜索引用列表",
    )
    raw_response: Optional[dict] = Field(None, description="原始响应")

    # Failure info
    error_message: Optional[str] = Field(None, description="错误信息")

    # Metadata
    fetch_duration: Optional[float] = Field(None, description="抓取耗时(秒)")
    fetched_at: datetime = Field(
        default_factory=datetime.utcnow, description="抓取时间"
    )


class FetchInput(BaseModel):
    """Input for FetchAgent.

    Contains questions to fetch and configuration options.
    """

    questions: list[dict] = Field(..., description="问题列表(SimulatedQuestion)")
    platforms: list[Platform] = Field(
        default=[
            Platform.DOUBAO,
            Platform.HUNYUAN,
            Platform.KIMI,
            Platform.DEEPSEEK,
        ],
        description="目标平台列表",
    )

    # API configuration
    api_timeout: int = Field(30, description="API超时(秒)")
    api_max_concurrent: int = Field(10, description="API最大并发数")

    # Browser configuration
    browser_timeout: int = Field(90, description="浏览器超时(秒)")
    browser_max_concurrent: int = Field(2, description="浏览器最大并发数")
    browser_headed: bool = Field(False, description="是否显示浏览器窗口")


class FetchOutput(BaseModel):
    """Output from FetchAgent.

    Contains all fetch results and statistics.
    """

    results: list[FetchResult] = Field(..., description="抓取结果列表")
    statistics: dict = Field(default_factory=dict, description="统计信息")
    failed_questions: list[str] = Field(
        default_factory=list,
        description="失败的问题ID列表",
    )


class FetchEventType(str, Enum):
    """Types of fetch events for progress streaming."""

    PROGRESS = "progress"
    PLATFORM_START = "platform_start"
    PLATFORM_COMPLETE = "platform_complete"
    BROWSER_STATE = "browser_state"
    COMPLETE = "complete"
    ERROR = "error"


class FetchEvent(BaseModel):
    """Fetch event for SSE streaming.

    Used to stream progress updates to the frontend.
    """

    type: FetchEventType = Field(..., description="事件类型")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="时间戳")
    message: str = Field(..., description="消息")
    progress: Optional[float] = Field(None, description="进度(0-1)")

    # Platform related
    platform: Optional[Platform] = Field(None, description="平台")

    # Browser state
    browser_state: Optional[str] = Field(None, description="浏览器状态")
    requires_action: bool = Field(False, description="是否需要用户操作")
    action_hint: Optional[str] = Field(None, description="操作提示")

    # Completion data
    data: Optional[FetchOutput] = Field(None, description="完成时的数据")


# Browser-specific schemas
class BrowserState(str, Enum):
    """Browser agent states."""

    IDLE = "idle"
    INITIALIZING = "initializing"
    NAVIGATING = "navigating"
    CHECKING_LOGIN = "checking_login"
    WAITING_FOR_LOGIN = "waiting_for_login"
    LOGGED_IN = "logged_in"
    ENABLING_SEARCH = "enabling_search"
    SUBMITTING = "submitting"
    WAITING_RESPONSE = "waiting_response"
    EXTRACTING = "extracting"
    COMPLETED = "completed"
    ERROR = "error"


class BrowserEvent(BaseModel):
    """Browser agent event.

    Emitted during browser-based fetching.
    """

    state: BrowserState = Field(..., description="当前状态")
    message: str = Field(..., description="描述")
    progress: float = Field(0.0, description="进度(0-1)")

    # Interaction
    requires_action: bool = Field(False, description="是否需要操作")
    action_type: Optional[str] = Field(None, description="操作类型")
    action_hint: Optional[str] = Field(None, description="操作提示")

    # Error
    error: Optional[str] = Field(None, description="错误信息")
    recoverable: bool = Field(True, description="是否可恢复")

    # Result
    data: Optional[FetchResult] = Field(None, description="完成时的数据")


# API-specific schemas
class LLMResponse(BaseModel):
    """Unified LLM API response.

    Used by API clients to return standardized data.
    """

    answer_text: str = Field(..., description="回答文本")
    search_references: list[SearchReference] = Field(
        default_factory=list,
        description="搜索引用",
    )
    raw_response: dict = Field(default_factory=dict, description="原始响应")
    duration: Optional[float] = Field(None, description="请求耗时")
