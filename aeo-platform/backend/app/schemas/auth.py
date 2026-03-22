from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.registration_application import RegistrationApplicationStatus
from app.models.verification_challenge import VerificationChannel, VerificationPurpose


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VerificationSendCodeRequest(BaseModel):
    channel: VerificationChannel
    purpose: VerificationPurpose
    target: str = Field(min_length=3, max_length=255)


class VerificationSendCodeResponse(BaseModel):
    challenge_id: str
    expires_in_seconds: int
    debug_code: str | None = None


class OtpLoginRequest(BaseModel):
    channel: VerificationChannel
    target: str = Field(min_length=3, max_length=255)
    verification_code: str = Field(min_length=4, max_length=12)


class RegistrationApplicationCreateRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    verification_channel: VerificationChannel
    verification_target: str = Field(min_length=3, max_length=255)
    verification_code: str = Field(min_length=4, max_length=12)
    organization_name: str = Field(min_length=2, max_length=255)
    job_title: str = Field(min_length=2, max_length=255)
    applicant_name: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_identity_and_channel(self) -> "RegistrationApplicationCreateRequest":
        if not self.email and not self.phone:
            raise ValueError("邮箱和手机号至少填写一项")
        if self.verification_channel == VerificationChannel.EMAIL:
            if not self.email:
                raise ValueError("邮箱验证码注册时必须填写邮箱")
            if self.verification_target.strip().lower() != self.email.strip().lower():
                raise ValueError("验证码目标邮箱与申请邮箱不一致")
        if self.verification_channel == VerificationChannel.PHONE:
            if not self.phone:
                raise ValueError("手机号验证码注册时必须填写手机号")
            if self.verification_target.strip() != self.phone.strip():
                raise ValueError("验证码目标手机号与申请手机号不一致")
        return self


class RegistrationApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr | None
    phone: str | None
    organization_name: str
    job_title: str
    applicant_name: str | None
    status: RegistrationApplicationStatus
    review_note: str | None
    reviewed_by_user_id: UUID | None
    approved_user_id: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RegistrationApplicationReviewRequest(BaseModel):
    review_note: str | None = Field(default=None, max_length=2000)


class RegistrationApplicationApproveRequest(BaseModel):
    organization_id: UUID | None = None
