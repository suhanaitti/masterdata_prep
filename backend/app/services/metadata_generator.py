"""
metadata_generator.py
----------------------
Two distinct upload shapes land here, auto-detected (see detect_field_list_columns):

1. ERP FIELD LIST / data dictionary (the common real-world case: a BPCS/SAP table
   export where each ROW is one ERP field - MATNR, WERKS, LGORT - and the columns
   are attributes ABOUT that field: Field Name, Data Element, Data Type, Length,
   Decimal, Short Description). Redesigned 2026-07-29 after a real bug: this shape
   was being treated as case 2 below, generating AI metadata for the raw column
   HEADERS ("Field Name" -> "Holds the name of a field...") instead of the actual
   ERP fields living in the rows - useless output, and it fed field_mapping_engine.py
   garbage field names like "Field"/"Data Type" instead of real ones like MATNR/WERKS.
   Handled by generate_field_metadata_for_rows() - one LLM call per CHUNK of ERP
   FIELD ROWS (not columns), each with whatever real data_type/length/description
   the source file already provided (ground truth, not re-inferred).

2. Raw master DATA export (a genuine business record per row - e.g. an actual
   Customer/Vendor export where each row is one real customer and each COLUMN is a
   field like CustomerID/CustomerName). Handled by the original
   generate_field_metadata_for_file() path: one LLM call per CHUNK of COLUMNS,
   inferring data_type/length/description from column name + sample values, since
   nothing in a raw data file declares its own type/length explicitly.

Wide files in EITHER path (more columns/fields than fit in one chunk) may still need
consolidate_metadata() for case 2 (see its own docstring) - not needed for case 1,
since each ERP field is independent and never split across chunks the way a single
column's identity could be."""
import json
import re

from app.config import chat_complete_with_meta
from app.services.json_utils import parse_ai_json

# Standard ERP field-list/data-dictionary header vocabulary (SAP table exports, BPCS
# field lists, etc.) - matched by exact normalized name, no LLM call needed since
# these are a small, well-known set of header spellings, not free-form business data.
FIELD_LIST_COLUMN_ALIASES = {
    "field_name": {"field name", "field", "fieldname", "column name", "column", "field_name"},
    "data_element": {"data element", "dataelement", "data_element", "edt"},
    "data_type": {"data type", "datatype", "data_type", "type"},
    "length": {"length", "len"},
    "decimal": {"decimal", "decimals", "dec"},
    "short_description": {
        "short description", "shortdescription", "short_description", "description",
        "desc", "label/des", "label", "text",
    },
}


def _normalize_header(h) -> str:
    return re.sub(r"\s+", " ", str(h).strip().lower())


def detect_field_list_columns(columns: list) -> dict | None:
    """Maps raw column headers to canonical field-list attributes. Returns None if no
    field_name-like column is found (the one REQUIRED attribute - a field list is
    meaningless without the field's own name) - callers should fall back to the
    column-wise raw-data-export path in that case, since None means this upload's
    columns are real business fields (e.g. CustomerID), not metadata-about-fields."""
    norm_map = {_normalize_header(c): c for c in columns}
    mapping = {}
    for canonical, aliases in FIELD_LIST_COLUMN_ALIASES.items():
        for norm, raw in norm_map.items():
            if norm in aliases:
                mapping[canonical] = raw
                break
    return mapping if "field_name" in mapping else None


def _row_field_records(rows: list, colmap: dict) -> list:
    """rows: raw row dicts (from master_rows.row_data). Extracts the canonical
    field-list attributes per row, skipping rows with no field_name (a blank line,
    or a stray total/footer row some exports include)."""
    records = []
    for row in rows:
        field_name = row.get(colmap["field_name"])
        if field_name is None or str(field_name).strip() == "":
            continue
        record = {"field_name": str(field_name).strip()}
        for canonical in ("data_element", "data_type", "length", "decimal", "short_description"):
            raw_col = colmap.get(canonical)
            if raw_col is None:
                continue
            v = row.get(raw_col)
            if v is not None and str(v).strip() != "":
                record[canonical] = v
        records.append(record)
    return records


def _coerce_erp_field_item(record: dict, item: dict) -> dict:
    """Normalizes one AI-generated field-metadata item. data_type/estimated_length
    come straight from the SOURCE file's own columns (ground truth already present
    in an ERP field list) rather than being re-inferred by the AI - only
    business_description/business_category/is_primary_key/is_business_identifier/
    confidence are the AI's own judgment."""
    try:
        confidence = float(item.get("confidence"))
    except (TypeError, ValueError):
        confidence = None
    try:
        estimated_length = int(record["length"]) if record.get("length") not in (None, "") else None
    except (TypeError, ValueError):
        estimated_length = None
    return {
        "column_name": record["field_name"],
        "description": item.get("business_description"),
        "business_category": item.get("business_category"),
        "data_type": record.get("data_type"),
        "estimated_length": estimated_length,
        "is_mandatory": False,  # not derivable from a field-list template - no null-ratio signal here
        "is_primary_key": bool(item.get("is_primary_key", False)),
        "is_business_identifier": bool(item.get("is_business_identifier", False)),
        "confidence": confidence,
        "remarks": None,
    }


def generate_erp_field_metadata(field_records: list, master_type: str) -> tuple:
    """Returns (fields, agent_calls) - fields is a list of per-ERP-field metadata
    dicts (same shape as _coerce_erp_field_item), one per field_records entry, in the
    same order; agent_calls is a list of {"agent", "duration_ms"} dicts, one per
    chunk's LLM call, for events.log_event() to record. CHUNK_SIZE fields per LLM
    call, same batching principle as the column-wise path - keeps each prompt
    bounded regardless of how many ERP fields the list has."""
    context = _MASTER_TYPE_CONTEXT.get(master_type, "a master-data record.")
    chunks = _chunk_columns(field_records, CHUNK_SIZE)
    all_fields = []
    agent_calls = []

    for chunk in chunks:
        payload = json.dumps(chunk, default=str)
        prompt = f"""This file is a field list / data dictionary for {context}

Below is a JSON array of real ERP FIELDS (e.g. MATNR, WERKS, LGORT) from that field list, each with whatever raw metadata attributes the source file provided (data_element, data_type, length, decimal, short_description - some may be missing).

Fields:
{payload}

For EACH field, using its name and any provided attributes as context, determine:
- business_description: one concise sentence explaining the real-world business fact this field holds (e.g. MATNR -> "Unique identifier assigned to a material/product in SAP").
- business_category: a short label for the kind of business concept this is (e.g. "Product Master", "Plant/Location", "Quantity", "Identifier", "Status Flag").
- is_primary_key: true ONLY if this field looks like it uniquely identifies each record (its name/description suggest a key, not a description or measured quantity).
- is_business_identifier: true if this is a meaningful BUSINESS key a person would recognize (e.g. a material number, plant code) - distinct from is_primary_key (database-level uniqueness). A field can be both, one, or neither.
- confidence: 0-100, how sure you are about this field's metadata as a whole.

Respond with ONLY a JSON array, one object per field, IN THE SAME ORDER as listed above:
[{{"field_name": "...", "business_description": "...", "business_category": "...", "is_primary_key": false, "is_business_identifier": false, "confidence": 90}}]"""

        raw, agent, duration_ms = chat_complete_with_meta([{"role": "user", "content": prompt}], max_tokens=4000)
        agent_calls.append({"agent": agent, "duration_ms": duration_ms})
        parsed = parse_ai_json(raw)
        by_name = {item.get("field_name"): item for item in parsed if isinstance(item, dict)} if isinstance(parsed, list) else {}
        all_fields.extend(_coerce_erp_field_item(rec, by_name.get(rec["field_name"], {})) for rec in chunk)

    return all_fields, agent_calls


def generate_field_metadata_for_rows(master_type: str, rows: list, colmap: dict) -> dict:
    """Row-wise entry point - see module docstring, case 1. Returns the same
    {"fields", "master_type", "business_purpose", "conflicts", "primary_keys",
    "business_identifiers"} shape as generate_field_metadata_for_file() (case 2), so
    masters.py can call whichever path applies without branching on the result shape.
    business_purpose/conflicts are empty here - those are specifically about
    reconciling COLUMN interpretations split across chunks (case 2's problem); each
    ERP field row is independent and never split across chunks, so there's nothing
    to reconcile."""
    field_records = _row_field_records(rows, colmap)
    fields, agent_calls = generate_erp_field_metadata(field_records, master_type)
    return {
        "fields": fields,
        "master_type": master_type,
        "business_purpose": None,
        "conflicts": [],
        "primary_keys": [f["column_name"] for f in fields if f["is_primary_key"]],
        "business_identifiers": [f["column_name"] for f in fields if f["is_business_identifier"]],
        "_agent_calls": agent_calls,
    }


_MASTER_TYPE_CONTEXT = {
    "Customer": "a customer master record - who the business sells to.",
    "Vendor": "a vendor/supplier master record - who the business buys from.",
    "Product": "a product/material master record - what the business makes, buys, sells, or stocks.",
    "Bank": "a bank master record - bank accounts/keys used for payments.",
    "GL Mapping": "a general ledger account structure/mapping record.",
    "Transaction Type": "a transaction-type classification record.",
    "Payment Terms": "a payment-terms record - due dates, discounts, installments.",
}

# Columns per LLM call. Not tuned against a measured token count the way the sibling
# Header_Mapping project's DEFAULT_BATCH_SIZE was - this is a conservative
# starting point (each column's prompt line carries a name + up to 5 sample values +
# two numbers, comparable in size to that project's per-field prompt lines) that keeps
# a full chunk comfortably under typical provider context limits.
CHUNK_SIZE = 30


def _chunk_columns(columns: list, size: int) -> list:
    return [columns[i:i + size] for i in range(0, len(columns), size)]


def _coerce_field_item(column_name: str, item: dict) -> dict:
    """Normalizes one field-metadata item from raw LLM JSON into the canonical shape,
    the same defensive coercion applied whether the item came from a fresh per-chunk
    generation call or was re-emitted by the consolidation pass - a value that fails to
    coerce becomes None/False rather than silently propagating a wrong type."""
    try:
        confidence = float(item.get("confidence"))
    except (TypeError, ValueError):
        confidence = None
    try:
        est_length = int(item.get("estimated_length"))
    except (TypeError, ValueError):
        est_length = None
    return {
        "column_name": column_name,
        "description": item.get("description"),
        "business_category": None,  # only populated by the row-wise ERP-field-list path
        "data_type": item.get("data_type"),
        "estimated_length": est_length,
        "is_mandatory": bool(item.get("is_mandatory", False)),
        "is_primary_key": bool(item.get("is_primary_key", False)),
        "is_business_identifier": bool(item.get("is_business_identifier", False)),
        "confidence": confidence,
        "remarks": item.get("remarks"),
    }


def generate_field_metadata(master_type: str, schema_summary: dict) -> tuple:
    """Returns (fields, agent, duration_ms). fields is a list of per-column metadata
    dicts, one per column in schema_summary, in the same order:
    {"column_name", "description", "data_type", "estimated_length", "is_mandatory",
     "is_primary_key", "is_business_identifier", "confidence", "remarks"}"""
    context = _MASTER_TYPE_CONTEXT.get(master_type, "a master-data record.")
    col_lines = "\n".join(
        f"  - {c['column_name']}  (null ratio: {c['null_ratio']}, distinct values: {c['distinct_count']}, "
        f"examples: {', '.join(c['sample_values']) or '(all blank)'})"
        for c in schema_summary["columns"]
    )

    prompt = f"""This file is {context}

For EACH column below, infer its metadata from its name and real example values. "null ratio" is the fraction of blank cells in that column across the whole file - a strong signal for mandatory vs optional (a column that's never blank is a good mandatory candidate; a column that's usually blank is optional). "distinct values" close to the row count suggests a unique identifier/key.

Columns:
{col_lines}

For each column, determine:
- description: one concise sentence explaining what real-world business fact this column holds.
- data_type: your best inference of the underlying data type - one of: String, Integer, Decimal, Date, Boolean, Code.
- estimated_length: your best guess at a reasonable max character/digit length for this field, as a plain integer. Base it on the example values actually seen (e.g. the longest sample, rounded up sensibly) - null if you cannot reasonably estimate.
- is_mandatory: true if this column looks like it should always be populated (low null ratio, appears essential to the record), false otherwise.
- is_primary_key: true ONLY if this column looks like it uniquely identifies each record (e.g. distinct_count is close to row_count, name suggests an ID/code).
- is_business_identifier: true if this is a meaningful BUSINESS key a person would recognize (e.g. a customer number, vendor code, IBAN) - distinct from is_primary_key, which is about database-level uniqueness. A column can be both, one, or neither.
- confidence: 0-100, how sure you are about this column's metadata as a whole.
- remarks: one short phrase noting anything uncertain or worth a human double-checking - null if nothing stands out.

Respond with ONLY a JSON array, one object per column, IN THE SAME ORDER as listed above:
[{{"column_name": "...", "description": "...", "data_type": "String", "estimated_length": 40, "is_mandatory": true, "is_primary_key": false, "is_business_identifier": true, "confidence": 85, "remarks": null}}]"""

    raw, agent, duration_ms = chat_complete_with_meta([{"role": "user", "content": prompt}], max_tokens=4000)
    parsed = parse_ai_json(raw)
    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON array of column metadata, got {type(parsed).__name__}")

    by_name = {item.get("column_name"): item for item in parsed if isinstance(item, dict)}
    fields = [
        _coerce_field_item(col["column_name"], by_name.get(col["column_name"], {}))
        for col in schema_summary["columns"]
    ]
    return fields, agent, duration_ms


def generate_field_metadata_for_file(master_type: str, filename: str, schema_summary: dict) -> dict:
    """Full per-file pipeline: splits columns into CHUNK_SIZE-sized chunks, generates
    metadata for each chunk independently, then - only if there was more than one
    chunk - runs consolidate_metadata() to reconcile them. Returns:
    {"fields": [...], "master_type": str, "business_purpose": str|None,
     "conflicts": [...], "primary_keys": [...], "business_identifiers": [...],
     "_agent_calls": [{"agent", "duration_ms"}, ...]}"""
    chunks = _chunk_columns(schema_summary["columns"], CHUNK_SIZE)
    all_fields = []
    agent_calls = []
    for chunk_cols in chunks:
        chunk_summary = {**schema_summary, "columns": chunk_cols}
        fields, agent, duration_ms = generate_field_metadata(master_type, chunk_summary)
        all_fields.extend(fields)
        agent_calls.append({"agent": agent, "duration_ms": duration_ms})

    if len(chunks) <= 1:
        return {
            "fields": all_fields,
            "master_type": master_type,
            "business_purpose": None,
            "conflicts": [],
            "primary_keys": [f["column_name"] for f in all_fields if f["is_primary_key"]],
            "business_identifiers": [f["column_name"] for f in all_fields if f["is_business_identifier"]],
            "_agent_calls": agent_calls,
        }

    result = consolidate_metadata(master_type, filename, all_fields)
    result["_agent_calls"] = agent_calls + result["_agent_calls"]
    return result


def consolidate_metadata(master_type: str, filename: str, chunk_fields: list) -> dict:
    """AI responsibility: reconcile metadata that was generated independently per-chunk
    for a wide file. Only ever called when a file needed more than one chunk (see
    generate_field_metadata_for_file) - a single-chunk file's metadata is already
    internally consistent by construction, nothing to reconcile.

    Follows the project's consolidation prompt: determine the overall master type,
    verify consistency, detect duplicate/conflicting field interpretations, identify
    primary keys/business identifiers across the whole file, summarize the business
    purpose, and return one finalized metadata document - without re-analyzing fields
    that have no conflict."""
    payload = json.dumps(chunk_fields, default=str)

    prompt = f"""You are an ERP Master Data expert.

The following JSON contains the metadata generated from multiple field chunks of the same master file ("{filename}", already classified as {master_type}):

{payload}

Your task is to:
1. Determine the overall master type (Customer, Vendor, Bank, Material, GL, Payment Terms, etc.).
2. Verify consistency across all fields.
3. Detect duplicate or conflicting field interpretations.
4. Identify primary keys and business identifiers.
5. Summarize the business purpose of the master.
6. Return a finalized metadata document.

Do not re-analyze individual fields unless there is a conflict.
Return only valid JSON, in this exact shape:
{{"master_type": "...", "business_purpose": "one or two sentence summary of what this master represents and is used for", "conflicts": [{{"column_name": "...", "issue": "one short phrase describing the inconsistency", "resolution": "one short phrase describing how it was resolved"}}], "primary_keys": ["column_name", ...], "business_identifiers": ["column_name", ...], "fields": [ /* the FULL reconciled field list, one entry per column, SAME shape as the input objects - unchanged fields copied through as-is, only conflicting ones corrected */ ]}}"""

    raw, agent, duration_ms = chat_complete_with_meta([{"role": "user", "content": prompt}], max_tokens=4000)
    parsed = parse_ai_json(raw)

    raw_fields = parsed.get("fields")
    if isinstance(raw_fields, list) and raw_fields:
        by_name = {item.get("column_name"): item for item in raw_fields if isinstance(item, dict)}
        # Reconciled against the ORIGINAL column list (not just whatever the model
        # echoed back) so a column the model accidentally dropped from its response
        # still survives in the finalized document, using its pre-consolidation values.
        original_by_name = {f["column_name"]: f for f in chunk_fields}
        fields = [
            _coerce_field_item(name, by_name.get(name, original_by_name[name]))
            for name in original_by_name
        ]
    else:
        # LLM didn't return a usable reconciled list - fall back to the un-reconciled
        # per-chunk fields rather than silently losing all metadata.
        fields = chunk_fields

    return {
        "fields": fields,
        "master_type": parsed.get("master_type") or master_type,
        "business_purpose": parsed.get("business_purpose"),
        "conflicts": parsed.get("conflicts") if isinstance(parsed.get("conflicts"), list) else [],
        "primary_keys": parsed.get("primary_keys") if isinstance(parsed.get("primary_keys"), list) else [],
        "business_identifiers": (
            parsed.get("business_identifiers") if isinstance(parsed.get("business_identifiers"), list) else []
        ),
        "_agent_calls": [{"agent": agent, "duration_ms": duration_ms}],
    }
