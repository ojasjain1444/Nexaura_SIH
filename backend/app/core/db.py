"""
backend/app/core/db.py — Database connection layer for MongoDB & GridFS.
"""

from __future__ import annotations

import logging
from typing import Optional

import gridfs
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import pymongo
from pymongo.database import Database

from backend.app.config import MONGO_DB_NAME, MONGO_URI

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages MongoDB connections for the FastAPI application."""

    def __init__(self, uri: str = MONGO_URI, db_name: str = MONGO_DB_NAME):
        self.uri = uri
        self.db_name = db_name
        self.sync_client: Optional[pymongo.MongoClient] = None
        self.async_client: Optional[AsyncIOMotorClient] = None
        self.sync_db: Optional[Database] = None
        self.async_db: Optional[AsyncIOMotorDatabase] = None
        self.fs: Optional[gridfs.GridFS] = None

    def connect(self) -> None:
        """Initialize sync and async clients."""
        if self.sync_client is None:
            self.sync_client = pymongo.MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self.sync_db = self.sync_client[self.db_name]
            self.fs = gridfs.GridFS(self.sync_db)

        if self.async_client is None:
            self.async_client = AsyncIOMotorClient(self.uri, serverSelectionTimeoutMS=5000)
            self.async_db = self.async_client[self.db_name]

        logger.info("Connected to MongoDB at %s (DB: %s)", self.uri, self.db_name)

    def close(self) -> None:
        """Close clients cleanly."""
        if self.sync_client:
            self.sync_client.close()
            self.sync_client = None
            self.sync_db = None
            self.fs = None

        if self.async_client:
            self.async_client.close()
            self.async_client = None
            self.async_db = None
        logger.info("MongoDB connections closed.")

    @property
    def db(self) -> Database:
        if self.sync_db is None:
            self.connect()
        return self.sync_db  # type: ignore

    @property
    def adb(self) -> AsyncIOMotorDatabase:
        if self.async_db is None:
            self.connect()
        return self.async_db  # type: ignore

    @property
    def grid_fs(self) -> gridfs.GridFS:
        if self.fs is None:
            self.connect()
        return self.fs  # type: ignore


# Global DB instance
db_manager = DatabaseManager()


def get_db() -> Database:
    """Dependency for sync endpoints or helper scripts."""
    return db_manager.db


def get_adb() -> AsyncIOMotorDatabase:
    """Dependency for async FastAPI endpoints."""
    return db_manager.adb


def get_gridfs() -> gridfs.GridFS:
    """Dependency for GridFS file access."""
    return db_manager.grid_fs
