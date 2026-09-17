# Graph Report - bis_ingestion  (2026-09-17)

## Corpus Check
- 30 files · ~140,764 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: .jsonl 2, .tmp 2, .csv 1)

## Summary
- 467 nodes · 871 edges · 33 communities (27 shown, 6 thin omitted)
- Extraction: 80% EXTRACTED · 20% INFERRED · 0% AMBIGUOUS · INFERRED: 175 edges (avg confidence: 0.88)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- BISDatabase
- sync_pdfs_and_expand_data.py
- chunk_standard
- pipeline.py
- BISLab
- BISStandard
- bis_standards.py
- RAGChunk
- exporters/__init__.py
- BISHTTPClient
- Any
- BISMongoDatabase
- _split_text
- text_utils.py
- test_parsers.py
- migrate_rag_chunks
- clean_text
- extract_is_numbers
- expand_new_industries
- .connect
- normalise_date
- normalise_is_number
- parse_is_components
- extract_amendment_numbers
- extract_year
- extract_ics_codes
- strip_html_tags
- .close
- clients/__init__.py
- __init__.py
- .get_standard
- .log_crawl_run
- tests/__init__.py

## God Nodes (most connected - your core abstractions)
1. `BISDatabase` - 50 edges
2. `BISStandard` - 44 edges
3. `BISMongoDatabase` - 40 edges
4. `chunk_standard()` - 22 edges
5. `BISLab` - 20 edges
6. `RAGChunk` - 15 edges
7. `_make_std()` - 15 edges
8. `TestBISStandard` - 12 edges
9. `_make_std()` - 12 edges
10. `run_export()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `row_to_std()` --calls--> `BISStandard`  [INFERRED]
  pipeline.py → schemas.py
- `row_to_std()` --calls--> `BISStandard`  [INFERRED]
  pipeline.py → schemas.py
- `main()` --calls--> `BISDatabase`  [INFERRED]
  __main__.py → storage/db.py
- `run_lims_crawl()` --calls--> `crawl_lims_range()`  [INFERRED]
  pipeline.py → clients/bis_lims.py
- `_parse_standard_from_html()` --uses--> `BISStandard`  [INFERRED]
  clients/bis_standards.py → schemas.py

## Import Cycles
- None detected.

## Communities (33 total, 6 thin omitted)

### Community 0 - "BISDatabase"
Cohesion: 0.06
Nodes (24): bis_ingestion_storage_db, BISDatabase, _connect(), Any, Connection, Path, Open (or create) the SQLite database and return a connection., Thin wrapper around SQLite for BIS standards and lab data. Usage:: with… (+16 more)

### Community 1 - "sync_pdfs_and_expand_data.py"
Cohesion: 0.09
Nodes (36): bis_ingestion_clients_bis_standards, bis_ingestion_config, bis_ingestion_rag_chunker, bis_ingestion_schemas, bis_ingestion_storage_mongo_db, http_client.py — Shared HTTP client with retry, rate limiting, and respectful…, config.py — Central configuration for the BIS Standards Ingestion Pipeline.…, csv (+28 more)

### Community 2 - "chunk_standard"
Cohesion: 0.09
Nodes (23): _approx_tokens(), _build_header(), chunk_standard(), _add(), chunk_standards_list(), iter_chunks_from_jsonl(), Path, Decompose a single BISStandard into a list of RAGChunks. Each logical section… (+15 more)

### Community 3 - "pipeline.py"
Cohesion: 0.08
Nodes (32): argparse, bis_ingestion, bis_ingestion_clients_bis_lims, bis_ingestion_clients_http_client, bis_ingestion_exporters, bis_ingestion_pipeline, bis_ingestion_rag, bis_ingestion_storage (+24 more)

### Community 4 - "BISLab"
Cohesion: 0.09
Nodes (24): BeautifulSoup, bs4, _build_search_url(), crawl_lims_by_is_number(), crawl_lims_range(), crawl_lims_search(), _get_total_count(), _parse_lims_table() (+16 more)

### Community 5 - "BISStandard"
Cohesion: 0.13
Nodes (9): field_validator, promote_labs_to_standards(), For every unique IS number in bis_labs, create a BISStandard stub record in…, BISStandard, Normalise IS number to consistent format: 'IS XXXX' or 'IS XXXX Part N'., Full metadata record for a single BIS / IS Standard., Insert or replace a BISStandard record., Bulk upsert. Returns number of records written. (+1 more)

### Community 6 - "bis_standards.py"
Cohesion: 0.17
Nodes (19): Client, _build_detail_url(), _build_search_url(), crawl_standards_api(), fetch_standard_metadata_simple(), fetch_standard_summary_api(), parse_api_standard(), _parse_standard_from_html() (+11 more)

### Community 7 - "RAGChunk"
Cohesion: 0.15
Nodes (13): BaseModel, datetime, pydantic, pytest, CrawlState, RAGChunk, schemas.py — Pydantic data models for BIS Standards metadata. Each model…, A chunk of text prepared for RAG ingestion with full provenance. (+5 more)

### Community 8 - "exporters/__init__.py"
Cohesion: 0.14
Nodes (17): export_db_rows_to_csv(), _flatten_db_row(), Path, Export raw SQLite rows (dicts) to a CSV file. Use this when pulling directly…, Flatten a raw SQLite row dict (JSON strings for lists)., exporters — CSV, JSON, and JSONL export for BIS ingestion pipeline., export_db_rows_to_jsonl(), export_standards_to_json() (+9 more)

### Community 9 - "BISHTTPClient"
Cohesion: 0.12
Nodes (12): BISHTTPClient, _get_robots(), is_crawl_allowed(), _polite_delay(), Any, Fetch and cache robots.txt for a given base URL., Return True if our User-Agent is allowed to fetch this URL., Sleep for a random interval between REQUEST_DELAY_MIN and REQUEST_DELAY_MAX. (+4 more)

### Community 10 - "Any"
Cohesion: 0.12
Nodes (8): Any, Insert or replace a standard document in MongoDB., Bulk upsert standards. Returns count written., Search standards with optional text query and filters., Insert or update an accredited lab document., Retrieve labs recognizing this standard doc number (e.g. '456' or 'IS 456')., Bulk upsert RAG chunks., Search chunks using MongoDB text index or regex match.

### Community 11 - "BISMongoDatabase"
Cohesion: 0.23
Nodes (4): Collection, BISMongoDatabase, MongoDB persistence manager for Nexaura BIS data. Usage:: with…, Aggregate high-level metrics across the database.

### Community 12 - "_split_text"
Cohesion: 0.21
Nodes (9): Split a long text into overlapping token-approximate windows. Args: text: Input…, _split_text(), download_pdf_stream(), extract_and_index_pdf(), Path, Parse PDF page-by-page using PyMuPDF and generate RAG chunks., Download a PDF using chunked stream writing with custom SSL context., run_pipeline() (+1 more)

### Community 13 - "text_utils.py"
Cohesion: 0.21
Nodes (8): parsers — Text normalisation and HTML parsing helpers., normalise_status(), parsers/text_utils.py — Shared text normalisation and extraction utilities.…, Convert a standard number to a URL-safe slug, e.g. 'IS 456' -> 'is-456'., Normalise a status string to a canonical value., slugify(), re, TestSlugify

### Community 14 - "test_parsers.py"
Cohesion: 0.22
Nodes (3): bis_ingestion_parsers, tests/test_parsers.py — Unit tests for text_utils parser helpers., TestNormaliseStatus

### Community 15 - "migrate_rag_chunks"
Cohesion: 0.25
Nodes (9): migrate_rag_chunks(), migrate_sqlite_labs(), migrate_sqlite_standards(), Connection, Path, Read standards from SQLite and insert into MongoDB., Read labs from SQLite and insert into MongoDB., Read RAG chunks from JSONL and insert into MongoDB. (+1 more)

### Community 16 - "clean_text"
Cohesion: 0.39
Nodes (3): clean_text(), Strip and collapse whitespace, optionally truncate. Returns None for empty or…, TestCleanText

### Community 17 - "extract_is_numbers"
Cohesion: 0.39
Nodes (3): extract_is_numbers(), Extract all IS numbers found in a block of text., TestExtractIsNumbers

### Community 18 - "expand_new_industries"
Cohesion: 0.25
Nodes (8): download_pdf_stream(), expand_new_industries(), main(), Path, Upload all downloaded PDFs into MongoDB GridFS and 'documents' collection., Fetch new sector standards from official BIS API and upsert into MongoDB., Download PDF stream using chunked writing., store_pdfs_in_mongodb()

### Community 19 - ".connect"
Cohesion: 0.29
Nodes (3): Database, Ensure all required performance and text indexes exist., Establish connection and ensure indexes exist.

### Community 20 - "normalise_date"
Cohesion: 0.43
Nodes (3): normalise_date(), Try to normalise a date string to ISO format (YYYY-MM-DD). Falls back to the…, TestNormaliseDate

### Community 21 - "normalise_is_number"
Cohesion: 0.43
Nodes (3): normalise_is_number(), Normalise an IS number string to canonical form: 'IS XXXX Part N Sec M'., TestNormaliseIsNumber

### Community 22 - "parse_is_components"
Cohesion: 0.43
Nodes (3): parse_is_components(), Parse an IS number string into its components. Returns: dict with keys: doc_no,…, TestParseIsComponents

### Community 23 - "extract_amendment_numbers"
Cohesion: 0.47
Nodes (3): extract_amendment_numbers(), Extract amendment numbers from text, e.g. 'AMD 1', 'Amendment 2'., TestExtractAmendmentNumbers

### Community 24 - "extract_year"
Cohesion: 0.47
Nodes (3): extract_year(), Extract the first 4-digit year from a string., TestExtractYear

### Community 25 - "extract_ics_codes"
Cohesion: 0.50
Nodes (3): extract_ics_codes(), Extract ICS codes (e.g. '91.080.30') from text., TestExtractIcsCodes

### Community 26 - "strip_html_tags"
Cohesion: 0.50
Nodes (3): Remove all HTML tags from a string., strip_html_tags(), TestStripHtmlTags

## Knowledge Gaps
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BISStandard` connect `BISStandard` to `BISDatabase`, `chunk_standard`, `pipeline.py`, `BISLab`, `bis_standards.py`, `RAGChunk`, `exporters/__init__.py`, `Any`, `BISMongoDatabase`, `expand_new_industries`?**
  _High betweenness centrality (0.208) - this node is a cross-community bridge._
- **Why does `BISMongoDatabase` connect `BISMongoDatabase` to `sync_pdfs_and_expand_data.py`, `BISLab`, `BISStandard`, `RAGChunk`, `Any`, `_split_text`, `migrate_rag_chunks`, `expand_new_industries`, `.connect`, `.close`, `.get_standard`, `.log_crawl_run`?**
  _High betweenness centrality (0.189) - this node is a cross-community bridge._
- **Why does `BISDatabase` connect `BISDatabase` to `sync_pdfs_and_expand_data.py`, `pipeline.py`, `BISLab`, `BISStandard`?**
  _High betweenness centrality (0.184) - this node is a cross-community bridge._
- **Are the 27 inferred relationships involving `BISDatabase` (e.g. with `main()` and `promote_labs_to_standards()`) actually correct?**
  _`BISDatabase` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `BISStandard` (e.g. with `crawl_standards_api()` and `fetch_standard_metadata_simple()`) actually correct?**
  _`BISStandard` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `BISMongoDatabase` (e.g. with `run_pipeline()` and `migrate_rag_chunks()`) actually correct?**
  _`BISMongoDatabase` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `chunk_standard()` (e.g. with `BISStandard` and `RAGChunk`) actually correct?**
  _`chunk_standard()` has 15 INFERRED edges - model-reasoned connections that need verification._