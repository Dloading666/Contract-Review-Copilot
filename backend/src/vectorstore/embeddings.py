"""
Embedding generation using ZhipuAI text-embedding-v4.
"""
import os
import numpy as np
from openai import OpenAI
from typing import List

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))

# ZhipuAI embedding model configuration
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", os.getenv("OPENAI_API_KEY", ""))
EMBEDDING_BASE_URL = os.getenv(
    "EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")

# Embedding dimension for text-embedding-v4
EMBEDDING_DIM = 1024


def get_embedding_client() -> OpenAI:
    """Get configured OpenAI client for embeddings."""
    return OpenAI(
        api_key=EMBEDDING_API_KEY,
        base_url=EMBEDDING_BASE_URL,
    )


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts using ZhipuAI text-embedding-v4.

    Returns a list of embedding vectors (normalized to unit length for cosine similarity).
    """
    if not texts:
        return []

    client = get_embedding_client()

    # Batch processing - ZhipuAI recommends max 20 texts per batch
    all_embeddings = []
    batch_size = 20

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )

        for item in response.data:
            embedding = item.embedding
            # Normalize to unit vector for cosine similarity
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = [x / norm for x in embedding]
            all_embeddings.append(embedding)

    return all_embeddings


def embed_text(text: str) -> List[float]:
    """Generate embedding for a single text."""
    return embed_texts([text])[0]
