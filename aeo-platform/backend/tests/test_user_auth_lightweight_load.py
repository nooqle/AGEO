"""Auth path must not hydrate session/message graphs (Wave Switch F4 / MemoryError).

Also: must not noload Organization.entities onto the identity map (entity-dup P1).
"""

from __future__ import annotations

from app.services.user_service import _lightweight_user_select


def test_lightweight_user_select_guards_heavy_paths():
    stmt = _lightweight_user_select()
    opts = list(getattr(stmt, "_with_options", ()) or [])
    assert len(opts) >= 3

    paths = [str(getattr(opt, "path", "") or "") for opt in opts]
    joined = " || ".join(paths)
    assert "User.sessions" in joined
    assert "User.owned_entities" in joined
    assert "User.organization" in joined

    # Must noload organization entirely — never selectinload+noload(entities)
    # (that poisons later Organization.entities loads in the same Session).
    org_paths = [p for p in paths if "User.organization" in p]
    assert org_paths
    assert not any("Organization.entities" in p for p in paths)


def test_session_messages_not_eager_default():
    from app.models.session import Session

    rel = Session.__mapper__.relationships["messages"]
    assert rel.lazy not in {"selectin", "joined"}


def test_user_sessions_not_eager_default():
    from app.models.user import User

    rel = User.__mapper__.relationships["sessions"]
    assert rel.lazy not in {"selectin", "joined"}
