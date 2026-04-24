from typing import Literal, Optional

from pydantic import BaseModel, Field


class ContractReviewRequest(BaseModel):
    contract_text: str = Field(..., max_length=100000, description="The contract text to review")
    session_id: Optional[str] = Field(None, max_length=128, description="Optional session ID for resuming")
    filename: Optional[str] = Field(None, max_length=255, description="Optional contract filename")
    review_mode: Literal["light", "deep"] = Field("deep", description="Whether to run only the initial scan or the full deep scan")


class SendCodeRequest(BaseModel):
    email: str = Field("", description="Email address used for verification")
    website: str = Field("", description="Honeypot field used for anti-bot protection")
    client_elapsed_ms: Optional[int] = Field(None, description="Milliseconds spent before requesting the verification code")
    captcha_token: Optional[str] = Field(None, description="Optional captcha token for bot protection")


class PasswordResetCodeRequest(BaseModel):
    email: str = Field("", description="Email address used for password reset")


class RegisterRequest(BaseModel):
    email: str = Field("", description="Email address used for registration")
    code: str = Field("", description="Verification code sent to the email")
    password: str = Field("", description="Password for the new account")
    website: str = Field("", description="Honeypot field used for anti-bot protection")
    client_elapsed_ms: Optional[int] = Field(None, description="Milliseconds spent before submitting registration")
    captcha_token: Optional[str] = Field(None, description="Optional captcha token for bot protection")


class LoginRequest(BaseModel):
    email: str = Field("", description="Email address used for login")
    password: str = Field("", description="Password for login")


class SecurityResetPasswordRequest(BaseModel):
    code: str = Field("", description="Email verification code used for password reset")
    new_password: str = Field("", description="New password for the current account")


class PublicPasswordResetRequest(BaseModel):
    email: str = Field("", description="Email address used for password reset")
    code: str = Field("", description="Password reset verification code")
    new_password: str = Field("", description="New password for the account")


class ConfirmRequest(BaseModel):
    confirmed: bool = Field(True, description="Whether the user confirmed to continue")
    contract_text: str = Field("", description="Fallback contract text for resuming aggregation")
    filename: Optional[str] = Field(None, description="Optional contract filename for fallback resume")
    issues: list[dict] = Field(default_factory=list, description="Fallback issues payload for resume")


class DeepReviewRequest(BaseModel):
    contract_text: str = Field(..., max_length=100000, description="Contract text used to resume deep review")
    session_id: Optional[str] = Field(None, max_length=128, description="Existing review session ID")
    issues: list[dict] = Field(default_factory=list, description="Current initial review issues")


class ExportReportRequest(BaseModel):
    report_paragraphs: list[str] = Field(..., description="Structured report paragraphs to export")
    filename: Optional[str] = Field(None, description="Optional source filename for the generated report")


class HealthResponse(BaseModel):
    status: str = "ok"


class ReviewSessionResponse(BaseModel):
    session_id: str
    status: str = "ready"


class ChatRequest(BaseModel):
    message: str = Field("", description="User message")
    contract_text: str = Field("", description="Contract text excerpt")
    risk_summary: str = Field("", description="Risk summary for context")
    review_session_id: str = Field("", description="Review session ID")
