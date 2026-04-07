from pydantic import BaseModel, Field
from typing import Optional


class ContractReviewRequest(BaseModel):
    contract_text: str = Field(..., description="The contract text to review")
    session_id: Optional[str] = Field(None, description="Optional session ID for resuming")


class ConfirmRequest(BaseModel):
    confirmed: bool = Field(True, description="Whether the user confirmed to continue")


class HealthResponse(BaseModel):
    status: str = "ok"


class ReviewSessionResponse(BaseModel):
    session_id: str
    status: str = "ready"
