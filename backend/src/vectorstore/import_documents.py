"""
Import local legal documents into pgvector.
"""
import argparse
from pathlib import Path

from .connection import close_pool
from .document_loader import chunk_contract_text, load_text_from_file
from .store import replace_contract_chunks, upsert_contract_source

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".doc", ".docx"}


def _iter_documents(source_dir: Path, recursive: bool) -> list[Path]:
    iterator = source_dir.rglob("*") if recursive else source_dir.glob("*")
    return sorted(
        path for path in iterator if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def import_documents(
    source_dir: str,
    *,
    recursive: bool = True,
    chunk_size: int = 500,
    overlap: int = 50,
    contract_type: str = "legal_document",
) -> tuple[int, int]:
    """Import files from a local directory into the vector store."""
    root = Path(source_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Source directory does not exist: {root}")

    documents = _iter_documents(root, recursive=recursive)
    if not documents:
        print(f"No supported files found under {root}", flush=True)
        return 0, 0

    imported_documents = 0
    imported_chunks = 0

    for path in documents:
        text = load_text_from_file(str(path))
        if not text.strip():
            print(f"Skipping empty file: {path}", flush=True)
            continue

        chunks = chunk_contract_text(text, chunk_size=chunk_size, overlap=overlap)
        if not chunks:
            print(f"Skipping file with no chunkable content: {path}", flush=True)
            continue

        resolved_path = str(path.resolve())
        source_key = f"file:{path.resolve().as_posix()}"
        contract_id = upsert_contract_source(
            title=path.stem,
            contract_type=contract_type,
            lessor=None,
            lessee=None,
            source_type="file_import",
            source_path=resolved_path,
            source_key=source_key,
        )
        metadata = [
            {
                "title": path.stem,
                "source_path": resolved_path,
                "source_type": "file_import",
                "source_key": source_key,
            }
            for _ in chunks
        ]
        chunk_ids = replace_contract_chunks(contract_id, chunks, metadata)
        imported_documents += 1
        imported_chunks += len(chunk_ids)
        print(f"Imported {path.name} ({len(chunk_ids)} chunks)", flush=True)

    return imported_documents, imported_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legal documents into pgvector.")
    parser.add_argument("source_dir", help="Directory containing .txt/.pdf/.doc/.docx files")
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only import files from the top-level directory",
    )
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--overlap", type=int, default=50)
    parser.add_argument("--contract-type", default="legal_document")
    args = parser.parse_args()

    try:
        document_count, chunk_count = import_documents(
            args.source_dir,
            recursive=not args.no_recursive,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            contract_type=args.contract_type,
        )
        print(
            f"Done. Imported {document_count} documents and {chunk_count} chunks.",
            flush=True,
        )
    finally:
        close_pool()


if __name__ == "__main__":
    main()
