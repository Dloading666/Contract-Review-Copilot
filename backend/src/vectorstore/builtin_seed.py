"""
Idempotent built-in legal knowledge seeding.
"""
from .seed import LEGAL_KNOWLEDGE, _chunk_legal_entry
from .store import count_contract_chunks, replace_contract_chunks, upsert_contract_source


def seed_builtin_legal_knowledge() -> int:
    """Seed the repository's built-in legal knowledge without duplicating rows."""
    total_chunks = 0

    for index, entry in enumerate(LEGAL_KNOWLEDGE):
        source_key = f"builtin:legal_knowledge:{index}"
        contract_id = upsert_contract_source(
            title=entry["title"],
            contract_type="legal_knowledge",
            lessor=None,
            lessee=None,
            source_type="builtin_legal_knowledge",
            source_path=None,
            source_key=source_key,
        )

        if count_contract_chunks(contract_id) > 0:
            print(f"  Skipped existing source: {entry['title']}", flush=True)
            continue

        chunks = _chunk_legal_entry(entry["content"], chunk_size=600)
        metadata = [
            {
                "title": entry["title"],
                "source_type": "builtin_legal_knowledge",
                "source_key": source_key,
            }
            for _ in chunks
        ]
        chunk_ids = replace_contract_chunks(contract_id, chunks, metadata)
        total_chunks += len(chunk_ids)
        print(f"  Seeded: {entry['title']} ({len(chunk_ids)} chunks)", flush=True)

    return total_chunks


if __name__ == "__main__":
    print("Seeding built-in legal knowledge...", flush=True)
    count = seed_builtin_legal_knowledge()
    print(f"Done. Seeded {count} new chunks.", flush=True)
