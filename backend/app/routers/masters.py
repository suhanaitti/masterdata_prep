"""
masters.py
----------
Endpoints for the master-data prep pipeline:
  POST /api/masters/list-sheets   - peek at an Excel workbook's sheet names before committing to one
  POST /api/masters/upload        - read + classify a file; auto-confirms and generates
                                     metadata immediately if confidence clears the threshold,
                                     otherwise leaves it pending for a human to confirm
  POST /api/masters/{id}/confirm  - human confirms/corrects the master type; triggers
                                     metadata generation for a file that was left pending
  GET    /api/masters              - list every uploaded file (for a review dashboard)
  GET    /api/masters/{id}         - one file's detail + its generated field metadata
  DELETE /api/masters/{id}         - remove a file and everything derived from it

Many-source/one-destination rule: per master type, any number of side='source' files
are allowed; side='destination' was previously capped at one CONFIRMED file per
master type (409 on a second upload) but that check is DISABLED as of 2026-07-29
(see _check_destination_conflict) so testing can upload the same or multiple
destination files freely - re-enable later by restoring that function's body.
"""
import io
import json
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from psycopg2.extras import execute_values

from app.config import get_connection
from app.schemas.master import (
    ConfirmMasterTypeIn, FieldMetadataOut, MasterFileDetailOut, MasterFileOut,
    MasterTypeCandidateOut, SheetListOut, UploadResultOut,
)
from app.services import excel_reader
from app.services.embeddings import embed_texts, field_embedding_text
from app.services.events import log_event
from app.services.master_classifier import CONFIDENT_THRESHOLD, MASTER_TYPES, classify_master_type
from app.services.metadata_generator import (
    detect_field_list_columns, generate_field_metadata_for_file, generate_field_metadata_for_rows,
)

router = APIRouter(prefix="/api/masters", tags=["masters"])


def _row_to_master_file_out(row: dict) -> MasterFileOut:
    return MasterFileOut(
        id=row["id"], filename=row["filename"], sheet_name=row["sheet_name"], side=row["side"],
        detected_master_type=row["detected_master_type"], detection_confidence=row["detection_confidence"],
        confirmed_master_type=row["confirmed_master_type"], status=row["status"],
        row_count=row["row_count"], column_count=row["column_count"],
        uploaded_at=row["uploaded_at"], confirmed_at=row["confirmed_at"],
        business_purpose=row.get("business_purpose"),
        consolidation_conflicts=row.get("consolidation_conflicts") or [],
    )


def _fetch_master_file(cur, master_file_id: int) -> dict:
    cur.execute(
        """SELECT id, filename, sheet_name, side, detected_master_type, detection_confidence,
                  confirmed_master_type, status, row_count, column_count, schema_summary,
                  business_purpose, consolidation_conflicts, uploaded_at, confirmed_at
           FROM master_files WHERE id = %s""",
        (master_file_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"master_file {master_file_id} not found")
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _check_destination_conflict(cur, master_type: str, exclude_file_id: int = None) -> None:
    """DISABLED (2026-07-29, user request): was enforcing one-CONFIRMED-destination-
    file-per-master-type, raising 409 on a second upload. Blocking real testing where
    the same file (or several destination candidates) needs to be uploaded more than
    once. Left in place, not deleted, so the rule can come back with a one-line
    revert once testing is done - restore the body below to re-enable:

    cur.execute(
        '''SELECT id, filename FROM master_files
           WHERE side = 'destination' AND confirmed_master_type = %s AND status = 'confirmed'
             AND id != %s''',
        (master_type, exclude_file_id or -1),
    )
    row = cur.fetchone()
    if row:
        raise HTTPException(
            status_code=409,
            detail=(
                f"A destination file already exists for {master_type} ({row[1]}) - "
                f"remove it first (DELETE /api/masters/{row[0]}) if you want to replace it."
            ),
        )
    """
    return


def _store_rows_and_metadata(cur, master_file_id: int, filename: str, schema_summary: dict, master_type: str) -> list:
    """Generates AI field metadata and persists master_fields plus the file's
    business_purpose/consolidation_conflicts. Returns the field metadata list.

    Auto-detects which of the two upload shapes this file is (see
    metadata_generator.py's module docstring): if the raw columns look like an ERP
    field list (Field Name/Data Element/Data Type/Length/Decimal/Short Description),
    metadata is generated PER ERP FIELD ROW (e.g. MATNR, WERKS) - the real fields
    field_mapping_engine.py needs to match on. Otherwise falls back to the original
    per-COLUMN path for a genuine raw data export (e.g. an actual Customer/Vendor
    record dump, one row = one business record)."""
    columns = [c["column_name"] for c in schema_summary["columns"]]
    colmap = detect_field_list_columns(columns)

    if colmap is not None:
        cur.execute(
            "SELECT row_data FROM master_rows WHERE master_file_id = %s ORDER BY row_index",
            (master_file_id,),
        )
        rows = [r[0] for r in cur.fetchall()]
        result = generate_field_metadata_for_rows(master_type, rows, colmap)
    else:
        result = generate_field_metadata_for_file(master_type, filename, schema_summary)
    fields = result["fields"]

    cur.execute(
        "UPDATE master_files SET business_purpose = %s, consolidation_conflicts = %s WHERE id = %s",
        (result["business_purpose"], json.dumps(result["conflicts"]), master_file_id),
    )

    total_duration_ms = sum(c["duration_ms"] or 0 for c in result["_agent_calls"])
    agents_used = sorted({c["agent"] for c in result["_agent_calls"]})
    log_event(
        cur, "metadata_generation", source_file_id=master_file_id,
        agent=", ".join(agents_used), duration_ms=total_duration_ms,
        detail={"field_count": len(fields), "llm_calls": len(result["_agent_calls"]), "mode": "row-wise" if colmap else "column-wise"},
    )

    # Embeddings computed here (once per field, right alongside the rest of its
    # metadata) rather than lazily at mapping-run time, so field_mapping_engine.py's
    # semantic-search candidate ranking never has to wait on model inference mid-run.
    embedding_texts = [field_embedding_text(f["column_name"], f["description"]) for f in fields]
    embeddings = embed_texts(embedding_texts)

    for order, (f, embedding) in enumerate(zip(fields, embeddings)):
        cur.execute(
            """INSERT INTO master_fields
                   (master_file_id, field_order, column_name, ai_description, business_category,
                    data_type, estimated_length, is_mandatory, is_primary_key, is_business_identifier,
                    confidence_score, ai_remarks, embedding)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (master_file_id, column_name) DO UPDATE SET
                   ai_description = EXCLUDED.ai_description, business_category = EXCLUDED.business_category,
                   data_type = EXCLUDED.data_type,
                   estimated_length = EXCLUDED.estimated_length, is_mandatory = EXCLUDED.is_mandatory,
                   is_primary_key = EXCLUDED.is_primary_key,
                   is_business_identifier = EXCLUDED.is_business_identifier,
                   confidence_score = EXCLUDED.confidence_score, ai_remarks = EXCLUDED.ai_remarks,
                   embedding = EXCLUDED.embedding""",
            (master_file_id, order, f["column_name"], f["description"], f.get("business_category"), f["data_type"],
             f["estimated_length"], f["is_mandatory"], f["is_primary_key"],
             f["is_business_identifier"], f["confidence"], f["remarks"], json.dumps(embedding)),
        )
    return fields


@router.post("/list-sheets", response_model=SheetListOut)
async def list_sheets(file: UploadFile = File(...)):
    content = await file.read()
    sheet_names = excel_reader.list_sheet_names(io.BytesIO(content), file.filename)
    return SheetListOut(sheet_names=sheet_names)


@router.post("/upload", response_model=UploadResultOut)
async def upload_master_file(
    file: UploadFile = File(...), sheet_name: str = Form(None), side: str = Form("source"),
):
    if side not in ("source", "destination"):
        raise HTTPException(status_code=400, detail="side must be 'source' or 'destination'")

    content = await file.read()
    try:
        df = excel_reader.read_file(io.BytesIO(content), file.filename, sheet_name=sheet_name or 0)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Couldn't read this file: {e}")

    schema_summary = excel_reader.build_schema_summary(df)

    try:
        classification = classify_master_type(file.filename, sheet_name or "", schema_summary)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI classification failed: {e}")

    is_confident = (
        classification["master_type"] is not None
        and classification["confidence"] >= CONFIDENT_THRESHOLD
    )

    confirmed_at = datetime.now() if is_confident else None

    conn = get_connection()
    cur = conn.cursor()
    try:
        # Many-source/one-destination rule (per master type): only checkable here when
        # the master type is ALREADY known, i.e. confident enough to auto-confirm this
        # upload immediately. If it's left pending, the same check runs again at
        # /confirm time, once a human (or auto-logic) actually settles the master type.
        if side == "destination" and is_confident:
            _check_destination_conflict(cur, classification["master_type"])

        cur.execute(
            """INSERT INTO master_files
                   (filename, sheet_name, side, detected_master_type, detection_confidence,
                    confirmed_master_type, status, row_count, column_count, schema_summary,
                    confirmed_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                file.filename, sheet_name, side, classification["master_type"], classification["confidence"],
                classification["master_type"] if is_confident else None,
                "confirmed" if is_confident else "pending_confirmation",
                schema_summary["row_count"], schema_summary["column_count"],
                json.dumps(schema_summary), confirmed_at,
            ),
        )
        master_file_id = cur.fetchone()[0]

        cur.execute(
            """INSERT INTO master_type_detection_log
                   (master_file_id, detected_type, confidence, reasoning, signals_used, candidates)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (master_file_id, classification["master_type"], classification["confidence"],
             classification["reasoning"], json.dumps(classification["signals_used"]),
             json.dumps(classification["candidates"])),
        )

        log_event(
            cur, "classification", source_file_id=master_file_id,
            agent=classification["_agent"], duration_ms=classification["_duration_ms"],
            detail={"detected_master_type": classification["master_type"], "confidence": classification["confidence"]},
        )

        # Bulk insert via execute_values (one round-trip for the whole file) instead of
        # one INSERT per row - the previous per-row loop took minutes on files with
        # tens of thousands of rows purely from round-trip overhead, not actual data
        # volume. Same NaN->None normalization as before (NaN isn't valid JSON).
        row_values = [
            (master_file_id, row_idx, json.dumps({k: (None if v != v else v) for k, v in row.items()}, default=str))
            for row_idx, row in enumerate(df.to_dict(orient="records"))
        ]
        if row_values:
            execute_values(
                cur,
                "INSERT INTO master_rows (master_file_id, row_index, row_data) VALUES %s",
                row_values,
                page_size=1000,
            )

        fields = []
        if is_confident:
            fields = _store_rows_and_metadata(cur, master_file_id, file.filename, schema_summary, classification["master_type"])

        # Read back within the SAME transaction/connection, right before commit - avoids
        # a second connection just to see a row this transaction itself just inserted.
        master_file_row = _fetch_master_file(cur, master_file_id)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except RuntimeError as e:
        # From chat_complete() - every configured AI provider failed (rate limit, no
        # credits, etc). Surfaced as a proper 502 with a JSON body, not a bare 500 -
        # this failure mode is expected to happen occasionally (shared free-tier
        # quotas), not a bug, so the caller needs an actionable message, not a stack trace.
        conn.rollback()
        raise HTTPException(status_code=502, detail=f"AI metadata generation failed: {e}")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return UploadResultOut(
        master_file=_row_to_master_file_out(master_file_row),
        needs_confirmation=not is_confident,
        reasoning=classification["reasoning"],
        candidates=[MasterTypeCandidateOut(**c) for c in classification["candidates"]],
        possible_master_types=list(MASTER_TYPES),
        fields=[
            FieldMetadataOut(
                column_name=f["column_name"], ai_description=f["description"],
                business_category=f.get("business_category"), data_type=f["data_type"],
                estimated_length=f["estimated_length"], is_mandatory=f["is_mandatory"],
                is_primary_key=f["is_primary_key"], is_business_identifier=f["is_business_identifier"],
                confidence_score=f["confidence"], ai_remarks=f["remarks"],
            )
            for f in fields
        ],
    )


@router.post("/{master_file_id}/confirm", response_model=MasterFileDetailOut)
def confirm_master_type(master_file_id: int, body: ConfirmMasterTypeIn):
    if body.confirmed_master_type not in MASTER_TYPES:
        raise HTTPException(status_code=400, detail=f"confirmed_master_type must be one of {MASTER_TYPES}")

    conn = get_connection()
    cur = conn.cursor()
    try:
        master_file_row = _fetch_master_file(cur, master_file_id)

        if master_file_row["side"] == "destination":
            _check_destination_conflict(cur, body.confirmed_master_type, exclude_file_id=master_file_id)

        schema_summary = master_file_row["schema_summary"]

        fields = _store_rows_and_metadata(
            cur, master_file_id, master_file_row["filename"], schema_summary, body.confirmed_master_type
        )

        cur.execute(
            """UPDATE master_files
               SET confirmed_master_type = %s, status = 'confirmed', confirmed_at = NOW()
               WHERE id = %s""",
            (body.confirmed_master_type, master_file_id),
        )
        # Read back within the SAME transaction, right before commit, so confirmed_at/
        # status reflect what was just written without a second connection.
        master_file_row = _fetch_master_file(cur, master_file_id)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except RuntimeError as e:
        conn.rollback()
        raise HTTPException(status_code=502, detail=f"AI metadata generation failed: {e}")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return MasterFileDetailOut(
        master_file=_row_to_master_file_out(master_file_row),
        fields=[
            FieldMetadataOut(
                column_name=f["column_name"], ai_description=f["description"],
                business_category=f.get("business_category"), data_type=f["data_type"],
                estimated_length=f["estimated_length"], is_mandatory=f["is_mandatory"],
                is_primary_key=f["is_primary_key"], is_business_identifier=f["is_business_identifier"],
                confidence_score=f["confidence"], ai_remarks=f["remarks"],
            )
            for f in fields
        ],
    )


@router.get("", response_model=list[MasterFileOut])
def list_master_files():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, filename, sheet_name, side, detected_master_type, detection_confidence,
                  confirmed_master_type, status, row_count, column_count,
                  business_purpose, consolidation_conflicts, uploaded_at, confirmed_at
           FROM master_files ORDER BY uploaded_at DESC"""
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return [_row_to_master_file_out(r) for r in rows]


@router.get("/{master_file_id}", response_model=MasterFileDetailOut)
def get_master_file(master_file_id: int):
    conn = get_connection()
    cur = conn.cursor()
    master_file_row = _fetch_master_file(cur, master_file_id)
    cur.execute(
        """SELECT column_name, ai_description, business_category, data_type, estimated_length, is_mandatory,
                  is_primary_key, is_business_identifier, confidence_score, ai_remarks
           FROM master_fields WHERE master_file_id = %s ORDER BY field_order""",
        (master_file_id,),
    )
    cols = [d[0] for d in cur.description]
    field_rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    conn.close()

    return MasterFileDetailOut(
        master_file=_row_to_master_file_out(master_file_row),
        fields=[FieldMetadataOut(**f) for f in field_rows],
    )


@router.delete("/{master_file_id}", status_code=204)
def delete_master_file(master_file_id: int):
    """Removes a file and everything derived from it (fields, rows, detection log -
    all ON DELETE CASCADE). This is what makes the "remove it first" wording in
    _check_destination_conflict's error actually actionable - replacing a destination
    file is a deliberate two-step (delete, then re-upload), never a silent overwrite."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        _fetch_master_file(cur, master_file_id)  # 404s if it doesn't exist
        cur.execute("DELETE FROM master_files WHERE id = %s", (master_file_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
