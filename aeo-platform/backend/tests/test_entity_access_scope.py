from types import SimpleNamespace
from uuid import uuid4

from app.models.user import UserRole
from app.services.access_scope_service import AccessScopeService
from app.services.entity_service import classify_entity_hygiene


def test_ownerless_entity_with_user_session_can_be_managed():
    user_id = uuid4()
    entity = SimpleNamespace(
        owner_user_id=None,
        sessions=[SimpleNamespace(user_id=user_id)],
    )
    user = SimpleNamespace(
        id=user_id,
        role=UserRole.CUSTOMER_USER,
    )

    assert AccessScopeService.can_manage_entity(entity, user) is True


def test_ownerless_entity_without_user_session_cannot_be_managed():
    entity = SimpleNamespace(
        owner_user_id=None,
        sessions=[SimpleNamespace(user_id=uuid4())],
    )
    user = SimpleNamespace(
        id=uuid4(),
        role=UserRole.CUSTOMER_USER,
    )

    assert AccessScopeService.can_manage_entity(entity, user) is False


def test_entity_hygiene_marks_internal_runtime_data():
    result = classify_entity_hygiene(
        name="Li Auto Runtime Smoke 20260521",
        domain="smoke.example.com",
        description="runtime smoke entity",
    )

    assert result["is_internal_test_data"] is True
    assert "automation_marker" in result["hygiene_labels"]
    assert "placeholder_domain" in result["hygiene_labels"]


def test_entity_hygiene_marks_corrupted_labels_non_primary():
    result = classify_entity_hygiene(
        name="?" * 4,
        domain="www.lixiang.com",
        description="Official brand workspace",
    )

    assert result["is_internal_test_data"] is True
    assert "corrupted_label" in result["hygiene_labels"]


def test_entity_hygiene_keeps_normal_brand_public():
    result = classify_entity_hygiene(
        name="Li Auto",
        domain="lixiang.com",
        description="Official brand workspace",
    )

    assert result == {
        "is_internal_test_data": False,
        "hygiene_labels": [],
    }
