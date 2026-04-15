"""
Dimension-specific prompt fragments for targeted clause analysis.

These can be injected into REVIEW_PROMPT's rag_context or used as
standalone prompts when analysing a single risk dimension in isolation.
"""
from __future__ import annotations

DIMENSION_PROMPTS: dict[str, str] = {
    "押金": """检查押金相关条款：
- 押金金额是否超过2个月租金（部分城市上限1个月）
- 退还条件是否合理（租期届满、无损坏、无欠费）
- 是否有"押金不退"或"押金冲抵全部违约金"条款
- 退还时限是否明确（建议7日内退还）
- 是否区分正常损耗与人为损坏""",

    "违约金": """检查违约金条款：
- 金额是否超过守约方实际损失的30%
- 是否存在"全额租金"等惩罚性条款
- 违约认定标准是否明确、合理
- 双方违约责任是否对等""",

    "滞纳金": """检查滞纳金条款：
- 日滞纳金折算年化是否超过LPR四倍（当前参考约14.8%/年）
- 计息起算日是否合理（应给予3-5日宽限期）
- 是否有复利或罚上加罚的安排""",

    "解约": """检查解约条款：
- 是否有单方随时解除权（只对甲方）
- 提前解约的告知时限是否不对等
- 违约退租的赔偿范围是否超出实际损失
- 不可抗力情形下是否允许免责解约""",

    "自动续租": """检查自动续租/续约条款：
- 是否以沉默/未通知视为续约
- 通知期限是否仅约束乙方
- 续约后租金是否自动上涨且涨幅不明""",

    "维修": """检查维修责任条款：
- 主体结构、管道、屋面等大修是否由出租方承担
- 家电大修/更换责任是否归乙方
- 是否有"现状出租"免责条款
- 报修响应时限是否明确""",

    "转租": """检查转租条款：
- 是否完全禁止转租（过严限制）
- 违约金是否与禁止转租直接绑定且金额过高
- 是否区分"整体转租"与"合租/分租""""，

    "入户检查": """检查入户检查条款：
- 是否允许甲方随时入户（侵犯居住安宁权）
- 是否要求提前通知（建议至少24小时）
- 紧急情况定义是否合理""",

    "费用分摊": """检查水电及公共费用条款：
- 水电气费计量方式是否明确
- 公摊费用（物业费/电梯/垃圾处理）归属是否清晰
- 是否有不合理的管理费或服务费""",

    "格式条款": """检查格式条款与显失公平条款：
- 是否有加重乙方责任、排除乙方主要权利的条款
- 是否有"最终解释权归甲方"等单方授权
- 是否有强制捆绑销售其他服务的条款
- 是否符合《民法典》第497条关于格式条款无效的规定""",
}


def get_dimension_hint(dimension_key: str) -> str:
    """Return the prompt hint for a named dimension, or empty string if unknown."""
    return DIMENSION_PROMPTS.get(dimension_key, "")


def list_dimensions() -> list[str]:
    """Return all available dimension keys."""
    return list(DIMENSION_PROMPTS.keys())
