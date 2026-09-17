"""
mongo_manager.py — MongoDB Connection and Collection Initialization

Project: Nexaura (SIH 2026 — SIH26107)

Provides:
    - Connection management via PyMongo
    - Database and Collection setup for 'KnowledgeBase'
    - Index initialization for clauses, features, tables, documents, and processing_log
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_mongo_url() -> str:
    """Get MongoDB connection URL from environment or fallback default."""
    url = os.environ.get("MONGO_URL") or os.environ.get("MONGODB_URL") or ""
    if not url:
        url = "mongodb://localhost:27017"
    return url


def get_mongo_db_name() -> str:
    """Get MongoDB database name."""
    return os.environ.get("MONGO_DB_NAME", "nexaura")


class MongoDBManager:
    """
    MongoDB connection and collection index manager.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        db_name: Optional[str] = None,
        server_selection_timeout_ms: int = 5000,
    ) -> None:
        self.url = url or get_mongo_url()
        self.db_name = db_name or get_mongo_db_name()
        self.server_selection_timeout_ms = server_selection_timeout_ms
        self._client = None
        self._db = None

    def get_client(self):
        """Get or create PyMongo MongoClient."""
        if self._client is None:
            try:
                import pymongo
            except ImportError as e:
                raise ImportError("pymongo required: pip install pymongo") from e

            logger.info("Connecting to MongoDB at %s...", self.url)
            self._client = pymongo.MongoClient(
                self.url,
                serverSelectionTimeoutMS=self.server_selection_timeout_ms,
            )
        return self._client

    def get_db(self):
        """Get the KnowledgeBase database instance."""
        if self._db is None:
            client = self.get_client()
            self._db = client[self.db_name]
        return self._db

    def init_collections(self) -> None:
        """
        Ensure required collections and indexes exist.
        Safe to call multiple times (idempotent).
        """
        import pymongo
        db = self.get_db()

        logger.info("Initializing MongoDB collections and indexes for database '%s'...", self.db_name)

        # 1. Documents collection
        db.documents.create_index([("standard_number", pymongo.ASCENDING)], unique=True)

        # 2. Clauses collection
        db.clauses.create_index([("knowledge_unit_id", pymongo.ASCENDING)], unique=True)
        db.clauses.create_index([("standard_number", pymongo.ASCENDING)])
        db.clauses.create_index([("clause", pymongo.ASCENDING)])

        # 3. Tables collection
        db.tables.create_index([("table_id", pymongo.ASCENDING)], unique=True)
        db.tables.create_index([("standard_number", pymongo.ASCENDING)])

        # 4. Features collection
        db.features.create_index([("feature_id", pymongo.ASCENDING)], unique=True)
        db.features.create_index([("knowledge_unit_id", pymongo.ASCENDING)])
        db.features.create_index([("standard_number", pymongo.ASCENDING)])
        db.features.create_index([("parameter_name", pymongo.ASCENDING)])

        # 5. Relationships collection
        db.relationships.create_index([("from_standard_number", pymongo.ASCENDING)])

        # 6. Documents Inventory collection (Multi-type A-P)
        db.documents_inventory.create_index([("document_id", pymongo.ASCENDING)], unique=True)
        db.documents_inventory.create_index([("document_type", pymongo.ASCENDING)])
        db.documents_inventory.create_index([("standard_number", pymongo.ASCENDING)])

        # 7. Document Relationships graph
        db.document_relationships.create_index([("from_id", pymongo.ASCENDING), ("to_id", pymongo.ASCENDING), ("relation_type", pymongo.ASCENDING)], unique=True)

        # 8. Coverage Reports collection
        db.coverage_reports.create_index([("standard_number", pymongo.ASCENDING)], unique=True)

        # 9. Sources collection
        db.sources.create_index([("source_pdf", pymongo.ASCENDING), ("file_hash", pymongo.ASCENDING)], unique=True)

        # 10. Processing Log collection
        db.processing_log.create_index([("file_hash", pymongo.ASCENDING)], unique=True)

        logger.info("MongoDB collections and indexes initialized successfully.")

    def test_connection(self) -> bool:
        """Test database connectivity."""
        try:
            client = self.get_client()
            client.admin.command("ping")
            logger.info("MongoDB connection OK")
            return True
        except Exception as exc:
            logger.error("MongoDB connection failed: %s", exc)
            return False

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None


# Singleton instance
_mongo_manager: Optional[MongoDBManager] = None


def get_mongo_manager() -> MongoDBManager:
    """Get or create global MongoDB manager."""
    global _mongo_manager
    if _mongo_manager is None:
        _mongo_manager = MongoDBManager()
    return _mongo_manager
