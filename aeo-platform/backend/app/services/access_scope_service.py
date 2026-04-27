from __future__ import annotations

from sqlalchemy import and_, false, or_, true

from app.models.entity import Entity, EntityVisibilityScope
from app.models.monitoring_schedule import MonitoringSchedule
from app.models.session import Session
from app.models.task import AnalysisTask
from app.models.user import User, UserRole


class AccessScopeService:
    """Shared visibility rules for personal / organization scoped resources."""

    @staticmethod
    def entity_visibility_filter(
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ):
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return true()
        filters = [
            Entity.owner_user_id == user.id,
            Entity.sessions.any(Session.user_id == user.id),
        ]
        if user.organization_id:
            filters.append(
                and_(
                    Entity.visibility_scope == EntityVisibilityScope.ORGANIZATION,
                    Entity.organization_id == user.organization_id,
                )
            )
        return or_(*filters) if filters else false()

    @staticmethod
    def session_visibility_filter(
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ):
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return true()
        filters = [Session.user_id == user.id]
        if user.organization_id:
            filters.append(
                Session.entity.has(
                    and_(
                        Entity.visibility_scope == EntityVisibilityScope.ORGANIZATION,
                        Entity.organization_id == user.organization_id,
                    )
                )
            )
        return or_(*filters) if filters else false()

    @staticmethod
    def task_visibility_filter(
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ):
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return true()
        filters = [AnalysisTask.user_id == user.id]
        if user.organization_id:
            filters.append(
                AnalysisTask.entity.has(
                    and_(
                        Entity.visibility_scope == EntityVisibilityScope.ORGANIZATION,
                        Entity.organization_id == user.organization_id,
                    )
                )
            )
        return or_(*filters) if filters else false()

    @staticmethod
    def schedule_visibility_filter(
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ):
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return true()
        filters = [MonitoringSchedule.user_id == user.id]
        if user.organization_id:
            filters.append(
                MonitoringSchedule.entity.has(
                    and_(
                        Entity.visibility_scope == EntityVisibilityScope.ORGANIZATION,
                        Entity.organization_id == user.organization_id,
                    )
                )
            )
        return or_(*filters) if filters else false()

    @staticmethod
    def can_access_entity(
        entity: Entity | None,
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ) -> bool:
        if entity is None:
            return False
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return True
        if entity.owner_user_id == user.id:
            return True
        if (
            user.organization_id
            and entity.visibility_scope == EntityVisibilityScope.ORGANIZATION
            and entity.organization_id == user.organization_id
        ):
            return True
        return False

    @staticmethod
    def can_manage_entity(
        entity: Entity | None,
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ) -> bool:
        if entity is None:
            return False
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return True
        if entity.owner_user_id == user.id:
            return True
        if entity.owner_user_id is None:
            return any(session.user_id == user.id for session in entity.sessions)
        return False

    @staticmethod
    def can_access_session(
        session: Session | None,
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ) -> bool:
        if session is None:
            return False
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return True
        if session.user_id == user.id:
            return True
        return AccessScopeService.can_access_entity(
            session.entity,
            user,
            allow_internal_admin_bypass=allow_internal_admin_bypass,
        )

    @staticmethod
    def can_access_task(
        task: AnalysisTask | None,
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ) -> bool:
        if task is None:
            return False
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return True
        if task.user_id == user.id:
            return True
        return AccessScopeService.can_access_entity(
            task.entity,
            user,
            allow_internal_admin_bypass=allow_internal_admin_bypass,
        )

    @staticmethod
    def can_access_schedule(
        schedule: MonitoringSchedule | None,
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ) -> bool:
        if schedule is None:
            return False
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return True
        if schedule.user_id == user.id:
            return True
        return AccessScopeService.can_access_entity(
            schedule.entity,
            user,
            allow_internal_admin_bypass=allow_internal_admin_bypass,
        )

    @staticmethod
    def can_manage_schedule(
        schedule: MonitoringSchedule | None,
        user: User,
        *,
        allow_internal_admin_bypass: bool = True,
    ) -> bool:
        if schedule is None:
            return False
        if allow_internal_admin_bypass and user.role == UserRole.INTERNAL_ADMIN:
            return True
        return schedule.user_id == user.id
