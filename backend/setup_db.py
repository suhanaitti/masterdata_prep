"""
setup_db.py
-----------
One-time database setup. Creates all tables if they don't exist. Safe to run
multiple times - never drops existing data.

Run create_database.py first if the target database doesn't exist yet.

Usage:
  python setup_db.py
"""
from app.config import get_connection

MASTER_TYPES = ("Customer", "Vendor", "Product", "Bank", "GL Mapping", "Transaction Type", "Payment Terms")


def setup():
    conn = get_connection()
    cur = conn.cursor()

    print("\n" + "=" * 55)
    print("  ERP MASTER DATA PREP - DATABASE SETUP")
    print("=" * 55)

    master_types_sql = ", ".join(f"'{t}'" for t in MASTER_TYPES)

    tables = {
        # One row per uploaded Excel file (or sheet, if a workbook has several sheets
        # worth processing independently). detected_master_type/detection_confidence are
        # the AI's own classification; confirmed_master_type is filled in once a human
        # confirms/corrects it, or automatically when confidence already clears
        # CONFIDENT_THRESHOLD (requirement 3: "ask the user for confirmation" only when
        # the AI isn't sure). schema_summary caches excel_reader.build_schema_summary()'s
        # output so a later metadata-generation call (after manual confirmation) doesn't
        # need to re-read every row back out of master_rows.
        # `side` mirrors Header_Mapping's schema_fields.side - master data
        # needs prepping on BOTH the source system and the destination system before
        # the schema-mapping engine can compare them, so every upload is tagged which
        # side it's from (the user knows this at upload time; the AI only figures out
        # the master TYPE, which is an orthogonal question).
        "master_files": f"""
            CREATE TABLE IF NOT EXISTS master_files (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(500) NOT NULL,
                sheet_name VARCHAR(255),
                side VARCHAR(20) NOT NULL DEFAULT 'source' CHECK (side IN ('source', 'destination')),
                detected_master_type VARCHAR(50) CHECK (detected_master_type IN ({master_types_sql})),
                detection_confidence NUMERIC(5,2),
                confirmed_master_type VARCHAR(50) CHECK (confirmed_master_type IN ({master_types_sql})),
                status VARCHAR(30) NOT NULL DEFAULT 'pending_confirmation'
                    CHECK (status IN ('pending_confirmation', 'confirmed', 'rejected')),
                row_count INTEGER,
                column_count INTEGER,
                schema_summary JSONB,
                uploaded_at TIMESTAMP DEFAULT NOW(),
                confirmed_at TIMESTAMP
            )
        """,
        # Audit trail of the AI's OWN classification reasoning - separate from
        # master_files so re-running detection (e.g. after a user correction) keeps
        # history instead of overwriting it. Satisfies "explain every decision it
        # makes" for the master-type identification step specifically. `candidates`
        # holds the FULL ranked list (not just the top pick) - e.g.
        # [{"master_type": "Customer", "confidence": 58}, {"master_type": "Vendor",
        # "confidence": 42}] - so an ambiguous case can show the user what else the AI
        # considered, not just a single low number.
        "master_type_detection_log": """
            CREATE TABLE IF NOT EXISTS master_type_detection_log (
                id SERIAL PRIMARY KEY,
                master_file_id INTEGER REFERENCES master_files(id) ON DELETE CASCADE,
                detected_type VARCHAR(50),
                confidence NUMERIC(5,2),
                reasoning TEXT,
                signals_used JSONB,
                candidates JSONB,
                detected_at TIMESTAMP DEFAULT NOW()
            )
        """,
        # AI-generated metadata per COLUMN of an uploaded file - the structured
        # metadata representation requirement 5 asks for. One row per raw column.
        "master_fields": """
            CREATE TABLE IF NOT EXISTS master_fields (
                id SERIAL PRIMARY KEY,
                master_file_id INTEGER REFERENCES master_files(id) ON DELETE CASCADE,
                field_order INTEGER,
                column_name VARCHAR(255) NOT NULL,
                ai_description TEXT,
                data_type VARCHAR(50),
                estimated_length INTEGER,
                is_mandatory BOOLEAN DEFAULT FALSE,
                is_primary_key BOOLEAN DEFAULT FALSE,
                is_business_identifier BOOLEAN DEFAULT FALSE,
                confidence_score NUMERIC(5,2),
                ai_remarks TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (master_file_id, column_name)
            )
        """,
        # Raw row data, stored generically as JSONB rather than one physical table
        # per master type - keeps the six master types (and any future ones) on the
        # same storage shape, since their real columns vary file to file/customer to
        # customer and are only known once a file is uploaded.
        "master_rows": """
            CREATE TABLE IF NOT EXISTS master_rows (
                id SERIAL PRIMARY KEY,
                master_file_id INTEGER REFERENCES master_files(id) ON DELETE CASCADE,
                row_index INTEGER NOT NULL,
                row_data JSONB NOT NULL,
                UNIQUE (master_file_id, row_index)
            )
        """,
        # Field-to-field mapping between one CONFIRMED source master_file and one
        # CONFIRMED destination master_file (same master type) - the AI-driven
        # counterpart to Header_Mapping's field_mappings table, operating on
        # master_fields (already AI-described) instead of raw schema_fields.
        "master_field_mappings": """
            CREATE TABLE IF NOT EXISTS master_field_mappings (
                id SERIAL PRIMARY KEY,
                source_field_id INTEGER REFERENCES master_fields(id) ON DELETE CASCADE,
                destination_field_id INTEGER REFERENCES master_fields(id) ON DELETE CASCADE,
                mapping_type VARCHAR(20) NOT NULL DEFAULT 'ai_suggested'
                    CHECK (mapping_type IN ('ai_suggested', 'manual')),
                status VARCHAR(20) NOT NULL DEFAULT 'suggested'
                    CHECK (status IN ('suggested', 'approved')),
                confidence_score NUMERIC(5,2),
                match_basis VARCHAR(30),
                remarks TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """,
        # Permanent audit trail of rejected suggestions, mirroring BPCS's
        # rejection_log - so a rejected pair is never re-proposed on a later run.
        "master_field_rejection_log": """
            CREATE TABLE IF NOT EXISTS master_field_rejection_log (
                id SERIAL PRIMARY KEY,
                source_field_id INTEGER REFERENCES master_fields(id) ON DELETE CASCADE,
                destination_field_id INTEGER REFERENCES master_fields(id) ON DELETE CASCADE,
                confidence_score NUMERIC(5,2),
                rejected_at TIMESTAMP DEFAULT NOW()
            )
        """,
        # Agent activity log: every AI call (classification, metadata generation,
        # field-mapping batch) AND every human decision (accept/reject/manual
        # correction) - which agent did it, what happened, how long it took. Separate
        # from master_field_mappings (the mapping DATA itself) - this is the AUDIT
        # TRAIL of how that data came to be. source_file_id/destination_file_id are
        # both nullable since a classification/metadata event concerns one file, while
        # a field-mapping event concerns a file PAIR.
        "events": """
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                event_type VARCHAR(50) NOT NULL,
                source_file_id INTEGER REFERENCES master_files(id) ON DELETE CASCADE,
                destination_file_id INTEGER REFERENCES master_files(id) ON DELETE CASCADE,
                agent VARCHAR(100),
                status VARCHAR(20) NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'failed')),
                duration_ms INTEGER,
                detail JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """,
    }

    for name, sql in tables.items():
        try:
            cur.execute(sql)
            conn.commit()
            print(f"  [OK]  {name}")
        except Exception as e:
            conn.rollback()
            print(f"  [ERR] {name}: {e}")

    # Migrations for columns added AFTER master_files/master_type_detection_log first
    # went live - CREATE TABLE IF NOT EXISTS above won't retroactively add a column to
    # an already-existing table, so these run every time and are no-ops once applied.
    migrations = {
        "master_files.side": """
            ALTER TABLE IF EXISTS master_files
                ADD COLUMN IF NOT EXISTS side VARCHAR(20) NOT NULL DEFAULT 'source'
                    CHECK (side IN ('source', 'destination'))
        """,
        "master_type_detection_log.candidates": """
            ALTER TABLE IF EXISTS master_type_detection_log
                ADD COLUMN IF NOT EXISTS candidates JSONB
        """,
        # Populated by metadata_generator.consolidate_metadata() - only for files wide
        # enough to need more than one chunk (see CHUNK_SIZE). NULL/empty for a
        # single-chunk file, which has nothing to reconcile.
        "master_files.business_purpose": """
            ALTER TABLE IF EXISTS master_files ADD COLUMN IF NOT EXISTS business_purpose TEXT
        """,
        "master_files.consolidation_conflicts": """
            ALTER TABLE IF EXISTS master_files ADD COLUMN IF NOT EXISTS consolidation_conflicts JSONB
        """,
        # "Product" was added to MASTER_TYPES after master_files first went live - the
        # CHECK constraints baked into the original CREATE TABLE don't retroactively
        # widen themselves, so drop and recreate both master-type constraints here.
        "master_files.master_type_check_widen": f"""
            ALTER TABLE IF EXISTS master_files
                DROP CONSTRAINT IF EXISTS master_files_detected_master_type_check,
                DROP CONSTRAINT IF EXISTS master_files_confirmed_master_type_check,
                ADD CONSTRAINT master_files_detected_master_type_check
                    CHECK (detected_master_type IN ({master_types_sql})),
                ADD CONSTRAINT master_files_confirmed_master_type_check
                    CHECK (confirmed_master_type IN ({master_types_sql}))
        """,
        # Local sentence-transformers vector (384-dim, plain JSON floats - no pgvector
        # extension needed at this field-count scale), computed at metadata-generation
        # time in masters.py. Used to add a semantic-search candidate ranking alongside
        # the existing BM25 keyword ranking in field_mapping_engine.py (the two are
        # combined via reciprocal_rank_fusion() - see retrieval.py).
        "master_fields.embedding": """
            ALTER TABLE IF EXISTS master_fields ADD COLUMN IF NOT EXISTS embedding JSONB
        """,
        # Short AI-assigned business grouping label (e.g. "Product Master",
        # "Quantity", "Identifier") - only populated for files processed through the
        # row-wise ERP-field-list path (see metadata_generator.detect_field_list_columns).
        "master_fields.business_category": """
            ALTER TABLE IF EXISTS master_fields ADD COLUMN IF NOT EXISTS business_category VARCHAR(100)
        """,
    }
    for name, sql in migrations.items():
        try:
            cur.execute(sql)
            conn.commit()
            print(f"  [OK]  migration: {name}")
        except Exception as e:
            conn.rollback()
            print(f"  [ERR] migration {name}: {e}")

    # Indexes worth having from day one: lookups by file are the dominant access
    # pattern (fetch all fields/rows for one uploaded file), and JSONB GIN indexing
    # lets a future "search raw values" feature use the index instead of a full scan.
    indexes = {
        "idx_master_fields_file": "CREATE INDEX IF NOT EXISTS idx_master_fields_file ON master_fields(master_file_id)",
        "idx_master_rows_file": "CREATE INDEX IF NOT EXISTS idx_master_rows_file ON master_rows(master_file_id)",
        "idx_master_rows_data_gin": "CREATE INDEX IF NOT EXISTS idx_master_rows_data_gin ON master_rows USING GIN (row_data)",
        "idx_mfm_source": "CREATE INDEX IF NOT EXISTS idx_mfm_source ON master_field_mappings(source_field_id)",
        "idx_mfm_dest": "CREATE INDEX IF NOT EXISTS idx_mfm_dest ON master_field_mappings(destination_field_id)",
        "idx_events_source": "CREATE INDEX IF NOT EXISTS idx_events_source ON events(source_file_id)",
        "idx_events_dest": "CREATE INDEX IF NOT EXISTS idx_events_dest ON events(destination_file_id)",
        "idx_events_created_at": "CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at DESC)",
    }
    for name, sql in indexes.items():
        try:
            cur.execute(sql)
            conn.commit()
            print(f"  [OK]  {name}")
        except Exception as e:
            conn.rollback()
            print(f"  [ERR] {name}: {e}")

    cur.close()
    conn.close()

    print("=" * 55)
    print("  Setup complete.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    setup()
