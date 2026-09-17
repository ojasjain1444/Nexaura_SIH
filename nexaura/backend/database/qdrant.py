"""
qdrant.py — Qdrant Vector Database Integration

Project: Nexaura (SIH 2026 — SIH26107)

Manages the Qdrant collection for semantic similarity search.

Collection: bis_knowledge
Vectors: Embeddings of KnowledgeUnit.search_text
Payload: All metadata needed for filtering and citation

URL and API key from environment variables only.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default collection name
DEFAULT_COLLECTION = "bis_knowledge"


class QdrantManager:
    """
    Manages the Qdrant vector database for semantic search.

    Features:
    - Creates collection if not exists (idempotent)
    - Batch vector upsert
    - Filtered similarity search
    - Payload includes all citation metadata
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        collection: str = DEFAULT_COLLECTION,
        vector_size: int = 384,
        distance: str = "Cosine",
    ) -> None:
        self.url = url or os.environ.get("QDRANT_URL", "http://localhost:6333")
        self.api_key = api_key or os.environ.get("QDRANT_API_KEY", "") or None
        self.collection = collection
        self.vector_size = vector_size
        self.distance = distance
        self._client = None

    def get_client(self):
        """Lazy-initialize the Qdrant client."""
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as e:
                raise ImportError("qdrant-client required: pip install qdrant-client") from e

            kwargs: dict[str, Any] = {"url": self.url}
            if self.api_key:
                kwargs["api_key"] = self.api_key

            self._client = QdrantClient(**kwargs)
            logger.info("Qdrant client initialized: %s", self.url)
        return self._client

    def init_collection(self) -> None:
        """
        Create the Qdrant collection if it doesn't exist.
        Safe to call multiple times.
        """
        from qdrant_client.models import Distance, VectorParams

        distance_map = {
            "Cosine": Distance.COSINE,
            "Dot": Distance.DOT,
            "Euclid": Distance.EUCLID,
        }
        dist = distance_map.get(self.distance, Distance.COSINE)

        client = self.get_client()
        existing = [c.name for c in client.get_collections().collections]

        if self.collection not in existing:
            client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.vector_size, distance=dist),
            )
            logger.info(
                "Qdrant collection created: %s (dim=%d, dist=%s)",
                self.collection, self.vector_size, self.distance,
            )
        else:
            logger.info("Qdrant collection already exists: %s", self.collection)

    def upsert_vectors(
        self,
        knowledge_units: list,
        vectors: list[list[float]],
        batch_size: int = 100,
    ) -> int:
        """
        Upsert knowledge unit vectors into Qdrant.

        Args:
            knowledge_units: List of KnowledgeUnit objects
            vectors: Corresponding embedding vectors (same length)
            batch_size: Number of vectors per Qdrant upsert call

        Returns:
            Number of vectors upserted
        """
        from qdrant_client.models import PointStruct

        if len(knowledge_units) != len(vectors):
            raise ValueError(
                f"Mismatch: {len(knowledge_units)} units vs {len(vectors)} vectors"
            )

        client = self.get_client()
        total = 0

        for i in range(0, len(knowledge_units), batch_size):
            batch_units = knowledge_units[i:i + batch_size]
            batch_vectors = vectors[i:i + batch_size]

            points = []
            for ku, vector in zip(batch_units, batch_vectors):
                # Build payload — all metadata for filtering and citation
                payload = {
                    "knowledge_unit_id": ku.id,
                    "standard_number":   ku.standard_number,
                    "title":             ku.title,
                    "edition":           ku.edition,
                    "year":              ku.year,
                    "part":              ku.part,
                    "status":            ku.status,
                    "clause":            ku.clause,
                    "sub_clause":        ku.sub_clause,
                    "parent_clause":     ku.parent_clause,
                    "heading":           ku.heading,
                    "content_type":      ku.content_type,
                    "section":           ku.section,
                    "page_start":        ku.page_start,
                    "page_end":          ku.page_end,
                    "source_pdf":        ku.source_pdf,
                    "product":           ku.product,
                    "application":       ku.application,
                    "material":          ku.material,
                    "keywords":          ku.keywords,
                    "technical_params":  [
                        {"name": p.name, "value": p.value, "unit": p.unit}
                        for p in ku.technical_parameters
                    ],
                    "needs_review":      ku.needs_review,
                    "ocr_confidence":    ku.ocr_confidence,
                }

                # Use a deterministic numeric ID based on hash of ku.id
                point_id = abs(hash(ku.id)) % (2**53)

                points.append(PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                ))

            client.upsert(collection_name=self.collection, points=points)
            total += len(points)
            logger.debug("Qdrant upsert batch %d: %d vectors", i // batch_size + 1, len(points))

        logger.info("Qdrant upsert complete: %d vectors in %s", total, self.collection)
        return total

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        filter_dict: Optional[dict] = None,
        score_threshold: float = 0.0,
    ) -> list[dict]:
        """
        Semantic similarity search in Qdrant.

        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            filter_dict: Optional Qdrant filter
            score_threshold: Minimum similarity score

        Returns:
            List of result dicts with payload and score
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = self.get_client()

        qdrant_filter = None
        if filter_dict:
            conditions = []
            for field, value in filter_dict.items():
                conditions.append(FieldCondition(key=field, match=MatchValue(value=value)))
            if conditions:
                qdrant_filter = Filter(must=conditions)

        results = client.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            score_threshold=score_threshold if score_threshold > 0 else None,
            with_payload=True,
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in results
        ]

    def collection_info(self) -> dict:
        """Return collection statistics."""
        client = self.get_client()
        info = client.get_collection(self.collection)
        return {
            "name": self.collection,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": str(info.status),
        }

    def test_connection(self) -> bool:
        """Test Qdrant connectivity."""
        try:
            client = self.get_client()
            client.get_collections()
            logger.info("Qdrant connection OK: %s", self.url)
            return True
        except Exception as exc:
            logger.error("Qdrant connection failed: %s", exc)
            return False
