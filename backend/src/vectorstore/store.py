"""
Vector storage and retrieval using pgvector.
"""
import os
import json
from typing import List, Optional
from .connection import get_connection
from .embeddings import embed_texts


def store_contract_chunks(
    contract_id: int,
    chunks: List[str],
    metadata: Optional[List[dict]] = None
) -> List[int]:
    """
    Store text chunks with their embeddings in pgvector.

    Args:
        contract_id: ID of the parent contract
        chunks: List of text chunks to store
        metadata: Optional list of metadata dicts for each chunk

    Returns:
        List of chunk IDs
    """
    if not chunks:
        return []

    # Generate embeddings
    embeddings = embed_texts(chunks)

    # Convert embeddings to PostgreSQL vector format
    chunk_ids = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                meta = metadata[i] if metadata and i < len(metadata) else {}
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

                cur.execute(
                    """
                    INSERT INTO contract_chunks (contract_id, chunk_text, chunk_index, embedding)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (contract_id, chunk, i, embedding_str)
                )
                chunk_id = cur.fetchone()[0]
                chunk_ids.append(chunk_id)

            conn.commit()

    return chunk_ids


def retrieve_similar_chunks(
    query: str,
    top_k: int = 5,
    contract_id: Optional[int] = None,
    min_similarity: float = 0.5
) -> List[dict]:
    """
    Retrieve most similar chunks for a query using cosine similarity.

    Args:
        query: Query text to search for
        top_k: Number of results to return
        contract_id: Optional filter to specific contract
        min_similarity: Minimum cosine similarity threshold (0-1)

    Returns:
        List of dicts with chunk_text, chunk_index, similarity score, and contract_id
    """
    # Generate query embedding
    query_embedding = embed_texts([query])[0]
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    # Build query
    if contract_id is not None:
        sql = """
            SELECT id, contract_id, chunk_text, chunk_index,
                   1 - (embedding <=> %s::vector) AS cosine_similarity
            FROM contract_chunks
            WHERE contract_id = %s
            AND 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params = (embedding_str, contract_id, embedding_str, min_similarity, embedding_str, top_k)
    else:
        sql = """
            SELECT id, contract_id, chunk_text, chunk_index,
                   1 - (embedding <=> %s::vector) AS cosine_similarity
            FROM contract_chunks
            WHERE 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        params = (embedding_str, embedding_str, min_similarity, embedding_str, top_k)

    results = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            for row in cur.fetchall():
                results.append({
                    "id": row[0],
                    "contract_id": row[1],
                    "chunk_text": row[2],
                    "chunk_index": row[3],
                    "similarity": float(row[4]),
                })

    return results


def get_contract_chunks(contract_id: int) -> List[dict]:
    """Get all chunks for a specific contract."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, chunk_text, chunk_index, created_at
                FROM contract_chunks
                WHERE contract_id = %s
                ORDER BY chunk_index
                """,
                (contract_id,)
            )
            return [
                {
                    "id": row[0],
                    "chunk_text": row[1],
                    "chunk_index": row[2],
                    "created_at": row[3],
                }
                for row in cur.fetchall()
            ]


def delete_contract(contract_id: int) -> int:
    """Delete a contract and all its chunks. Returns number of chunks deleted."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Chunks are deleted via CASCADE
            cur.execute("DELETE FROM contracts WHERE id = %s RETURNING id", (contract_id,))
            deleted = cur.rowcount
            conn.commit()
    return deleted
