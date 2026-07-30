"""
events.py (router)
-------------------
Read-only access to the agent activity log (see app/services/events.py for the
write path). One endpoint: list recent events, optionally filtered by file/pair or
event type - "which agent did what, when, how long" as a queryable log.
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.config import get_connection

router = APIRouter(prefix="/api/events", tags=["events"])


class EventOut(BaseModel):
    id: int
    event_type: str
    source_file_id: Optional[int] = None
    destination_file_id: Optional[int] = None
    agent: Optional[str] = None
    status: str
    duration_ms: Optional[int] = None
    detail: Optional[dict] = None
    created_at: datetime


@router.get("", response_model=list[EventOut])
def list_events(
    source_file_id: Optional[int] = None,
    destination_file_id: Optional[int] = None,
    event_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    conn = get_connection()
    cur = conn.cursor()
    clauses, params = [], []
    if source_file_id is not None:
        clauses.append("source_file_id = %s")
        params.append(source_file_id)
    if destination_file_id is not None:
        clauses.append("destination_file_id = %s")
        params.append(destination_file_id)
    if event_type is not None:
        clauses.append("event_type = %s")
        params.append(event_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    cur.execute(
        f"""SELECT id, event_type, source_file_id, destination_file_id, agent, status, duration_ms, detail, created_at
            FROM events {where} ORDER BY created_at DESC LIMIT %s""",
        params,
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return [EventOut(**r) for r in rows]
