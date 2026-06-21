import os
from types import SimpleNamespace
from uuid import uuid4

from openpyxl import Workbook

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.services.brand_association_circle_variant import (  # noqa: E402
    build_amway_association_context,
)
from app.services.entity_service import EntityService  # noqa: E402
from app.tools.question_generation import (
    build_association_circle_question_matrix,
    normalize_uploaded_question_payload,
)
from app.services.monitoring_plan_service import MonitoringPlanService
from app.services.table_intake_service import TableIntakeService
from app.models.file_metadata import FileMetadata
from app.services.brand_intelligence_run_service import (  # noqa: E402
    _build_brand_run_initial_state,
)
from app.workflow.nodes_a4 import _question_metadata_for_fetch_result


def test_association_circle_question_matrix_has_required_tags():
    questions = build_association_circle_question_matrix()

    assert len(questions) == 16
    assert {question["probe_type"] for question in questions} == {
        "无品牌自然探针",
        "路径探针",
        "品牌锚定探针",
        "机会探针",
    }
    assert {"25-35 健康预防期", "35-50 初老期", "50-65 人生转换期", "活力银发"} == {
        question["audience_segment"] for question in questions
    }
    assert all(question["center_terms"] for question in questions)
    assert all(
        question["source"] == "association_circle_matrix" for question in questions
    )
    assert {
        "安利社群外显",
        "科技安利",
        "安利人品牌表达",
        "事业机会作为多段人生再出发平台",
        "长寿时代",
    }.issubset({question["opportunity_point"] for question in questions})


def test_uploaded_question_payload_preserves_association_tags():
    simulated, flattened = normalize_uploaded_question_payload(
        [
            {
                "id": "u_001",
                "text": "中年人抗衰除了产品还需要什么生活方式？",
                "audience_segment": "35-50 初老期",
                "core_anxiety": "抗衰焦虑",
                "life_scene": "身体状态变化",
                "opportunity_point": "科技抗衰",
                "probe_type": "路径探针",
                "center_terms": ["安利", "纽崔莱"],
            }
        ]
    )

    assert simulated[0]["audience_segment"] == "35-50 初老期"
    assert simulated[0]["opportunity_point"] == "科技抗衰"
    assert simulated[0]["probe_type"] == "路径探针"
    assert flattened[0]["center_terms"] == ["安利", "纽崔莱"]


def test_uploaded_question_payload_preserves_gravity_table_tags():
    simulated, flattened = normalize_uploaded_question_payload(
        [
            {
                "id": "Q01",
                "text": "50 岁以后怎么做长期健康管理？",
                "mother_theme": "身体透支与长期健康管理",
                "question_type": "不点名",
                "mentions_amway": "否",
                "life_stage": "50-65 人生转换期",
                "four_have": "有健康",
                "touchpoint": "长期健康管理",
                "monitoring_purpose": "观察健康管理是否自然连接安利",
                "question_set_version": "uploaded_amway_gravity_circle_v1",
            }
        ],
        association_mode=True,
        center_terms=["安利"],
    )

    assert simulated[0]["mother_theme"] == "身体透支与长期健康管理"
    assert simulated[0]["question_type"] == "不点名"
    assert simulated[0]["life_stage"] == "50-65 人生转换期"
    assert simulated[0]["touchpoint"] == "长期健康管理"
    assert flattened[0]["monitoring_purpose"] == "观察健康管理是否自然连接安利"
    assert flattened[0]["metadata_status"] == "inferred_needs_review"


def test_table_intake_xlsx_selects_question_sheet_and_preserves_amway_columns(tmp_path):
    workbook = Workbook()
    readme = workbook.active
    readme.title = "ReadMe_方法说明"
    readme.append(["步骤", "说明"])
    readme.append(["1", "不是问题表"])
    questions = workbook.create_sheet("Questions_32题库")
    questions.append(
        [
            "QID",
            "母题",
            "模拟问题",
            "问题类型",
            "是否点名安利",
            "年龄/人生阶段",
            "对应四有",
            "对应触点",
            "主要监测目的",
        ]
    )
    questions.append(
        [
            "Q01",
            "身体透支与长期健康管理",
            "50 岁以后怎么做长期健康管理？",
            "不点名",
            "否",
            "50-65 人生转换期",
            "有健康",
            "长期健康管理",
            "观察健康管理是否自然连接安利",
        ]
    )
    path = tmp_path / "amway-questions.xlsx"
    workbook.save(path)
    workbook.close()

    parsed = TableIntakeService(None)._parse_file(  # noqa: SLF001
        FileMetadata(
            id=uuid4(),
            name="amway-questions.xlsx",
            size=path.stat().st_size,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            path=str(path),
            url="/api/v1/files/test",
        )
    )
    result = TableIntakeService(None)._deterministic_classify(parsed)  # noqa: SLF001
    question = result["normalized_payload"]["questions"][0]

    assert parsed.sheet_name == "Questions_32题库"
    assert result["table_kind"] == "question_list"
    assert question["id"] == "Q01"
    assert question["mother_theme"] == "身体透支与长期健康管理"
    assert question["question_type"] == "不点名"
    assert question["life_stage"] == "50-65 人生转换期"
    assert question["touchpoint"] == "长期健康管理"
    assert question["monitoring_purpose"] == "观察健康管理是否自然连接安利"
    path.unlink()
    assert not path.exists()


def test_uploaded_question_payload_infers_missing_association_tags_in_circle_mode():
    simulated, flattened = normalize_uploaded_question_payload(
        [
            {
                "id": "u_002",
                "text": "退休后怎么避免孤独，并找到一个能长期陪伴的健康社群？",
            }
        ],
        association_mode=True,
        center_terms=["安利", "安利中国", "纽崔莱"],
    )

    assert simulated[0]["audience_segment"] == "活力银发"
    assert simulated[0]["opportunity_point"] == "安利社群外显"
    assert simulated[0]["probe_type"] == "路径探针"
    assert simulated[0]["metadata_status"] == "inferred_needs_review"
    assert simulated[0]["metadata_missing_fields"] == []
    assert flattened[0]["question_set_version"] == "uploaded_association_circle_v1"


def test_a4_fetch_result_metadata_projection_keeps_question_context():
    metadata = _question_metadata_for_fetch_result(
        {
            "id": "ac_001",
            "text": "提到安利，你最先想到什么？",
            "category": "品牌联想圈层",
            "intent": "识别 AI 回答中的品牌联想距离和连接路径",
            "stage": "认知",
            "source": "association_circle_matrix",
            "audience_segment": "35-50 初老期",
            "core_anxiety": "抗衰焦虑",
            "life_scene": "身体状态变化",
            "opportunity_point": "科技抗衰",
            "probe_type": "品牌锚定探针",
            "mother_theme": "安利品牌基础认知",
            "question_type": "基础认知",
            "mentions_amway": "是",
            "life_stage": "通用",
            "four_have": "有健康",
            "touchpoint": "品牌基础认知",
            "monitoring_purpose": "观察安利第一联想",
            "center_terms": ["安利", "纽崔莱"],
        }
    )

    assert metadata["audience_segment"] == "35-50 初老期"
    assert metadata["opportunity_point"] == "科技抗衰"
    assert metadata["probe_type"] == "品牌锚定探针"
    assert metadata["mother_theme"] == "安利品牌基础认知"
    assert metadata["question_type"] == "基础认知"
    assert metadata["monitoring_purpose"] == "观察安利第一联想"
    assert metadata["user_intent"] == metadata["intent"]
    assert metadata["decision_stage"] == metadata["stage"]


def test_monitoring_question_set_normalize_preserves_association_tags():
    normalized = MonitoringPlanService.normalize_questions(
        [
            {
                "id": "ac_001",
                "text": "提到安利，你最先想到什么？",
                "category": "品牌联想圈层",
                "intent": "识别 AI 回答中的品牌联想距离和连接路径",
                "stage": "认知",
                "audience_segment": "35-50 初老期",
                "opportunity_point": "科技抗衰",
                "probe_type": "品牌锚定探针",
                "center_terms": ["安利", "纽崔莱"],
            }
        ]
    )

    assert normalized[0]["question_text"] == "提到安利，你最先想到什么？"
    assert normalized[0]["scene"] == "品牌联想圈层"
    assert normalized[0]["audience_segment"] == "35-50 初老期"
    assert normalized[0]["center_terms"] == ["安利", "纽崔莱"]


def test_amway_dashboard_variant_builds_circle_workflow_state():
    entity_id = uuid4()
    run_id = uuid4()
    context = build_amway_association_context(name="安利中国", domain="")
    state = _build_brand_run_initial_state(
        run=SimpleNamespace(
            id=run_id,
            entity_id=entity_id,
            created_by_user_id=uuid4(),
            input_scope={},
            analysis_mode="panorama",
            run_goal="分析当前品牌在 AI 平台里的表现",
        ),
        entity=SimpleNamespace(
            id=entity_id,
            name="安利中国",
            domain="",
            industry="健康",
            description="",
        ),
        session_uuid=uuid4(),
        task_id=uuid4(),
        task_run_uuid=uuid4(),
    )

    assert context["dashboard_variant"] == "amway_association_circle"
    assert state["analysis_mode"] == "brand_association_circle"
    assert state["user_decisions"]["a3_mode"] == "brand_association_circle"
    assert state["dashboard_context"]["center_terms"][:3] == [
        "安利",
        "安利中国",
        "纽崔莱",
    ]
    assert state["next_required_action"]["tool_args"]["analysis_mode"] == (
        "brand_association_circle"
    )


def test_amway_dashboard_run_state_routes_uploaded_questions_to_a3_list_mode():
    entity_id = uuid4()
    state = _build_brand_run_initial_state(
        run=SimpleNamespace(
            id=uuid4(),
            entity_id=entity_id,
            created_by_user_id=uuid4(),
            input_scope={
                "dashboard_variant": "amway_association_circle",
                "uploaded_question_file_id": str(uuid4()),
                "uploaded_question_source": "amway-questions.csv",
                "uploaded_questions": [
                    {
                        "id": "u_001",
                        "text": "退休后怎么避免孤独，并找到长期陪伴的健康社群？",
                    }
                ],
            },
            analysis_mode="brand_association_circle",
            run_goal="生成安利品牌联想圈层报告",
        ),
        entity=SimpleNamespace(
            id=entity_id,
            name="安利",
            domain="",
            industry="健康",
            description="",
        ),
        session_uuid=uuid4(),
        task_id=uuid4(),
        task_run_uuid=uuid4(),
    )

    assert state["user_decisions"]["a3_mode"] == "uploaded_list"
    assert state["table_intake_result"]["table_kind"] == "question_list"
    assert state["table_intake_result"]["source_file"]["name"] == (
        "amway-questions.csv"
    )
    assert state["table_intake_result"]["source_file"]["file_id"]
    assert state["table_intake_result"]["normalized_payload"]["questions"][0]["id"] == (
        "u_001"
    )
    assert state["next_required_action"]["tool_args"]["mode"] == "uploaded_list"
    assert state["next_required_action"]["metadata"]["uploaded_question_count"] == 1


def test_entity_projection_includes_amway_association_context():
    payload = EntityService()._model_to_dict(  # noqa: SLF001
        SimpleNamespace(
            id=uuid4(),
            name="安利中国",
            aliases='["Amway China", "Nutrilite"]',
            domain="amway.com.cn",
            industry="健康",
            description="",
            visibility_scope=SimpleNamespace(value="personal"),
            owner_user_id=None,
            organization_id=None,
            last_analyzed=None,
            status=SimpleNamespace(value="active"),
            created_at=None,
            updated_at=None,
        )
    )

    assert payload["dashboard_variant"] == "amway_association_circle"
    assert payload["association_brand_cluster"] == ["安利", "安利中国", "纽崔莱"]
    assert payload["center_terms"][:3] == ["安利", "安利中国", "纽崔莱"]


def test_entity_projection_keeps_regular_brand_without_amway_context():
    payload = EntityService()._model_to_dict(  # noqa: SLF001
        SimpleNamespace(
            id=uuid4(),
            name="普通品牌",
            aliases=None,
            domain="example-brand.cn",
            industry="消费",
            description="",
            visibility_scope=SimpleNamespace(value="personal"),
            owner_user_id=None,
            organization_id=None,
            last_analyzed=None,
            status=SimpleNamespace(value="active"),
            created_at=None,
            updated_at=None,
        )
    )

    assert "dashboard_variant" not in payload
    assert "association_brand_cluster" not in payload
