"""Pure per-run collection routing contract, using public platform IDs."""

from typing import Any

PLATFORMS = ("doubao", "yuanbao", "kimi", "deepseek")


def resolve_platform_fetch_methods(
    methods: Any, *, platforms: Any = None, fetch_mode: str = "fast",
    explicit: bool = False, legacy_yuanbao_browser: bool = False,
) -> dict[str, str]:
    defaults = {
        platform: "browser" if fetch_mode == "full" or platform == "deepseek" else "api"
        for platform in PLATFORMS
    }
    if explicit:
        if not isinstance(methods, dict) or not methods:
            raise ValueError("platform_fetch_methods must be a non-empty object")
        if any(key not in PLATFORMS for key in methods):
            raise ValueError("platform_fetch_methods contains an unsupported platform")
        if any(value not in ("api", "browser") for value in methods.values()):
            raise ValueError("platform_fetch_methods values must be api or browser")
        selected = platforms or PLATFORMS
        if isinstance(selected, str):
            selected = [selected]
        selected = {"yuanbao" if p == "hunyuan" else p for p in selected}
        missing = selected.difference(methods)
        if missing:
            raise ValueError("platform_fetch_methods missing selected platforms: " + ", ".join(sorted(missing)))
        return {**defaults, **methods}
    if legacy_yuanbao_browser:
        defaults["yuanbao"] = "browser"
    return defaults


def methods_from_endpoints(endpoint_ids: list[str]) -> dict[str, str]:
    methods: dict[str, str] = {}
    for endpoint in endpoint_ids:
        platform, separator, method = endpoint.rpartition("_")
        if not separator or platform not in PLATFORMS or method not in ("api", "browser"):
            raise ValueError(f"Unsupported collection endpoint: {endpoint}")
        if platform in methods and methods[platform] != method:
            raise ValueError(f"Conflicting collection methods for {platform}")
        methods[platform] = method
    return methods
