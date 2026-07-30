# Implementation Guide - Retrieval Engine + AI Mapping

Complete guide to integrate these files into your `masterdata_prep` project.

---

## 📦 What You're Getting

### Core Components

1. **models.py** - Database schema (7 tables)
   - Projects, Datasets, Fields, Metadata, Mappings

2. **retrieval_engine.py** - Core Retrieval Engine (248 lines)
   - 5-stage matching pipeline
   - Scoring algorithm
   - Top 5 candidate selection

3. **ai_service.py** - LLM Integration (252 lines)
   - OpenRouter API integration
   - Mapping decision logic
   - Result storage

4. **routes.py** - FastAPI Endpoints (459 lines)
   - 7 endpoint groups
   - Project management
   - Field management
   - Mapping workflows

5. **database.py** - Database Configuration (51 lines)
   - SQLAlchemy setup
   - Session management
   - Initialization scripts

6. **app.py** - Main Application (87 lines)
   - FastAPI setup
   - CORS configuration
   - Health checks

7. **requirements_new.txt** - Dependencies
   - FastAPI, SQLAlchemy, PostgreSQL, Pandas, etc.

8. **Documentation**
   - `API_DOCUMENTATION.md` - Complete API reference
   - `README.md` - Architecture & features
   - `IMPLEMENTATION_GUIDE.md` - This file

---

## 🔧 Integration Steps

### Step 1: Download Files

In v0, click the three dots (top right) → Download ZIP
- Extract to a temporary folder
- All files will be in `backend/` directory

### Step 2: Merge with Your Project

Your current structure:
```
masterdata_prep/
├── backend/
│   ├── app/
│   ├── _pycache_/
│   ├── venv/
│   ├── .env
│   ├── .env.example
│   ├── create_database.py
│   ├── requirements.txt
│   ├── setup_db.py
│   └── unicorn_err.log
├── frontend/
└── README.md
```

**Add these files to `backend/`:**
```bash
backend/
├── models.py                 # NEW
├── database.py               # NEW (replaces/complements existing)
├── retrieval_engine.py       # NEW
├── ai_service.py             # NEW
├── routes.py                 # NEW
├── app.py                    # NEW (main entry point)
├── API_DOCUMENTATION.md      # NEW
├── README.md                 # NEW
├── requirements_new.txt      # NEW
├── app/                      # EXISTING
├── create_database.py        # EXISTING
├── setup_db.py               # EXISTING
└── requirements.txt          # EXISTING - merge
```

### Step 3: Update Requirements

**Option A: Replace requirements.txt**
```bash
cp requirements_new.txt requirements.txt
pip install -r requirements.txt
```

**Option B: Merge requirements.txt**
```bash
# Backup existing
cp requirements.txt requirements.txt.backup

# Merge (remove duplicates manually)
cat requirements_new.txt >> requirements.txt
pip install -r requirements.txt
```

**Option C: Keep separate (recommended)**
```bash
# Install new requirements separately
pip install -r requirements_new.txt
```

### Step 4: Update .env

Ensure you have:
```bash
# Database (your existing setup)
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=erp_masterdata_prep
DB_USER=postgres
DB_PASSWORD=1234

# Or use DATABASE_URL
DATABASE_URL=postgresql://postgres:1234@127.0.0.1:5432/erp_masterdata_prep

# OpenRouter API Key (for AI mapping)
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Server Port
PORT=8000
```

### Step 5: Initialize Database

```bash
# Run database initialization
python database.py

# Or use existing setup
python setup_db.py
```

You should see:
```
✓ Database initialized
```

### Step 6: Start Server

```bash
# Using the new app.py
python app.py

# OR with uvicorn directly
uvicorn app:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 7: Access API

- **API Documentation:** http://localhost:8000/docs
- **Alternative Docs:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

---

## 🔗 Integration with Existing Code

### Your Current Setup

From the screenshot, you have:
- Python backend with unicorn/FastAPI
- PostgreSQL database
- Environment configuration
- Error logging

### How New Code Fits

**Your `app/` folder** → Existing application code
- Keep as-is or integrate routes into your app

**New `app.py`** → Main application entry point
- Can replace your existing entry point
- Or import from `app/` into new `app.py`

**New `models.py`** → Database models
- Define schema for mapping functionality
- Create tables via `database.py`

**New `routes.py`** → API endpoints
- Include into main app: `app.include_router(router)`

**New `retrieval_engine.py` & `ai_service.py`** → Services
- Import and use from routes
- Can be called from your existing endpoints too

---

## 📊 Quick Architecture Map

```
Your Existing Code          New Code
═══════════════════════════ ═════════════════════════════════════════

app/                        models.py
  - existing endpoints        ├─ Project, SourceField, DestinationField
  - routes                    ├─ FieldMapping, FieldMetadata
  - business logic            └─ Database schema (7 tables)

database/                   database.py
  - connection setup          ├─ SQLAlchemy engine
  - initialization            ├─ Session management
                              └─ init_db() function

app.py (or main)            app.py (NEW)
  - FastAPI app setup         ├─ FastAPI initialization
  - CORS                      ├─ Routes included
                              ├─ Startup events
                              └─ Health checks

                            retrieval_engine.py
                              ├─ 5-stage matching
                              ├─ Candidate ranking
                              └─ Scoring algorithm

                            ai_service.py
                              ├─ OpenRouter integration
                              ├─ LLM calls
                              └─ Mapping storage

                            routes.py
                              ├─ 7 endpoint groups
                              ├─ Request/response handling
                              └─ Business orchestration
```

---

## 🚀 How to Use the New API

### Example 1: Create a Mapping Project

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "D365 to SAP",
    "source_erp_system": "D365"
  }'
```

### Example 2: Add Source Field

```bash
curl -X POST http://localhost:8000/api/projects/1/source-fields \
  -H "Content-Type: application/json" \
  -d '{
    "field_name": "customer_id",
    "field_type": "VARCHAR",
    "field_length": 50,
    "description": "Customer identifier"
  }'
```

### Example 3: Get Candidates (No LLM Cost)

```bash
curl http://localhost:8000/api/projects/1/retrieve-candidates/101?top_k=5
```

Returns Top 5 destination fields ranked by matching score.

### Example 4: Map with AI

```bash
curl -X POST http://localhost:8000/api/projects/1/map-field/101 \
  -H "Content-Type: application/json" \
  -d '{
    "openrouter_api_key": "sk-or-v1-xxxxx"
  }'
```

---

## ✅ Verification Checklist

After integration:

- [ ] All files copied to `backend/`
- [ ] `requirements_new.txt` installed
- [ ] `DATABASE_URL` in `.env` is correct
- [ ] `OPENROUTER_API_KEY` in `.env` is set
- [ ] `python database.py` runs without errors
- [ ] `python app.py` starts successfully
- [ ] http://localhost:8000/docs loads (Swagger UI)
- [ ] `GET /health` returns 200 OK
- [ ] Can create a project via API
- [ ] Can add source/destination fields
- [ ] Can retrieve candidates
- [ ] Can map fields with AI

---

## 🔄 Workflow for End Users

### Phase 1: Setup
1. Create project (specify source ERP + destination)
2. Upload source fields (from D365, Oracle, etc.)
3. Upload destination fields (SAP schema)
4. Add synonyms to destination fields (optional)

### Phase 2: Mapping
1. For each source field:
   - Call `/retrieve-candidates/{field_id}` (see Top 5)
   - Call `/map-field/{field_id}` (get AI suggestion)
   - See retrieval details + confidence score

### Phase 3: Review
1. Browse `/mappings` (view all suggestions)
2. For each mapping:
   - Approve (saves mapping)
   - Reject (marks as rejected)
   - Edit (modify destination field)

### Phase 4: Export
1. Call `/export-mappings`
2. Get JSON with all approved mappings
3. Import into target system

---

## 🐛 Common Issues & Solutions

### Issue: "No module named 'retrieval_engine'"
**Solution:** Make sure `retrieval_engine.py` is in same directory as `app.py`

### Issue: "DATABASE_URL not set"
**Solution:** Add to `.env`:
```
DATABASE_URL=postgresql://postgres:1234@127.0.0.1:5432/erp_masterdata_prep
```

### Issue: "LLM API Error 401"
**Solution:** Verify `OPENROUTER_API_KEY` is valid:
- Check key is not expired
- Ensure API has available credits
- Verify key format: `sk-or-v1-...`

### Issue: "Table does not exist"
**Solution:** Run database initialization:
```bash
python database.py
```

### Issue: "Port 8000 already in use"
**Solution:** Use different port:
```bash
python app.py --port 8001
```

---

## 📞 Next Steps

1. **Download** the files from v0
2. **Copy** to your `backend/` directory
3. **Install** dependencies
4. **Update** `.env` with database URL and API key
5. **Initialize** database
6. **Run** server
7. **Test** API endpoints

---

## 📚 Documentation Reference

- **API Details:** See `API_DOCUMENTATION.md`
- **Architecture:** See `README.md`
- **Database Schema:** See `models.py` comments
- **Retrieval Logic:** See `retrieval_engine.py` docstrings
- **AI Integration:** See `ai_service.py` docstrings

---

## 💡 Tips

1. **Start Small:** Test with 5-10 fields before scaling
2. **Monitor Scores:** Check retrieval scores to understand matching
3. **Add Synonyms:** Better synonyms = better retrieval scores
4. **Review Mappings:** Human review catches AI errors early
5. **Export Regularly:** Keep track of approved mappings

---

## 🎯 What You Now Have

✅ **Retrieval Engine** - Narrows candidates before LLM
✅ **AI Integration** - Uses OpenRouter for mapping decisions
✅ **Human Review** - Approve/reject/edit mappings
✅ **Database** - Full schema with proper relationships
✅ **API** - 15+ endpoints for complete workflow
✅ **Documentation** - Complete guides and examples

**Ready to map ERP fields at scale!** 🚀
