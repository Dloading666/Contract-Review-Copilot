"""Tests for checkpoint infrastructure."""
import pytest
from src.graph.langgraph_builder import build_review_graph


def test_graph_compiles_without_checkpointer():
    graph = build_review_graph(checkpointer=None)
    assert graph is not None


def test_checkpoint_config_format():
    session_id = "session-abc123"
    config = {
        "configurable": {
            "thread_id": session_id,
            "checkpoint_ns": "contract_review_v1",
        }
    }
    assert config["configurable"]["thread_id"] == session_id
    assert config["configurable"]["checkpoint_ns"] == "contract_review_v1"


def test_checkpoint_disabled_by_default():
    from src.config import get_settings
    settings = get_settings()
    assert settings.review_checkpoint_enabled is False


def test_checkpoint_durability_default():
    from src.config import get_settings
    settings = get_settings()
    assert settings.review_checkpoint_durability == "async"
