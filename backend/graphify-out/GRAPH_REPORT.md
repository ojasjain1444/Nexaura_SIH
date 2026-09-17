# Graph Report - backend  (2026-09-17)

## Corpus Check
- 16 files · ~2,685 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 138 nodes · 196 edges · 14 communities (10 shown, 4 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 9 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- main.py
- db.py
- schemas.py
- test_api.py
- standards.py
- rag_engine.py
- typing
- health_check
- get_system_stats
- config.py

## God Nodes (most connected - your core abstractions)
1. `DatabaseManager` - 8 edges
2. `query_rag()` - 7 edges
3. `list_labs()` - 6 edges
4. `list_standards()` - 6 edges
5. `get_system_stats()` - 5 edges
6. `live_bis_search()` - 4 edges
7. `get_standard_detail()` - 4 edges
8. `download_standard_pdf()` - 4 edges
9. `get_labs_for_standard()` - 4 edges
10. `RAGEngine` - 4 edges

## Surprising Connections (you probably didn't know these)
- `list_standards()` --uses--> `PaginatedResponse`  [INFERRED]
  app/api/v1/endpoints/standards.py → app/models/schemas.py
- `list_standards()` --uses--> `StandardSummary`  [INFERRED]
  app/api/v1/endpoints/standards.py → app/models/schemas.py
- `get_system_stats()` --uses--> `StatsResponse`  [INFERRED]
  app/api/v1/endpoints/stats.py → app/models/schemas.py
- `health_check()` --uses--> `HealthResponse`  [INFERRED]
  app/main.py → app/models/schemas.py
- `list_labs()` --uses--> `LabResponse`  [INFERRED]
  app/api/v1/endpoints/labs.py → app/models/schemas.py

## Import Cycles
- None detected.

## Communities (14 total, 4 thin omitted)

### Community 0 - "main.py"
Cohesion: 0.12
Nodes (19): backend/app/api/v1/api_router.py — Aggregates all v1 API route modules., backend/app/api/v1/endpoints/labs.py — Accredited testing laboratories…, backend/app/api/v1/endpoints/rag.py — RAG retrieval and standards question…, backend/app/api/v1/endpoints/stats.py — Database statistics and system health…, lifespan(), backend/app/main.py — Main FastAPI Application instance for Nexaura., Application startup and shutdown events., backend_app_api_v1_api_router (+11 more)

### Community 1 - "db.py"
Cohesion: 0.11
Nodes (16): DatabaseManager, get_adb(), get_db(), get_gridfs(), AsyncIOMotorDatabase, backend/app/core/db.py — Database connection layer for MongoDB & GridFS., Manages MongoDB connections for the FastAPI application., Initialize sync and async clients. (+8 more)

### Community 2 - "schemas.py"
Cohesion: 0.15
Nodes (20): list_labs(), AsyncIOMotorDatabase, get, Search and filter official BIS accredited testing laboratories., AsyncIOMotorDatabase, query_rag(), Ask a question or search for technical requirements across Indian Standards.…, HealthResponse (+12 more)

### Community 3 - "test_api.py"
Cohesion: 0.17
Nodes (17): backend_app_main, fastapi_testclient, fixture, pytest, TestClient, client(), backend/tests/test_api.py — Integration and endpoint test suite for Nexaura…, test_get_labs_for_standard() (+9 more)

### Community 4 - "standards.py"
Cohesion: 0.21
Nodes (13): download_standard_pdf(), get_labs_for_standard(), get_standard_detail(), list_standards(), AsyncIOMotorDatabase, get, backend/app/api/v1/endpoints/standards.py — Standards search, detail, and PDF…, Stream or download official standard PDF stored inside MongoDB GridFS. (+5 more)

### Community 5 - "rag_engine.py"
Cohesion: 0.17
Nodes (10): Any, AsyncIOMotorDatabase, RAGEngine, backend/app/core/rag_engine.py — High-precision RAG retrieval and citation…, Retrieves relevant standards clauses and formats evidence-based answers., Search and rank chunks from MongoDB using hybrid text search + RapidFuzz., Generate structured answer with citations based on retrieved context., logging (+2 more)

### Community 6 - "typing"
Cohesion: 0.25
Nodes (7): live_bis_search(), Any, get, backend/app/api/v1/endpoints/bis_live.py — Live BIS official portal proxy…, Directly query official Bureau of Indian Standards review-service in real time.…, bis_ingestion_clients_bis_standards, typing

### Community 7 - "health_check"
Cohesion: 0.40
Nodes (5): health_check(), get, Redirect root to interactive API documentation., Health check endpoint confirming API and MongoDB status., root()

### Community 8 - "get_system_stats"
Cohesion: 0.50
Nodes (4): get_system_stats(), AsyncIOMotorDatabase, get, Return high-level database metrics, collection counts, and system status.

### Community 9 - "config.py"
Cohesion: 0.50
Nodes (3): backend/app/config.py — Configuration settings for the Nexaura Backend API., os, pathlib

## Knowledge Gaps
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `query_rag()` connect `schemas.py` to `main.py`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `query_rag()` (e.g. with `RAGChunkResponse` and `RAGQueryRequest`) actually correct?**
  _`query_rag()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `main.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11956521739130435 - nodes in this community are weakly interconnected._
- **Should `db.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11462450592885376 - nodes in this community are weakly interconnected._
- **Should `schemas.py` be split into smaller, more focused modules?**
  _Cohesion score 0.14761904761904762 - nodes in this community are weakly interconnected._