"""
FastAPI routes for Master Data Mapping Platform
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from models import (
    Project, SourceDataset, DestinationDataset, SourceField, DestinationField,
    FieldMapping, MappingStatus, FieldMetadata
)
from database import get_db
from ai_service import AIService
from retrieval_engine import RetrievalEngine

router = APIRouter(prefix="/api", tags=["mapping"])


# ============= Pydantic Schemas =============

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    source_erp_system: str
    destination_system: str = "SAP"

    class Config:
        from_attributes = True


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    source_erp_system: str
    destination_system: str
    created_at: datetime

    class Config:
        from_attributes = True


class SourceFieldCreate(BaseModel):
    field_name: str
    field_type: str
    field_length: Optional[int] = None
    description: Optional[str] = None
    business_meaning: Optional[str] = None


class SourceFieldResponse(BaseModel):
    id: int
    field_name: str
    field_type: str
    field_length: Optional[int]
    description: Optional[str]
    business_meaning: Optional[str]

    class Config:
        from_attributes = True


class DestinationFieldCreate(BaseModel):
    field_name: str
    field_type: str
    field_length: Optional[int] = None
    description: Optional[str] = None
    synonyms: Optional[List[str]] = None


class DestinationFieldResponse(BaseModel):
    id: int
    field_name: str
    field_type: str
    field_length: Optional[int]
    description: Optional[str]
    synonyms: Optional[List[str]]

    class Config:
        from_attributes = True


class MappingResponse(BaseModel):
    id: int
    source_field_id: int
    destination_field_id: Optional[int]
    status: str
    ai_confidence_score: Optional[float]
    retrieval_candidates: Optional[Dict[str, Any]]
    review_notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class MappingApprovalRequest(BaseModel):
    destination_field_id: int
    review_notes: Optional[str] = None


# ============= Project Endpoints =============

@router.post("/projects", response_model=ProjectResponse)
def create_project(project: ProjectCreate, db: Session = Depends(get_db)):
    """Create a new mapping project"""
    existing = db.query(Project).filter(Project.name == project.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project name already exists"
        )
    
    db_project = Project(**project.dict())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project


@router.get("/projects", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    """List all projects"""
    projects = db.query(Project).all()
    return projects


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    """Get project details"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ============= Source Fields Endpoints =============

@router.post("/projects/{project_id}/source-fields", response_model=SourceFieldResponse)
def add_source_field(
    project_id: int,
    field: SourceFieldCreate,
    db: Session = Depends(get_db)
):
    """Add a source field to a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get or create source dataset
    source_dataset = db.query(SourceDataset).filter(
        SourceDataset.project_id == project_id
    ).first()
    
    if not source_dataset:
        source_dataset = SourceDataset(
            project_id=project_id,
            name=f"{project.source_erp_system} Source",
            source_system=project.source_erp_system
        )
        db.add(source_dataset)
        db.commit()
        db.refresh(source_dataset)
    
    db_field = SourceField(dataset_id=source_dataset.id, **field.dict())
    db.add(db_field)
    
    # Update total fields count
    source_dataset.total_fields += 1
    
    db.commit()
    db.refresh(db_field)
    return db_field


@router.get("/projects/{project_id}/source-fields", response_model=List[SourceFieldResponse])
def list_source_fields(project_id: int, db: Session = Depends(get_db)):
    """List all source fields for a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    source_dataset = db.query(SourceDataset).filter(
        SourceDataset.project_id == project_id
    ).first()
    
    if not source_dataset:
        return []
    
    fields = db.query(SourceField).filter(
        SourceField.dataset_id == source_dataset.id
    ).all()
    return fields


# ============= Destination Fields Endpoints =============

@router.post("/projects/{project_id}/destination-fields", response_model=DestinationFieldResponse)
def add_destination_field(
    project_id: int,
    field: DestinationFieldCreate,
    db: Session = Depends(get_db)
):
    """Add a destination field to a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get or create destination dataset
    dest_dataset = db.query(DestinationDataset).filter(
        DestinationDataset.project_id == project_id
    ).first()
    
    if not dest_dataset:
        dest_dataset = DestinationDataset(
            project_id=project_id,
            name=f"{project.destination_system} Schema"
        )
        db.add(dest_dataset)
        db.commit()
        db.refresh(dest_dataset)
    
    db_field = DestinationField(
        dataset_id=dest_dataset.id,
        **field.dict()
    )
    db.add(db_field)
    
    # Update total fields count
    dest_dataset.total_fields += 1
    
    db.commit()
    db.refresh(db_field)
    return db_field


@router.get("/projects/{project_id}/destination-fields", response_model=List[DestinationFieldResponse])
def list_destination_fields(project_id: int, db: Session = Depends(get_db)):
    """List all destination fields for a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    dest_dataset = db.query(DestinationDataset).filter(
        DestinationDataset.project_id == project_id
    ).first()
    
    if not dest_dataset:
        return []
    
    fields = db.query(DestinationField).filter(
        DestinationField.dataset_id == dest_dataset.id
    ).all()
    return fields


# ============= Retrieval Engine Endpoints =============

@router.get("/projects/{project_id}/retrieve-candidates/{source_field_id}")
def retrieve_candidates(
    project_id: int,
    source_field_id: int,
    top_k: int = 5,
    db: Session = Depends(get_db)
):
    """Get top K candidate destination fields for a source field"""
    
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get source field
    source_field = db.query(SourceField).filter(SourceField.id == source_field_id).first()
    if not source_field:
        raise HTTPException(status_code=404, detail="Source field not found")
    
    # Get destination dataset
    dest_dataset = db.query(DestinationDataset).filter(
        DestinationDataset.project_id == project_id
    ).first()
    
    if not dest_dataset:
        raise HTTPException(status_code=404, detail="No destination dataset found")
    
    # Run retrieval engine
    retrieval_engine = RetrievalEngine(db)
    candidates = retrieval_engine.retrieve_candidates(
        source_field,
        dest_dataset.id,
        top_k=top_k
    )
    
    return {
        "source_field_id": source_field_id,
        "source_field_name": source_field.field_name,
        "candidates": [
            {
                "id": c.destination_field_id,
                "name": c.field_name,
                "type": c.field_type,
                "description": c.description,
                "overall_score": round(c.overall_score, 4),
                "exact_match_score": round(c.exact_match_score, 4),
                "synonym_match_score": round(c.synonym_match_score, 4),
                "metadata_similarity_score": round(c.metadata_similarity_score, 4),
                "type_compatibility_score": round(c.type_compatibility_score, 4)
            }
            for c in candidates
        ]
    }


# ============= AI Mapping Endpoints =============

@router.post("/projects/{project_id}/map-field/{source_field_id}")
def map_source_field(
    project_id: int,
    source_field_id: int,
    openrouter_api_key: str,
    db: Session = Depends(get_db)
):
    """
    Map a source field using Retrieval Engine + LLM.
    
    Steps:
    1. Retrieval Engine gets Top 5 candidates
    2. LLM makes final decision from Top 5
    3. Mapping stored in database
    """
    
    # Verify project and source field
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    source_field = db.query(SourceField).filter(SourceField.id == source_field_id).first()
    if not source_field:
        raise HTTPException(status_code=404, detail="Source field not found")
    
    # Get destination dataset
    dest_dataset = db.query(DestinationDataset).filter(
        DestinationDataset.project_id == project_id
    ).first()
    
    if not dest_dataset:
        raise HTTPException(status_code=400, detail="No destination dataset found")
    
    # Call AI service
    ai_service = AIService(openrouter_api_key)
    result = ai_service.map_source_field(
        db,
        source_field,
        dest_dataset.id,
        project_id
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result


# ============= Mapping Review Endpoints =============

@router.get("/projects/{project_id}/mappings", response_model=List[MappingResponse])
def list_mappings(
    project_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all mappings for a project"""
    query = db.query(FieldMapping).filter(FieldMapping.project_id == project_id)
    
    if status:
        query = query.filter(FieldMapping.status == status)
    
    mappings = query.all()
    return mappings


@router.post("/mappings/{mapping_id}/approve", response_model=MappingResponse)
def approve_mapping(
    mapping_id: int,
    request: MappingApprovalRequest,
    reviewed_by: str,
    db: Session = Depends(get_db)
):
    """Approve a suggested mapping"""
    mapping = db.query(FieldMapping).filter(FieldMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    mapping.destination_field_id = request.destination_field_id
    mapping.status = MappingStatus.APPROVED
    mapping.review_notes = request.review_notes
    mapping.reviewed_by = reviewed_by
    
    db.commit()
    db.refresh(mapping)
    return mapping


@router.post("/mappings/{mapping_id}/reject", response_model=MappingResponse)
def reject_mapping(
    mapping_id: int,
    review_notes: str,
    reviewed_by: str,
    db: Session = Depends(get_db)
):
    """Reject a suggested mapping"""
    mapping = db.query(FieldMapping).filter(FieldMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    
    mapping.status = MappingStatus.REJECTED
    mapping.review_notes = review_notes
    mapping.reviewed_by = reviewed_by
    
    db.commit()
    db.refresh(mapping)
    return mapping


@router.get("/projects/{project_id}/export-mappings")
def export_approved_mappings(
    project_id: int,
    db: Session = Depends(get_db)
):
    """Export all approved mappings for a project"""
    mappings = db.query(FieldMapping).filter(
        FieldMapping.project_id == project_id,
        FieldMapping.status == MappingStatus.APPROVED
    ).all()
    
    export_data = []
    for mapping in mappings:
        source = db.query(SourceField).filter(SourceField.id == mapping.source_field_id).first()
        destination = db.query(DestinationField).filter(DestinationField.id == mapping.destination_field_id).first()
        
        export_data.append({
            "source_field_name": source.field_name,
            "source_field_type": source.field_type,
            "destination_field_name": destination.field_name,
            "destination_field_type": destination.field_type,
            "confidence_score": mapping.ai_confidence_score,
            "reviewed_by": mapping.reviewed_by,
            "review_date": mapping.updated_at
        })
    
    return {
        "project_id": project_id,
        "total_approved": len(export_data),
        "mappings": export_data
    }
