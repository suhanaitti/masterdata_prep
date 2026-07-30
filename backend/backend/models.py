"""
Database models for Master Data Mapping Platform
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Integer, DateTime, Float, Text, ForeignKey, Enum, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    description = Column(Text, nullable=True)
    source_erp_system = Column(String(100))  # D365, Oracle, Legacy, etc.
    destination_system = Column(String(100))  # SAP
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source_datasets = relationship("SourceDataset", back_populates="project")
    destination_dataset = relationship("DestinationDataset", back_populates="project", uselist=False)
    mappings = relationship("FieldMapping", back_populates="project")

    __table_args__ = (Index("idx_project_name", "name"),)


class SourceDataset(Base):
    __tablename__ = "source_datasets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    name = Column(String(255))
    source_system = Column(String(100))  # D365, Oracle, Legacy
    total_fields = Column(Integer, default=0)
    mapped_fields = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="source_datasets")
    source_fields = relationship("SourceField", back_populates="dataset")


class DestinationDataset(Base):
    __tablename__ = "destination_datasets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), unique=True, index=True)
    name = Column(String(255))  # SAP schema name
    total_fields = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="destination_dataset")
    destination_fields = relationship("DestinationField", back_populates="dataset")


class SourceField(Base):
    __tablename__ = "source_fields"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("source_datasets.id"), index=True)
    field_name = Column(String(255), index=True)
    field_type = Column(String(50))  # VARCHAR, INT, DECIMAL, etc.
    field_length = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    business_meaning = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("SourceDataset", back_populates="source_fields")
    metadata = relationship("FieldMetadata", back_populates="source_field", uselist=False)
    mappings = relationship("FieldMapping", back_populates="source_field")

    __table_args__ = (Index("idx_source_field_name", "field_name"),)


class DestinationField(Base):
    __tablename__ = "destination_fields"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("destination_datasets.id"), index=True)
    field_name = Column(String(255), index=True)
    field_type = Column(String(50))
    field_length = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    business_meaning = Column(Text, nullable=True)
    synonyms = Column(JSON, default=[])  # Business terminology synonyms
    created_at = Column(DateTime, default=datetime.utcnow)

    dataset = relationship("DestinationDataset", back_populates="destination_fields")
    mappings = relationship("FieldMapping", back_populates="destination_field")

    __table_args__ = (Index("idx_dest_field_name", "field_name"),)


class FieldMetadata(Base):
    __tablename__ = "field_metadata"

    id = Column(Integer, primary_key=True, index=True)
    source_field_id = Column(Integer, ForeignKey("source_fields.id"), unique=True, index=True)
    ai_generated_description = Column(Text)  # LLM-generated business description
    keywords = Column(JSON, default=[])  # Extracted keywords for retrieval
    semantic_embedding = Column(JSON, nullable=True)  # Future: vector embeddings
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source_field = relationship("SourceField", back_populates="metadata")


class MappingStatus(str, enum.Enum):
    PENDING = "pending"
    SUGGESTED = "suggested"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"


class FieldMapping(Base):
    __tablename__ = "field_mappings"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), index=True)
    source_field_id = Column(Integer, ForeignKey("source_fields.id"), index=True)
    destination_field_id = Column(Integer, ForeignKey("destination_fields.id"), index=True)
    
    status = Column(Enum(MappingStatus), default=MappingStatus.PENDING, index=True)
    
    # AI suggestion details
    ai_suggested_destination_id = Column(Integer, ForeignKey("destination_fields.id"), nullable=True)
    ai_confidence_score = Column(Float, nullable=True)  # 0-1 score
    
    # Retrieval engine results
    retrieval_candidates = Column(JSON, nullable=True)  # Top 5 candidates with scores
    
    # Human review
    reviewed_by = Column(String(255), nullable=True)
    review_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="mappings")
    source_field = relationship("SourceField", back_populates="mappings")
    destination_field = relationship("DestinationField", back_populates="mappings")

    __table_args__ = (
        Index("idx_mapping_project_status", "project_id", "status"),
        Index("idx_mapping_source_dest", "source_field_id", "destination_field_id"),
    )
