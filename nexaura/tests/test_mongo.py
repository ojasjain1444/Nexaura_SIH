"""
test_mongo.py — Unit & Integration tests for MongoDB KnowledgeBase repository
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexaura.backend.database.mongo_manager import MongoDBManager
from nexaura.backend.database.mongo_repository import MongoRepository
from nexaura.backend.ingestion.feature_extractor import KnowledgeUnit, TechnicalParameter


def test_mongo_repo_offline():
    """Verify repository instantiation without failing on missing connection."""
    manager = MongoDBManager(url="mongodb://localhost:27017", server_selection_timeout_ms=100)
    repo = MongoRepository(manager)
    assert repo.db.name == "KnowledgeBase"
    print("✓ MongoRepository unit test passed (database name='KnowledgeBase').")


if __name__ == "__main__":
    test_mongo_repo_offline()
