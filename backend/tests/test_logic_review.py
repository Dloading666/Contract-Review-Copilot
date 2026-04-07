from src.agents import entity_extraction, logic_review


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [type('Choice', (), {'message': type('Message', (), {'content': content})()})()]


def test_review_clauses_includes_rag_context(monkeypatch):
    capture: dict[str, str] = {}
    monkeypatch.setattr(
        logic_review,
        'create_chat_completion',
        lambda **kwargs: capture.update({'prompt': kwargs['messages'][1]['content']}) or _FakeResponse(
            '[{"clause":"押金条款","severity":"high","risk_level":3,"issue":"押金偏高","suggestion":"协商下调","legal_reference":"《民法典》第585条"}]',
        ),
    )
    monkeypatch.setattr(logic_review, 'build_search_context', lambda routing, entities: '法规上下文：北京市押金规则')

    issues = logic_review.review_clauses(
      '合同文本',
      routing={'primary_source': 'pgvector'},
      entities={
          'contract_type': '租赁合同',
          'parties': {'lessor': '张三', 'lessee': '李四'},
          'property': {'address': '北京市朝阳区'},
          'lease_term': {'duration_text': '12个月'},
          'rent': {'monthly': 8500},
          'deposit': {'amount': 17000, 'conditions': '退租返还'},
          'penalty_clause': '两个月租金',
      },
    )

    assert '法规上下文：北京市押金规则' in capture['prompt']
    assert issues[0]['level'] == 'high'
    assert issues[0]['severity'] == 'high'
    assert issues[0]['matched_text'] == ''


def test_rule_based_review_attaches_matched_contract_text():
    issues = logic_review._rule_based_review(
        '月租金：人民币 5000 元\n押金：人民币 17000 元\n违约金：合同总额的200%\n',
    )

    matched_lines = {issue['matched_text'] for issue in issues}
    assert '押金：人民币 17000 元' in matched_lines
    assert '违约金：合同总额的200%' in matched_lines


def test_regex_fallback_extracts_parties_and_amounts_from_uploaded_contract():
    contract_text = '''
房屋租赁合同
甲方（出租方）：周志远（身份证：310101198806127890，已与房东签署托管协议）
乙方（承租方）：赵文静（身份证：500101199705061234）
房屋地址：成都市锦江区春熙路太古里旁王府大厦B座1201室
房屋面积：50 平方米
月租金：人民币 2,200 元
租金支付方式：押一付三
押金：人民币 2,200 元
押金退还条件：合同到期归还房屋时退还
租赁开始日期：2024年10月1日
租赁结束日期：2025年9月30日
如乙方提前退租，须提前45天书面通知，并支付两个月租金作为违约金
'''.strip()

    entities = entity_extraction._regex_fallback(contract_text)

    assert entities['parties']['lessor'] == '周志远'
    assert entities['parties']['lessee'] == '赵文静'
    assert entities['property']['address'] == '成都市锦江区春熙路太古里旁王府大厦B座1201室'
    assert entities['rent']['monthly'] == 2200
    assert entities['deposit']['amount'] == 2200
    assert entities['deposit']['conditions'] == '合同到期归还房屋时退还'
    assert entities['rent']['payment_cycle'] == '押一付三'


def test_review_clauses_merges_rule_based_risks_when_model_response_is_too_weak(monkeypatch):
    monkeypatch.setattr(
        logic_review,
        'create_chat_completion',
        lambda **kwargs: _FakeResponse(
            '[{"clause":"整体评估","severity":"low","risk_level":1,"issue":"未发现明显风险","suggestion":"仔细阅读后签约","legal_reference":"《民法典》合同编"}]',
        ),
    )
    monkeypatch.setattr(logic_review, 'build_search_context', lambda routing, entities: '')

    contract_text = '''
甲方（出租方）：周志远（身份证：310101198806127890，已与房东签署托管协议）
乙方（承租方）：赵文静（身份证：500101199705061234）
月租金：人民币 2,200 元
押金：人民币 2,200 元
实际房东已全权委托本公司处理出租事宜，乙方无需联系原房东
乙方逾期支付租金超过5日，视为自动退租，甲方有权立即收回房屋且押金不予退还
如乙方提前退租，须提前45天书面通知，并支付两个月租金作为违约金
如乙方欠费超过一个月，甲方有权断水断电且不构成违约
争议解决：提交甲方所在地仲裁委员会仲裁（一裁终局）
'''.strip()

    issues = logic_review.review_clauses(
        contract_text,
        routing={'primary_source': 'pgvector'},
        entities={
            'contract_type': '租赁合同',
            'parties': {'lessor': '周志远', 'lessee': '赵文静'},
            'property': {'address': '成都市锦江区春熙路太古里旁王府大厦B座1201室'},
            'lease_term': {'duration_text': '12个月'},
            'rent': {'monthly': 2200},
            'deposit': {'amount': 2200, 'conditions': '合同到期归还房屋时退还'},
            'penalty_clause': '支付两个月租金作为违约金',
        },
    )

    clauses = {issue['clause'] for issue in issues}
    assert '整体评估' not in clauses
    assert '出租权限与房东身份条款' in clauses
    assert '押金退还条款' in clauses
    assert '断水断电免责条款' in clauses
