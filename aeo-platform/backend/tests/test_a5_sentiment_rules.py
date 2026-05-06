from pathlib import Path

from app.workflow.a5.metrics import analyze_sentiment


def test_analysis_report_skill_guidance_contains_reading_and_sentiment_examples():
    skill_path = (
        Path(__file__).resolve().parents[1]
        / "skill_packages"
        / "analysis-report"
        / "SKILL.md"
    )
    text = skill_path.read_text(encoding="utf-8")

    assert "先判断有没有有效分母" in text
    assert "分母存在、分子为 0" in text
    assert "损害品牌声誉、指出产品硬伤、合规性失败或客观负面事件" in text
    assert "不符合 GB/T 18801 标准" in text
    assert "通过 ISO 27001 信息安全认证" in text


def test_post_analysis_skill_guidance_contains_same_sentiment_boundary():
    skill_path = (
        Path(__file__).resolve().parents[1]
        / "skill_packages"
        / "post-analysis"
        / "SKILL.md"
    )
    text = skill_path.read_text(encoding="utf-8")

    assert "先判断有没有有效分母" in text
    assert "品牌提及为 0 时" in text
    assert "损害品牌声誉、指出产品硬伤、合规性失败或客观负面事件" in text


def test_sentiment_rules_mark_compliance_failure_as_negative():
    text = (
        "根据近期的抽检报告显示，该品牌的 A 型号净化器在甲醛 CADR 值上"
        "不符合国家最新的 GB/T 18801 标准，存在参数虚标的情况。"
    )

    assert analyze_sentiment(text) == "negative"


def test_sentiment_rules_mark_privacy_crisis_as_negative():
    text = (
        "该品牌陷入严重的隐私泄露争议，多家媒体报道其未经授权收集用户定位数据，"
        "导致其面临监管机构的巨额罚款。"
    )

    assert analyze_sentiment(text) == "negative"


def test_sentiment_rules_mark_recall_and_objective_defect_as_negative():
    recall_text = "电池管理系统在极端高温下存在热失控风险，品牌方已主动召回涉事批次。"
    defect_text = (
        "虽然采用了最新芯片，但散热模组设计妥协，长时间高负载运行时"
        "会出现明显降频现象，性能释放受限。"
    )

    assert analyze_sentiment(recall_text) == "negative"
    assert analyze_sentiment(defect_text) == "negative"


def test_sentiment_rules_mark_certification_and_breakthrough_as_positive():
    certification_text = (
        "该架构通过 ISO 27001 信息安全认证，并获得国际红点设计大奖，"
        "是该领域的标杆产品。"
    )
    breakthrough_text = "最新算法突破传统模型的上下文窗口限制，提升长文本处理准确率。"

    assert analyze_sentiment(certification_text) == "positive"
    assert analyze_sentiment(breakthrough_text) == "positive"


def test_sentiment_rules_mark_plain_specs_as_neutral():
    text = "该产品支持 220V 输入，额定功率 800W，提供标准模式和节能模式。"

    assert analyze_sentiment(text) == "neutral"
