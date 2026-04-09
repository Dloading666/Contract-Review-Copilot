from io import BytesIO

from docx import Document

from src.report_export import build_report_docx


def test_build_report_docx_strips_markdown_and_normalizes_export_text():
    docx_bytes = build_report_docx(
        [
            "## 审查结论",
            "### 风险条款摘要\n\n"
            "🟠 **押金条款**（HIGH）\n\n"
            "问题：提前退租需支付两个月租金作违约金。\n\n"
            "建议：将违约金调整为一个月租金。\n\n"
            "依据：《民法典》第585条",
            "### 免责声明\n\n---\n⚠️ *本报告由 AI 自动生成，仅供参考。*\n📋 *报告生成时间：2026-04-09 10:00:00*",
        ],
        "租房合同.docx",
    )

    document = Document(BytesIO(docx_bytes))
    texts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]

    assert texts[0] == "合同避坑指南"
    assert "来源文件：租房合同" in texts[1]
    assert any(text == "审查结论" for text in texts)
    assert any(text == "风险条款摘要" for text in texts)
    assert any(text == "[高风险] 押金条款（HIGH）" for text in texts)
    assert any(text == "问题：提前退租需支付两个月租金作违约金。" for text in texts)
    assert any(text == "建议：将违约金调整为一个月租金。" for text in texts)
    assert any(text == "依据：《民法典》第585条" for text in texts)
    assert any(text == "[提示] 本报告由 AI 自动生成，仅供参考。" for text in texts)
    assert any(text == "[说明] 报告生成时间：2026-04-09 10:00:00" for text in texts)
    assert all("**" not in text for text in texts)
    assert all("⚠️" not in text and "📋" not in text for text in texts)
