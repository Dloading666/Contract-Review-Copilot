from typing import TypedDict, NotRequired


class ReviewState(TypedDict):
    """LangGraph state for the contract review pipeline."""

    messages: list[str]
    contract_text: str
    session_id: str
    extracted_entities: NotRequired[dict | None]
    routing_decision: NotRequired[dict | None]
    logic_review_results: NotRequired[list[dict] | None]
    needs_human_review: NotRequired[bool]
    human_feedback: NotRequired[dict | None]
    final_report: NotRequired[str]
    stream_buffer: NotRequired[dict[str, str]]
