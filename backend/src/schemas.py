from typing import Optional

from pydantic import BaseModel, Field


class ContractReviewRequest(BaseModel):
    contract_text: str = Field(..., description="The contract text to review")
    session_id: Optional[str] = Field(None, description="Optional session ID for resuming")


class SendCodeRequest(BaseModel):
    email: str = Field("", description="Email address used for verification")


class RegisterRequest(BaseModel):
    email: str = Field("", description="Email address used for registration")
    code: str = Field("", description="Verification code sent to the email")
    password: str = Field("", description="Password for the new account")


class LoginRequest(BaseModel):
    email: str = Field("", description="Email address used for login")
    password: str = Field("", description="Password for login")


class ConfirmRequest(BaseModel):
    confirmed: bool = Field(True, description="Whether the user confirmed to continue")


class ExportReportRequest(BaseModel):
    report_paragraphs: list[str] = Field(..., description="Structured report paragraphs to export")
    filename: Optional[str] = Field(None, description="Optional source filename for the generated report")


class HealthResponse(BaseModel):
    status: str = "ok"


class ReviewSessionResponse(BaseModel):
    session_id: str
    status: str = "ready"
