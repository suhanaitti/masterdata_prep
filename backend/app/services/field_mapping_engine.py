"""
field_mapping_engine.py
------------------------
Field-to-field mapping between one CONFIRMED source master_file and one CONFIRMED
destination master_file of the SAME master type - the AI-driven counterpart to
Header_Mapping's mapping_engine.py, operating on master_fields (already
AI-described: column_name, ai_description, data_type, length, PK/business-ID flags)
rather than raw schema_fields.

Simpler than the sibling engine in one respect: both sides' data_type values come
from the SAME AI vocabulary (String/Integer/Decimal/Date/Boolean/Code, see
metadata_generator.py's prompt) - there's no D365-vs-SAP type-family translation
needed, a case-insensitive equality check is enough.

Full retrieval pipeline (2026-07-29): exact field-name match (fastest, skips the LLM
entirely) -> BM25 keyword search + embedding cosine similarity, combined via
Reciprocal Rank Fusion (see retrieval.py / embeddings.py) -> data-type/length
compatibility re-ranks the fused pool (SOFT boost, not a hard exclude - a
legitimately transformed field, e.g. a Decimal becoming a String, must still reach
the LLM as a candidate) -> LLM makes the final judgment call and explains it.
"""
import json

from app.config import chat_complete_with_meta
from app.services.embeddings import top_n_by_cosine
from app.services.events import log_event
from app.services.json_utils import parse_ai_json
from app.services.retrieval import BM25Index, reciprocal_rank_fusion

TOP_K_CANDIDATES = 8
# Wider pool fed into the type/length re-rank step before it's trimmed down to
# TOP_K_CANDIDATES for the LLM prompt - gives the compatibility boost real
# candidates to choose among instead of just re-ordering an already-tiny list.
FUSION_POOL_SIZE = 20
BATCH_SIZE = 8
MIN_CONFIDENCE_TO_STORE = 30.0  # below this, treat as "no match" and don't store at all
# Two lengths are treated as "compatible" if neither is more than this factor larger
# than the other - loose enough that a plausible varchar-padding difference (e.g. 40
# vs 50) doesn't get penalized, tight enough that a 3-char code vs a 200-char free-text
# field still reads as a real mismatch.
LENGTH_COMPATIBLE_RATIO = 1.5


def _field_text(f: dict) -> str:
    parts = [f["column_name"]]
    if f.get("ai_description"):
        parts.append(f["ai_description"])
    return " - ".join(parts)


def _fetch_fields(cur, master_file_id: int) -> list:
    cur.execute(
        """SELECT id, column_name, ai_description, data_type, estimated_length,
                  is_mandatory, is_primary_key, is_business_identifier, embedding
           FROM master_fields WHERE master_file_id = %s ORDER BY field_order""",
        (master_file_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _normalized_name(f: dict) -> str:
    return (f.get("column_name") or "").strip().upper()


def _types_compatible(src: dict, dst: dict) -> bool:
    src_type, dst_type = (src.get("data_type") or "").strip().lower(), (dst.get("data_type") or "").strip().lower()
    return bool(src_type) and src_type == dst_type


def _lengths_compatible(src: dict, dst: dict) -> bool:
    src_len, dst_len = src.get("estimated_length"), dst.get("estimated_length")
    if not src_len or not dst_len:
        return True  # missing on either side - not usable as evidence either way, don't penalize
    lo, hi = min(src_len, dst_len), max(src_len, dst_len)
    return hi <= lo * LENGTH_COMPATIBLE_RATIO


def _fused_candidates(source: dict, destinations: list, bm25: BM25Index, dest_vectors: dict, by_id: dict) -> list:
    """One source field's ranked destination candidate list: BM25 keyword ranking and
    embedding cosine-similarity ranking are computed independently, then combined via
    Reciprocal Rank Fusion so neither signal alone decides (BM25 catches literal/ERP-
    synonym term overlap; embeddings catch same-meaning-different-words cases BM25
    misses). The fused pool is then SOFT re-ranked by data-type/length compatibility -
    compatible candidates are promoted to the front, but incompatible ones are kept
    (never dropped) since a genuine mapping can still require a type/length transform."""
    bm25_ranked = bm25.top_n(_field_text(source), FUSION_POOL_SIZE)

    src_vector = source.get("embedding")
    if src_vector:
        dest_ids_with_vectors = [d["id"] for d in destinations if dest_vectors.get(d["id"])]
        embed_ranked = top_n_by_cosine(
            src_vector, dest_ids_with_vectors,
            [dest_vectors[i] for i in dest_ids_with_vectors], FUSION_POOL_SIZE,
        )
    else:
        embed_ranked = []

    fused_ids = reciprocal_rank_fusion([bm25_ranked, embed_ranked])[:FUSION_POOL_SIZE]
    fused = [by_id[i] for i in fused_ids if i in by_id]

    compatible = [d for d in fused if _types_compatible(source, d) or _lengths_compatible(source, d)]
    other = [d for d in fused if d not in compatible]
    return (compatible + other)[:TOP_K_CANDIDATES]


def _exact_name_matches(sources: list, destinations: list, rejected_pairs: set) -> list:
    """Fast path: a source and destination field with the IDENTICAL normalized name
    (case/whitespace-insensitive) are matched directly - no BM25/embedding retrieval,
    no LLM call. Greedy one-to-one (a destination name is claimed by at most one
    source), skips any pair already in the permanent rejection log. Returns a list of
    (source, destination) tuples; callers must exclude these from further processing."""
    dest_by_name = {}
    for d in destinations:
        dest_by_name.setdefault(_normalized_name(d), d)

    matches = []
    claimed_dst_ids = set()
    for s in sources:
        dst = dest_by_name.get(_normalized_name(s))
        if not dst or dst["id"] in claimed_dst_ids:
            continue
        if (s["id"], dst["id"]) in rejected_pairs:
            continue
        matches.append((s, dst))
        claimed_dst_ids.add(dst["id"])
    return matches


def _existing_mappings(cur, source_ids: list, destination_ids: list) -> list:
    cur.execute(
        """SELECT fm.id, fm.source_field_id, fm.destination_field_id, fm.mapping_type,
                  fm.status, fm.confidence_score, fm.match_basis, fm.remarks,
                  sf.column_name AS source_name, sf.ai_description AS source_description,
                  sf.data_type AS source_type, sf.estimated_length AS source_length,
                  sf.is_primary_key AS source_pk, sf.is_business_identifier AS source_biz_id,
                  df.column_name AS destination_name, df.ai_description AS destination_description,
                  df.data_type AS destination_type, df.estimated_length AS destination_length,
                  df.is_primary_key AS destination_pk, df.is_business_identifier AS destination_biz_id
           FROM master_field_mappings fm
           JOIN master_fields sf ON sf.id = fm.source_field_id
           JOIN master_fields df ON df.id = fm.destination_field_id
           WHERE fm.source_field_id = ANY(%s) OR fm.destination_field_id = ANY(%s)""",
        (source_ids, destination_ids),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _pair_view(row: dict) -> dict:
    return {
        "mapping_id": row["id"],
        "mapping_type": row["mapping_type"],
        "status": row["status"],
        "confidence": float(row["confidence_score"]) if row["confidence_score"] is not None else None,
        "match_basis": row.get("match_basis"),
        "remarks": row.get("remarks"),
        "source": {
            "id": row["source_field_id"], "column_name": row["source_name"],
            "description": row["source_description"], "data_type": row["source_type"],
            "length": row["source_length"], "is_primary_key": row["source_pk"],
            "is_business_identifier": row["source_biz_id"],
        },
        "destination": {
            "id": row["destination_field_id"], "column_name": row["destination_name"],
            "description": row["destination_description"], "data_type": row["destination_type"],
            "length": row["destination_length"], "is_primary_key": row["destination_pk"],
            "is_business_identifier": row["destination_biz_id"],
        },
    }


def get_mapping_view(cur, source_file_id: int, destination_file_id: int) -> dict:
    """Read-only view - no LLM calls. Returns matches (approved), ai_suggestions
    (pending review), unmapped_source, unmapped_destination."""
    sources = _fetch_fields(cur, source_file_id)
    destinations = _fetch_fields(cur, destination_file_id)
    rows = _existing_mappings(cur, [s["id"] for s in sources], [d["id"] for d in destinations])

    matched_src, matched_dst = set(), set()
    matches, ai_suggestions = [], []
    for row in rows:
        pair = _pair_view(row)
        matched_src.add(row["source_field_id"])
        matched_dst.add(row["destination_field_id"])
        (matches if row["status"] == "approved" else ai_suggestions).append(pair)

    return {
        "matches": matches,
        "ai_suggestions": ai_suggestions,
        "unmapped_source": [s for s in sources if s["id"] not in matched_src],
        "unmapped_destination": [d for d in destinations if d["id"] not in matched_dst],
    }


def _build_prompt(source_batch: list, candidates_by_source: dict, batch_num: int, total_batches: int) -> str:
    sections = []
    for s in source_batch:
        cands = candidates_by_source.get(s["id"], [])
        if cands:
            cand_lines = "\n".join(
                f"    - {c['column_name']}: {c.get('ai_description') or '(no description)'} "
                f"[type: {c.get('data_type') or 'unknown'}, "
                f"{'PK, ' if c.get('is_primary_key') else ''}{'business ID' if c.get('is_business_identifier') else ''}]"
                for c in cands
            )
        else:
            cand_lines = "    (no candidates)"
        sections.append(
            f"SOURCE FIELD: {s['column_name']}: {s.get('ai_description') or '(no description)'} "
            f"[type: {s.get('data_type') or 'unknown'}, "
            f"{'PK, ' if s.get('is_primary_key') else ''}{'business ID' if s.get('is_business_identifier') else ''}]\n"
            f"  Candidate destination fields (pick at most ONE, or none):\n{cand_lines}"
        )
    body = "\n\n".join(sections)

    return f"""You are an ERP master-data migration expert matching fields between a SOURCE system's master data file and a DESTINATION (SAP) system's master data file of the same master type. (Batch {batch_num}/{total_batches})

Field names will often differ completely between the two systems - judge each match on MEANING (the description), not spelling. A field marked "business ID" is a meaningful business key (e.g. a customer number, IBAN) a person would recognize; "PK" means it uniquely identifies each record technically. Two fields both being IDs does NOT mean they identify the same thing - a source's own internal record ID has no reason to correspond to the destination's business key.

{body}

Rules:
- Only pick a destination that appears in that source field's own candidate list.
- Each destination field must be used at most once across your entire response.
- A wrong match is worse than no match - if the descriptions clearly describe different real-world things, omit the source field entirely (contribute no array entry for it). Omission is the correct, expected outcome whenever nothing is truly equivalent.
- Be strict: shared topic vocabulary (e.g. both mention "date" or "code") is not enough - they must describe the SAME specific business fact.

Respond with ONLY a JSON array, no other text:
[{{"source_field": "...", "destination_field": "...", "confidence": 0-100, "match_basis": "Description", "remarks": "one short honest phrase"}}]
Or [] if nothing in this batch has a genuine match."""


def run_mapping(source_file_id: int, destination_file_id: int, cur, should_stop=None, progress_callback=None) -> dict:
    """Runs one pass over every currently-unmapped source field:

    1. Exact field-name match (fastest) - identical normalized names are paired
       directly, no retrieval or LLM call spent on them.
    2. Everything left is batched; each source field's candidates come from BM25 +
       embedding cosine similarity fused via RRF, then soft-reranked by data-type/
       length compatibility (see _fused_candidates).
    3. The LLM judges each batch's candidates and explains its pick.

    Does not commit - caller's responsibility. should_stop, if given, is called
    between batches - if it returns True, dispatch stops immediately (matching
    Header_Mapping's Stop-button pattern). Batches already completed keep their
    suggestions (nothing is rolled back just because the run was stopped early) -
    the caller commits whatever's accumulated in `cur` up to that point.
    progress_callback(batch_num, total_batches), if given, is called after each
    batch completes (the exact-name pass, being instant, doesn't report progress)."""
    view = get_mapping_view(cur, source_file_id, destination_file_id)
    candidate_sources = view["unmapped_source"]
    candidate_destinations = view["unmapped_destination"]

    if not candidate_sources or not candidate_destinations:
        return {"new_suggestions": 0, "failed_batches": [], "total_batches": 0, "stopped_early": False}

    cur.execute("SELECT source_field_id, destination_field_id FROM master_field_rejection_log")
    rejected_pairs = set(cur.fetchall())

    new_count = 0
    seen_dst_overall = set()

    exact_matches = _exact_name_matches(candidate_sources, candidate_destinations, rejected_pairs)
    if exact_matches:
        matched_src_ids = {s["id"] for s, _ in exact_matches}
        matched_dst_ids = {d["id"] for _, d in exact_matches}
        for s, d in exact_matches:
            cur.execute(
                """INSERT INTO master_field_mappings
                       (source_field_id, destination_field_id, mapping_type, status,
                        confidence_score, match_basis, remarks)
                   VALUES (%s, %s, 'ai_suggested', 'suggested', 100, 'Exact Name', %s)""",
                (s["id"], d["id"], "Field names match exactly - no AI call needed."),
            )
            new_count += 1
            seen_dst_overall.add(d["id"])
        candidate_sources = [s for s in candidate_sources if s["id"] not in matched_src_ids]
        candidate_destinations = [d for d in candidate_destinations if d["id"] not in matched_dst_ids]
        log_event(
            cur, "exact_name_match", source_file_id=source_file_id, destination_file_id=destination_file_id,
            agent="rule-based (no LLM call)", duration_ms=0,
            detail={"matches_found": len(exact_matches)},
        )

    if not candidate_sources or not candidate_destinations:
        return {"new_suggestions": new_count, "failed_batches": [], "total_batches": 0, "stopped_early": False}

    dst_by_name = {d["column_name"]: d for d in candidate_destinations}
    bm25 = BM25Index(
        [d["id"] for d in candidate_destinations],
        [_field_text(d) for d in candidate_destinations],
    )
    dest_vectors = {d["id"]: d["embedding"] for d in candidate_destinations if d.get("embedding")}
    by_id = {d["id"]: d for d in candidate_destinations}

    batches = [candidate_sources[i:i + BATCH_SIZE] for i in range(0, len(candidate_sources), BATCH_SIZE)]
    total_batches = len(batches)
    failed_batches = []
    stopped_early = False

    for batch_num, source_batch in enumerate(batches, start=1):
        if should_stop is not None and should_stop():
            stopped_early = True
            break
        candidates_by_source = {}
        for s in source_batch:
            fused = _fused_candidates(s, candidate_destinations, bm25, dest_vectors, by_id)
            cands = [c for c in fused if (s["id"], c["id"]) not in rejected_pairs]
            candidates_by_source[s["id"]] = cands

        prompt = _build_prompt(source_batch, candidates_by_source, batch_num, total_batches)
        try:
            raw, agent, duration_ms = chat_complete_with_meta([{"role": "user", "content": prompt}], max_tokens=2000)
            suggested = parse_ai_json(raw)
            if not isinstance(suggested, list):
                raise ValueError(f"Expected a JSON array, got {type(suggested).__name__}")
        except Exception as e:
            print(f"    [field_mapping] batch {batch_num}/{total_batches} failed ({e}) - skipping")
            failed_batches.append(batch_num)
            log_event(
                cur, "field_mapping_batch", source_file_id=source_file_id, destination_file_id=destination_file_id,
                status="failed", detail={"batch_num": batch_num, "total_batches": total_batches, "error": str(e)},
            )
            continue

        log_event(
            cur, "field_mapping_batch", source_file_id=source_file_id, destination_file_id=destination_file_id,
            agent=agent, duration_ms=duration_ms,
            detail={"batch_num": batch_num, "total_batches": total_batches, "batch_size": len(source_batch)},
        )

        src_by_name = {s["column_name"]: s for s in source_batch}
        for item in suggested:
            if not isinstance(item, dict):
                continue
            src = src_by_name.get(item.get("source_field"))
            dst = dst_by_name.get(item.get("destination_field"))
            if not src or not dst or dst["id"] in seen_dst_overall:
                continue
            if (src["id"], dst["id"]) in rejected_pairs:
                continue
            try:
                confidence = float(item.get("confidence"))
            except (TypeError, ValueError):
                continue
            if confidence < MIN_CONFIDENCE_TO_STORE:
                continue

            type_match = (
                (src.get("data_type") or "").strip().lower() == (dst.get("data_type") or "").strip().lower()
                and src.get("data_type")
            )
            if not type_match:
                confidence = round(confidence * 0.95, 1)

            seen_dst_overall.add(dst["id"])
            cur.execute(
                """INSERT INTO master_field_mappings
                       (source_field_id, destination_field_id, mapping_type, status,
                        confidence_score, match_basis, remarks)
                   VALUES (%s, %s, 'ai_suggested', 'suggested', %s, %s, %s)""",
                (src["id"], dst["id"], confidence, item.get("match_basis"), item.get("remarks")),
            )
            new_count += 1

        if progress_callback:
            progress_callback(batch_num, total_batches)

    return {
        "new_suggestions": new_count, "failed_batches": failed_batches, "total_batches": total_batches,
        "stopped_early": stopped_early,
    }


def _file_ids_for_fields(cur, source_field_id: int, destination_field_id: int) -> tuple:
    """Human-decision events (accept/reject/manual) only ever have FIELD ids handy,
    but events.log_event() is keyed on FILE ids (matching every other event type) -
    one lookup to bridge the two."""
    cur.execute(
        "SELECT master_file_id FROM master_fields WHERE id = %s", (source_field_id,),
    )
    src_row = cur.fetchone()
    cur.execute(
        "SELECT master_file_id FROM master_fields WHERE id = %s", (destination_field_id,),
    )
    dst_row = cur.fetchone()
    return (src_row[0] if src_row else None, dst_row[0] if dst_row else None)


def accept_mapping(cur, mapping_id: int) -> None:
    cur.execute(
        "SELECT source_field_id, destination_field_id FROM master_field_mappings WHERE id = %s",
        (mapping_id,),
    )
    row = cur.fetchone()
    cur.execute(
        "UPDATE master_field_mappings SET status = 'approved', updated_at = NOW() WHERE id = %s",
        (mapping_id,),
    )
    if row:
        src_file_id, dst_file_id = _file_ids_for_fields(cur, row[0], row[1])
        log_event(
            cur, "accept", source_file_id=src_file_id, destination_file_id=dst_file_id,
            agent="human", detail={"mapping_id": mapping_id},
        )


def reject_mapping(cur, mapping_id: int) -> None:
    cur.execute(
        "SELECT source_field_id, destination_field_id, confidence_score FROM master_field_mappings WHERE id = %s",
        (mapping_id,),
    )
    row = cur.fetchone()
    if row is None:
        return
    cur.execute(
        "INSERT INTO master_field_rejection_log (source_field_id, destination_field_id, confidence_score) VALUES (%s, %s, %s)",
        row,
    )
    cur.execute("DELETE FROM master_field_mappings WHERE id = %s", (mapping_id,))
    src_file_id, dst_file_id = _file_ids_for_fields(cur, row[0], row[1])
    log_event(
        cur, "reject", source_file_id=src_file_id, destination_file_id=dst_file_id,
        agent="human", detail={"mapping_id": mapping_id},
    )


def manual_map(cur, source_field_id: int, destination_field_id: int) -> None:
    cur.execute(
        "DELETE FROM master_field_mappings WHERE source_field_id = %s OR destination_field_id = %s",
        (source_field_id, destination_field_id),
    )
    cur.execute(
        """INSERT INTO master_field_mappings
               (source_field_id, destination_field_id, mapping_type, status, confidence_score)
           VALUES (%s, %s, 'manual', 'approved', 100)""",
        (source_field_id, destination_field_id),
    )
    src_file_id, dst_file_id = _file_ids_for_fields(cur, source_field_id, destination_field_id)
    log_event(
        cur, "manual_map", source_file_id=src_file_id, destination_file_id=dst_file_id,
        agent="human", detail={"source_field_id": source_field_id, "destination_field_id": destination_field_id},
    )


def get_rejection_log(cur, source_file_id: int, destination_file_id: int) -> list:
    """Every rejection ever logged for fields belonging to this specific source/
    destination file pair, most recent first - mirrors BPCS's get_rejection_log."""
    cur.execute(
        """SELECT rl.id, rl.confidence_score, rl.rejected_at,
                  sf.id AS source_id, sf.column_name AS source_name, sf.ai_description AS source_description,
                  df.id AS destination_id, df.column_name AS destination_name, df.ai_description AS destination_description
           FROM master_field_rejection_log rl
           JOIN master_fields sf ON sf.id = rl.source_field_id
           JOIN master_fields df ON df.id = rl.destination_field_id
           WHERE sf.master_file_id = %s AND df.master_file_id = %s
           ORDER BY rl.rejected_at DESC""",
        (source_file_id, destination_file_id),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def restore_rejection(cur, rejection_id: int) -> None:
    """Un-rejects a pair: removes it from the rejection log (so it can be re-proposed
    or manually mapped again) and immediately confirms it as an approved mapping -
    the same one-click intent as BPCS's "Restore" button."""
    cur.execute(
        "SELECT source_field_id, destination_field_id FROM master_field_rejection_log WHERE id = %s",
        (rejection_id,),
    )
    row = cur.fetchone()
    if row is None:
        return
    source_field_id, destination_field_id = row
    cur.execute("DELETE FROM master_field_rejection_log WHERE id = %s", (rejection_id,))
    manual_map(cur, source_field_id, destination_field_id)
