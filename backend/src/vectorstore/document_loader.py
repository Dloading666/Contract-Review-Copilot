"""
Contract document loading and chunking utilities.
"""
import re
from typing import List, Tuple, Optional
from pathlib import Path


def chunk_contract_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50
) -> List[str]:
    """
    Split contract text into overlapping chunks for embedding.

    Args:
        text: Full contract text
        chunk_size: Maximum characters per chunk
        overlap: Number of overlapping characters between chunks

    Returns:
        List of text chunks
    """
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        # Find a good break point (prefer sentence/paragraph boundaries)
        end = start + chunk_size

        if end < text_len:
            # Try to break at sentence end
            sentence_break = max(
                text.rfind('。', start, end),
                text.rfind('；', start, end),
                text.rfind('，', start, end),
                text.rfind('\n', start, end),
            )
            if sentence_break > start + chunk_size // 2:
                end = sentence_break + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end < text_len else text_len

    return chunks


def extract_contract_metadata(text: str) -> dict:
    """
    Extract basic metadata from contract text using pattern matching.

    Returns dict with keys: contract_type, lessor, lessee, property_address,
    monthly_rent, deposit, duration
    """
    metadata = {}

    # Extract monthly rent
    rent_match = re.search(r'月租金[：为]?\s*[\""]?([0-9,，.]+)\s*元', text)
    if rent_match:
        rent_str = rent_match.group(1).replace(',', '').replace('，', '')
        try:
            metadata['monthly_rent'] = float(rent_str)
        except ValueError:
            pass

    # Extract deposit
    deposit_match = re.search(r'押金[：为]?\s*[\""]?([0-9,，.]+)\s*元', text)
    if deposit_match:
        deposit_str = deposit_match.group(1).replace(',', '').replace('，', '')
        try:
            metadata['deposit'] = float(deposit_str)
        except ValueError:
            pass

    # Extract parties
    lessor_match = re.search(r'甲方（[^）]+）[：]?\s*([^\n，。]{2,50})', text)
    if lessor_match:
        metadata['lessor'] = lessor_match.group(1).strip()

    lessee_match = re.search(r'乙方（[^）]+）[：]?\s*([^\n，。]{2,50})', text)
    if lessee_match:
        metadata['lessee'] = lessee_match.group(1).strip()

    # Extract property address
    addr_match = re.search(r'房屋地址[：]\s*([^\n]{10,100})', text)
    if addr_match:
        metadata['property_address'] = addr_match.group(1).strip()

    # Extract duration
    duration_match = re.search(r'租赁期限[：]\s*([^\n]{5,30})', text)
    if duration_match:
        metadata['duration'] = duration_match.group(1).strip()

    # Extract contract type
    if '商业' in text:
        metadata['contract_type'] = '商业租赁'
    elif '办公' in text:
        metadata['contract_type'] = '办公租赁'
    else:
        metadata['contract_type'] = '住宅租赁'

    return metadata


def load_text_from_file(filepath: str) -> str:
    """Load text content from a contract file (supports .txt, .docx)."""
    path = Path(filepath)

    if path.suffix.lower() == '.txt':
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    elif path.suffix.lower() in ('.docx', '.doc'):
        try:
            from docx import Document
            doc = Document(path)
            return '\n'.join([para.text for para in doc.paragraphs])
        except ImportError:
            raise ValueError("python-docx not installed. Install with: pip install python-docx")

    elif path.suffix.lower() == '.pdf':
        try:
            import PyPDF2
            with open(path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ''
                for page in reader.pages:
                    text += page.extract_text() + '\n'
                return text
        except ImportError:
            raise ValueError("PyPDF2 not installed. Install with: pip install PyPDF2")

    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")
