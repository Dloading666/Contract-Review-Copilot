import pytest

from src.graph import review_graph


@pytest.mark.asyncio
async def test_run_review_stream_emits_breakpoint_sequence(monkeypatch):
    async def no_sleep(_: float):
        return None

    monkeypatch.setattr(review_graph.asyncio, 'sleep', no_sleep)
    monkeypatch.setattr(review_graph, 'extract_entities', lambda contract_text: {
        'contract_type': '租赁合同',
        'parties': {'lessor': '张三', 'lessee': '李四'},
        'property': {'address': '北京市朝阳区', 'area': '45'},
        'rent': {'monthly': 8500},
        'deposit': {'amount': 17000, 'conditions': '退租返还'},
        'lease_term': {'duration_text': '12个月'},
        'penalty_clause': '两个月租金',
    })
    monkeypatch.setattr(review_graph, 'decide_routing', lambda contract_text, entities: {
        'primary_source': 'pgvector',
        'secondary_source': None,
        'reason': '测试路由',
        'confidence': 0.9,
        'local_context': '',
        'legal_focus': ['押金退还'],
        'pgvector_results': [],
    })
    monkeypatch.setattr(review_graph, 'review_clauses', lambda contract_text, routing, entities: [
        {
            'clause': '押金条款',
            'level': 'high',
            'risk_level': 3,
            'issue': '押金过高',
            'suggestion': '降低押金',
            'legal_reference': '《民法典》第585条',
        },
        {
            'clause': '违约金条款',
            'level': 'critical',
            'risk_level': 5,
            'issue': '违约金过高',
            'suggestion': '降为一个月租金',
            'legal_reference': '《民法典》第585条',
        },
    ])
    review_graph.get_review_graph.cache_clear()

    events = []
    async for event in review_graph.run_review_stream('合同文本', 'session-1'):
        events.append(event)

    assert [event['event'] for event in events] == [
        'review_started',
        'entity_extraction',
        'routing',
        'logic_review',
        'logic_review',
        'breakpoint',
    ]
    assert events[-1]['data']['issues'][0]['clause'] == '押金条款'
