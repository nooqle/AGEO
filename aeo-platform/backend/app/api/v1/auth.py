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
from app.models.verification_challenge import VerificationPurpose
from app.schemas.auth import (
    LoginRequest,
    OtpLoginRequest,
    RegistrationApplicationApproveRequest,
    RegistrationApplicationCreateRequest,
    RegistrationApplicationResponse,
    RegistrationApplicationReviewRequest,
    TokenResponse,
    VerificationSendCodeRequest,
    VerificationSendCodeResponse,
)
from app.schemas.user import UserCreate, UserResponse
from app.services.registration_application_service import RegistrationApplicationService
from app.services.user_service import UserService
from app.services.verification_service import VerificationService
from app.services.verification_service import VerificationThrottleError
from app.services.verification_delivery_service import VerificationDeliveryError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_410_GONE)
async def register_user(_: UserCreate):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="请改用验证码注册申请流程，注册后需等待后台审核开通",
    )


@router.post("/verification/send-code", response_model=VerificationSendCodeResponse)
async def send_verification_code(
    payload: VerificationSendCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    service = VerificationService(db)
    try:
        response = await service.send_code(
            channel=payload.channel,
            target=payload.target.strip(),
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
    service = RegistrationApplicationService(db)
    try:
        application = await service.create_application(
            email=payload.email.strip().lower() if payload.email else None,
            phone=payload.phone.strip() if payload.phone else None,
            verification_channel=payload.verification_channel,
            verification_target=payload.verification_target.strip(),
            verification_code=payload.verification_code.strip(),
            organization_name=payload.organization_name.strip(),
            job_title=payload.job_title.strip(),
            applicant_name=(
                payload.applicant_name.strip() if payload.applicant_name else None
            ),
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
    verification = VerificationService(db)
    target = (
        payload.target.strip().lower()
        if payload.channel.value == "email"
        else payload.target.strip()
    )
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
    if user is None:
        application = await RegistrationApplicationService(
            db
        ).get_latest_application_by_identity(
            channel=payload.channel,
            target=target,
        )
        if (
            application
            and application.status == RegistrationApplicationStatus.PENDING_REVIEW
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号待审核开通",
            )
        if application and application.status == RegistrationApplicationStatus.REJECTED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号审核未通过，请联系管理员",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账号不存在，请先提交注册申请",
        )

    if not user.is_active or user.status != UserStatus.ACTIVE:
        if user.status == UserStatus.PENDING_REVIEW:
            detail = "账号待审核开通"
        elif user.status == UserStatus.REJECTED:
            detail = "账号审核未通过，请联系管理员"
        else:
            detail = "账号已停用，请联系管理员"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )

    token = create_access_token(str(user.id), user.email, user.phone)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user=Depends(get_current_user)):
    return current_user
