"""
Vector storage and retrieval using pgvector.
"""
from typing import List, Optional

from psycopg2.extras import Json

from ..cache import build_cache_key, get_json, get_ttl_seconds, set_json
from .connection import get_connection
from .embeddings import embed_texts


def upsert_contract_source(
    *,
    title: str,
    contract_type: str,
    source_key: str,
    lessor: str | None = None,
    lessee: str | None = None,
    source_type: str = "contract",
    source_path: str | None = None,
) -> int:
    """Create or update a logical source document and return its contract id."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO contracts (
                    title,
                    contract_type,
                    lessor,
                    lessee,
                    source_type,
                    source_path,
                    source_key
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_key) DO UPDATE
                SET title = EXCLUDED.title,
                    contract_type = EXCLUDED.contract_type,
                    lessor = EXCLUDED.lessor,
                    lessee = EXCLUDED.lessee,
                    source_type = EXCLUDED.source_type,
                    source_path = EXCLUDED.source_path
                RETURNING id
                """,
                (
                    title,
                    contract_type,
                    lessor,
                    lessee,
                    source_type,
                    source_path,
                    source_key,
                ),
            )
            contract_id = cur.fetchone()[0]
            conn.commit()
    return contract_id


def count_contract_chunks(contract_id: int) -> int:
    """Return how many chunks are already indexed for a contract source."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM contract_chunks WHERE contract_id = %s",
                (contract_id,),
            )
            return int(cur.fetchone()[0])


def _insert_contract_chunks(
    contract_id: int,
    chunks: List[str],
    metadata: Optional[List[dict]] = None,
) -> List[int]:
    if not chunks:
        return []

    embeddings = embed_texts(chunks)
    chunk_ids: List[int] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                meta = metadata[i] if metadata and i < len(metadata) else {}
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                cur.execute(
                    """
                    INSERT INTO contract_chunks (
                        contract_id,
                        chunk_text,
                        chunk_index,
                        embedding,
                        metadata
                    )
                    VALUES (%s, %s, %s, %s::vector, %s)
                    RETURNING id
                    """,
                    (
                        contract_id,
                        chunk,
                        i,
                        embedding_str,
                        Json(meta),
                    ),
                )
                chunk_ids.append(cur.fetchone()[0])

            conn.commit()

    return chunk_ids


def store_contract_chunks(
    contract_id: int,
    chunks: List[str],
    metadata: Optional[List[dict]] = None,
) -> List[int]:
    """
    Store text chunks with their embeddings in pgvector.

    This assumes the contract has not been indexed before. For re-indexing,
    use replace_contract_chunks.
    """
    return _insert_contract_chunks(contract_id, chunks, metadata)


def replace_contract_chunks(
    contract_id: int,
    chunks: List[str],
    metadata: Optional[List[dict]] = None,
) -> List[int]:
    """Replace all stored chunks for a given contract source."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM contract_chunks WHERE contract_id = %s",
                (contract_id,),
            )
            conn.commit()

    return _insert_contract_chunks(contract_id, chunks, metadata)


def retrieve_similar_chunks(
    query: str,
    top_k: int = 5,
    contract_id: Optional[int] = None,
    min_similarity: float = 0.5,
) -> List[dict]:
    """
    Retrieve most similar chunks for a query using cosine similarity.

    Returns dicts with chunk text, chunk metadata, similarity, and contract id.
    """
    cache_key = build_cache_key(
        "search",
        {
            "provider": "pgvector",
            "query": query,
            "top_k": top_k,
            "contract_id": contract_id,
            "min_similarity": min_similarity,
        },
    )
    cached_results = get_json(cache_key)
    if isinstance(cached_results, list):
        return cached_results

    query_embedding = embed_texts([query])[0]
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    if contract_id is not None:
        sql = """
            SELECT id, contract_id, chunk_text, chunk_index, metadata,
                   1 - (embedding <=> %s::vector) AS cosine_similarity
            FROM contract_chunks
            WHERE contract_id = %s
              AND 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params = (
            embedding_str,
            contract_id,
            embedding_str,
            min_similarity,
            embedding_str,
            top_k,
        )
    else:
        sql = """
            SELECT id, contract_id, chunk_text, chunk_index, metadata,
                   1 - (embedding <=> %s::vector) AS cosine_similarity
            FROM contract_chunks
            WHERE 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params = (
            embedding_str,
            embedding_str,
            min_similarity,
            embedding_str,
            top_k,
        )

    results: List[dict] = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                results.append(
                    {
                        "id": row[0],
                        "contract_id": row[1],
                        "chunk_text": row[2],
                        "chunk_index": row[3],
                        "metadata": row[4] or {},
                        "similarity": float(row[5]),
                    }
                )

    set_json(cache_key, results, get_ttl_seconds("search"))
    return results


def get_contract_chunks(contract_id: int) -> List[dict]:
    """Get all chunks for a specific contract."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, chunk_text, chunk_index, metadata, created_at
                FROM contract_chunks
                WHERE contract_id = %s
                ORDER BY chunk_index
                """,
                (contract_id,),
            )
            return [
                {
                    "id": row[0],
                    "chunk_text": row[1],
                    "chunk_index": row[2],
                    "metadata": row[3] or {},
                    "created_at": row[4],
                }
                for row in cur.fetchall()
            ]


def delete_contract(contract_id: int) -> int:
    """Delete a contract and all its chunks. Returns number of chunks deleted."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM contracts WHERE id = %s RETURNING id", (contract_id,))
            deleted = cur.rowcount
            conn.commit()
    return deleted
