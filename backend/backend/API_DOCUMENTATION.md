# ERP Master Data Mapping Platform - API Documentation

## Overview

This API implements an AI-driven ERP Master Data Mapping Platform with a **Retrieval Engine** that reduces search space before LLM processing.

### Architecture

```
Source Field → Retrieval Engine → Top 5 Candidates → LLM Decision → Mapping Stored
```

## Base URL

```
http://localhost:8000/api
```

## Authentication

Currently uses OpenRouter API key passed in request headers or body.

---

## Endpoints

### 1. Projects Management

#### Create Project
```
POST /projects
```

**Request:**
```json
{
  "name": "D365 to SAP Migration",
  "description": "Mapping D365 fields to SAP schema",
  "source_erp_system": "D365",
  "destination_system": "SAP"
}
```

**Response:**
```json
{
  "id": 1,
  "name": "D365 to SAP Migration",
  "description": "Mapping D365 fields to SAP schema",
  "source_erp_system": "D365",
  "destination_system": "SAP",
  "created_at": "2026-07-30T10:00:00"
}
```

#### List Projects
```
GET /projects
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "D365 to SAP Migration",
    "description": "...",
    "source_erp_system": "D365",
    "destination_system": "SAP",
    "created_at": "2026-07-30T10:00:00"
  }
]
```

#### Get Project Details
```
GET /projects/{project_id}
```

---

### 2. Source Fields Management

#### Add Source Field
```
POST /projects/{project_id}/source-fields
```

**Request:**
```json
{
  "field_name": "customer_id",
  "field_type": "VARCHAR",
  "field_length": 50,
  "description": "Unique customer identifier",
  "business_meaning": "The primary key for customer records in D365"
}
```

**Response:**
```json
{
  "id": 101,
  "field_name": "customer_id",
  "field_type": "VARCHAR",
  "field_length": 50,
  "description": "Unique customer identifier",
  "business_meaning": "The primary key for customer records in D365"
}
```

#### List Source Fields
```
GET /projects/{project_id}/source-fields
```

**Response:**
```json
[
  {
    "id": 101,
    "field_name": "customer_id",
    "field_type": "VARCHAR",
    "field_length": 50,
    "description": "...",
    "business_meaning": "..."
  },
  {
    "id": 102,
    "field_name": "customer_name",
    "field_type": "VARCHAR",
    "field_length": 255,
    "description": "Full customer name",
    "business_meaning": "..."
  }
]
```

---

### 3. Destination Fields Management

#### Add Destination Field
```
POST /projects/{project_id}/destination-fields
```

**Request:**
```json
{
  "field_name": "KUNNR",
  "field_type": "CHAR",
  "field_length": 10,
  "description": "Customer Number",
  "synonyms": ["customer_number", "cust_id", "customer_account"]
}
```

**Response:**
```json
{
  "id": 201,
  "field_name": "KUNNR",
  "field_type": "CHAR",
  "field_length": 10,
  "description": "Customer Number",
  "synonyms": ["customer_number", "cust_id", "customer_account"]
}
```

#### List Destination Fields
```
GET /projects/{project_id}/destination-fields
```

---

### 4. Retrieval Engine

#### Retrieve Top 5 Candidates
```
GET /projects/{project_id}/retrieve-candidates/{source_field_id}?top_k=5
```

**Description:** Uses the Retrieval Engine to get top K candidate destination fields without calling LLM.

**Response:**
```json
{
  "source_field_id": 101,
  "source_field_name": "customer_id",
  "candidates": [
    {
      "id": 201,
      "name": "KUNNR",
      "type": "CHAR",
      "description": "Customer Number",
      "overall_score": 0.8542,
      "exact_match_score": 0.7,
      "synonym_match_score": 0.9,
      "metadata_similarity_score": 0.85,
      "type_compatibility_score": 0.6
    },
    {
      "id": 202,
      "name": "CUST_ID",
      "type": "VARCHAR",
      "description": "Customer Identifier",
      "overall_score": 0.7823,
      ...
    },
    ...
  ]
}
```

**Retrieval Pipeline:**
1. **Exact field name matching** (35% weight)
2. **Synonym matching** (25% weight)
3. **Metadata similarity** (25% weight)
4. **Data type compatibility** (10% weight)
5. **Field length compatibility** (5% weight)

---

### 5. AI Mapping

#### Map Source Field (Retrieval + LLM)
```
POST /projects/{project_id}/map-field/{source_field_id}
```

**Request:**
```json
{
  "openrouter_api_key": "sk-or-v1-xxxxx"
}
```

**Process:**
1. Retrieval Engine retrieves Top 5 candidates
2. Candidates sent to LLM
3. LLM makes final decision
4. Mapping stored in database

**Response:**
```json
{
  "success": true,
  "mapping_id": 1001,
  "source_field_id": 101,
  "destination_field_id": 201,
  "confidence_score": 0.92,
  "retrieval_candidates": [
    {
      "id": 201,
      "name": "KUNNR",
      "score": 0.8542,
      "description": "Customer Number"
    },
    ...
  ]
}
```

---

### 6. Human Review

#### List Mappings
```
GET /projects/{project_id}/mappings?status=suggested
```

**Query Parameters:**
- `status` (optional): `pending`, `suggested`, `approved`, `rejected`, `edited`

**Response:**
```json
[
  {
    "id": 1001,
    "source_field_id": 101,
    "destination_field_id": 201,
    "status": "suggested",
    "ai_confidence_score": 0.92,
    "retrieval_candidates": [...],
    "review_notes": null,
    "created_at": "2026-07-30T10:15:00"
  }
]
```

#### Approve Mapping
```
POST /mappings/{mapping_id}/approve
```

**Request:**
```json
{
  "destination_field_id": 201,
  "review_notes": "Verified - correct mapping"
}
```

**Query Parameters:**
- `reviewed_by` (required): User name/ID performing review

**Response:**
```json
{
  "id": 1001,
  "status": "approved",
  "destination_field_id": 201,
  "review_notes": "Verified - correct mapping",
  "updated_at": "2026-07-30T10:20:00"
}
```

#### Reject Mapping
```
POST /mappings/{mapping_id}/reject
```

**Query Parameters:**
- `review_notes` (required): Reason for rejection
- `reviewed_by` (required): User name/ID

**Response:**
```json
{
  "id": 1001,
  "status": "rejected",
  "review_notes": "Wrong mapping - customer_id should map to CUST_ID",
  "updated_at": "2026-07-30T10:20:00"
}
```

---

### 7. Export

#### Export Approved Mappings
```
GET /projects/{project_id}/export-mappings
```

**Description:** Export all approved mappings for integration with target system

**Response:**
```json
{
  "project_id": 1,
  "total_approved": 45,
  "mappings": [
    {
      "source_field_name": "customer_id",
      "source_field_type": "VARCHAR",
      "destination_field_name": "KUNNR",
      "destination_field_type": "CHAR",
      "confidence_score": 0.92,
      "reviewed_by": "john_doe",
      "review_date": "2026-07-30T10:20:00"
    },
    ...
  ]
}
```

---

## Database Schema

### Tables

1. **projects** - Mapping projects
2. **source_datasets** - Source ERP datasets (D365, Oracle, Legacy)
3. **destination_datasets** - Target SAP schema
4. **source_fields** - Source ERP fields
5. **destination_fields** - SAP destination fields
6. **field_metadata** - AI-generated metadata for source fields
7. **field_mappings** - Mapping records with status and review info

---

## Error Handling

All endpoints return errors in this format:

```json
{
  "detail": "Error message"
}
```

**Common Status Codes:**
- `200` - Success
- `400` - Bad request
- `404` - Resource not found
- `500` - Server error

---

## Usage Example

```python
import requests

BASE_URL = "http://localhost:8000/api"
API_KEY = "sk-or-v1-xxxxx"

# 1. Create project
project = requests.post(f"{BASE_URL}/projects", json={
    "name": "D365 to SAP",
    "source_erp_system": "D365"
}).json()

project_id = project["id"]

# 2. Add source field
source_field = requests.post(
    f"{BASE_URL}/projects/{project_id}/source-fields",
    json={
        "field_name": "customer_id",
        "field_type": "VARCHAR",
        "field_length": 50
    }
).json()

# 3. Add destination fields
requests.post(
    f"{BASE_URL}/projects/{project_id}/destination-fields",
    json={
        "field_name": "KUNNR",
        "field_type": "CHAR",
        "field_length": 10,
        "synonyms": ["customer_number", "cust_id"]
    }
)

# 4. Retrieve candidates (no LLM call)
candidates = requests.get(
    f"{BASE_URL}/projects/{project_id}/retrieve-candidates/{source_field['id']}"
).json()

# 5. Map with LLM
mapping = requests.post(
    f"{BASE_URL}/projects/{project_id}/map-field/{source_field['id']}",
    json={"openrouter_api_key": API_KEY}
).json()

# 6. Review and approve
requests.post(
    f"{BASE_URL}/mappings/{mapping['mapping_id']}/approve",
    json={
        "destination_field_id": mapping["destination_field_id"],
        "review_notes": "Verified"
    },
    params={"reviewed_by": "admin"}
)

# 7. Export
export = requests.get(
    f"{BASE_URL}/projects/{project_id}/export-mappings"
).json()
```

---

## Next Steps

1. Set up PostgreSQL database
2. Install requirements: `pip install -r requirements_new.txt`
3. Run migrations: `python database.py`
4. Start server: `python app.py`
5. Access API docs: `http://localhost:8000/docs`

---

## Future Enhancements

- Vector embeddings for semantic search
- Learning from approved/rejected mappings
- Batch processing for large datasets
- WebSocket support for real-time updates
- Advanced metrics and analytics dashboard
