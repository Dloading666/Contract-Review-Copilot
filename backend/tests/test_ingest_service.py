import pytest

from src.ocr.ingest_service import UploadedContractFile, ingest_contract_files


def test_ingest_contract_files_merges_images_in_selected_order(monkeypatch):
    files = [
        UploadedContractFile(filename="page-1.png", content=b"img-1", content_type="image/png"),
        UploadedContractFile(filename="page-2.png", content=b"img-2", content_type="image/png"),
    ]

    def fake_extract_text_from_uploaded_image(file):
        if file.filename == "page-1.png":
            return "page one text", "PaddlePaddle/PaddleOCR-VL-1.5"
        return "page two text", "PaddlePaddle/PaddleOCR-VL-1.5"

    monkeypatch.setattr(
        "src.ocr.ingest_service._extract_text_from_uploaded_image",
        fake_extract_text_from_uploaded_image,
    )

    result = ingest_contract_files(files)

    assert result.source_type == "image_batch"
    assert "2" in result.display_name
    assert result.used_ocr_model == "PaddlePaddle/PaddleOCR-VL-1.5"
    assert [page.filename for page in result.pages] == ["page-1.png", "page-2.png"]
    assert result.pages[0].text == "page one text"
    assert result.pages[1].text == "page two text"
    assert result.merged_text == "page one text\n\npage two text"
    assert result.warnings == []


def test_ingest_contract_files_keeps_successful_pages_when_one_image_page_fails(monkeypatch):
    files = [
        UploadedContractFile(filename="page-1.png", content=b"img-1", content_type="image/png"),
        UploadedContractFile(filename="page-2.png", content=b"img-2", content_type="image/png"),
    ]

    def fake_extract_text_from_uploaded_image(file):
        if file.filename == "page-1.png":
            return "page one text", "PaddlePaddle/PaddleOCR-VL-1.5"
        raise RuntimeError("vision OCR unavailable")

    monkeypatch.setattr(
        "src.ocr.ingest_service._extract_text_from_uploaded_image",
        fake_extract_text_from_uploaded_image,
    )

    result = ingest_contract_files(files)

    assert result.used_ocr_model == "PaddlePaddle/PaddleOCR-VL-1.5"
    assert [page.filename for page in result.pages] == ["page-1.png"]
    assert result.merged_text == "page one text"
    assert any("第 2 页 OCR 失败" in warning for warning in result.warnings)


def test_ingest_contract_files_uses_pdf_ocr_for_all_pdfs(monkeypatch):
    monkeypatch.setattr(
        "src.ocr.ingest_service._render_pdf_to_images",
        lambda _file: [
            UploadedContractFile(filename="lease-page-1.png", content=b"img-1", content_type="image/png"),
            UploadedContractFile(filename="lease-page-2.png", content=b"img-2", content_type="image/png"),
        ],
    )

    def fake_extract_text_from_uploaded_image(file):
        page_number = "1" if file.filename.endswith("1.png") else "2"
        return f"page {page_number} text", "PaddlePaddle/PaddleOCR-VL-1.5"

    monkeypatch.setattr(
        "src.ocr.ingest_service._extract_text_from_uploaded_image",
        fake_extract_text_from_uploaded_image,
    )

    result = ingest_contract_files(
        [UploadedContractFile(filename="lease.pdf", content=b"fake-pdf", content_type="application/pdf")]
    )

    assert result.source_type == "pdf_ocr"
    assert result.display_name == "lease.pdf"
    assert result.used_ocr_model == "PaddlePaddle/PaddleOCR-VL-1.5"
    assert result.merged_text == "page 1 text\n\npage 2 text"


def test_ingest_contract_files_reads_txt_and_docx_without_ocr(monkeypatch):
    monkeypatch.setattr(
        "src.ocr.ingest_service._extract_text_from_uploaded_image",
        lambda _file: (_ for _ in ()).throw(AssertionError("OCR should not be used")),
    )

    txt_result = ingest_contract_files(
        [UploadedContractFile(filename="lease.txt", content="租赁合同正文".encode("utf-8"), content_type="text/plain")]
    )
    assert txt_result.source_type == "txt"
    assert txt_result.used_ocr_model is None
    assert txt_result.merged_text == "租赁合同正文"


def test_ingest_contract_files_surfaces_image_ocr_quality_failure(monkeypatch):
    monkeypatch.setattr(
        "src.ocr.ingest_service._extract_text_from_uploaded_image",
        lambda _file: (_ for _ in ()).throw(RuntimeError("OCR 结果疑似为模型补全的空白模板")),
    )

    with pytest.raises(RuntimeError, match="空白模板"):
        ingest_contract_files(
            [UploadedContractFile(filename="contract.png", content=b"img", content_type="image/png")]
        )
