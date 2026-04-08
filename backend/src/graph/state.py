from typing import NotRequired, TypedDict


class ReviewState(TypedDict):
    """LangGraph state for the contract review pipeline."""

    contract_text: str
    session_id: str
    model_key: NotRequired[str | None]
    extracted_entities: NotRequired[dict | None]
    routing_decision: NotRequired[dict | None]
    logic_review_results: NotRequired[list[dict] | None]
    breakpoint_data: NotRequired[dict | None]
    final_report: NotRequired[list[str] | None]
