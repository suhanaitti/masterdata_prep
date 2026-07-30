# ERP Master Data Mapping Platform - Backend

AI-driven schema mapping platform for automating ERP field mappings from multiple source systems (D365, Oracle, Legacy) to SAP destination schema.

## 🎯 Key Features

### Retrieval Engine
- **Reduces search space** before LLM processing
- **5-stage matching pipeline:**
  1. Exact field name matching (35%)
  2. Synonym matching - business terminology (25%)
  3. Metadata similarity - AI descriptions (25%)
  4. Data type compatibility (10%)
  5. Field length compatibility (5%)

- Returns **Top 5 candidates** without LLM cost
- Candidates sent to LLM for final decision

### AI Integration
- Uses OpenRouter API for LLM calls
- Only queries LLM with Top 5 candidates (not full schema)
- Receives confidence scores with mappings
- Stores retrieval details for transparency

### Human-in-the-Loop Review
- Users can **Approve**, **Reject**, or **Edit** mappings
- Feedback stored for future improvements
- Maintains audit trail with reviewer info
- Export approved mappings for integration

### PostgreSQL Storage
- Projects and datasets management
- Source and destination field schemas
- AI-generated metadata storage
- Mapping history and status tracking

---

## 📁 File Structure

```
backend/
├── app.py                   # Main FastAPI application
├── models.py               # SQLAlchemy database models
├── database.py             # Database configuration
├── routes.py               # FastAPI endpoints
├── retrieval_engine.py     # Core Retrieval Engine logic
├── ai_service.py           # LLM integration service
├── requirements_new.txt    # Python dependencies
├── API_DOCUMENTATION.md    # Complete API docs
└── README.md              # This file
```

---

## 🚀 Quick Start

### 1. Installation

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -r requirements_new.txt

# OR merge with existing requirements
cat requirements_new.txt >> requirements.txt
pip install -r requirements.txt
```

### 2. Database Setup

Update your `.env` file:
```
DATABASE_URL=postgresql://postgres:password@localhost:5432/erp_masterdata_prep
OPENROUTER_API_KEY=sk-or-v1-xxxxx
```

Initialize database:
```bash
python database.py
```

### 3. Run Server

```bash
python app.py
```

Server will start at `http://localhost:8000`

Access API documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 🔄 How It Works

### Mapping Flow

```
1. USER CREATES PROJECT
   └─ Specify source ERP system (D365, Oracle, Legacy)
   └─ Specify destination system (SAP)

2. USER ADDS FIELDS
   └─ Upload/add source fields from ERP
   └─ Add destination SAP schema fields

3. RETRIEVAL ENGINE PROCESSES SOURCE FIELD
   └─ Run 5-stage matching pipeline
   └─ Return Top 5 candidates (no LLM cost)
   
4. LLM MAKES DECISION
   └─ Query LLM with only Top 5 candidates
   └─ LLM provides selected mapping + confidence score
   
5. MAPPING STORED
   └─ Save suggestion with confidence score
   └─ Store retrieval pipeline results
   
6. HUMAN REVIEWS
   └─ User approves/rejects/edits mapping
   └─ Feedback recorded for future improvements
   
7. EXPORT RESULTS
   └─ Export approved mappings for integration
```

---

## 📊 Retrieval Engine Details

### Matching Pipeline

The engine evaluates each destination field against the source field:

#### 1. Exact Name Match (35% weight)
- Case-insensitive comparison
- Handles naming conventions (snake_case vs camelCase)
- Substring matches get lower scores

#### 2. Synonym Match (25% weight)
- Matches against business terminology stored in DB
- Example: `customer_id` matches synonym `cust_id`
- Priority for exact synonym matches

#### 3. Metadata Similarity (25% weight)
- Compares AI-generated descriptions
- Uses sequence matching for text similarity
- Leverages LLM-generated business context

#### 4. Type Compatibility (10% weight)
- Matches data types (VARCHAR → VARCHAR = 1.0)
- Groups compatible types (INT, DECIMAL, FLOAT = 0.8)
- Penalizes incompatible types

#### 5. Length Compatibility (5% weight)
- Destination length ≥ source length = 1.0
- Smaller destination field = 0.3 to ratio
- Handles NULL values gracefully

### Example Scoring

```
Source: customer_id (VARCHAR, 50)
Destination: KUNNR (CHAR, 10)

Exact Match:        0.7  (partial name match)
Synonym Match:      0.9  (matches "cust_id" synonym)
Metadata Sim:       0.85 (descriptions similar)
Type Compat:        0.6  (CHAR vs VARCHAR)
Length Compat:      0.2  (10 < 50, risky)

Overall Score = 0.7×0.35 + 0.9×0.25 + 0.85×0.25 + 0.6×0.10 + 0.2×0.05
             = 0.2450 + 0.2250 + 0.2125 + 0.0600 + 0.0100
             = 0.7525 (75.25%)
```

---

## 🧠 AI Integration

### OpenRouter API

The platform uses OpenRouter for model flexibility:

```python
# Models supported
"grok-2-1212"              # Recommended
"claude-3.5-sonnet"
"gpt-4"
"mistral-large"
# ... and 50+ more models
```

### LLM Prompt

The LLM receives:
```
Source Field Details:
- Name, Type, Length, Description, Business Meaning

Top 5 Destination Candidates:
1. Field Name, Type, Description, Score
2. Field Name, Type, Description, Score
... up to 5

Decide: Which field is the best match?
Response: Field index (1-5), Confidence (0-1), Reasoning
```

---

## 🗄️ Database Schema

### Core Tables

#### projects
```sql
- id (PK)
- name (unique)
- source_erp_system (D365, Oracle, Legacy, etc)
- destination_system (SAP)
- created_at
```

#### source_fields
```sql
- id (PK)
- dataset_id (FK)
- field_name (indexed)
- field_type
- field_length
- description
- business_meaning
```

#### destination_fields
```sql
- id (PK)
- dataset_id (FK)
- field_name (indexed)
- field_type
- field_length
- description
- synonyms (JSON) ← For synonym matching
```

#### field_mappings
```sql
- id (PK)
- project_id (FK, indexed)
- source_field_id (FK)
- destination_field_id (FK)
- status (pending/suggested/approved/rejected)
- ai_confidence_score
- retrieval_candidates (JSON) ← Top 5 stored here
- reviewed_by
- review_notes
- created_at
- updated_at
```

#### field_metadata
```sql
- source_field_id (FK, unique)
- ai_generated_description ← LLM-generated business context
- keywords (JSON)
- semantic_embedding (JSON) ← Future: vector embeddings
```

---

## 🔌 API Endpoints

### Projects
- `POST /projects` - Create new project
- `GET /projects` - List all projects
- `GET /projects/{id}` - Get project details

### Source Fields
- `POST /projects/{id}/source-fields` - Add source field
- `GET /projects/{id}/source-fields` - List source fields

### Destination Fields
- `POST /projects/{id}/destination-fields` - Add destination field
- `GET /projects/{id}/destination-fields` - List destination fields

### Retrieval Engine
- `GET /projects/{id}/retrieve-candidates/{field_id}` - Get Top 5 (no LLM)

### Mapping
- `POST /projects/{id}/map-field/{field_id}` - Map field (Retrieval + LLM)
- `GET /projects/{id}/mappings` - List all mappings
- `POST /mappings/{id}/approve` - Approve mapping
- `POST /mappings/{id}/reject` - Reject mapping
- `GET /projects/{id}/export-mappings` - Export approved mappings

See `API_DOCUMENTATION.md` for complete details.

---

## ⚙️ Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/erp_masterdata_prep

# API
PORT=8000

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-xxxxx
```

### Database Connection

Supports any PostgreSQL connection string format:
```
postgresql://user:password@host:port/database
```

---

## 🛠️ Development

### File Descriptions

#### models.py
- SQLAlchemy ORM models for all entities
- Relationships and constraints defined
- Indexes on frequently queried columns

#### retrieval_engine.py
- Core `RetrievalEngine` class
- Implements 5-stage matching pipeline
- Scoring algorithms and normalization

#### ai_service.py
- `AIService` class for LLM integration
- Handles OpenRouter API calls
- Response parsing and error handling

#### routes.py
- FastAPI endpoints for all operations
- Request/response validation with Pydantic
- Business logic orchestration

#### database.py
- SQLAlchemy engine and session setup
- Database initialization function
- Session dependency for FastAPI

#### app.py
- FastAPI app creation
- CORS configuration
- Startup events and health checks

---

## 📈 Future Enhancements

### Phase 2
- [ ] Vector embeddings for semantic search
- [ ] Batch field mapping API
- [ ] Learning from approved/rejected mappings
- [ ] Confidence score trends

### Phase 3
- [ ] WebSocket support for real-time updates
- [ ] Advanced analytics dashboard
- [ ] Multi-language support
- [ ] Integration with data quality tools

### Phase 4
- [ ] Support for Oracle, DB2, SQL Server
- [ ] Automated mapping quality scores
- [ ] Feedback loop to improve LLM suggestions
- [ ] Workflow orchestration for large migrations

---

## 🐛 Troubleshooting

### Database Connection Error
```
Error: could not translate host name "localhost" to address
```
**Solution:** Verify PostgreSQL is running and connection string is correct

### LLM API Error
```
Error: LLM API error: 401
```
**Solution:** Check `OPENROUTER_API_KEY` is valid and has credits

### Model Not Found
```
Error: Model "grok-2-1212" not found
```
**Solution:** Check OpenRouter docs for available models, update in `ai_service.py`

---

## 📞 Support

For issues or questions:
1. Check `API_DOCUMENTATION.md` for endpoint details
2. Review error messages in the response
3. Check database logs for SQL errors
4. Verify environment variables are set

---

## 📄 License

Internal project - Use only for authorized ERP migrations.

---

**Built with:** Python 3.13 • FastAPI • SQLAlchemy • PostgreSQL • OpenRouter API
