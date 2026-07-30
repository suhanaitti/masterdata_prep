"""
field_mappings.py
------------------
Field-to-field mapping between a CONFIRMED source master_file and a CONFIRMED
destination master_file of the same master type - see field_mapping_engine.py.

  GET  /api/field-mappings                          - read-only mapping view (no LLM call)
  POST /api/field-mappings/run/start                  - start a mapping run in a background thread
  POST /api/field-mappings/run/stop                   - ask the current run for this file pair to stop
  GET  /api/field-mappings/run/status                 - poll progress (batches done, running/done/stopped)
  GET  /api/field-mappings/rejections                - permanent rejection history for a file pair
  POST /api/field-mappings/rejections/{id}/restore    - un-reject a pair, confirm it as approved
  GET  /api/field-mappings/export                    - download suggestions or approved mappings as xlsx/csv/json
  POST /api/field-mappings/{id}/accept                - approve a suggestion
  POST /api/field-mappings/{id}/reject                - reject a suggestion (never re-proposed)
  POST /api/field-mappings/manual                     - manually confirm a source<->destination pair

Run/stop mirrors Header_Mapping's Streamlit Stop-button pattern (background
thread + a stop Event checked between batches, partial results kept) - adapted to
FastAPI's stateless request/response model via an in-memory _RUNS dict keyed by
(source_file_id, destination_file_id), since a single HTTP request can't stay open
while a separate "stop" request comes in on another connection.
"""
import io
import threading

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.config import get_connection
from app.schemas.field_mapping import (
    FieldMappingPairOut, ManualMapIn, MappingFieldOut, MappingViewOut,
    RejectionLogEntryOut, RunStatusOut,
)
from app.services import field_mapping_engine

router = APIRouter(prefix="/api/field-mappings", tags=["field-mappings"])

# In-process only - fine for a single-worker dev/small-deployment backend. Keyed by
# (source_file_id, destination_file_id). Each entry: {"thread", "stop_event", "status",
# "batches_done", "total_batches", "new_suggestions", "failed_batches", "error"}.
_RUNS: dict[tuple[int, int], dict] = {}


def _to_field_out(f: dict) -> MappingFieldOut:
    return MappingFieldOut(
        id=f["id"], column_name=f["column_name"],
        description=f.get("ai_description") or f.get("description"),
        data_type=f.get("data_type"), length=f.get("estimated_length") or f.get("length"),
        is_primary_key=bool(f.get("is_primary_key")),
        is_business_identifier=bool(f.get("is_business_identifier")),
    )


def _to_pair_out(p: dict) -> FieldMappingPairOut:
    return FieldMappingPairOut(
        mapping_id=p["mapping_id"], mapping_type=p["mapping_type"], status=p["status"],
        confidence=p["confidence"], match_basis=p.get("match_basis"), remarks=p.get("remarks"),
        source=_to_field_out(p["source"]), destination=_to_field_out(p["destination"]),
    )


@router.get("", response_model=MappingViewOut)
def get_mapping_view(source_file_id: int, destination_file_id: int):
    conn = get_connection()
    cur = conn.cursor()
    view = field_mapping_engine.get_mapping_view(cur, source_file_id, destination_file_id)
    cur.close()
    conn.close()
    return MappingViewOut(
        matches=[_to_pair_out(p) for p in view["matches"]],
        ai_suggestions=[_to_pair_out(p) for p in view["ai_suggestions"]],
        unmapped_source=[_to_field_out(f) for f in view["unmapped_source"]],
        unmapped_destination=[_to_field_out(f) for f in view["unmapped_destination"]],
    )


@router.post("/run/start", response_model=RunStatusOut)
def start_run(source_file_id: int, destination_file_id: int):
    key = (source_file_id, destination_file_id)
    existing = _RUNS.get(key)
    if existing and existing["status"] == "running":
        raise HTTPException(status_code=409, detail="A mapping run is already in progress for this file pair.")

    stop_event = threading.Event()
    state = {
        "status": "running", "batches_done": 0, "total_batches": 0,
        "new_suggestions": 0, "failed_batches": [], "error": None, "stop_event": stop_event,
    }
    _RUNS[key] = state

    def _worker():
        conn = get_connection()
        cur = conn.cursor()

        def _progress(batch_num, total_batches):
            state["batches_done"] = batch_num
            state["total_batches"] = total_batches

        try:
            result = field_mapping_engine.run_mapping(
                source_file_id, destination_file_id, cur,
                should_stop=stop_event.is_set, progress_callback=_progress,
            )
            conn.commit()
            state["new_suggestions"] = result["new_suggestions"]
            state["failed_batches"] = result["failed_batches"]
            state["total_batches"] = result["total_batches"]
            state["status"] = "stopped" if result["stopped_early"] else "done"
        except Exception as e:
            conn.rollback()
            state["status"] = "error"
            state["error"] = str(e)
        finally:
            cur.close()
            conn.close()

    thread = threading.Thread(target=_worker, daemon=True)
    state["thread"] = thread
    thread.start()
    return RunStatusOut(status="running")


@router.get("/run/status", response_model=RunStatusOut)
def get_run_status(source_file_id: int, destination_file_id: int):
    state = _RUNS.get((source_file_id, destination_file_id))
    if state is None:
        return RunStatusOut(status="idle")
    return RunStatusOut(
        status=state["status"], batches_done=state["batches_done"], total_batches=state["total_batches"],
        new_suggestions=state["new_suggestions"], failed_batches=state["failed_batches"], error=state["error"],
    )


@router.post("/run/stop", status_code=204)
def stop_run(source_file_id: int, destination_file_id: int):
    state = _RUNS.get((source_file_id, destination_file_id))
    if state is None or state["status"] != "running":
        return
    state["stop_event"].set()


@router.get("/rejections", response_model=list[RejectionLogEntryOut])
def get_rejection_log(source_file_id: int, destination_file_id: int):
    conn = get_connection()
    cur = conn.cursor()
    rows = field_mapping_engine.get_rejection_log(cur, source_file_id, destination_file_id)
    cur.close()
    conn.close()
    return [
        RejectionLogEntryOut(
            id=r["id"], confidence_score=float(r["confidence_score"]) if r["confidence_score"] is not None else None,
            rejected_at=r["rejected_at"].isoformat(),
            source=_to_field_out({
                "id": r["source_id"], "column_name": r["source_name"], "ai_description": r["source_description"],
            }),
            destination=_to_field_out({
                "id": r["destination_id"], "column_name": r["destination_name"],
                "ai_description": r["destination_description"],
            }),
        )
        for r in rows
    ]


@router.post("/rejections/{rejection_id}/restore", status_code=204)
def restore_rejection(rejection_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        field_mapping_engine.restore_rejection(cur, rejection_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


_EXPORT_MEDIA_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "json": "application/json",
}


def _ai_reason(p: dict) -> str:
    """Combines match_basis + remarks into one human-readable "why" phrase, e.g.
    "Description match - Both represent product classification" - matches what the
    UI's reasoning checklist already shows, condensed to one export column."""
    parts = [p.get("match_basis"), p.get("remarks")]
    text = " - ".join(x for x in parts if x)
    return text or "NA"


@router.get("/export")
def export_suggestions(
    source_file_id: int,
    destination_file_id: int,
    format: str = Query("xlsx", pattern="^(xlsx|csv|json)$"),
    dataset: str = Query("suggestions", pattern="^(suggestions|approved|all)$"),
):
    """Download field mappings for this file pair. `dataset=suggestions` (default)
    exports the still-pending AI suggestions; `dataset=approved` exports confirmed
    matches (both AI-accepted and manual) instead; `dataset=all` combines BOTH into
    one simple sheet - Source Field / Destination Field / Confidence / AI Reason /
    Status - so the AI's proposed mappings can be downloaded and reviewed/shared
    right after a run, before (or regardless of) how far human approval has
    progressed; Status reflects each row's CURRENT state (Approved vs Pending
    Review) at download time. `format` picks xlsx/csv/json."""
    conn = get_connection()
    cur = conn.cursor()
    view = field_mapping_engine.get_mapping_view(cur, source_file_id, destination_file_id)
    cur.close()
    conn.close()

    if dataset == "all":
        rows = [
            {
                "Source Field": p["source"]["column_name"],
                "Destination Field": p["destination"]["column_name"],
                "Confidence": p["confidence"],
                "AI Reason": _ai_reason(p),
                "Status": "Approved",
            }
            for p in view["matches"]
        ] + [
            {
                "Source Field": p["source"]["column_name"],
                "Destination Field": p["destination"]["column_name"],
                "Confidence": p["confidence"],
                "AI Reason": _ai_reason(p),
                "Status": "Pending Review",
            }
            for p in view["ai_suggestions"]
        ]
    else:
        pairs = view["ai_suggestions"] if dataset == "suggestions" else view["matches"]
        rows = [
            {
                "Source Field": p["source"]["column_name"],
                "Source Description": p["source"].get("description") or "NA",
                "Source Type": p["source"].get("data_type") or "NA",
                "Destination Field": p["destination"]["column_name"],
                "Destination Description": p["destination"].get("description") or "NA",
                "Destination Type": p["destination"].get("data_type") or "NA",
                "Confidence %": p["confidence"],
                "Match Basis": p.get("match_basis") or "NA",
                "Remarks": p.get("remarks") or "NA",
            }
            for p in pairs
        ]
    df = pd.DataFrame(rows)
    filename_base = f"field_mapping_{dataset}_{source_file_id}_{destination_file_id}"

    if format == "csv":
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        body = buf.getvalue()
        return StreamingResponse(
            iter([body]),
            media_type=_EXPORT_MEDIA_TYPES["csv"],
            headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"},
        )

    if format == "json":
        body = df.to_json(orient="records", indent=2)
        return StreamingResponse(
            iter([body]),
            media_type=_EXPORT_MEDIA_TYPES["json"],
            headers={"Content-Disposition": f"attachment; filename={filename_base}.json"},
        )

    sheet_names = {"suggestions": "Suggestions", "approved": "Approved", "all": "Field Mapping"}
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_names[dataset])
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type=_EXPORT_MEDIA_TYPES["xlsx"],
        headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"},
    )


@router.post("/{mapping_id}/accept", status_code=204)
def accept_mapping(mapping_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        field_mapping_engine.accept_mapping(cur, mapping_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@router.post("/{mapping_id}/reject", status_code=204)
def reject_mapping(mapping_id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        field_mapping_engine.reject_mapping(cur, mapping_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@router.post("/manual", status_code=204)
def manual_map(body: ManualMapIn):
    conn = get_connection()
    cur = conn.cursor()
    try:
        field_mapping_engine.manual_map(cur, body.source_field_id, body.destination_field_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
