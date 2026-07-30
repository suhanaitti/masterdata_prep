"""
master_classifier.py
---------------------
AI responsibility #1: identify WHICH master type an uploaded file belongs to, using
filename, sheet name, column names, and sample data (never the whole file - see
excel_reader.build_schema_summary). Returns a confidence score and the AI's own
reasoning, so the caller can decide whether to auto-proceed or ask the user to
confirm (requirement 3).
"""
from app.config import chat_complete_with_meta
from app.services.json_utils import parse_ai_json

MASTER_TYPES = ("Customer", "Vendor", "Product", "Bank", "GL Mapping", "Transaction Type", "Payment Terms")

# Below this confidence, the caller should ask the user to confirm rather than
# auto-proceed - requirement 3 ("If the AI cannot confidently identify the master, it
# should ask the user for confirmation"). Kept here (not buried in the router) so the
# threshold is defined once, next to the classifier that produces the score it's
# compared against.
CONFIDENT_THRESHOLD = 75.0

_MASTER_TYPE_HINTS = {
    "Customer": "who a company sells TO - billing/shipping details, credit terms, sales org assignment.",
    "Vendor": "who a company buys FROM (a supplier) - payment details, purchasing org assignment, bank info for paying them.",
    "Product": "material/product master data - SKU, material group, unit of measure, plant/valuation data, product hierarchy.",
    "Bank": "bank account / bank key master data - IBAN, SWIFT/BIC, branch, routing details.",
    "GL Mapping": "general ledger account structure/mapping - chart of accounts, account groups, cost elements.",
    "Transaction Type": "codes classifying the KIND of a business transaction (e.g. invoice, credit memo, payment, journal entry type).",
    "Payment Terms": "rules for WHEN and how a payment is due - net days, discount %, discount days, installment schedules.",
}


def classify_master_type(filename: str, sheet_name: str, schema_summary: dict) -> dict:
    """Returns {"master_type": one of MASTER_TYPES or None, "confidence": 0-100,
    "reasoning": "...", "signals_used": [...], "candidates": [...]}. master_type is None
    only if the model's response didn't name one of the fixed six types at all (treated
    as zero-confidence, not silently defaulted to a guess).

    candidates is the model's FULL ranked guess list (not just the top pick), e.g.
    [{"master_type": "Customer", "confidence": 58}, {"master_type": "Vendor",
    "confidence": 42}] - this is what lets the caller show "Possible Master: Customer
    (58%), Vendor (42%) - confidence too low, please confirm" instead of a single
    number with no context, when names/values are genuinely ambiguous between two
    types (e.g. a file with generic ID/name/address columns could plausibly be either
    Customer or Vendor master data)."""
    hints = "\n".join(f"- {t}: {desc}" for t, desc in _MASTER_TYPE_HINTS.items())
    col_lines = "\n".join(
        f"  - {c['column_name']}  (examples: {', '.join(c['sample_values']) or '(all blank)'})"
        for c in schema_summary["columns"]
    )

    prompt = f"""You are classifying an uploaded ERP master-data file into ONE of these six fixed master-data types:

{hints}

File metadata:
- Filename: {filename}
- Sheet name: {sheet_name or "(n/a - not an Excel workbook)"}
- Row count: {schema_summary['row_count']}
- Column count: {schema_summary['column_count']}

Columns (name + a few real example values from the file):
{col_lines}

Decide which of the six types above this file most likely represents, based on the actual column names and example values - not just the filename (a filename can be misleading or generic; the columns and data are the real evidence).

If BOTH the column names AND the example values are genuinely ambiguous between two (or more) types - e.g. generic ID/name/address columns that could equally be a Customer or a Vendor - do NOT force a single confident guess. Instead split your confidence across the plausible candidates so it reflects the real ambiguity (e.g. Customer 58, Vendor 42) rather than picking one arbitrarily and calling it 85% sure.

Respond with ONLY a JSON object, no other text:
{{"candidates": [{{"master_type": "<one of the six>", "confidence": 0-100}}, ...up to 3, sorted highest confidence first, confidences need not sum to 100], "reasoning": "one or two sentences citing the SPECIFIC columns/values that drove this decision, and naming the runner-up if confidence is split", "signals_used": ["filename", "column_names", "sample_data"]}}

Always include at least one candidate. Only include a second/third candidate when there is genuine, real ambiguity - do not pad the list with implausible types just to fill it."""

    raw, agent, duration_ms = chat_complete_with_meta([{"role": "user", "content": prompt}])
    parsed = parse_ai_json(raw)

    raw_candidates = parsed.get("candidates") or []
    candidates = []
    for c in raw_candidates:
        if not isinstance(c, dict) or c.get("master_type") not in MASTER_TYPES:
            continue
        try:
            conf = float(c.get("confidence"))
        except (TypeError, ValueError):
            continue
        candidates.append({"master_type": c["master_type"], "confidence": conf})
    candidates.sort(key=lambda c: c["confidence"], reverse=True)

    top = candidates[0] if candidates else None

    return {
        "master_type": top["master_type"] if top else None,
        "confidence": top["confidence"] if top else 0.0,
        "reasoning": parsed.get("reasoning"),
        "signals_used": parsed.get("signals_used") or ["filename", "column_names", "sample_data"],
        "candidates": candidates,
        # Agent-activity metadata for events.log_event() - underscore-prefixed so
        # callers know these are internal bookkeeping, not part of the public
        # classification result the frontend consumes.
        "_agent": agent,
        "_duration_ms": duration_ms,
    }
