from pydantic import BaseModel, Field
from typing import Optional


class ContractReviewRequest(BaseModel):
    contract_text: str = Field(..., description="The contract text to review")
    model: Optional[str] = Field(None, description="Optional model key for this review session")
    session_id: Optional[str] = Field(None, description="Optional session ID for resuming")


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
