from .ingest_service import ContractIngestResult, IngestedPageResult, UploadedContractFile, ingest_contract_files
from .paddle_service import OcrExtractionResult, extract_contract_text_from_image

__all__ = [
    "ContractIngestResult",
    "IngestedPageResult",
    "OcrExtractionResult",
    "UploadedContractFile",
    "extract_contract_text_from_image",
    "ingest_contract_files",
]
