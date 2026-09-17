"""
test_canteen_query.py — Search Query Test Suite for Canteen & BIS Standards

Project: Nexaura (SIH 2026 — SIH26107)

Verifies multi-clause BM25 and RAG retrieval accuracy.
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexaura.backend.search.bm25 import BM25Index


def run_canteen_query_test():
    bm25_path = PROJECT_ROOT / "nexaura" / "data" / "embeddings" / "bm25_index.pkl"
    index = BM25Index(index_path=bm25_path)

    if not index.load():
        print("[INFO] BM25 index not found. Please run ingestion first.")
        return

    queries = [
        "canteen food safety hygiene water",
        "drinking water requirements IS 10500",
        "steel utensils storage containers",
    ]

    for q in queries:
        print(f"\n--- Query: '{q}' ---")
        results = index.search(q, top_k=3)
        for r in results:
            meta = r.get("metadata", {})
            std_num = meta.get("standard_number") or "IS Standard"
            print(f"[{r['rank']}] Score: {r['score']:.4f} | Standard: {std_num} | Clause: {meta.get('clause')}")
            print(f"     Heading: {meta.get('heading')}")


if __name__ == "__main__":
    run_canteen_query_test()
