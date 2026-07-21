"""3b-1-A: topology flow_plan surfaces in orchestrator dashboard context."""

from app.workflow.orchestrator_context_packets import (
    build_dashboard_context_packet,
    render_dashboard_context_packet,
)


def test_dashboard_packet_reads_flow_plan_from_dashboard_context():
    state = {
        "dashboard_context": {
            "entry_source": "brand_intelligence_run",
            "flow_plan": {
                "source": "topology_constraint",
                "summary": "将执行 7 步 · 平台：deepseek,kimi",
                "planned_platforms": ["deepseek", "kimi"],
                "steps": [
                    {
                        "node_id": "platform-doubao",
                        "label": "豆包",
                        "status": "skipped",
                        "skip_reason": "画布已断开该平台连线",
                    },
                    {
                        "node_id": "fetch",
                        "label": "答案采集",
                        "status": "pending",
                    },
                ],
            },
        }
    }
    packet = build_dashboard_context_packet(state)
    assert packet.flow_plan_summary and "平台" in packet.flow_plan_summary
    assert packet.flow_plan_source == "topology_constraint"
    assert list(packet.flow_planned_platforms) == ["deepseek", "kimi"]
    assert any("豆包" in item for item in packet.flow_skipped_steps)

    rendered = render_dashboard_context_packet(packet)
    assert "画布拓扑执行计划" in rendered
    assert "deepseek" in rendered
    assert "豆包" in rendered
    assert "跳过" in rendered or "已跳过" in rendered


def test_dashboard_packet_reads_flow_plan_from_input_scope_fallback():
    state = {
        "dashboard_context": {"entry_source": "brand_intelligence_run"},
        "input_scope": {
            "flow_plan": {
                "source": "topology_constraint",
                "summary": "将执行 8 步",
                "planned_platforms": ["kimi"],
                "steps": [],
            }
        },
    }
    packet = build_dashboard_context_packet(state)
    assert packet.flow_plan_summary == "将执行 8 步"
    assert list(packet.flow_planned_platforms) == ["kimi"]
