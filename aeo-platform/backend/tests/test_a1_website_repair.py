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
async def test_repair_a1_website_uses_official_evidence_candidate_without_probe() -> (
    None
):
    profile, competitors = await repair_a1_website_fields(
        {
            "brand_name": "安利",
            "brand_name_en": "Amway",
            "official_website": "www.amway.com.cn",
        },
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
    )

    assert profile["official_website"] == ""
    assert competitors[0]["website"] == "https://www.herbalife.cn/"


@pytest.mark.asyncio
async def test_repair_a1_website_clears_model_website_without_evidence() -> None:
    _profile, competitors = await repair_a1_website_fields(
        {"brand_name": "安利", "official_website": ""},
        [{"name": "示例竞品", "website": "https://dead.example.com/"}],
        [],
    )

    assert competitors[0]["website"] == ""
