from src.ocr import paddle_service


class _FakePageResult:
    def __init__(self):
        self.res = {
            "rec_texts": ["page bottom", "page top", ""],
            "rec_scores": [0.99, 0.82, 0.0],
            "rec_polys": [
                [[0, 40], [100, 40], [100, 60], [0, 60]],
                [[0, 10], [100, 10], [100, 30], [0, 30]],
                [[0, 70], [100, 70], [100, 90], [0, 90]],
            ],
        }


class _FakePaddleEngine:
    def __init__(self):
        self.seen_path: str | None = None

    def predict(self, image_path: str):
        self.seen_path = image_path
        return [_FakePageResult()]


def test_extract_contract_text_from_image_uses_paddle_engine(monkeypatch):
    engine = _FakePaddleEngine()
    monkeypatch.setattr(paddle_service, "_get_paddle_ocr_engine", lambda: engine)
    monkeypatch.setattr(paddle_service, "_preprocess_image_bytes", lambda image_bytes: image_bytes)

    result = paddle_service.extract_contract_text_from_image(
        image_bytes=b"fake-image",
        mime_type="image/png",
        filename="contract.png",
    )

    assert engine.seen_path is not None
    assert result.text == "page top\npage bottom"
    assert result.lines == ["page top", "page bottom"]
    assert result.average_confidence == (0.99 + 0.82) / 2
    assert result.low_confidence_lines == ["page top"]
    assert len(result.warnings) == 1


def test_extract_contract_text_from_image_rejects_unsupported_file_type():
    try:
        paddle_service.extract_contract_text_from_image(
            image_bytes=b"fake-pdf",
            mime_type="application/pdf",
            filename="contract.pdf",
        )
    except ValueError as exc:
        assert "JPG" in str(exc)
    else:
        raise AssertionError("expected ValueError for unsupported file type")
