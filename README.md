# ERP Master Data Prep

AI-driven master data preparation for ERP schema mapping. Users upload Excel/CSV
files for one of six master types (Customer, Vendor, Bank, GL Mapping, Transaction
Type, Payment Terms); the AI identifies which master a file belongs to, generates
per-column metadata (description, data type, length, mandatory/key flags), and stores
both the raw data and the AI-generated metadata in Postgres for the schema-mapping
engine to consume next.

Stack: **FastAPI** (backend) + **PostgreSQL** (database) + **Next.js** (frontend).
No FAISS/vector search in this first version, per project decision.

This lives inside `Header_Mapping/masterdata_prep/` as one project - a
separate FastAPI+Next.js codebase and its own Postgres database (`erp_masterdata_prep`),
distinct from the Streamlit app one level up, but part of the same overall repo/initiative.

## Backend setup

```
cd masterdata_prep/backend
pip install -r requirements.txt
cp .env.example .env        # then fill in DB_PASSWORD and (optionally) AI provider keys
python create_database.py   # one-time: creates the erp_masterdata_prep database
python setup_db.py          # one-time: creates all tables
uvicorn app.main:app --reload --port 8000
```

Already done once during initial setup: the database and tables exist and the
`/api/masters` endpoints have been verified working end-to-end against the real
database (empty-list response confirmed). AI provider keys are NOT yet filled in -
the classify/metadata-generation endpoints need at least one of `OPENROUTER_API_KEY_1`
or `GROQ_API_KEY_1` set in `backend/.env` before an actual file upload will work.

API docs once running: http://localhost:8000/docs

## Frontend setup

**Node.js is not installed on this machine** - the frontend code is complete but
UNTESTED (no `npm install`/`npm run dev` has been run). Install Node.js 18+ first,
then:

```
cd masterdata_prep/frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Runs at http://localhost:3000. Pages:
- `/` - upload a file, see the AI's master-type classification + confidence, confirm
  manually if the AI wasn't confident, then see the generated field metadata table
  with color-coded confidence pills (green ≥90%, yellow ≥75%, red <75%).
- `/masters` - every uploaded file and its status.
- `/masters/[id]` - one file's full field metadata.

## Architecture

```
Upload Excel/CSV
      │
      ▼
excel_reader.py    - reads the file, builds a SMALL schema summary
                      (column names + a few sample values) - never sends the
                      whole file to the LLM
      │
      ▼
master_classifier.py - AI identifies which of the 6 master types this is,
                        with a confidence score + reasoning
      │
      ├── confidence >= 75% ──────────────► auto-confirmed
      │
      └── confidence < 75% ──► user confirms/corrects via the UI
      │
      ▼
metadata_generator.py - AI generates per-column description, data type,
                         estimated length, mandatory/key flags
      │
      ▼
Postgres (master_files / master_fields / master_rows /
          master_type_detection_log)
      │
      ▼
(next stage: schema mapping engine)
```

## Known gaps / next steps

- Frontend is unverified - install Node.js and run it to confirm.
- No auth - fine for local/dev use, not for anything exposed beyond localhost.
- No pagination on `master_rows` yet if a file has many thousands of rows.
- Vector search intentionally deferred (FAISS/pgvector) - add if/when the schema
  mapping engine needs to search across master-data fields semantically.
