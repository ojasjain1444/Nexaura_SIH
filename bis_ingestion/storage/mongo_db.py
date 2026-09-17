"""
storage/mongo_db.py — MongoDB persistence layer for BIS Standards and Labs data.

Collections in MongoDB 'nexaura' database:
  - `standards`  : Indian Standard specifications with metadata, amendments, and links.
  - `labs`       : Testing laboratories accredited for specific IS numbers.
  - `rag_chunks` : Pre-chunked documents for RAG (Retrieval-Augmented Generation).
  - `crawl_log`  : Historical log of crawler runs and ingestion metrics.

Features:
  - Full-text search indexes on standards, labs, and rag_chunks.
  - Idempotent upserts based on unique natural keys.
  - Fast compound indexes for filtering by standard number, state, status, committee.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

import pymongo
from pymongo import ASCENDING, TEXT, IndexModel, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from bis_ingestion.config import MONGO_DB_NAME, MONGO_URI
from bis_ingestion.schemas import BISLab, BISStandard, RAGChunk

logger = logging.getLogger(__name__)


class BISMongoDatabase:
    """
    MongoDB persistence manager for Nexaura BIS data.

    Usage::

        with BISMongoDatabase() as db:
            db.upsert_standard(standard)
            std = db.get_standard("IS 456")
            labs = db.get_labs_for_standard("456")
    """

    def __init__(
        self,
        uri: str = MONGO_URI,
        db_name: str = MONGO_DB_NAME,
    ):
        self.uri = uri
        self.db_name = db_name
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None

    # --- Context Manager ------------------------------------------------------

    def __enter__(self) -> "BISMongoDatabase":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def connect(self) -> None:
        """Establish connection and ensure indexes exist."""
        if self._client is None:
            self._client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self._db = self._client[self.db_name]
            self._init_indexes()
            logger.info("Connected to MongoDB at %s (DB: %s)", self.uri, self.db_name)

    def close(self) -> None:
        """Close connection cleanly."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    @property
    def db(self) -> Database:
        if self._db is None:
            self.connect()
        return self._db  # type: ignore

    @property
    def standards_col(self) -> Collection:
        return self.db["standards"]

    @property
    def labs_col(self) -> Collection:
        return self.db["labs"]

    @property
    def rag_chunks_col(self) -> Collection:
        return self.db["rag_chunks"]

    @property
    def crawl_log_col(self) -> Collection:
        return self.db["crawl_log"]

    # --- Index Initialization -------------------------------------------------

    def _init_indexes(self) -> None:
        """Ensure all required performance and text indexes exist."""
        try:
            # 1. Standards Indexes
            self.standards_col.create_indexes([
                IndexModel([("standard_number", ASCENDING)], unique=True, name="idx_std_num_unique"),
                IndexModel([("doc_no", ASCENDING)], name="idx_std_doc_no"),
                IndexModel([("status", ASCENDING)], name="idx_std_status"),
                IndexModel([("technical_committee", ASCENDING)], name="idx_std_tc"),
                IndexModel([("department", ASCENDING)], name="idx_std_dept"),
                IndexModel(
                    [
                        ("standard_number", TEXT),
                        ("title", TEXT),
                        ("scope", TEXT),
                    ],
                    name="idx_std_text_search",
                ),
            ])

            # 2. Labs Indexes
            self.labs_col.create_indexes([
                IndexModel([("lab_name", ASCENDING), ("is_number", ASCENDING)], unique=True, name="idx_lab_unique"),
                IndexModel([("is_doc_no", ASCENDING)], name="idx_lab_doc_no"),
                IndexModel([("state", ASCENDING)], name="idx_lab_state"),
                IndexModel([("product", ASCENDING)], name="idx_lab_product"),
                IndexModel(
                    [
                        ("lab_name", TEXT),
                        ("product", TEXT),
                    ],
                    name="idx_lab_text_search",
                ),
            ])

            # 3. RAG Chunks Indexes
            self.rag_chunks_col.create_indexes([
                IndexModel([("chunk_id", ASCENDING)], unique=True, name="idx_chunk_id_unique"),
                IndexModel([("standard_number", ASCENDING)], name="idx_chunk_std_num"),
                IndexModel([("text", TEXT)], name="idx_chunk_text_search"),
            ])

            # 4. Crawl Log Indexes
            self.crawl_log_col.create_indexes([
                IndexModel([("run_at", ASCENDING)], name="idx_crawl_run_at"),
            ])
            logger.debug("MongoDB indexes verified successfully.")
        except Exception as e:
            logger.warning("Index creation notice: %s", e)

    # --- Standards Operations -------------------------------------------------

    def upsert_standard(self, std: BISStandard | dict[str, Any]) -> None:
        """Insert or replace a standard document in MongoDB."""
        data = std.model_dump() if isinstance(std, BISStandard) else dict(std)
        # Ensure _id or natural key
        std_num = data.get("standard_number", "").strip().upper()
        if not std_num:
            raise ValueError("standard_number is required")

        data["standard_number"] = std_num
        data["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.standards_col.update_one(
            {"standard_number": std_num},
            {"$set": data},
            upsert=True,
        )

    def upsert_standards_batch(self, standards: list[BISStandard | dict[str, Any]]) -> int:
        """Bulk upsert standards. Returns count written."""
        if not standards:
            return 0

        operations = []
        for std in standards:
            data = std.model_dump() if isinstance(std, BISStandard) else dict(std)
            std_num = data.get("standard_number", "").strip().upper()
            if std_num:
                data["standard_number"] = std_num
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                operations.append(
                    pymongo.UpdateOne(
                        {"standard_number": std_num},
                        {"$set": data},
                        upsert=True,
                    )
                )

        if operations:
            result = self.standards_col.bulk_write(operations, ordered=False)
            count = result.upserted_count + result.modified_count
            logger.info("MongoDB: %d standards upserted/modified", count)
            return len(operations)
        return 0

    def get_standard(self, standard_number: str) -> Optional[dict[str, Any]]:
        """Fetch standard document by standard_number (e.g. 'IS 456')."""
        clean = standard_number.strip().upper()
        doc = self.standards_col.find_one({"standard_number": clean}, {"_id": 0})
        if not doc:
            # Try fuzzy/normalized search
            doc = self.standards_col.find_one(
                {"standard_number": {"$regex": f"^{re.escape(clean)}", "$options": "i"}},
                {"_id": 0},
            )
        return doc

    def search_standards(
        self,
        query: Optional[str] = None,
        status: Optional[str] = None,
        committee: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search standards with optional text query and filters."""
        filters: dict[str, Any] = {}
        if status:
            filters["status"] = {"$regex": f"^{re.escape(status)}", "$options": "i"}
        if committee:
            filters["technical_committee"] = {"$regex": f"^{re.escape(committee)}", "$options": "i"}

        if query:
            # Use regex for flexible partial match if text search isn't preferred
            q = query.strip()
            filters["$or"] = [
                {"standard_number": {"$regex": re.escape(q), "$options": "i"}},
                {"title": {"$regex": re.escape(q), "$options": "i"}},
                {"scope": {"$regex": re.escape(q), "$options": "i"}},
            ]

        cursor = self.standards_col.find(filters, {"_id": 0}).skip(skip).limit(limit)
        return list(cursor)

    def count_standards(self) -> int:
        return self.standards_col.count_documents({})

    def iter_all_standards(self) -> Iterator[dict[str, Any]]:
        cursor = self.standards_col.find({}, {"_id": 0}).sort("standard_number", ASCENDING)
        for doc in cursor:
            yield doc

    # --- Labs Operations ------------------------------------------------------

    def upsert_lab(self, lab: BISLab | dict[str, Any]) -> None:
        """Insert or update an accredited lab document."""
        data = lab.model_dump() if isinstance(lab, BISLab) else dict(lab)
        lab_name = data.get("lab_name", "").strip()
        is_number = data.get("is_number", "").strip()

        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.labs_col.update_one(
            {"lab_name": lab_name, "is_number": is_number},
            {"$set": data},
            upsert=True,
        )

    def upsert_labs_batch(self, labs: list[BISLab | dict[str, Any]]) -> int:
        """Bulk upsert labs."""
        if not labs:
            return 0

        operations = []
        for lab in labs:
            data = lab.model_dump() if isinstance(lab, BISLab) else dict(lab)
            lab_name = data.get("lab_name", "").strip()
            is_number = data.get("is_number", "").strip()
            if lab_name and is_number:
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                operations.append(
                    pymongo.UpdateOne(
                        {"lab_name": lab_name, "is_number": is_number},
                        {"$set": data},
                        upsert=True,
                    )
                )

        if operations:
            result = self.labs_col.bulk_write(operations, ordered=False)
            count = result.upserted_count + result.modified_count
            logger.info("MongoDB: %d labs upserted/modified", count)
            return len(operations)
        return 0

    def get_labs_for_standard(self, is_doc_no: str) -> list[dict[str, Any]]:
        """Retrieve labs recognizing this standard doc number (e.g. '456' or 'IS 456')."""
        clean = is_doc_no.replace("IS", "").strip()
        cursor = self.labs_col.find(
            {
                "$or": [
                    {"is_doc_no": clean},
                    {"is_number": {"$regex": f"\\b{re.escape(clean)}\\b", "$options": "i"}},
                ]
            },
            {"_id": 0},
        )
        return list(cursor)

    def count_labs(self) -> int:
        return self.labs_col.count_documents({})

    # --- RAG Chunks Operations ------------------------------------------------

    def upsert_rag_chunks_batch(self, chunks: list[RAGChunk | dict[str, Any]]) -> int:
        """Bulk upsert RAG chunks."""
        if not chunks:
            return 0

        operations = []
        for c in chunks:
            data = c.model_dump() if isinstance(c, RAGChunk) else dict(c)
            chunk_id = data.get("chunk_id")
            if chunk_id:
                operations.append(
                    pymongo.UpdateOne(
                        {"chunk_id": chunk_id},
                        {"$set": data},
                        upsert=True,
                    )
                )

        if operations:
            self.rag_chunks_col.bulk_write(operations, ordered=False)
            return len(operations)
        return 0

    def search_rag_chunks(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search chunks using MongoDB text index or regex match."""
        try:
            cursor = self.rag_chunks_col.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}, "_id": 0},
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            results = list(cursor)
            if results:
                return results
        except Exception:
            pass

        # Fallback to regex search
        cursor = self.rag_chunks_col.find(
            {"text": {"$regex": re.escape(query), "$options": "i"}},
            {"_id": 0},
        ).limit(limit)
        return list(cursor)

    def count_rag_chunks(self) -> int:
        return self.rag_chunks_col.count_documents({})

    # --- Crawl Log & Stats ----------------------------------------------------

    def log_crawl_run(
        self,
        source: str,
        records_added: int = 0,
        records_updated: int = 0,
        errors: int = 0,
        notes: str = "",
    ) -> None:
        """Record crawler execution summary."""
        doc = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "records_added": records_added,
            "records_updated": records_updated,
            "errors": errors,
            "notes": notes,
        }
        self.crawl_log_col.insert_one(doc)

    def get_stats(self) -> dict[str, Any]:
        """Aggregate high-level metrics across the database."""
        return {
            "standards_count": self.count_standards(),
            "labs_count": self.count_labs(),
            "rag_chunks_count": self.count_rag_chunks(),
            "last_crawl": self.crawl_log_col.find_one({}, sort=[("run_at", pymongo.DESCENDING)], projection={"_id": 0}),
        }


import re
