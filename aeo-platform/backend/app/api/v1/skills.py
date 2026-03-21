"""Skill registry API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.skill import (
    SkillCreateRequest,
    SkillListResponse,
    SkillPublishResponse,
    SkillResponse,
    SkillUpdateRequest,
    SkillVersionResponse,
)
from app.services.skill_registry_service import SkillRegistryService

router = APIRouter(prefix="/skills", tags=["skills"])


def _parse_uuid(value: str, field_name: str = "id") -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        ) from exc


@router.get("", response_model=SkillListResponse)
async def list_skills(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    service = SkillRegistryService(db)
    return {"skills": await service.list_skills()}


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: SkillCreateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = SkillRegistryService(db)
    try:
        return await service.create_skill(
            template_skill_key=payload.template_skill_key,
            display_name=payload.display_name,
            description=payload.description,
            default_params=payload.default_params,
            prompt_overlay=payload.prompt_overlay,
            enabled=payload.enabled,
            created_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    payload: SkillUpdateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    parsed_skill_id = _parse_uuid(skill_id, "skill_id")
    service = SkillRegistryService(db)
    updated = await service.update_skill(
        skill_id=parsed_skill_id,
        updates=payload.model_dump(exclude_unset=True),
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return updated


@router.get("/{skill_id}/versions", response_model=list[SkillVersionResponse])
async def get_skill_versions(
    skill_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    parsed_skill_id = _parse_uuid(skill_id, "skill_id")
    service = SkillRegistryService(db)
    versions = await service.get_versions(parsed_skill_id)
    if not versions:
        skill = await service.get_skill_by_id(parsed_skill_id)
        if skill is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return versions


@router.post("/{skill_id}/publish", response_model=SkillPublishResponse)
async def publish_skill(
    skill_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del current_user
    parsed_skill_id = _parse_uuid(skill_id, "skill_id")
    service = SkillRegistryService(db)
    published = await service.publish_skill(skill_id=parsed_skill_id)
    if published is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    return published

