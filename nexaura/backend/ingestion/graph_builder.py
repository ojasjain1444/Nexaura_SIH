"""
graph_builder.py — Phase 10: Knowledge Graph Construction

Project: Nexaura (SIH 2026 — SIH26107)

Builds a knowledge graph of relationships between BIS standards.

Graph structure:
    Standard → Edition → Clause → Sub-Clause

Cross-document edges:
    Standard → Superseded By → Standard
    Standard → Amendment → Amendment
    Standard → References → Standard
    Standard → Related Standard → Standard

CRITICAL RULE:
    Only populate relationships from EVIDENCE found in the document.
    NEVER infer a relationship merely because two standards look similar.
    NEVER fabricate supersession, amendment, or reference relationships.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Graph Models
# =============================================================================

@dataclass
class GraphNode:
    """A node in the knowledge graph."""
    node_id: str
    node_type: str      # standard | edition | clause | sub_clause | amendment
    label: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge in the knowledge graph."""
    edge_id: str
    from_node: str
    to_node: str
    relation: str       # contains | supersedes | references | amended_by | related_to
    source_evidence: str = ""   # The text that provides evidence for this edge


@dataclass
class KnowledgeGraph:
    """The complete knowledge graph for the BIS corpus."""
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        # Avoid duplicate edges
        for existing in self.edges:
            if (existing.from_node == edge.from_node
                    and existing.to_node == edge.to_node
                    and existing.relation == edge.relation):
                return
        self.edges.append(edge)

    def to_dict(self) -> dict:
        return {
            "nodes": {k: {
                "node_id": v.node_id,
                "node_type": v.node_type,
                "label": v.label,
                "attributes": v.attributes,
            } for k, v in self.nodes.items()},
            "edges": [{
                "edge_id": e.edge_id,
                "from": e.from_node,
                "to": e.to_node,
                "relation": e.relation,
                "source_evidence": e.source_evidence,
            } for e in self.edges],
            "statistics": {
                "total_nodes": len(self.nodes),
                "total_edges": len(self.edges),
                "node_types": self._count_by_type("node"),
                "edge_types": self._count_by_type("edge"),
            }
        }

    def _count_by_type(self, entity: str) -> dict:
        if entity == "node":
            types: dict[str, int] = {}
            for n in self.nodes.values():
                types[n.node_type] = types.get(n.node_type, 0) + 1
            return types
        else:
            types = {}
            for e in self.edges:
                types[e.relation] = types.get(e.relation, 0) + 1
            return types


# =============================================================================
# Graph Builder
# =============================================================================

class GraphBuilder:
    """
    Incrementally builds the knowledge graph as PDFs are processed.

    Usage:
        builder = GraphBuilder()
        for each PDF:
            builder.add_document(meta, clauses)
        builder.save(output_path)
    """

    def __init__(self) -> None:
        self.graph = KnowledgeGraph()
        self._edge_counter = 0

    def add_document(
        self,
        metadata,        # DocumentMetadata
        knowledge_units: list,  # list[KnowledgeUnit]
    ) -> None:
        """
        Add a processed BIS document to the knowledge graph.

        Args:
            metadata: DocumentMetadata for the document
            knowledge_units: List of KnowledgeUnit records from this document
        """
        std_num = metadata.standard_number
        if not std_num or std_num == "unknown":
            logger.warning("Skipping graph entry for unknown standard")
            return

        # --- Standard node ---
        std_node_id = self._std_id(std_num)
        self.graph.add_node(GraphNode(
            node_id=std_node_id,
            node_type="standard",
            label=std_num,
            attributes={
                "title": metadata.title,
                "status": metadata.status,
                "source_pdf": metadata.source_pdf,
            },
        ))

        # --- Edition node ---
        if metadata.year or metadata.edition:
            edition_label = metadata.edition or str(metadata.year)
            ed_node_id = f"{std_node_id}_ED_{edition_label}"
            self.graph.add_node(GraphNode(
                node_id=ed_node_id,
                node_type="edition",
                label=f"{std_num}:{edition_label}",
                attributes={"year": metadata.year, "edition": metadata.edition},
            ))
            self.graph.add_edge(GraphEdge(
                edge_id=self._next_edge_id(),
                from_node=std_node_id,
                to_node=ed_node_id,
                relation="has_edition",
            ))

        # --- Clause nodes ---
        for ku in knowledge_units:
            clause_node_id = f"{std_node_id}_{ku.clause}"
            self.graph.add_node(GraphNode(
                node_id=clause_node_id,
                node_type="clause",
                label=f"{std_num} — {ku.clause}",
                attributes={
                    "heading": ku.heading,
                    "content_type": ku.content_type,
                    "page_start": ku.page_start,
                    "page_end": ku.page_end,
                },
            ))

            # Parent edge
            if ku.parent_clause:
                parent_node_id = f"{std_node_id}_{ku.parent_clause}"
                self.graph.add_edge(GraphEdge(
                    edge_id=self._next_edge_id(),
                    from_node=parent_node_id,
                    to_node=clause_node_id,
                    relation="contains",
                ))
            else:
                # Top-level clause connects to edition or standard
                parent = ed_node_id if (metadata.year or metadata.edition) else std_node_id
                self.graph.add_edge(GraphEdge(
                    edge_id=self._next_edge_id(),
                    from_node=parent,
                    to_node=clause_node_id,
                    relation="contains",
                ))

        # --- Supersession (evidence-based only) ---
        if metadata.supersedes:
            target_id = self._std_id(metadata.supersedes)
            self.graph.add_node(GraphNode(
                node_id=target_id,
                node_type="standard",
                label=metadata.supersedes,
                attributes={"status": "superseded"},
            ))
            self.graph.add_edge(GraphEdge(
                edge_id=self._next_edge_id(),
                from_node=std_node_id,
                to_node=target_id,
                relation="supersedes",
                source_evidence="Document foreword/metadata",
            ))

        if metadata.superseded_by:
            target_id = self._std_id(metadata.superseded_by)
            self.graph.add_node(GraphNode(
                node_id=target_id,
                node_type="standard",
                label=metadata.superseded_by,
            ))
            self.graph.add_edge(GraphEdge(
                edge_id=self._next_edge_id(),
                from_node=std_node_id,
                to_node=target_id,
                relation="superseded_by",
                source_evidence="Document foreword/metadata",
            ))

        # --- References (evidence-based only) ---
        for ref in metadata.references:
            if not ref or not ref.strip():
                continue
            ref_node_id = self._std_id(ref)
            if ref_node_id not in self.graph.nodes:
                self.graph.add_node(GraphNode(
                    node_id=ref_node_id,
                    node_type="standard",
                    label=ref,
                ))
            self.graph.add_edge(GraphEdge(
                edge_id=self._next_edge_id(),
                from_node=std_node_id,
                to_node=ref_node_id,
                relation="references",
                source_evidence="Document references section",
            ))

        # --- Amendments (evidence-based only) ---
        for amend in metadata.amended_by:
            amend_node_id = f"{std_node_id}_AMEND_{amend}"
            self.graph.add_node(GraphNode(
                node_id=amend_node_id,
                node_type="amendment",
                label=f"{std_num} Amendment {amend}",
            ))
            self.graph.add_edge(GraphEdge(
                edge_id=self._next_edge_id(),
                from_node=std_node_id,
                to_node=amend_node_id,
                relation="amended_by",
                source_evidence="Document metadata",
            ))

        logger.info(
            "Graph updated: %s → nodes=%d edges=%d",
            std_num, len(self.graph.nodes), len(self.graph.edges),
        )

    def save(self, output_path: Path) -> None:
        """Save the knowledge graph as JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        graph_dict = self.graph.to_dict()
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(graph_dict, f, ensure_ascii=False, indent=2)
        logger.info(
            "Knowledge graph saved: %s (nodes=%d, edges=%d)",
            output_path, graph_dict["statistics"]["total_nodes"],
            graph_dict["statistics"]["total_edges"],
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _std_id(self, standard_number: str) -> str:
        """Generate a graph node ID from a standard number."""
        import re
        return "STD_" + re.sub(r"[^A-Za-z0-9]", "_", standard_number).upper()

    def _next_edge_id(self) -> str:
        self._edge_counter += 1
        return f"E{self._edge_counter:06d}"
