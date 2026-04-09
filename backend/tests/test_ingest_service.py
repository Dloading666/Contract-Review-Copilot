from src.ocr.ingest_service import UploadedContractFile, ingest_contract_files
from src.ocr.paddle_service import OcrExtractionResult


def test_ingest_contract_files_merges_images_in_selected_order(monkeypatch):
    files = [
        UploadedContractFile(filename="page-1.png", content=b"img-1", content_type="image/png"),
        UploadedContractFile(filename="page-2.png", content=b"img-2", content_type="image/png"),
    ]

    def fake_extract_contract_text_from_image(**kwargs):
        if kwargs["filename"] == "page-1.png":
            return OcrExtractionResult(
                text="page one raw",
                lines=["page one raw"],
                average_confidence=0.96,
                low_confidence_lines=[],
                warnings=[],
            )
        return OcrExtractionResult(
            text="page two raw",
            lines=["page two raw"],
            average_confidence=0.81,
            low_confidence_lines=["page two raw"],
            warnings=["page confidence is low"],
        )

    def fake_correct_ocr_text_with_kimi(raw_text, **_kwargs):
        return f"{raw_text} corrected", "kimi-k2.5"

    monkeypatch.setattr(
        "src.ocr.ingest_service.extract_contract_text_from_image",
        fake_extract_contract_text_from_image,
    )
    monkeypatch.setattr(
        "src.ocr.ingest_service.correct_ocr_text_with_kimi",
        fake_correct_ocr_text_with_kimi,
    )

    result = ingest_contract_files(files)

    assert result.source_type == "image_batch"
    assert "2" in result.display_name
    assert result.used_ocr_model == "kimi-k2.5"
    assert [page.filename for page in result.pages] == ["page-1.png", "page-2.png"]
    assert result.pages[0].text == "page one raw corrected"
    assert result.pages[1].text == "page two raw corrected"
    assert result.merged_text == "page one raw corrected\n\npage two raw corrected"
    assert any("1" in warning for warning in result.warnings)


def test_ingest_contract_files_prefers_embedded_pdf_text(monkeypatch):
    long_page = "Section 1 rent terms\n" * 20

    monkeypatch.setattr(
        "src.ocr.ingest_service._extract_pdf_text_pages",
        lambda _file: [long_page, long_page],
    )

    result = ingest_contract_files(
        [UploadedContractFile(filename="lease.pdf", content=b"fake-pdf", content_type="application/pdf")]
    )

    assert result.source_type == "pdf_text"
    assert result.used_ocr_model is None
    assert len(result.pages) == 2
    assert "Section 1 rent terms" in result.merged_text


def test_ingest_contract_files_falls_back_to_pdf_ocr(monkeypatch):
    monkeypatch.setattr(
        "src.ocr.ingest_service._extract_pdf_text_pages",
        lambda _file: ["", ""],
    )
    monkeypatch.setattr(
        "src.ocr.ingest_service._render_pdf_to_images",
        lambda _file: [
            UploadedContractFile(filename="lease-page-1.png", content=b"img-1", content_type="image/png"),
            UploadedContractFile(filename="lease-page-2.png", content=b"img-2", content_type="image/png"),
        ],
    )

    def fake_extract_contract_text_from_image(**kwargs):
        page_number = "1" if kwargs["filename"].endswith("1.png") else "2"
        return OcrExtractionResult(
            text=f"page {page_number} raw",
            lines=[f"page {page_number} raw"],
            average_confidence=0.95,
            low_confidence_lines=[],
            warnings=[],
        )

    monkeypatch.setattr(
        "src.ocr.ingest_service.extract_contract_text_from_image",
        fake_extract_contract_text_from_image,
    )
    monkeypatch.setattr(
        "src.ocr.ingest_service.correct_ocr_text_with_kimi",
        lambda raw_text, **_kwargs: (raw_text, "kimi-k2.5"),
    )

    result = ingest_contract_files(
        [UploadedContractFile(filename="lease.pdf", content=b"fake-pdf", content_type="application/pdf")]
    )

    assert result.source_type == "pdf_ocr"
    assert result.display_name == "lease.pdf"
    assert result.used_ocr_model == "kimi-k2.5"
    assert result.merged_text == "page 1 raw\n\npage 2 raw"
