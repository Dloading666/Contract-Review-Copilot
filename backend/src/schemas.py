from typing import Optional

from pydantic import BaseModel, Field


class ContractReviewRequest(BaseModel):
    contract_text: str = Field(..., max_length=100000, description="The contract text to review")
    session_id: Optional[str] = Field(None, max_length=128, description="Optional session ID for resuming")
    filename: Optional[str] = Field(None, max_length=255, description="Optional contract filename")


class SendCodeRequest(BaseModel):
    email: str = Field("", description="Email address used for verification")


class PhoneSendCodeRequest(BaseModel):
    phone: str = Field("", description="Phone number used for verification")


class RegisterRequest(BaseModel):
    email: str = Field("", description="Email address used for registration")
    code: str = Field("", description="Verification code sent to the email")
    password: str = Field("", description="Password for the new account")


class LoginRequest(BaseModel):
    email: str = Field("", description="Email address used for login")
    password: str = Field("", description="Password for login")


class PhoneLoginRequest(BaseModel):
    phone: str = Field("", description="Phone number used for login")
    code: str = Field("", description="Verification code sent to the phone")


class BindPhoneRequest(BaseModel):
    phone: str = Field("", description="Phone number to bind")
    code: str = Field("", description="Verification code sent to the phone")


class ConfirmRequest(BaseModel):
    confirmed: bool = Field(True, description="Whether the user confirmed to continue")
    contract_text: str = Field("", description="Fallback contract text for resuming aggregation")
    filename: Optional[str] = Field(None, description="Optional contract filename for fallback resume")
    issues: list[dict] = Field(default_factory=list, description="Fallback issues payload for resume")


class ExportReportRequest(BaseModel):
    report_paragraphs: list[str] = Field(..., description="Structured report paragraphs to export")
    filename: Optional[str] = Field(None, description="Optional source filename for the generated report")


class HealthResponse(BaseModel):
    status: str = "ok"


class ReviewSessionResponse(BaseModel):
    session_id: str
    status: str = "ready"


class RechargeOrderCreateRequest(BaseModel):
    amount_fen: int = Field(..., description="Recharge amount in fen")


class ChatRequest(BaseModel):
    message: str = Field("", description="User message")
    contract_text: str = Field("", description="Contract text excerpt")
    risk_summary: str = Field("", description="Risk summary for context")
    review_session_id: str = Field("", description="Review session ID used for quota tracking")
