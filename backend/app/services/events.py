"""
events.py
---------
Agent activity log: one row per AI call or human decision, so "which agent did
what, when, how long" is answerable after the fact - separate from
master_field_mappings (the mapping DATA itself), this is the AUDIT TRAIL of how
that data came to be. Every write goes through log_event() so the shape stays
consistent regardless of caller (classifier, metadata generator, mapping engine,
or a human accept/reject action).
"""
import json


def log_event(
    cur,
    event_type: str,
    source_file_id: int = None,
    destination_file_id: int = None,
    agent: str = None,
    status: str = "success",
    duration_ms: int = None,
    detail: dict = None,
) -> None:
    """event_type examples: 'classification', 'metadata_generation',
    'field_mapping_batch', 'accept', 'reject', 'manual_map'. agent is the provider/key
    that served an AI call (e.g. "Groq (key 2)") or "human" for a review decision.
    Uses the caller's own cursor/transaction - a failed event write should never be
    the reason a real operation's transaction rolls back, so callers that log
    speculatively (e.g. right before a commit) should treat this as best-effort."""
    cur.execute(
        """INSERT INTO events
               (event_type, source_file_id, destination_file_id, agent, status, duration_ms, detail)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (event_type, source_file_id, destination_file_id, agent, status, duration_ms,
         json.dumps(detail) if detail is not None else None),
    )
