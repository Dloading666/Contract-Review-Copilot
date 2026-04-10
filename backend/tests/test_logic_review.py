import pytest

from src.agents import entity_extraction, logic_review


class _FakeResponse:
    def __init__(self, content: str, model: str = "Qwen/Qwen3.5-4B"):
        self.model = model
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


def test_review_clauses_includes_contract_text_and_extended_fields(monkeypatch):
    capture: dict[str, str] = {}

    monkeypatch.setattr(
        logic_review,
        "create_chat_completion",
        lambda **kwargs: capture.update({"prompt": kwargs["messages"][1]["content"]}) or _FakeResponse(
            '[{"clause":"押金条款","severity":"high","risk_level":3,"issue":"押金偏高","suggestion":"协商下调","legal_reference":"《民法典》第585条"}]',
        ),
    )
    monkeypatch.setattr(logic_review, "build_search_context", lambda routing, entities: "法规上下文：北京市押金规则")

    issues = logic_review.review_clauses(
        "第一条 押金不予退还。\n第二条 逾期按每日0.5%收取滞纳金。\n第三条 甲方可随时解除合同。",
        routing={"primary_source": "pgvector"},
        entities={
            "contract_type": "租赁合同",
            "parties": {"lessor": "张三", "lessee": "李四"},
            "property": {"address": "北京市朝阳区"},
            "lease_term": {"duration_text": "12个月"},
            "rent": {"monthly": 8500},
            "deposit": {"amount": 17000, "conditions": "退租返还"},
            "penalty_clause": "两个月租金",
            "late_fee": "逾期按每日0.5%收取滞纳金",
            "termination_clause": "甲方可随时解除合同",
        },
    )

    assert "法规上下文：北京市押金规则" in capture["prompt"]
    assert "合同原文（重点逐条审查）：" in capture["prompt"]
    assert "押金不予退还" in capture["prompt"]
    assert "- 滞纳金条款：逾期按每日0.5%收取滞纳金" in capture["prompt"]
    assert "- 解约条款：甲方可随时解除合同" in capture["prompt"]
    assert issues[0]["level"] == "high"


def test_extract_suspicious_clauses_prefers_risky_sections_for_long_contract():
    filler = "\n".join(f"第{i}条 本条仅说明普通入住事项。" for i in range(1, 80))
    risky_tail = """
第八十条 押金不予退还。
第八十一条 甲方有权随时进入房屋检查。
第八十二条 如乙方提前退租，需支付全部剩余租期租金。
""".strip()
    contract_text = f"{filler}\n{risky_tail}"

    extracted = logic_review._extract_suspicious_clauses(contract_text)

    assert "押金不予退还" in extracted
    assert "甲方有权随时进入房屋检查" in extracted
    assert "需支付全部剩余租期租金" in extracted


def test_rule_based_review_attaches_matched_contract_text():
    issues = logic_review._rule_based_review(
        "月租金：人民币 5000 元\n押金：人民币 17000 元\n违约金：合同总额的200%\n",
    )

    matched_lines = {issue["matched_text"] for issue in issues}
    assert "押金：人民币 17000 元" in matched_lines
    assert "违约金：合同总额的200%" in matched_lines


def test_regex_fallback_extracts_parties_and_amounts_from_uploaded_contract():
    contract_text = """
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
""".strip()

    entities = entity_extraction._regex_fallback(contract_text)

    assert entities["parties"]["lessor"] == "周志远"
    assert entities["parties"]["lessee"] == "赵文静"
    assert entities["property"]["address"] == "成都市锦江区春熙路太古里旁王府大厦B座1201室"
    assert entities["rent"]["monthly"] == 2200
    assert entities["deposit"]["amount"] == 2200
    assert entities["deposit"]["conditions"] == "合同到期归还房屋时退还"
    assert entities["rent"]["payment_cycle"] == "押一付三"


def test_review_clauses_merges_rule_based_risks_when_model_response_is_too_weak(monkeypatch):
    monkeypatch.setattr(
        logic_review,
        "create_chat_completion",
        lambda **kwargs: _FakeResponse(
            '[{"clause":"整体评估","severity":"low","risk_level":1,"issue":"未发现明显风险","suggestion":"仔细阅读后签约","legal_reference":"《民法典》合同编"}]',
        ),
    )
    monkeypatch.setattr(logic_review, "build_search_context", lambda routing, entities: "")

    contract_text = """
甲方（出租方）：周志远（身份证：310101198806127890，已与房东签署托管协议）
乙方（承租方）：赵文静（身份证：500101199705061234）
月租金：人民币 2,200 元
押金：人民币 2,200 元
实际房东已全权委托本公司处理出租事宜，乙方无需联系原房东
乙方逾期支付租金超过5日，视为自动退租，甲方有权立即收回房屋且押金不予退还
如乙方提前退租，须提前45天书面通知，并支付两个月租金作为违约金
如乙方欠费超过一个月，甲方有权断水断电且不构成违约
争议解决：提交甲方所在地仲裁委员会仲裁（一裁终局）
""".strip()

    issues = logic_review.review_clauses(
        contract_text,
        routing={"primary_source": "pgvector"},
        entities={
            "contract_type": "租赁合同",
            "parties": {"lessor": "周志远", "lessee": "赵文静"},
            "property": {"address": "成都市锦江区春熙路太古里旁王府大厦B座1201室"},
            "lease_term": {"duration_text": "12个月"},
            "rent": {"monthly": 2200},
            "deposit": {"amount": 2200, "conditions": "合同到期归还房屋时退还"},
            "penalty_clause": "支付两个月租金作为违约金",
        },
    )

    clauses = {issue["clause"] for issue in issues}
    assert "整体评估" not in clauses
    assert "出租权限与房东身份条款" in clauses
    assert "押金退还条款" in clauses
    assert "断水断电免责条款" in clauses


@pytest.mark.parametrize(
    ("contract_text", "expected_clause"),
    [
        ("甲方有权根据市场情况调整租金。", "租金调整条款"),
        ("如到期前30日未书面通知，则视为自动续租。", "自动续租条款"),
        ("房屋主体结构及管道维修均由乙方负责。", "维修责任条款"),
        ("甲方可以随时解除合同并收回房屋。", "解约权条款"),
        ("乙方提前30天书面通知方可退租。", "提前通知条款"),
        ("禁止转租，违者支付违约金5000元。", "禁止转租违约条款"),
        ("甲方可以随时进入房屋检查。", "入户检查条款"),
        ("乙方同意办理租金分期并授权征信查询和委托扣款。", "租金贷条款"),
        ("租期为24个月，押金2000元无息退还。", "押金利息条款"),
        ("房屋按现状出租，甲方不承担任何维修责任。", "现状交付条款"),
        ("如乙方提前退租，应支付全部剩余租期租金。", "提前退租赔偿条款"),
        ("双方确认一切口头承诺无效，以本合同为准。", "口头承诺条款"),
    ],
)
def test_rule_based_review_detects_new_rule_families(contract_text, expected_clause):
    issues = logic_review._rule_based_review(contract_text)
    assert expected_clause in {issue["clause"] for issue in issues}
