from src.vectorstore.curated_knowledge import CURATED_LEGAL_KNOWLEDGE
from src.vectorstore.seed import LEGAL_KNOWLEDGE, _entry_metadata


def test_curated_knowledge_expands_contract_review_coverage():
    assert len(LEGAL_KNOWLEDGE) >= 80
    assert len(CURATED_LEGAL_KNOWLEDGE) >= 25

    categories = {entry["category"] for entry in CURATED_LEGAL_KNOWLEDGE}
    assert "regulation" in categories
    assert "judicial_interpretation" in categories
    assert "consumer_contract" in categories
    assert "evidence_practice" in categories

    titles = {entry["title"] for entry in CURATED_LEGAL_KNOWLEDGE}
    assert "预付式消费司法解释 - 退款、转卡与霸王条款" in titles
    assert "网络交易监督管理办法 - 自动续费与自动展期" in titles
    assert "城镇房屋租赁司法解释 - 转租与次承租人保护" in titles


def test_curated_entries_have_retrieval_metadata():
    for entry in CURATED_LEGAL_KNOWLEDGE:
        metadata = _entry_metadata(entry, source_key="test-key")

        assert metadata["title"] == entry["title"]
        assert metadata["category"]
        assert metadata["jurisdiction"]
        assert metadata["source_name"]
        assert metadata["source_url"].startswith("https://")
        assert metadata["article_refs"]
        assert metadata["risk_tags"]
        assert metadata["contract_types"]
        assert metadata["source_key"] == "test-key"
