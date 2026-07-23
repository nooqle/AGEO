"""Auth path must not hydrate session/message graphs (Wave Switch F4 / MemoryError)."""

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

    # Nested noload on Organization.users / entities (third option's context)
    org_opt = next(o for o in opts if "organization" in str(getattr(o, "path", "")))
    org_ctx = getattr(org_opt, "context", ()) or ()
    # parent selectin + two noloads for users/entities
    assert len(org_ctx) >= 3


def test_session_messages_not_eager_default():
    from app.models.session import Session

    rel = Session.__mapper__.relationships["messages"]
    assert rel.lazy not in {"selectin", "joined"}


def test_user_sessions_not_eager_default():
    from app.models.user import User

    rel = User.__mapper__.relationships["sessions"]
    assert rel.lazy not in {"selectin", "joined"}
