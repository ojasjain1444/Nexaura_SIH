"""
evaluator.py — Evaluation Framework

Project: Nexaura (SIH 2026 — SIH26107)

Evaluates retrieval quality (Recall@k, MRR) and extraction accuracy.
"""

from __future__ import annotations

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class Evaluator:
    """Evaluates retrieval metrics based on ground truth data."""

    def evaluate_retrieval(self, queries: List[Dict], search_func, top_k: int = 10) -> Dict:
        """
        Evaluate search retrieval performance.
        
        queries: List of dicts with 'query' and 'ground_truth_id'
        search_func: Callable that takes a query string and returns a list of result IDs
        """
        total = len(queries)
        if total == 0:
             return {}
             
        hits = 0
        rr_sum = 0.0
        
        for q in queries:
             query_text = q['query']
             gt_id = q['ground_truth_id']
             
             results = search_func(query_text, top_k=top_k)
             result_ids = [r.knowledge_unit_id for r in results]
             
             if gt_id in result_ids:
                 hits += 1
                 rank = result_ids.index(gt_id) + 1
                 rr_sum += 1.0 / rank
                 
        metrics = {
             f"recall@{top_k}": hits / total,
             "mrr": rr_sum / total,
             "total_queries": total
        }
        return metrics
