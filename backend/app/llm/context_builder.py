"""
Context builder — retrieved chunks -> structured LLM context.

Kept separate from ChatService per Phase 5's architecture requirement:
ChatService coordinates the workflow, but does not itself know how
retrieved chunks get formatted for the LLM. See app/llm/grounding.py for
the actual delimiter format (build_context_block), which this module
feeds.
"""

from app.schemas.retrieval import RetrievedChunk

# Controlled context strategy (Phase 5 §15): only the N most recent prior
# messages are included, never the full conversation history — bounds
# prompt size and prevents very old exchanges from diluting the current
# grounding evidence.
MAX_HISTORY_MESSAGES = 6


def chunks_to_context_dicts(chunks: list[RetrievedChunk]) -> list[dict]:
    """Converts RetrievedChunk objects into the plain dicts
    build_context_block() expects — keeps app/llm/grounding.py free of any
    dependency on the retrieval schema module."""
    return [
        {
            "document_name": chunk.document_name,
            "page_number": chunk.page_number,
            "section": chunk.section,
            "text": chunk.text,
        }
        for chunk in chunks
    ]


def truncate_history(history: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Keeps only the most recent MAX_HISTORY_MESSAGES (role, content)
    pairs. The current user query and retrieved evidence are handled
    separately by the caller — this function only bounds prior turns."""
    if len(history) <= MAX_HISTORY_MESSAGES:
        return history
    return history[-MAX_HISTORY_MESSAGES:]
