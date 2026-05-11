from __future__ import annotations

import pytest

from app.tools.a1_evidence import normalize_website_url, repair_a1_website_fields


def test_normalize_website_url_does_not_add_duplicate_www() -> None:
    assert normalize_website_url("www.perfect99.com") == "https://www.perfect99.com/"
    assert (
        normalize_website_url("https://www.perfect99.com")
        == "https://www.perfect99.com/"
    )
    assert normalize_website_url("未公开") == ""


@pytest.mark.asyncio
async def test_repair_a1_website_uses_reachable_official_evidence_candidate() -> None:
    async def probe(url: str) -> bool:
        return url == "https://www.herbalife.cn/"

    profile, competitors = await repair_a1_website_fields(
        {"brand_name": "安利", "official_website": "www.amway.com.cn"},
        [
            {
                "name": "康宝莱",
                "name_en": "Herbalife",
                "website": "https://www.herbalife.com.cn/",
            }
        ],
        [
            {
                "title": "关于康宝莱 - 康宝莱",
                "link": "https://www.herbalife.cn/channel/index/119",
                "usage": "用于核验康宝莱官网",
            }
        ],
        reachability_probe=probe,
    )

    assert profile["official_website"] == ""
    assert competitors[0]["website"] == "https://www.herbalife.cn/"


@pytest.mark.asyncio
async def test_repair_a1_website_clears_unverified_dead_candidate() -> None:
    async def probe(_url: str) -> bool:
        return False

    _profile, competitors = await repair_a1_website_fields(
        {"brand_name": "安利", "official_website": ""},
        [{"name": "示例竞品", "website": "https://dead.example.com/"}],
        [],
        reachability_probe=probe,
    )

    assert competitors[0]["website"] == ""
