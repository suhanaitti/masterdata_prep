from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SheetListOut(BaseModel):
    sheet_names: list[str]


class FieldMetadataOut(BaseModel):
    column_name: str
    ai_description: Optional[str] = None
    business_category: Optional[str] = None
    data_type: Optional[str] = None
    estimated_length: Optional[int] = None
    is_mandatory: bool = False
    is_primary_key: bool = False
    is_business_identifier: bool = False
    confidence_score: Optional[float] = None
    ai_remarks: Optional[str] = None


class MasterTypeCandidateOut(BaseModel):
    master_type: str
    confidence: float


class ConsolidationConflictOut(BaseModel):
    column_name: str
    issue: str
    resolution: str


class MasterFileOut(BaseModel):
    id: int
    filename: str
    sheet_name: Optional[str] = None
    side: str
    detected_master_type: Optional[str] = None
    detection_confidence: Optional[float] = None
    confirmed_master_type: Optional[str] = None
    status: str
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    business_purpose: Optional[str] = None
    consolidation_conflicts: list[ConsolidationConflictOut] = []
    uploaded_at: datetime
    confirmed_at: Optional[datetime] = None


class UploadResultOut(BaseModel):
    master_file: MasterFileOut
    needs_confirmation: bool
    reasoning: Optional[str] = None
    candidates: list[MasterTypeCandidateOut] = []
    possible_master_types: list[str]
    fields: list[FieldMetadataOut] = []


class ConfirmMasterTypeIn(BaseModel):
    confirmed_master_type: str


class MasterFileDetailOut(BaseModel):
    master_file: MasterFileOut
    fields: list[FieldMetadataOut]
