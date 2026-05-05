from app.workflow.confirmation import (
    resolve_confirmation_selection,
    resolve_known_confirmation_label,
)


def _resolve_option(option_id: str, state_values: dict | None = None):
    return resolve_confirmation_selection(
        selection={"optionId": option_id, "label": option_id},
        option_id=option_id,
        user_content=option_id,
        user_decisions={},
        state_values=state_values or {"session_id": "session-confirmation"},
    )


def test_panorama_fast_confirmation_sets_deterministic_route():
    resolution = _resolve_option("panorama_fast")

    assert resolution.user_decisions["a3_mode"] == "baseline_dynamic"
    assert resolution.user_decisions["fetch_mode_confirmed"] is True
    assert resolution.state_updates["analysis_mode"] == "baseline"
    assert resolution.state_updates["fetch_mode"] == "fast"

    action = resolution.state_updates["next_required_action"]
    assert action["tool_name"] == "question_simulation"
    assert action["tool_args"] == {"mode": "baseline_dynamic"}
    assert action["authority"] == "user_confirmation"


def test_panorama_full_confirmation_sets_full_fetch_mode():
    resolution = _resolve_option("panorama_full")

    assert resolution.user_decisions["a3_mode"] == "baseline_dynamic"
    assert resolution.state_updates["fetch_mode"] == "full"
    assert resolution.state_updates["next_required_action"]["tool_name"] == (
        "question_simulation"
    )


def test_persona_first_confirmation_sets_deterministic_route():
    resolution = _resolve_option("persona_first")

    assert resolution.user_decisions["a3_mode"] == "persona"
    assert resolution.state_updates["analysis_mode"] == "persona"
    assert resolution.state_updates["next_required_action"]["tool_name"] == (
        "persona_generation"
    )


def test_generic_panorama_confirmation_sets_deterministic_route():
    resolution = _resolve_option("panorama")

    assert resolution.user_decisions["a3_mode"] == "baseline_dynamic"
    assert resolution.state_updates["analysis_mode"] == "baseline"
    assert resolution.state_updates["next_required_action"]["tool_name"] == (
        "question_simulation"
    )


def test_fetch_mode_confirmation_continues_to_answer_fetch_when_questions_exist():
    resolution = _resolve_option(
        "fast",
        {
            "session_id": "session-confirmation",
            "questions": [{"id": "q1", "text": "测试问题"}],
        },
    )

    assert resolution.user_decisions["fetch_mode_confirmed"] is True
    assert resolution.state_updates["fetch_mode"] == "fast"
    action = resolution.state_updates["next_required_action"]
    assert action["tool_name"] == "answer_fetch"
    assert action["tool_args"] == {"fetch_mode": "fast"}


def test_generic_scenario_confirmation_routes_to_persona_generation():
    resolution = _resolve_option("scenario")

    assert resolution.user_decisions["a3_mode"] == "persona"
    assert resolution.state_updates["next_required_action"]["tool_name"] == (
        "persona_generation"
    )


def test_generated_confirmation_labels_are_known():
    assert resolve_known_confirmation_label("panorama_fast") == (
        "品牌全景分析（快速模式）"
    )
    assert resolve_known_confirmation_label("panorama") == "品牌全景分析"
    assert resolve_known_confirmation_label("scenario") == "场景细化分析"
    assert resolve_known_confirmation_label("custom_questions") == "我自定义问题"
