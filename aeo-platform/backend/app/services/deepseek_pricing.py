"""Versioned official CNY tariff; never backfill historical stored estimates."""

from datetime import datetime, time, timedelta, timezone

CHINA_TIME = timezone(timedelta(hours=8), "Asia/Shanghai")
FLASH_CUTOVER = datetime(2026, 9, 10, 12, tzinfo=CHINA_TIME)
HISTORICAL_START = datetime(2026, 8, 17, tzinfo=CHINA_TIME)
PRO_CUTOVER = datetime(2026, 9, 14, 12, tzinfo=CHINA_TIME)
PRICE_VERSION = "deepseek-cn-2026-09-10"
SOURCE_URL = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"


def resolve_deepseek_tariff(model_name: str, occurred_at: datetime) -> dict | None:
    """Resolve only documented names and time intervals, independent of role config."""
    if occurred_at.tzinfo is None:
        raise ValueError("Pricing timestamp must be timezone aware")
    local = occurred_at.astimezone(CHINA_TIME)
    if local < HISTORICAL_START:
        return None
    model = model_name.strip().lower()
    historical = local < FLASH_CUTOVER
    if historical and model == "deepseek-v4-flash":
        effective_model = "deepseek-v4-flash"
    elif historical and model == "deepseek-v4-pro":
        effective_model = "deepseek-v4-pro"
    elif historical:
        return None
    elif model in {"deepseek-flash", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp"}:
        effective_model = "deepseek-flash"
    elif model == "deepseek-v4-pro":
        effective_model = "deepseek-v4-pro" if local < PRO_CUTOVER else "deepseek-flash"
    else:
        return None
    peak = (historical or local.weekday() < 5) and (
        time(9) <= local.time() < time(12)
        or time(14) <= local.time() < time(18)
    )
    hit, miss, output = {
        "deepseek-flash": (0.02, 1.0, 4.0),
        "deepseek-v4-flash": (0.05, 1.5, 4.5),
        "deepseek-v4-pro": (0.15, 4.5, 13.5),
    }[effective_model]
    factor = 2 if peak else 1
    version = "deepseek-cn-2026-08-17" if historical else PRICE_VERSION
    source_url = "https://api-docs.deepseek.com/zh-cn/news/news260813/" if historical else SOURCE_URL
    return {
        "pricing_model": effective_model,
        "input_cache_hit_price_per_mtokens": hit * factor,
        "input_cache_miss_price_per_mtokens": miss * factor,
        "output_price_per_mtokens": output * factor,
        "pricing_currency": "CNY",
        "reporting_currency": "CNY",
        "source": version,
        "source_url": source_url,
        "rate_version": version,
        "tariff_period": "peak" if peak else "off_peak",
        "priced_at": occurred_at.isoformat(),
        "pricing_timezone": "Asia/Shanghai",
    }
