from types import SimpleNamespace
from uuid import uuid4

from app.models.user import UserRole
from app.services.access_scope_service import AccessScopeService


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
