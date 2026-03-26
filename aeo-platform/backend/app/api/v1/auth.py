from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_internal_admin_user,
    get_current_user,
    get_db,
)
from app.core.security import create_access_token
from app.models.registration_application import RegistrationApplicationStatus
from app.models.user import UserStatus
from app.models.verification_challenge import VerificationChannel, VerificationPurpose
from app.schemas.auth import (
    InvitationRedeemRequest,
    LoginRequest,
    OtpLoginRequest,
    RegistrationApplicationApproveRequest,
    RegistrationApplicationCreateRequest,
    RegistrationApplicationIssueInviteRequest,
    RegistrationApplicationResponse,
    RegistrationApplicationReviewRequest,
    TokenResponse,
    VerificationSendCodeRequest,
    VerificationSendCodeResponse,
)
from app.schemas.user import UserCreate, UserResponse
from app.services.registration_application_service import RegistrationApplicationService
from app.services.identity_normalization_service import normalize_email, normalize_phone
from app.services.user_service import UserService
from app.services.verification_service import VerificationService
from app.services.verification_service import VerificationThrottleError
from app.services.verification_delivery_service import VerificationDeliveryError

router = APIRouter(prefix="/auth", tags=["auth"])
PENDING_REVIEW_DETAIL = "该邮箱已完成登记，请等待邀请码邮件。"
INVITE_REQUIRED_DETAIL = "该邮箱已登记，请输入邀请码完成开通。"
REGISTER_FIRST_DETAIL = "请先填写公司信息并完成邮箱验证。"
REJECTED_DETAIL = "账号审核未通过，请联系管理员"


def _ensure_email_only(channel: VerificationChannel, action: str) -> None:
    if channel != VerificationChannel.EMAIL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"当前阶段仅支持邮箱验证码{action}",
        )


@router.post("/register", status_code=status.HTTP_410_GONE)
async def register_user(_: UserCreate):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="请改用邮箱登记与邀请码流程",
    )


@router.post("/verification/send-code", response_model=VerificationSendCodeResponse)
async def send_verification_code(
    payload: VerificationSendCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    _ensure_email_only(payload.channel, "发送")
    target = normalize_email(payload.target)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的邮箱地址",
        )
    service = VerificationService(db)
    try:
        response = await service.send_code(
            channel=payload.channel,
            target=target,
            purpose=payload.purpose,
        )
    except VerificationDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except VerificationThrottleError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    return VerificationSendCodeResponse(**response)


@router.post(
    "/registration-applications",
    response_model=RegistrationApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_registration_application(
    payload: RegistrationApplicationCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    _ensure_email_only(payload.verification_channel, "注册")
    verification_target = normalize_email(payload.verification_target)
    if not verification_target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的验证码目标邮箱",
        )
    service = RegistrationApplicationService(db)
    try:
        application = await service.create_application(
            email=normalize_email(payload.email),
            phone=normalize_phone(payload.phone),
            verification_channel=payload.verification_channel,
            verification_target=verification_target,
            verification_code=payload.verification_code.strip(),
            organization_name=payload.organization_name.strip(),
            job_title=payload.job_title.strip(),
            applicant_name=(
                payload.applicant_name.strip() if payload.applicant_name else None
            ),
            company_size=payload.company_size.strip() if payload.company_size else None,
            is_agency=payload.is_agency,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return application


@router.get(
    "/registration-applications",
    response_model=list[RegistrationApplicationResponse],
)
async def list_registration_applications(
    _: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = RegistrationApplicationService(db)
    return await service.list_applications()


@router.post(
    "/registration-applications/{application_id}/approve",
    response_model=RegistrationApplicationResponse,
)
async def approve_registration_application(
    application_id: UUID,
    payload: RegistrationApplicationApproveRequest | None = None,
    current_user: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = RegistrationApplicationService(db)
    try:
        return await service.approve_application(
            application_id=application_id,
            reviewer_user_id=current_user.id,
            organization_id=payload.organization_id if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/registration-applications/{application_id}/issue-invite",
    response_model=RegistrationApplicationResponse,
)
async def issue_registration_application_invite(
    application_id: UUID,
    payload: RegistrationApplicationIssueInviteRequest | None = None,
    current_user: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = RegistrationApplicationService(db)
    try:
        return await service.issue_invite_code(
            application_id=application_id,
            reviewer_user_id=current_user.id,
            organization_id=payload.organization_id if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except VerificationDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post(
    "/registration-applications/{application_id}/reject",
    response_model=RegistrationApplicationResponse,
)
async def reject_registration_application(
    application_id: UUID,
    payload: RegistrationApplicationReviewRequest,
    current_user: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = RegistrationApplicationService(db)
    try:
        return await service.reject_application(
            application_id=application_id,
            reviewer_user_id=current_user.id,
            review_note=payload.review_note,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/login", status_code=status.HTTP_410_GONE)
async def login(_: LoginRequest):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="请改用邮箱或手机号验证码登录",
    )


@router.post("/login/otp", response_model=TokenResponse)
async def otp_login(payload: OtpLoginRequest, db: AsyncSession = Depends(get_db)):
    _ensure_email_only(payload.channel, "登录")
    target = normalize_email(payload.target) or ""
    if not target:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入有效的邮箱地址",
        )
    verification = VerificationService(db)
    challenge = await verification.verify_code(
        channel=payload.channel,
        target=target,
        purpose=VerificationPurpose.LOGIN,
        code=payload.verification_code.strip(),
        consume=True,
    )
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="验证码无效或已过期",
        )

    users = UserService(db)
    user = await users.get_user_by_identity(
        channel=payload.channel.value, target=target
    )
    application_service = RegistrationApplicationService(db)
    if user is None:
        application = await application_service.get_latest_application_by_identity(
            channel=payload.channel,
            target=target,
        )
        if application and application.invite_code_sent_at:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=INVITE_REQUIRED_DETAIL,
            )
        if (
            application
            and application.status == RegistrationApplicationStatus.PENDING_REVIEW
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=PENDING_REVIEW_DETAIL,
            )
        if application and application.status == RegistrationApplicationStatus.REJECTED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=REJECTED_DETAIL,
            )
        if application and application.status == RegistrationApplicationStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已开通，请重新发送登录验证码后登录。",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                PENDING_REVIEW_DETAIL if application is not None else REGISTER_FIRST_DETAIL
            ),
        )

    if not user.is_active or user.status != UserStatus.ACTIVE:
        if user.status == UserStatus.PENDING_REVIEW:
            detail = PENDING_REVIEW_DETAIL
        elif user.status == UserStatus.REJECTED:
            detail = REJECTED_DETAIL
        else:
            detail = "账号已停用，请联系管理员"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

    token = create_access_token(str(user.id), user.email, user.phone)
    return TokenResponse(access_token=token)


@router.post("/invite/redeem", response_model=TokenResponse)
async def redeem_invite_code(
    payload: InvitationRedeemRequest,
    db: AsyncSession = Depends(get_db),
):
    service = RegistrationApplicationService(db)
    try:
        _, user = await service.redeem_invite_code(
            email=payload.email,
            invite_code=payload.invite_code,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    token = create_access_token(str(user.id), user.email, user.phone)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user=Depends(get_current_user)):
    return current_user
